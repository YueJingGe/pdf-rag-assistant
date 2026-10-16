"""Chat conversation business logic (SSE event assembly stays in the route layer, D3)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_kb_or_raise
from app.core.config import settings
from app.core.llm_gateway import get_llm
from app.core.rag_chain import (
    RAG_PROMPT,
    _build_citations,
    _deduplicate_documents,
    _format_context,
    _to_langchain_messages,
    _trim_chat_history,
    rag_query,
    retrieve_with_strategy,
)
from app.utils.logging import get_langfuse_handler, logger
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.services.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceError,
    ValidationError,
)


async def get_own_conversation(
    db: AsyncSession, conversation_id: int, user: User
) -> Conversation:
    """加载会话并校验归属；不存在或非本人会话一律 NotFoundError（404，防止会话 ID 枚举探测）。"""
    conversation = await db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise NotFoundError("Conversation not found")
    return conversation


async def prepare_chat(
    db: AsyncSession,
    knowledge_base_id: int | None,
    question: str,
    conversation_id: int | None,
    user: User,
) -> tuple[Conversation, list[dict]]:
    """RAG 模式读权限校验 + 会话获取/创建 + 最近 10 条历史加载（供 SSE 路由使用）。"""
    if knowledge_base_id:
        # RAG 模式校验知识库读权限；普通聊天无知识库归属，仅需登录
        await get_kb_or_raise(knowledge_base_id, user, "viewer", db)

    if conversation_id:
        # 校验会话归属：只能在自己名下的会话里继续对话
        conversation = await get_own_conversation(db, conversation_id, user)
    else:
        conversation = Conversation(
            knowledge_base_id=knowledge_base_id or 0,
            title=question[:50],
            user_id=user.id,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    history_msgs = list(reversed(result.scalars().all()))
    chat_history = [{"role": m.role, "content": m.content} for m in history_msgs]
    return conversation, chat_history


async def save_user_message(
    db: AsyncSession,
    conversation_id: int,
    question: str,
    images: list[str] | None,
    file_name: str | None,
) -> Message:
    """持久化用户消息（SSE 流开始前调用）。"""
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=question,
        images=images,
        file_name=file_name,
    )
    db.add(user_msg)
    await db.commit()
    return user_msg


async def save_assistant_message(
    db: AsyncSession, conversation_id: int, content: str, citations: list
) -> Message:
    """持久化助手消息（SSE 流结束后调用）。"""
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        citations=citations,
    )
    db.add(assistant_msg)
    await db.commit()
    return assistant_msg


async def list_conversations(
    db: AsyncSession, kb_id: int, user: User
) -> list[Conversation]:
    """只返回当前用户自己的会话（会话归属隔离）；kb_id=0（普通聊天）无知识库校验。"""
    if kb_id:
        # RAG 模式校验读权限
        await get_kb_or_raise(kb_id, user, "viewer", db)
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.knowledge_base_id == kb_id,
            Conversation.user_id == user.id,
        )
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


async def get_messages(
    db: AsyncSession, conversation_id: int, user: User
) -> list[dict]:
    """读取本人会话的消息历史（按时间正序）。"""
    await get_own_conversation(db, conversation_id, user)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "images": m.images,
            "file_name": m.file_name,
            "citations": m.citations,
            "created_at": m.created_at.isoformat(),
        }
        for m in result.scalars().all()
    ]


async def get_own_message(
    db: AsyncSession, message_id: int, user: User
) -> tuple[Message, Conversation]:
    """加载消息及其会话并校验归属；不存在或非本人会话一律 NotFoundError（404 防枚举）。

    P0-4「存为文档」前置校验：返回 (message, conversation)，会话标题用于生成文档名。
    """
    result = await db.execute(
        select(Message, Conversation)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.id == message_id, Conversation.user_id == user.id)
    )
    row = result.first()
    if not row:
        raise NotFoundError("Message not found")
    return row[0], row[1]


async def delete_conversation(
    db: AsyncSession, conversation_id: int, user: User
) -> None:
    """删除本人会话及其全部消息。"""
    conversation = await get_own_conversation(db, conversation_id, user)
    await db.execute(sa_delete(Message).where(Message.conversation_id == conversation_id))
    await db.delete(conversation)
    await db.commit()


async def query_rag(
    db: AsyncSession,
    knowledge_base_id: int | None,
    question: str,
    conversation_id: int | None,
    use_hyde: bool,
    user: User,
) -> dict:
    """非流式 RAG 查询（A/B 测试）。

    领域异常直接透传（保持 404/403 语义），其余异常包装为 ServiceError（500）。
    """
    if knowledge_base_id:
        # RAG 模式校验知识库读权限
        await get_kb_or_raise(knowledge_base_id, user, "viewer", db)

    chat_history: list[dict] = []
    if conversation_id:
        # 归属校验：只能引用本人会话的历史（不存在/他人会话一律 404 防枚举）
        # —— P0-1 遗留安全修复，经用户确认为本轮例外（区别于纯重构）
        await get_own_conversation(db, conversation_id, user)
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10)  # 每次请求从数据库加载最近 10 条消息
        )
        history_msgs = list(reversed(result.scalars().all()))
        chat_history = [{"role": m.role, "content": m.content} for m in history_msgs]

    try:
        return await rag_query(
            knowledge_base_id, question, chat_history, use_hyde=use_hyde
        )
    except (NotFoundError, PermissionDeniedError, ValidationError, ConflictError):
        raise  # 领域异常直接透传，保持 404/403 语义
    except Exception as exc:
        raise ServiceError(f"RAG query failed: {exc}")


# ======================== P0-4 第二轮：多库合并链（方案甲，需求 §8.3） ========================

async def check_multi_kb_access(db: AsyncSession, kb_ids: list[int], user: User) -> None:
    """多库信息源：SSE 流开始前逐库读权限校验（越权 403，不进事件流）。"""
    for kb_id in kb_ids:
        await get_kb_or_raise(kb_id, user, "viewer", db)


async def multi_kb_retrieve(kb_ids: list[int], question: str) -> list:
    """逐库检索 → metadata 标记来源库 → RRF 分数降序合并 → 去重 → 截断 top_k。

    禁区文件只读引用：retrieve_with_strategy / _deduplicate_documents 原样调用，
    单库检索逻辑零复制零修改（方案甲核心约束，需求 §8.3）。
    RRF 分数只依赖库内名次（同 rank 同分），跨库天然可比，无需归一化。
    """
    flat: list = []
    for kb_id in kb_ids:
        docs = await retrieve_with_strategy(kb_id, question, use_hyde=False)
        for doc in docs:
            doc.metadata["knowledge_base_id"] = kb_id  # 来源库标记（引用/调试归因用）
            flat.append(doc)
    merged = sorted(flat, key=lambda d: d.metadata.get("score", 0.0), reverse=True)
    return _deduplicate_documents(merged)[: settings.retrieval_top_k]


async def multi_kb_rag_stream(
    kb_ids: list[int],
    question: str,
    chat_history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """多库信息源流式问答：SSE chunk 协议与 rag_stream 一致
    （retrieval_debug / token / citations / done），路由层与前端零改动兼容。

    与单库 rag_stream 的差异（需求 §8.3 明确）：
    - 不支持 HyDE（逐库生成假设文档成本翻倍）与语义缓存（跨库缓存键不成立）
    - 生成走 llm_gateway get_llm("rag_generate")（P0-3b 网关角色，与 rag_chain 内部工厂等价）
    """
    start_time = time.time()
    trimmed_history = _trim_chat_history(chat_history)
    retrieved_docs = await multi_kb_retrieve(kb_ids, question)
    retrieval_time_ms = int((time.time() - start_time) * 1000)

    yield {"type": "retrieval_debug", "content": {
        "chunks": [
            {"content": doc.page_content, "metadata": doc.metadata}
            for doc in retrieved_docs
        ],
        "retrieval_time_ms": retrieval_time_ms,
        "strategy": "multi_kb",
    }}

    context = _format_context(retrieved_docs)
    citations = _build_citations(retrieved_docs, question)
    messages = _to_langchain_messages(trimmed_history)

    llm = get_llm("rag_generate", streaming=True)
    chain = RAG_PROMPT | llm

    kwargs: dict = {
        "context": context,
        "chat_history": messages,
        "question": question,
    }
    config: dict = {}
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        langfuse_handler.metadata = {
            "knowledge_base_ids": kb_ids,
            "strategy": "multi_kb",
            "history_rounds": len(trimmed_history) // 2,
            "retrieval_time_ms": retrieval_time_ms,
        }

    full_answer = ""
    async for chunk in chain.astream(kwargs, config=config):
        token = chunk.content
        if token:
            full_answer += token
            yield {"type": "token", "content": token}

    total_time_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"Multi-KB RAG query completed: kbs={kb_ids}, "
        f"retrieval={retrieval_time_ms}ms, total={total_time_ms}ms"
    )

    yield {"type": "citations", "content": citations}
    yield {"type": "done", "content": full_answer}


# ---- P0-4 第三轮（T8）：文档级问答（信息源=单个文档；service 层后过滤，禁区零触碰） ----


async def check_doc_access(
    db: AsyncSession, kb_id: int, document_id: int, user: User
) -> None:
    """文档级问答前置校验：kb 读权限（403）+ 文档存在且属于该 kb（404 防串库枚举）。"""
    await get_kb_or_raise(kb_id, user, "viewer", db)
    doc = await db.get(Document, document_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")


async def doc_retrieve(kb_id: int, document_id: int, question: str) -> list:
    """文档级检索：常规混合检索候选 → 按 chunk metadata.document_id 后过滤 → 截断 top_k。

    禁区零触碰：retrieve_with_strategy 只读引用；候选量即其默认返回（settings.retrieval_top_k，
    hybrid_merge 截断后的全库最优集）。document_id 由入库管道写入 metadata（document_service）。
    过滤后为空返回 []（上层 yield「文档中未找到相关内容」提示，不进 LLM）。
    """
    candidates = await retrieve_with_strategy(kb_id, question, use_hyde=False)
    scoped = [d for d in candidates if d.metadata.get("document_id") == document_id]
    return scoped[: settings.retrieval_top_k]


async def doc_rag_stream(
    kb_id: int,
    document_id: int,
    question: str,
    chat_history: list[dict] | None = None,
) -> AsyncIterator[dict]:
    """文档级问答流式：SSE chunk 协议与 multi_kb_rag_stream 同款（strategy="doc_scoped"）。

    与 multi_kb 链同样不走 HyDE/语义缓存；生成走 llm_gateway get_llm("rag_generate")。
    轻流式：调用方（路由层）不创建会话、不持久化消息（信息源=文档/全部知识两档均不落会话）。
    """
    start_time = time.time()
    trimmed_history = _trim_chat_history(chat_history)
    retrieved_docs = await doc_retrieve(kb_id, document_id, question)
    retrieval_time_ms = int((time.time() - start_time) * 1000)

    yield {"type": "retrieval_debug", "content": {
        "chunks": [
            {"content": doc.page_content, "metadata": doc.metadata}
            for doc in retrieved_docs
        ],
        "retrieval_time_ms": retrieval_time_ms,
        "strategy": "doc_scoped",
    }}

    if not retrieved_docs:
        hint = "文档中未找到与问题相关的内容，请换个问法，或在信息源中切换为全部知识。"
        yield {"type": "token", "content": hint}
        yield {"type": "citations", "content": []}
        yield {"type": "done", "content": hint}
        return

    context = _format_context(retrieved_docs)
    citations = _build_citations(retrieved_docs, question)
    messages = _to_langchain_messages(trimmed_history)

    llm = get_llm("rag_generate", streaming=True)
    chain = RAG_PROMPT | llm
    kwargs: dict = {
        "context": context,
        "chat_history": messages,
        "question": question,
    }
    config: dict = {}
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        langfuse_handler.metadata = {
            "knowledge_base_id": kb_id,
            "document_id": document_id,
            "strategy": "doc_scoped",
            "retrieval_time_ms": retrieval_time_ms,
        }

    full_answer = ""
    async for chunk in chain.astream(kwargs, config=config):
        token = chunk.content
        if token:
            full_answer += token
            yield {"type": "token", "content": token}

    yield {"type": "citations", "content": citations}
    yield {"type": "done", "content": full_answer}
    total_time_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"Doc-scoped RAG query completed: kb={kb_id}, doc={document_id}, "
        f"chunks={len(retrieved_docs)}, retrieval={retrieval_time_ms}ms, total={total_time_ms}ms"
    )

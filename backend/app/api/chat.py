"""Chat API with SSE streaming support."""

from __future__ import annotations

import json
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.models.database import get_db
from app.models.user import User
from app.core.auth import require_user
from app.core.rag_chain import rag_stream, plain_chat_stream
from app.core.config import settings
from app.services import agent_service, chat_service, document_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    knowledge_base_id: int | None = None
    # P0-4 第二轮：多库信息源（len>1 时走 service 层多库合并链；单元素/空忽略，向后兼容）
    knowledge_base_ids: list[int] | None = None
    # P0-4 第三轮（T8）：文档级问答（与 knowledge_base_id 同传时切文档级轻流式，不落会话）
    document_id: int | None = None
    # P0-4 第五轮（T6，§11）：文档级多选（目录勾选=前端展开的文档集合；
    # 与 knowledge_base_ids 可并存=多范围合并链，落会话）
    document_ids: list[int] | None = None
    question: str
    conversation_id: int | None = None
    use_hyde: bool = False
    images: list[str] | None = None  # base64 data URIs or image URLs for multimodal chat
    file_content: str | None = None  # extracted text from uploaded file (via /upload-file)
    file_name: str | None = None  # original filename for display
    web_search: bool = False  # enable web search for plain chat


class ConversationResponse(BaseModel):
    id: int
    knowledge_base_id: int
    title: str

    model_config = {"from_attributes": True}


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # P0-4 第二轮：多库信息源判定（len>1 走多库合并链；单库/空路径行为不变）
    multi_kb_ids = [kb for kb in (req.knowledge_base_ids or []) if kb]
    is_multi_kb = len(multi_kb_ids) > 1
    # P0-4 第五轮（T6）：文档级多选 → 多范围合并链（纯文档范围时 kb_ids 可为空）；
    # 归属解析+逐文档权限校验在 SSE 前完成（403/404 不进事件流）
    scope_doc_ids = [d for d in (req.document_ids or []) if d]
    doc_scopes = (
        await chat_service.resolve_doc_scopes(db, scope_doc_ids, current_user)
        if scope_doc_ids
        else None
    )
    # 会话主信息源：kbIds[0] → 文档组首库 → 请求体 knowledge_base_id（直聊 kb=0 语义不变）
    scope_primary = (
        multi_kb_ids[0]
        if multi_kb_ids
        else (next(iter(doc_scopes)) if doc_scopes else req.knowledge_base_id)
    )
    primary_kb_id = multi_kb_ids[0] if is_multi_kb else scope_primary
    # Determine if this is a plain chat (no KB) or RAG chat
    is_plain_chat = primary_kb_id is None or primary_kb_id == 0

    # 多库：SSE 流开始前逐库读权限校验（越权 403，不进事件流）
    if is_multi_kb:
        await chat_service.check_multi_kb_access(db, multi_kb_ids, current_user)

    # P0-4 第三轮（T8）：文档级问答（kb_id + document_id 同传）→ 轻流式，不落会话/消息；
    # kb 读权限（403）与文档归属（404 防串库枚举）编排在 chat_service
    if req.document_id is not None and primary_kb_id:
        await chat_service.check_doc_access(db, primary_kb_id, req.document_id, current_user)
        return EventSourceResponse(
            _doc_sse_events(primary_kb_id, req.document_id, req.question)
        )

    # 权限校验、会话获取/创建、历史加载、用户消息持久化下沉 chat_service（D3：SSE 事件组装留路由层）
    # 多库时会话挂主信息源（第一个选中库）
    conversation, chat_history = await chat_service.prepare_chat(
        db, primary_kb_id, req.question, req.conversation_id, current_user
    )
    await chat_service.save_user_message(
        db, conversation.id, req.question, req.images, req.file_name
    )

    return EventSourceResponse(
        _chat_sse_events(
            db, req, conversation, chat_history,
            is_plain_chat=is_plain_chat,
            primary_kb_id=primary_kb_id,
            multi_kb_ids=multi_kb_ids if is_multi_kb else None,
            doc_scopes=doc_scopes,
        )
    )


async def _chat_sse_events(
    db: AsyncSession, req: ChatRequest, conversation, chat_history, *,
    is_plain_chat: bool, primary_kb_id: int | None = None,
    multi_kb_ids: list[int] | None = None,
    doc_scopes: dict[int, list[int]] | None = None,
):
    """老端点 SSE 生成器（P0-3a 提取：/stream 与 /agent/stream 的 plain/rag 分支共用）。

    P0-4 第二轮：多库信息源（multi_kb_ids len>1）时 rag 分支切换为 service 层多库
    合并链（chunk 协议与 rag_stream 一致）；否则走单库 rag_stream，行为零变化。
    P0-4 第五轮（T6）：doc_scopes 非空时切多范围合并链（整库+文档组，strategy=multi_scope）。
    """
    full_answer = ""
    citations = []

    yield {"event": "conversation", "data": json.dumps({
        "conversation_id": conversation.id,
    })}

    if is_plain_chat:
        # Plain chat mode: routes to GLM-4V-Flash (multimodal) or glm-4-flash-250414 (text+web_search)
        import logging
        logging.getLogger("app").info(f"[CHAT] web_search={req.web_search}, images={bool(req.images)}")
        async for chunk in plain_chat_stream(
            req.question, chat_history, images=req.images,
            file_content=req.file_content, web_search=req.web_search,
        ):
            if chunk["type"] == "token":
                full_answer += chunk["content"]
                yield {"event": "token", "data": json.dumps({"content": chunk["content"]})}
            elif chunk["type"] == "done":
                yield {"event": "done", "data": json.dumps({"content": full_answer})}
    else:
        if doc_scopes:
            # 多范围合并链（第五轮 T6）：整库 + 文档组混合；纯文档范围时 kb_ids 可为空
            stream = chat_service.multi_scope_rag_stream(
                multi_kb_ids or [], doc_scopes, req.question, chat_history
            )
        elif multi_kb_ids and len(multi_kb_ids) > 1:
            # 多库合并链（service 层方案甲）：不支持 HyDE，chunk 协议与单库一致
            stream = chat_service.multi_kb_rag_stream(
                multi_kb_ids, req.question, chat_history
            )
        else:
            # 单库路径：primary_kb_id 缺省时回落 req.knowledge_base_id（agent 转发路径不传）
            rag_kb_id = primary_kb_id if primary_kb_id is not None else req.knowledge_base_id
            stream = rag_stream(
                rag_kb_id, req.question, chat_history, use_hyde=req.use_hyde
            )
        async for chunk in stream:
            if chunk["type"] == "token":
                full_answer += chunk["content"]
                yield {"event": "token", "data": json.dumps({"content": chunk["content"]})}
            elif chunk["type"] == "citations":
                citations = chunk["content"]
                yield {"event": "citations", "data": json.dumps({"citations": citations})}
            elif chunk["type"] == "retrieval_debug":
                yield {"event": "retrieval_debug", "data": json.dumps(chunk["content"])}
            elif chunk["type"] == "done":
                yield {"event": "done", "data": json.dumps({"content": full_answer})}

    await chat_service.save_assistant_message(db, conversation.id, full_answer, citations)


async def _doc_sse_events(kb_id: int, document_id: int, question: str):
    """文档级问答 SSE 生成器（P0-4 第三轮 T8）：轻流式不落会话。

    chunk 协议与 multi_kb_rag_stream 一致（retrieval_debug / token / citations / done），
    生成/检索编排在 chat_service.doc_rag_stream（service 层后过滤，禁区零触碰）。
    """
    async for chunk in chat_service.doc_rag_stream(kb_id, document_id, question):
        if chunk["type"] == "token":
            yield {"event": "token", "data": json.dumps({"content": chunk["content"]})}
        elif chunk["type"] == "citations":
            yield {"event": "citations", "data": json.dumps({"citations": chunk["content"]})}
        elif chunk["type"] == "retrieval_debug":
            yield {"event": "retrieval_debug", "data": json.dumps(chunk["content"])}
        elif chunk["type"] == "done":
            yield {"event": "done", "data": json.dumps({"content": chunk["content"]})}


@router.post("/agent/stream")
async def agent_stream(
    req: ChatRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """P0-3a 统一 Agent 入口：意图分类后接力——plain/rag 复用现有生成器，tool 走 Agent 循环。"""
    conversation, chat_history = await chat_service.prepare_chat(
        db, req.knowledge_base_id, req.question, req.conversation_id, current_user
    )
    await chat_service.save_user_message(db, conversation.id, req.question, req.images, req.file_name)
    return EventSourceResponse(_agent_sse_events(db, req, current_user, conversation, chat_history))


async def _agent_sse_events(db, req, current_user, conversation, chat_history):
    """Agent 端点 SSE 组装（D3：生成器与事件组装留路由层）。

    三分支接力：plain/rag 转发 _chat_sse_events（与老端点零重复实现），tool 走 run_agent_loop。
    contextvar set/reset 成对包在 try/finally（提醒 1：generator 被客户端中断也不泄漏身份）。
    """
    intent = await agent_service.classify_intent(db, current_user, req.question, req.knowledge_base_id)
    yield {"event": "intent", "data": json.dumps({"intent": intent})}

    if intent != "tool":
        # plain/rag：接力复用老端点生成器（零重复实现，_chat_sse_events 自带 conversation 首事件）
        async for ev in _chat_sse_events(db, req, conversation, chat_history, is_plain_chat=(intent == "plain")):
            yield ev
        return

    # tool：Agent 循环（身份只在 contextvar，LLM 无法触碰——头号安全约束）
    yield {"event": "conversation", "data": json.dumps({"conversation_id": conversation.id})}
    tokens = agent_service.set_agent_context(db, current_user)
    full_answer = ""
    try:
        async for ev_type, payload in agent_service.run_agent_loop(req.question, chat_history):
            if ev_type == "token":
                full_answer += payload["content"]
            yield {"event": ev_type, "data": json.dumps(payload, ensure_ascii=False)}
        await chat_service.save_assistant_message(db, conversation.id, full_answer, [])
        # done 事件由路由层统一收尾（覆盖场景①直接回答与③④强制终止两条路径，格式与老端点一致）
        yield {"event": "done", "data": json.dumps({"content": full_answer})}
    finally:
        agent_service.reset_agent_context(tokens)


@router.post("/query")
async def chat_query(
    req: ChatRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming RAG query for A/B testing."""
    return await chat_service.query_rag(
        db, req.knowledge_base_id, req.question, req.conversation_id, req.use_hyde, current_user
    )


@router.get("/conversations/{kb_id}", response_model=list[ConversationResponse])
async def list_conversations(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 普通聊天（kb_id=0）无知识库校验；RAG 模式校验读权限（编排在 chat_service）
    return await chat_service.list_conversations(db, kb_id, current_user)


@router.get("/messages/{conversation_id}")
async def get_messages(
    conversation_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 只能读取本人会话的消息历史（编排在 chat_service）
    return await chat_service.get_messages(db, conversation_id, current_user)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 只能删除本人会话（编排在 chat_service）
    await chat_service.delete_conversation(db, conversation_id, current_user)
    return {"detail": "Conversation deleted"}


class ConversationRenameRequest(BaseModel):
    name: str


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: int,
    req: ConversationRenameRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """重命名会话（P0-4 第五轮返工 R26：历史条目「⋮」→ 编辑名称）。"""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name 不能为空")
    await chat_service.rename_conversation(db, conversation_id, name, current_user)
    return {"detail": "Conversation renamed"}


ALLOWED_FILE_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".csv", ".py", ".txt", ".md",
    ".bmp", ".gif",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload-file")
async def upload_file_for_chat(
    file: UploadFile = File(...),
    current_user: User = Depends(require_user),
):
    """Upload a file to Zhipu AI for content extraction (GLM-4V-Flash file understanding).

    Returns extracted text content that can be used as context in plain chat.
    """
    if not settings.chat_api_key:
        raise HTTPException(status_code=500, detail="CHAT_API_KEY not configured")

    # Validate file extension
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}"
        )

    # Read file content
    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum 50MB.")

    # Step 1: Upload file to Zhipu AI
    zhipu_base = settings.chat_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.chat_api_key}"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        upload_resp = await client.post(
            f"{zhipu_base}/files",
            headers=headers,
            files={"file": (file.filename, file_bytes, file.content_type or "application/octet-stream")},
            data={"purpose": "file-extract"},
        )

        if upload_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Zhipu file upload failed: {upload_resp.text}"
            )

        upload_data = upload_resp.json()
        file_id = upload_data.get("id")
        if not file_id:
            raise HTTPException(status_code=502, detail=f"No file ID returned: {upload_data}")

        # Step 2: Get extracted file content
        content_resp = await client.get(
            f"{zhipu_base}/files/{file_id}/content",
            headers=headers,
        )

        if content_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Zhipu file content extraction failed: {content_resp.text}"
            )

        extracted_content = content_resp.json().get("content", content_resp.text)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "content": extracted_content,
    }


class SaveMessageToKBRequest(BaseModel):
    kb_id: int
    category_id: int | None = None


@router.post("/messages/{message_id}/save-to-kb")
async def save_message_to_kb(
    message_id: int,
    req: SaveMessageToKBRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """消息存为知识库文档（P0-4 沉淀闭环）：校验消息归属 → 复用在线文档入库管道。

    标题取所属会话标题截断（与 prepare_chat 的 question[:50] 对齐）；
    消息归属 404 防枚举编排在 chat_service，KB 权限与入库编排在 document_service。
    """
    message, conversation = await chat_service.get_own_message(db, message_id, current_user)
    doc = await document_service.create_online_document(
        db, current_user, req.kb_id,
        title=conversation.title[:50], content=message.content,
        category_id=req.category_id,
    )
    return {
        "detail": "Message saved to knowledge base",
        "document_id": doc.id,
        "kb_id": doc.knowledge_base_id,
        "filename": doc.filename,
        "source": doc.source,
        "category_id": doc.category_id,
    }

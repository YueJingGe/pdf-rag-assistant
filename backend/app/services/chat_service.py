"""Chat conversation business logic (SSE event assembly stays in the route layer, D3)."""

from __future__ import annotations

from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_kb_or_raise
from app.core.rag_chain import rag_query
from app.models.conversation import Conversation, Message
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

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
from app.models.conversation import Conversation, Message
from app.core.auth import require_user, ensure_kb_permission
from app.core.rag_chain import rag_stream, rag_query, plain_chat_stream
from app.core.config import settings

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    knowledge_base_id: int | None = None
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


async def _get_own_conversation(
    conversation_id: int,
    current_user: User,
    db: AsyncSession,
) -> Conversation:
    """加载会话并校验归属；不存在或非本人会话一律 404（防止会话 ID 枚举探测）。"""
    conversation = await db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # Determine if this is a plain chat (no KB) or RAG chat
    is_plain_chat = req.knowledge_base_id is None or req.knowledge_base_id == 0

    if not is_plain_chat:
        # RAG 模式校验知识库读权限；普通聊天无知识库归属，仅需登录
        await ensure_kb_permission(req.knowledge_base_id, current_user, "viewer", db)

    if req.conversation_id:
        # 校验会话归属：只能在自己名下的会话里继续对话
        conversation = await _get_own_conversation(req.conversation_id, current_user, db)
    else:
        conversation = Conversation(
            knowledge_base_id=req.knowledge_base_id or 0,
            title=req.question[:50],
            user_id=current_user.id,
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

    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=req.question,
        images=req.images,
        file_name=req.file_name,
    )
    db.add(user_msg)
    await db.commit()

    async def event_generator():
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
            async for chunk in rag_stream(
                req.knowledge_base_id, req.question, chat_history, use_hyde=req.use_hyde
            ):
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

        assistant_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=full_answer,
            citations=citations,
        )
        db.add(assistant_msg)
        await db.commit()

    return EventSourceResponse(event_generator())


@router.post("/query")
async def chat_query(
    req: ChatRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming RAG query for A/B testing."""
    if req.knowledge_base_id:
        # RAG 模式校验知识库读权限
        await ensure_kb_permission(req.knowledge_base_id, current_user, "viewer", db)

    chat_history: list[dict] = []
    if req.conversation_id:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == req.conversation_id)
            .order_by(Message.created_at.desc())
            .limit(10) # 每次请求从数据库加载最近 10 条消息
        )
        history_msgs = list(reversed(result.scalars().all()))
        chat_history = [{"role": m.role, "content": m.content} for m in history_msgs]

    try:
        response = await rag_query(
            req.knowledge_base_id, req.question, chat_history, use_hyde=req.use_hyde
        )
        return response
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(exc)}")


@router.get("/conversations/{kb_id}", response_model=list[ConversationResponse])
async def list_conversations(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 普通聊天（kb_id=0）无知识库校验；RAG 模式校验读权限
    if kb_id:
        await ensure_kb_permission(kb_id, current_user, "viewer", db)
    # 只返回当前用户自己的会话（会话归属隔离）
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.knowledge_base_id == kb_id,
            Conversation.user_id == current_user.id,
        )
        .order_by(Conversation.created_at.desc())
    )
    return result.scalars().all()


@router.get("/messages/{conversation_id}")
async def get_messages(
    conversation_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 只能读取本人会话的消息历史
    await _get_own_conversation(conversation_id, current_user, db)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
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
        for m in messages
    ]


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 只能删除本人会话
    conversation = await _get_own_conversation(conversation_id, current_user, db)
    await db.execute(sa_delete(Message).where(Message.conversation_id == conversation_id))
    await db.delete(conversation)
    await db.commit()
    return {"detail": "Conversation deleted"}


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

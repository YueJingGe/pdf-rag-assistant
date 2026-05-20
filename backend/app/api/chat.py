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
from app.models.knowledge_base import KnowledgeBase
from app.models.conversation import Conversation, Message
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


class ConversationResponse(BaseModel):
    id: int
    knowledge_base_id: int
    title: str

    model_config = {"from_attributes": True}


@router.post("/stream")
async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    # Determine if this is a plain chat (no KB) or RAG chat
    is_plain_chat = req.knowledge_base_id is None or req.knowledge_base_id == 0

    if not is_plain_chat:
        kb = await db.get(KnowledgeBase, req.knowledge_base_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

    if req.conversation_id:
        conversation = await db.get(Conversation, req.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(
            knowledge_base_id=req.knowledge_base_id or 0,
            title=req.question[:50],
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
            # Plain chat mode: GLM-4V-Flash (free multimodal) 直接调用 LLM 不走 RAG 检索链
            async for chunk in plain_chat_stream(
                req.question, chat_history, images=req.images, file_content=req.file_content
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
async def chat_query(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Non-streaming RAG query for A/B testing."""
    kb = await db.get(KnowledgeBase, req.knowledge_base_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

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
async def list_conversations(kb_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.knowledge_base_id == kb_id)
        .order_by(Conversation.created_at.desc())
    )
    return result.scalars().all()


@router.get("/messages/{conversation_id}")
async def get_messages(conversation_id: int, db: AsyncSession = Depends(get_db)):
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
async def delete_conversation(conversation_id: int, db: AsyncSession = Depends(get_db)):
    conversation = await db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
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
async def upload_file_for_chat(file: UploadFile = File(...)):
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

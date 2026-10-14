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
from app.services import agent_service, chat_service

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


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # Determine if this is a plain chat (no KB) or RAG chat
    is_plain_chat = req.knowledge_base_id is None or req.knowledge_base_id == 0

    # 权限校验、会话获取/创建、历史加载、用户消息持久化下沉 chat_service（D3：SSE 事件组装留路由层）
    conversation, chat_history = await chat_service.prepare_chat(
        db, req.knowledge_base_id, req.question, req.conversation_id, current_user
    )
    await chat_service.save_user_message(
        db, conversation.id, req.question, req.images, req.file_name
    )

    return EventSourceResponse(_chat_sse_events(db, req, conversation, chat_history, is_plain_chat=is_plain_chat))


async def _chat_sse_events(
    db: AsyncSession, req: ChatRequest, conversation, chat_history, *, is_plain_chat: bool
):
    """老端点 SSE 生成器（P0-3a 提取：/stream 与 /agent/stream 的 plain/rag 分支共用，行为零变化）。"""
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

    await chat_service.save_assistant_message(db, conversation.id, full_answer, citations)


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

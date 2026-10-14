"""Retrieval feedback API for relevance marking and tuning data."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import User
from app.core.auth import require_user, require_admin
from app.services import feedback_service

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackCreateRequest(BaseModel):
    message_id: int
    knowledge_base_id: int
    question: str
    chunk_content: str
    chunk_metadata: dict | None = None
    is_relevant: bool


class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    knowledge_base_id: int
    question: str
    is_relevant: bool
    created_at: str

    model_config = {"from_attributes": True}


class FeedbackStats(BaseModel):
    total: int
    relevant: int
    irrelevant: int
    relevance_rate: float


@router.post("", response_model=dict)
async def create_feedback(
    req: FeedbackCreateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 记录检索反馈；KB 读权限校验在 service（viewer 级，P0-2 安全修复补齐）
    feedback = await feedback_service.create_feedback(
        db, current_user,
        message_id=req.message_id, knowledge_base_id=req.knowledge_base_id,
        question=req.question, chunk_content=req.chunk_content,
        chunk_metadata=req.chunk_metadata, is_relevant=req.is_relevant,
    )
    return {"id": feedback.id, "detail": "Feedback recorded"}


@router.get("/stats/{kb_id}", response_model=FeedbackStats)
async def get_feedback_stats(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 反馈统计可能暴露检索质量信息，先校验知识库读权限（编排在 feedback_service）
    return FeedbackStats(**await feedback_service.get_feedback_stats(db, current_user, kb_id))


@router.get("/export/{kb_id}")
async def export_feedback(
    kb_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export all feedback for a knowledge base (for reranker training)."""
    # 仅 admin 且需为该库 owner：admin 由 require_admin 保证，owner 校验在 service
    return await feedback_service.export_feedback(db, current_user, kb_id)

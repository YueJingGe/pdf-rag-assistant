"""Retrieval feedback API for relevance marking and tuning data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import User
from app.models.feedback import RetrievalFeedback
from app.core.auth import require_user, require_admin, ensure_kb_permission

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
    feedback = RetrievalFeedback(
        message_id=req.message_id,
        knowledge_base_id=req.knowledge_base_id,
        question=req.question,
        chunk_content=req.chunk_content,
        chunk_metadata=req.chunk_metadata,
        is_relevant=req.is_relevant,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return {"id": feedback.id, "detail": "Feedback recorded"}


@router.get("/stats/{kb_id}", response_model=FeedbackStats)
async def get_feedback_stats(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 反馈统计可能暴露检索质量信息，先校验知识库读权限
    await ensure_kb_permission(kb_id, current_user, "viewer", db)
    total_result = await db.execute(
        select(func.count(RetrievalFeedback.id))
        .where(RetrievalFeedback.knowledge_base_id == kb_id)
    )
    total = total_result.scalar() or 0

    relevant_result = await db.execute(
        select(func.count(RetrievalFeedback.id))
        .where(
            RetrievalFeedback.knowledge_base_id == kb_id,
            RetrievalFeedback.is_relevant == True,
        )
    )
    relevant = relevant_result.scalar() or 0
    irrelevant = total - relevant
    relevance_rate = (relevant / total) if total > 0 else 0.0

    return FeedbackStats(
        total=total,
        relevant=relevant,
        irrelevant=irrelevant,
        relevance_rate=round(relevance_rate, 4),
    )


@router.get("/export/{kb_id}")
async def export_feedback(
    kb_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export all feedback for a knowledge base (for reranker training)."""
    # 导出含原始问答语料，仅 admin 且需为该库 owner（admin 由 require_admin 保证）
    await ensure_kb_permission(kb_id, current_user, "owner", db)
    result = await db.execute(
        select(RetrievalFeedback)
        .where(RetrievalFeedback.knowledge_base_id == kb_id)
        .order_by(RetrievalFeedback.created_at.desc())
    )
    feedbacks = result.scalars().all()
    return [
        {
            "question": f.question,
            "chunk_content": f.chunk_content,
            "chunk_metadata": f.chunk_metadata,
            "is_relevant": f.is_relevant,
            "created_at": f.created_at.isoformat(),
        }
        for f in feedbacks
    ]

"""Retrieval feedback business logic (relevance marking, stats, reranker export)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_kb_or_raise
from app.models.feedback import RetrievalFeedback


async def create_feedback(
    db: AsyncSession,
    user: User,
    *,
    message_id: int,
    knowledge_base_id: int,
    question: str,
    chunk_content: str,
    chunk_metadata: dict | None,
    is_relevant: bool,
) -> RetrievalFeedback:
    """记录检索反馈。"""
    feedback = RetrievalFeedback(
        message_id=message_id,
        knowledge_base_id=knowledge_base_id,
        question=question,
        chunk_content=chunk_content,
        chunk_metadata=chunk_metadata,
        is_relevant=is_relevant,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback


async def get_feedback_stats(db: AsyncSession, user: User, kb_id: int) -> dict:
    """反馈统计（可能暴露检索质量信息，先校验知识库读权限）。"""
    await get_kb_or_raise(kb_id, user, "viewer", db)

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

    return {
        "total": total,
        "relevant": relevant,
        "irrelevant": irrelevant,
        "relevance_rate": round(relevance_rate, 4),
    }


async def export_feedback(db: AsyncSession, user: User, kb_id: int) -> list[dict]:
    """Export all feedback for a knowledge base (for reranker training).

    含原始问答语料，仅 owner 可导出；admin 门槛由路由层 require_admin 保证。
    """
    await get_kb_or_raise(kb_id, user, "owner", db)
    result = await db.execute(
        select(RetrievalFeedback)
        .where(RetrievalFeedback.knowledge_base_id == kb_id)
        .order_by(RetrievalFeedback.created_at.desc())
    )
    return [
        {
            "question": f.question,
            "chunk_content": f.chunk_content,
            "chunk_metadata": f.chunk_metadata,
            "is_relevant": f.is_relevant,
            "created_at": f.created_at.isoformat(),
        }
        for f in result.scalars().all()
    ]

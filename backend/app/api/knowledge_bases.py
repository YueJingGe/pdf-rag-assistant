"""Knowledge base management API routes."""

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.core.auth import require_user, ensure_kb_permission
from app.core.vector_store import vector_store_manager

router = APIRouter(prefix="/api/knowledge_bases", tags=["knowledge_bases"])


class KBCreateRequest(BaseModel):
    name: str
    description: str = ""
    permission: str = "private"


class KBResponse(BaseModel):
    id: int
    name: str
    description: str
    permission: str
    document_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=KBResponse)
async def create_knowledge_base(
    req: KBCreateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 创建者即 owner，数据归属当前登录用户
    kb = KnowledgeBase(
        name=req.name, description=req.description,
        permission=req.permission, user_id=current_user.id,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return KBResponse(
        id=kb.id, name=kb.name, description=kb.description,
        permission=kb.permission, document_count=0,
        created_at=kb.created_at, updated_at=kb.updated_at,
    )


@router.get("", response_model=list[KBResponse])
async def list_knowledge_bases(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.document import Document
    from sqlalchemy import func
    # 可见性：自己拥有的 + 公开的 + 存量无主（user_id 为 NULL，视为公共）；admin 全量可见
    query = select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
    if not current_user.is_admin:
        query = query.where(or_(
            KnowledgeBase.user_id == current_user.id,
            KnowledgeBase.permission == "public",
            KnowledgeBase.user_id.is_(None),
        ))
    result = await db.execute(query)
    kbs = result.scalars().all()
    responses = []
    for kb in kbs:
        count_result = await db.execute(
            select(func.count(Document.id)).where(
                Document.knowledge_base_id == kb.id,
                Document.status == "ready",
            )
        )
        ready_count = count_result.scalar() or 0
        responses.append(KBResponse(
            id=kb.id, name=kb.name, description=kb.description,
            permission=kb.permission, document_count=ready_count,
            created_at=kb.created_at, updated_at=kb.updated_at,
        ))
    return responses


@router.get("/{kb_id}", response_model=KBResponse)
async def get_knowledge_base(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.document import Document
    from sqlalchemy import func
    # 读权限校验：public / 本人 / 授权用户；不存在 404，无权限 403
    kb = await ensure_kb_permission(kb_id, current_user, "viewer", db)
    count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == kb.id,
            Document.status == "ready",
        )
    )
    ready_count = count_result.scalar() or 0
    return KBResponse(
        id=kb.id, name=kb.name, description=kb.description,
        permission=kb.permission, document_count=ready_count,
        created_at=kb.created_at, updated_at=kb.updated_at,
    )


class KBUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


# 更新名称/描述
@router.put("/{kb_id}", response_model=KBResponse)
async def update_knowledge_base(
    kb_id: int,
    req: KBUpdateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.document import Document
    from sqlalchemy import func

    # 写权限校验：仅 owner / admin
    kb = await ensure_kb_permission(kb_id, current_user, "owner", db)

    if req.name is not None:
        kb.name = req.name
    if req.description is not None:
        kb.description = req.description

    await db.commit()
    await db.refresh(kb)

    count_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == kb.id,
            Document.status == "ready",
        )
    )
    ready_count = count_result.scalar() or 0
    return KBResponse(
        id=kb.id, name=kb.name, description=kb.description,
        permission=kb.permission, document_count=ready_count,
        created_at=kb.created_at, updated_at=kb.updated_at,
    )


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 写权限校验：仅 owner / admin
    kb = await ensure_kb_permission(kb_id, current_user, "owner", db)
    vector_store_manager.delete_index(kb_id)
    await db.delete(kb)
    await db.commit()
    return {"detail": "Knowledge base deleted"}

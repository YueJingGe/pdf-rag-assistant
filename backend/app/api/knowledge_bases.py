"""Knowledge base management API routes."""

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import User
from app.core.auth import require_user
from app.services import kb_service

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
    """创建知识库（创建者即 owner，数据归属当前登录用户）。"""
    kb = await kb_service.create_kb(
        db, current_user,
        name=req.name, description=req.description, permission=req.permission,
    )
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
    """列出当前用户可见的知识库（可见性过滤在 service：本人 + public + 存量无主，admin 全量）。"""
    return [KBResponse(**item) for item in await kb_service.list_visible_kbs(db, current_user)]


@router.get("/{kb_id}", response_model=KBResponse)
async def get_knowledge_base(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取知识库详情（读权限校验在 service：public/本人/授权可读；不存在 404，无权限 403）。"""
    return KBResponse(**await kb_service.get_kb_detail(db, current_user, kb_id))


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
    """更新知识库名称/描述（写权限校验在 service：仅 owner/admin）。"""
    return KBResponse(**await kb_service.update_kb(
        db, current_user, kb_id, name=req.name, description=req.description,
    ))


@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """删除知识库（写权限校验在 service；同时清理 FAISS 向量索引）。"""
    await kb_service.delete_kb(db, current_user, kb_id)
    return {"detail": "Knowledge base deleted"}

"""Knowledge base management API routes."""

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import User
from app.core.auth import require_user
from app.services import category_service, kb_service

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


# ---------------- P0-4：目录树与混合树 ----------------

class CategoryCreateRequest(BaseModel):
    name: str
    parent_id: int | None = None


class CategoryUpdateRequest(BaseModel):
    name: str


class CategoryResponse(BaseModel):
    id: int
    kb_id: int
    parent_id: int | None = None
    name: str
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TreeNodeDocument(BaseModel):
    id: int
    filename: str
    source: str = "upload"
    category_id: int | None = None
    status: str
    file_type: str
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TreeResponse(BaseModel):
    categories: list[CategoryResponse]
    documents: list[TreeNodeDocument]


@router.post("/{kb_id}/categories", response_model=CategoryResponse)
async def create_category(
    kb_id: int,
    req: CategoryCreateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """新建目录（P0-4；写权限校验在 service，父目录需同库）。"""
    return await category_service.create_category(
        db, current_user, kb_id, name=req.name, parent_id=req.parent_id
    )


@router.get("/{kb_id}/tree", response_model=TreeResponse)
async def get_kb_tree(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """目录 + 文档混合树数据（P0-4；一次拉全量，前端组树，读权限校验在 service）。"""
    return await category_service.get_tree(db, current_user, kb_id)


@router.patch("/{kb_id}/categories/{category_id}", response_model=CategoryResponse)
async def rename_category(
    kb_id: int,
    category_id: int,
    req: CategoryUpdateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """重命名目录（P0-4；写权限校验在 service）。"""
    return await category_service.rename_category(
        db, current_user, kb_id, category_id, name=req.name
    )


@router.delete("/{kb_id}/categories/{category_id}")
async def delete_category(
    kb_id: int,
    category_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """删除目录（P0-4；子目录上提一级，文档移至根不删文档，写权限校验在 service）。"""
    return await category_service.delete_category(db, current_user, kb_id, category_id)

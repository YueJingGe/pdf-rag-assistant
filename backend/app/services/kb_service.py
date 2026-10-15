"""知识库服务：CRUD、可见性过滤与权限校验编排。

业务逻辑自 api/knowledge_bases.py 下沉至此（P0-2 第 1 轮），
路由层只保留参数校验、依赖注入与响应组装。
权限判定统一走 core/auth.py 的 get_kb_or_raise（抛领域异常），
由 main.py 全局 exception handler 转 HTTP（404/403）。
"""

from __future__ import annotations

import shutil

from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_kb_or_raise
from app.core.config import settings
from app.core.vector_store import vector_store_manager
from app.models.category import Category
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase


async def _ready_document_count(db: AsyncSession, kb_id: int) -> int:
    """统计指定知识库下 status=ready 的文档数。"""
    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == kb_id,
            Document.status == "ready",
        )
    )
    return result.scalar() or 0


def _kb_to_dict(kb: KnowledgeBase, document_count: int) -> dict:
    """KB 实体 → 路由响应兼容 dict（字段与 api 层 KBResponse 对齐）。"""
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "permission": kb.permission,
        "document_count": document_count,
        "created_at": kb.created_at,
        "updated_at": kb.updated_at,
    }


async def create_kb(
    db: AsyncSession,
    user: User,
    *,
    name: str,
    description: str = "",
    permission: str = "private",
) -> KnowledgeBase:
    """创建知识库（创建者即 owner，数据归属当前登录用户）。"""
    kb = KnowledgeBase(
        name=name, description=description,
        permission=permission, user_id=user.id,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


async def list_visible_kbs(db: AsyncSession, user: User) -> list[dict]:
    """列出当前用户可见的知识库（含 ready 文档数）。

    可见性：自己拥有的 + public + 存量无主（user_id IS NULL 视为公共）；
    admin 全量可见。
    """
    query = select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
    if not user.is_admin:
        query = query.where(or_(
            KnowledgeBase.user_id == user.id,
            KnowledgeBase.permission == "public",
            KnowledgeBase.user_id.is_(None),
        ))
    result = await db.execute(query)
    kbs = result.scalars().all()
    return [
        _kb_to_dict(kb, await _ready_document_count(db, kb.id))
        for kb in kbs
    ]


async def get_kb_detail(db: AsyncSession, user: User, kb_id: int) -> dict:
    """获取单个知识库详情（viewer 读权限；不存在/无权限由领域异常表达）。"""
    kb = await get_kb_or_raise(kb_id, user, "viewer", db)
    return _kb_to_dict(kb, await _ready_document_count(db, kb.id))


async def update_kb(
    db: AsyncSession,
    user: User,
    kb_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """更新知识库名称/描述（owner 写权限），返回更新后详情。"""
    kb = await get_kb_or_raise(kb_id, user, "owner", db)
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    await db.commit()
    await db.refresh(kb)
    return _kb_to_dict(kb, await _ready_document_count(db, kb.id))


async def delete_kb(db: AsyncSession, user: User, kb_id: int) -> None:
    """删除知识库（owner 写权限），级联清理其全部数据。

    P0-4 修复：此前仅删 KB 行与 FAISS 索引，categories/documents/conversations/
    messages 行与 uploads 物理目录全部残留为孤儿（冒烟临时库残留实证：孤儿目录
    被后续新建的同 id 库认领）。顺序：先删子表行再删 KB 行，commit 成功后才删
    物理文件（FAISS + uploads 目录），物理删除失败不影响 DB 一致性且可重跑幂等。
    """
    kb = await get_kb_or_raise(kb_id, user, "owner", db)

    # 1) 会话与消息（先删子表 messages）
    conv_ids = (
        await db.execute(
            select(Conversation.id).where(Conversation.knowledge_base_id == kb_id)
        )
    ).scalars().all()
    if conv_ids:
        await db.execute(sa_delete(Message).where(Message.conversation_id.in_(conv_ids)))
        await db.execute(sa_delete(Conversation).where(Conversation.id.in_(conv_ids)))

    # 2) 目录与文档行（文档物理文件随 uploads 目录整体清理）
    await db.execute(sa_delete(Category).where(Category.kb_id == kb_id))
    await db.execute(sa_delete(Document).where(Document.knowledge_base_id == kb_id))

    await db.delete(kb)
    await db.commit()

    # 3) 物理清理（commit 成功后）
    vector_store_manager.delete_index(kb_id)
    shutil.rmtree(settings.upload_dir / str(kb_id), ignore_errors=True)

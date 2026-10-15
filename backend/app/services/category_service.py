"""目录树服务：KB 内目录 CRUD、混合树拉取与文档挂载（P0-4）。

权限语义与既有 service 一致：目录/树读走 viewer，目录写与文档移动走 owner；
权限判定统一走 core/auth.py 的 get_kb_or_raise（抛领域异常），
由 main.py 全局 exception handler 转 HTTP（404/403）。

删除目录策略（需求 §4.2 两个选项中拍板后者）：**不删任何文档**——
直接子目录上提至被删目录的父级（根目录子级上提为根），文档全部移至根（category_id=NULL）。
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_kb_or_raise
from app.models.category import Category
from app.models.document import Document
from app.services.exceptions import NotFoundError, ValidationError


async def get_category_or_raise(db: AsyncSession, kb_id: int, category_id: int) -> Category:
    """加载目录并校验库归属；不存在或不属于该 KB 一律 NotFoundError（404）。"""
    category = await db.get(Category, category_id)
    if not category or category.kb_id != kb_id:
        raise NotFoundError("Category not found")
    return category


async def create_category(
    db: AsyncSession, user: User, kb_id: int, *, name: str, parent_id: int | None = None
) -> Category:
    """新建目录（写操作，仅 owner / admin）；parent_id 需为同库目录。"""
    await get_kb_or_raise(kb_id, user, "owner", db)
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("Category name cannot be empty")
    if parent_id is not None:
        await get_category_or_raise(db, kb_id, parent_id)

    category = Category(kb_id=kb_id, parent_id=parent_id, name=clean_name)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def rename_category(
    db: AsyncSession, user: User, kb_id: int, category_id: int, *, name: str
) -> Category:
    """重命名目录（写操作，仅 owner / admin）。"""
    await get_kb_or_raise(kb_id, user, "owner", db)
    category = await get_category_or_raise(db, kb_id, category_id)
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValidationError("Category name cannot be empty")

    category.name = clean_name
    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, user: User, kb_id: int, category_id: int) -> dict:
    """删除目录（写操作，仅 owner / admin）：子目录上提一级，文档移至根，不删文档。"""
    await get_kb_or_raise(kb_id, user, "owner", db)
    category = await get_category_or_raise(db, kb_id, category_id)

    # 子目录上提：parent 指向被删目录的原父级（根目录的子级上提为根）
    await db.execute(
        update(Category)
        .where(Category.parent_id == category_id)
        .values(parent_id=category.parent_id)
    )
    # 文档移至根（未归类），不删除任何文档
    await db.execute(
        update(Document)
        .where(Document.category_id == category_id)
        .values(category_id=None)
    )
    await db.delete(category)
    await db.commit()
    return {"detail": "Category deleted", "documents_moved_to_root": True}


async def move_documents(
    db: AsyncSession, user: User, kb_id: int, *, document_ids: list[int], category_id: int | None
) -> int:
    """批量移动文档到目录（category_id=None 表示移至根/未归类）；返回实际移动数。"""
    await get_kb_or_raise(kb_id, user, "owner", db)
    if not document_ids:
        raise ValidationError("No document IDs provided")
    if category_id is not None:
        await get_category_or_raise(db, kb_id, category_id)

    moved = 0
    for doc_id in document_ids:
        doc = await db.get(Document, doc_id)
        if doc and doc.knowledge_base_id == kb_id:
            doc.category_id = category_id
            moved += 1
    await db.commit()
    return moved


async def get_tree(db: AsyncSession, user: User, kb_id: int) -> dict:
    """目录 + 文档混合树数据（一次拉全量，前端组树；个人库规模不构成瓶颈）。"""
    await get_kb_or_raise(kb_id, user, "viewer", db)

    cat_result = await db.execute(
        select(Category)
        .where(Category.kb_id == kb_id)
        .order_by(Category.sort_order.asc(), Category.id.asc())
    )
    doc_result = await db.execute(
        select(Document)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.asc())
    )
    return {
        "categories": [
            {
                "id": c.id,
                "kb_id": c.kb_id,
                "parent_id": c.parent_id,
                "name": c.name,
                "sort_order": c.sort_order,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in cat_result.scalars().all()
        ],
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "source": d.source,
                "category_id": d.category_id,
                "status": d.status,
                "file_type": d.file_type,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at,
                "updated_at": d.updated_at,
            }
            for d in doc_result.scalars().all()
        ],
    }

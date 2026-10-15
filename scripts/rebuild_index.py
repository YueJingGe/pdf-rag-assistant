"""Rebuild FAISS indexes for all or a specific knowledge base."""

# Python 3.9 兼容：注解延迟求值（否则 `int | None` 在函数定义时报 TypeError）
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# P0-4 修复：.env 的 DATABASE_URL/faiss 路径均为相对路径（./data/...），必须先 chdir 到
# backend 再 import app（engine 在 import 时即创建并解析相对路径），否则从项目根执行
# 会误建空库/空索引（实证：误产物 <项目根>/data/db.sqlite3）
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.loader import load_document
from app.core.splitter import split_documents
from app.core.vector_store import vector_store_manager
from app.models.database import async_session_factory, engine, Base
import app.models.category  # noqa: F401  P0-4：注册 categories 表（documents.category_id FK 依赖）
import app.models.user  # noqa: F401  注册 users 表（knowledge_bases.user_id FK 依赖）
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from sqlalchemy import select


async def rebuild(kb_id: int | None = None):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        if kb_id:
            kbs = [await db.get(KnowledgeBase, kb_id)]
            kbs = [kb for kb in kbs if kb]
        else:
            result = await db.execute(select(KnowledgeBase))
            kbs = list(result.scalars().all())

        for kb in kbs:
            print(f"\n=== Rebuilding index for KB #{kb.id}: {kb.name} ===")
            result = await db.execute(
                select(Document).where(Document.knowledge_base_id == kb.id, Document.status == "ready")
            )
            docs = result.scalars().all()

            all_chunks = []
            for doc in docs:
                try:
                    raw = load_document(doc.file_path)
                    chunks = split_documents(raw)
                    for chunk in chunks:
                        chunk.metadata["document_id"] = doc.id
                        chunk.metadata["knowledge_base_id"] = kb.id
                    all_chunks.extend(chunks)
                    print(f"  ✓ {doc.filename}: {len(chunks)} chunks")
                except Exception as exc:
                    print(f"  ✗ {doc.filename}: {exc}")

            vector_store_manager.rebuild_index(kb.id, all_chunks)
            print(f"  Total: {len(all_chunks)} chunks indexed")

    print("\nDone.")


if __name__ == "__main__":
    target_kb_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(rebuild(target_kb_id))

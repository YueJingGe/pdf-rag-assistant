"""Knowledge base document business logic (upload/list/delete/rename/rebuild index)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_kb_or_raise
from app.core.loader import load_document, SUPPORTED_EXTENSIONS
from app.core.splitter import split_documents
from app.core.vector_store import vector_store_manager
from app.models.document import Document
from app.services.exceptions import NotFoundError, ServiceError, ValidationError
from app.utils.file_utils import save_upload_file, delete_upload_file, get_file_extension


async def upload_document(
    db: AsyncSession,
    user: User,
    kb_id: int,
    *,
    filename: str,
    content: bytes,
) -> Document:
    """上传文档（写操作，仅 owner / admin）。

    落盘 -> 解析切分 -> 向量化 -> 状态流转；解析失败时文档置 error 并抛 ServiceError（500）。
    """
    await get_kb_or_raise(kb_id, user, "owner", db)

    extension = get_file_extension(filename or "")
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type: {extension}. Supported: {SUPPORTED_EXTENSIONS}"
        )

    file_path = save_upload_file(content, filename or "document", kb_id)

    doc_record = Document(
        knowledge_base_id=kb_id,
        filename=filename or "document",
        file_type=extension,
        file_path=str(file_path),
        file_size=len(content),
        status="processing",
    )
    db.add(doc_record)
    await db.commit()
    await db.refresh(doc_record)

    try:
        raw_docs = load_document(file_path)
        chunks = split_documents(raw_docs)

        for chunk in chunks:
            chunk.metadata["document_id"] = doc_record.id
            chunk.metadata["knowledge_base_id"] = kb_id

        chunk_count = vector_store_manager.add_documents(kb_id, chunks)

        doc_record.chunk_count = chunk_count
        doc_record.status = "ready"
        await db.commit()
        await db.refresh(doc_record)

    except Exception as exc:
        doc_record.status = "error"
        doc_record.error_message = str(exc)
        await db.commit()
        await db.refresh(doc_record)
        raise ServiceError(f"Document processing failed: {exc}")

    return doc_record


async def list_documents(db: AsyncSession, user: User, kb_id: int) -> list[Document]:
    """列出知识库文档（读权限：public / 本人 / 授权用户），按创建时间倒序。"""
    await get_kb_or_raise(kb_id, user, "viewer", db)

    result = await db.execute(
        select(Document)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_document(db: AsyncSession, user: User, kb_id: int, doc_id: int) -> None:
    """删除文档（写操作，仅 owner / admin）并触发索引重建。"""
    await get_kb_or_raise(kb_id, user, "owner", db)
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")

    delete_upload_file(doc.file_path)
    await db.delete(doc)
    await db.commit()

    await _rebuild_kb_index(db, kb_id)


async def batch_delete_documents(
    db: AsyncSession, user: User, kb_id: int, doc_ids: list[int]
) -> int:
    """批量删除多个文档，索引只重建一次；返回实际删除数量。"""
    await get_kb_or_raise(kb_id, user, "owner", db)

    if not doc_ids:
        raise ValidationError("No document IDs provided")

    deleted_count = 0
    for doc_id in doc_ids:
        doc = await db.get(Document, doc_id)
        if doc and doc.knowledge_base_id == kb_id:
            delete_upload_file(doc.file_path)
            await db.delete(doc)
            deleted_count += 1

    await db.commit()

    await _rebuild_kb_index(db, kb_id)
    return deleted_count


async def _rebuild_kb_index(db: AsyncSession, kb_id: int) -> None:
    """Rebuild the FAISS index for a knowledge base from remaining ready documents."""
    remaining = await db.execute(
        select(Document).where(
            Document.knowledge_base_id == kb_id,
            Document.status == "ready",
        )
    )
    remaining_docs = remaining.scalars().all()

    all_chunks = []
    for remaining_doc in remaining_docs:
        try:
            raw = load_document(remaining_doc.file_path)
            chunks = split_documents(raw)
            for chunk in chunks:
                chunk.metadata["document_id"] = remaining_doc.id
                chunk.metadata["knowledge_base_id"] = kb_id
            all_chunks.extend(chunks)
        except Exception:
            pass

    vector_store_manager.rebuild_index(kb_id, all_chunks)

    # Invalidate semantic cache for this KB since documents changed
    from app.core.rag_chain import semantic_cache
    semantic_cache.invalidate(kb_id)


def _load_content_from_chunks(kb_id: int, source_filename: str) -> dict | None:
    """优先从 FAISS docstore 取已解析 chunks 拼全文（与检索/引用同源）。

    避免 viewer 打开时对原文档现场重新解析——扫描件 PDF 每次都重跑 OCR
    （11 页 15s+）且同步阻塞事件循环；chunks 是入库时的解析结果，读
    docstore 毫秒级，且与引用段落同源，高亮匹配率更高。
    索引缺失 / 无匹配 chunk 时返回 None，由调用方走 load_document 兑底。
    """
    store = vector_store_manager.get_store(kb_id)
    if store is None:
        return None
    chunks = []
    for doc in getattr(store.docstore, "_dict", {}).values():
        meta = doc.metadata or {}
        stored = str(meta.get("source_filename") or meta.get("source") or "")
        if stored == source_filename or source_filename in stored:
            chunks.append(
                (meta.get("page") or 0, meta.get("chunk_index") or 0, doc.page_content)
            )
    if not chunks:
        return None
    chunks.sort(key=lambda t: (t[0], t[1]))
    return {
        "content": "\n\n".join(t[2] for t in chunks),
        "page_count": len({t[0] for t in chunks}),
    }


async def get_document_by_source(
    db: AsyncSession, user: User, kb_id: int, source_filename: str
) -> dict:
    """按 source_filename（磁盘存储名）取文档全文（读权限：public / 本人 / 授权用户）。"""
    await get_kb_or_raise(kb_id, user, "viewer", db)

    result = await db.execute(
        select(Document).where(Document.knowledge_base_id == kb_id)
    )
    docs = result.scalars().all()

    # Match by file_path containing the source_filename
    target_doc = None
    for doc in docs:
        stored_name = Path(doc.file_path).name
        if stored_name == source_filename or source_filename in stored_name:
            target_doc = doc
            break

    if not target_doc:
        raise NotFoundError("Document not found by source filename")

    # 优先读已解析 chunks（毫秒级）；索引不可用时兑底重新解析原文档
    chunks_result = _load_content_from_chunks(kb_id, source_filename)
    if chunks_result is not None:
        return {"filename": target_doc.filename, **chunks_result}

    try:
        raw_docs = load_document(target_doc.file_path)
        content = "\n\n".join(d.page_content for d in raw_docs)
        return {"filename": target_doc.filename, "content": content, "page_count": len(raw_docs)}
    except Exception as exc:
        raise ServiceError(f"Failed to read document: {exc}")


async def get_document_content(
    db: AsyncSession, user: User, kb_id: int, doc_id: int
) -> dict:
    """Get the full text content of a document for viewer display."""
    # 读权限：public / 本人 / 授权用户
    await get_kb_or_raise(kb_id, user, "viewer", db)
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")

    # 优先读已解析 chunks（同 get_document_by_source，避免扫描件 PDF 现场 OCR）
    display_name = Path(doc.file_path).name
    chunks_result = _load_content_from_chunks(kb_id, display_name)
    if chunks_result is not None:
        return {"filename": doc.filename, **chunks_result}

    try:
        raw_docs = load_document(doc.file_path)
        content = "\n\n".join(d.page_content for d in raw_docs)
        return {"filename": doc.filename, "content": content, "page_count": len(raw_docs)}
    except Exception as exc:
        raise ServiceError(f"Failed to read document: {exc}")


async def rename_document(
    db: AsyncSession, user: User, kb_id: int, doc_id: int, filename: str
) -> Document:
    """Rename a document's display name（写操作，仅 owner / admin）。"""
    await get_kb_or_raise(kb_id, user, "owner", db)
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise NotFoundError("Document not found")

    if not filename.strip():
        raise ValidationError("Filename cannot be empty")

    doc.filename = filename.strip()
    await db.commit()
    await db.refresh(doc)
    return doc

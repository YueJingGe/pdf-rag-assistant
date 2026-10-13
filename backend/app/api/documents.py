"""Document upload, list, and delete API routes."""

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.document import Document
from app.models.user import User
from app.core.auth import require_user, ensure_kb_permission
from app.core.loader import load_document, SUPPORTED_EXTENSIONS
from app.core.splitter import split_documents
from app.core.vector_store import vector_store_manager
from app.utils.file_utils import save_upload_file, delete_upload_file, get_file_extension

router = APIRouter(prefix="/api/knowledge_bases/{kb_id}/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    error_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=DocumentResponse)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 上传是写操作，仅 owner / admin；不存在 404，无权限 403
    await ensure_kb_permission(kb_id, current_user, "owner", db)

    extension = get_file_extension(file.filename or "")
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {extension}. Supported: {SUPPORTED_EXTENSIONS}",
        )

    content = await file.read()
    file_path = save_upload_file(content, file.filename or "document", kb_id)

    doc_record = Document(
        knowledge_base_id=kb_id,
        filename=file.filename or "document",
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
        raise HTTPException(status_code=500, detail=f"Document processing failed: {exc}")

    return doc_record


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 读权限：public / 本人 / 授权用户
    await ensure_kb_permission(kb_id, current_user, "viewer", db)

    result = await db.execute(
        select(Document)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{doc_id}")
async def delete_document(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 删除是写操作，仅 owner / admin
    await ensure_kb_permission(kb_id, current_user, "owner", db)
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_upload_file(doc.file_path)
    await db.delete(doc)
    await db.commit()

    await _rebuild_kb_index(kb_id, db)

    return {"detail": "Document deleted and index rebuilt"}


class BatchDeleteRequest(BaseModel):
    doc_ids: list[int]


@router.post("/batch_delete")
async def batch_delete_documents(
    kb_id: int,
    req: BatchDeleteRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch delete multiple documents and rebuild the FAISS index once."""
    # 批量删除是写操作，仅 owner / admin
    await ensure_kb_permission(kb_id, current_user, "owner", db)

    if not req.doc_ids:
        raise HTTPException(status_code=400, detail="No document IDs provided")

    deleted_count = 0
    for doc_id in req.doc_ids:
        doc = await db.get(Document, doc_id)
        if doc and doc.knowledge_base_id == kb_id:
            delete_upload_file(doc.file_path)
            await db.delete(doc)
            deleted_count += 1

    await db.commit()

    await _rebuild_kb_index(kb_id, db)

    return {"detail": f"{deleted_count} documents deleted and index rebuilt", "deleted_count": deleted_count}


async def _rebuild_kb_index(kb_id: int, db: AsyncSession):
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


@router.get("/by_source")
async def get_document_content_by_source(
    kb_id: int,
    source_filename: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document content by source_filename (the stored filename on disk)."""
    # 读权限：public / 本人 / 授权用户
    await ensure_kb_permission(kb_id, current_user, "viewer", db)
    from pathlib import Path

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
        raise HTTPException(status_code=404, detail="Document not found by source filename")

    try:
        raw_docs = load_document(target_doc.file_path)
        content = "\n\n".join(d.page_content for d in raw_docs)
        return {"filename": target_doc.filename, "content": content, "page_count": len(raw_docs)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read document: {exc}")


@router.get("/{doc_id}/content")
async def get_document_content(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full text content of a document for viewer display."""
    # 读权限：public / 本人 / 授权用户
    await ensure_kb_permission(kb_id, current_user, "viewer", db)
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        raw_docs = load_document(doc.file_path)
        content = "\n\n".join(d.page_content for d in raw_docs)
        return {"filename": doc.filename, "content": content, "page_count": len(raw_docs)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read document: {exc}")


class RenameDocumentRequest(BaseModel):
    filename: str

# 重命名文档
@router.put("/{doc_id}/rename", response_model=DocumentResponse)
async def rename_document(
    kb_id: int,
    doc_id: int,
    req: RenameDocumentRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename a document's display name."""
    # 重命名是写操作，仅 owner / admin
    await ensure_kb_permission(kb_id, current_user, "owner", db)
    doc = await db.get(Document, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found")

    if not req.filename.strip():
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    doc.filename = req.filename.strip()
    await db.commit()
    await db.refresh(doc)
    return doc

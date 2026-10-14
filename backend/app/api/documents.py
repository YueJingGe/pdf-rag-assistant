"""Document upload, list, and delete API routes."""

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import User
from app.core.auth import require_user
from app.services import document_service

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
    # 上传是写操作，仅 owner / admin；不存在 404，无权限 403（编排在 document_service）
    content = await file.read()
    doc = await document_service.upload_document(
        db, current_user, kb_id, filename=file.filename or "document", content=content
    )
    return doc


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    kb_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 读权限：public / 本人 / 授权用户（编排在 document_service）
    return await document_service.list_documents(db, current_user, kb_id)


@router.delete("/{doc_id}")
async def delete_document(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 删除是写操作，仅 owner / admin（编排在 document_service）
    await document_service.delete_document(db, current_user, kb_id, doc_id)
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
    # 批量删除是写操作，仅 owner / admin（编排在 document_service）
    deleted_count = await document_service.batch_delete_documents(db, current_user, kb_id, req.doc_ids)
    return {"detail": f"{deleted_count} documents deleted and index rebuilt", "deleted_count": deleted_count}


@router.get("/by_source")
async def get_document_content_by_source(
    kb_id: int,
    source_filename: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get document content by source_filename (the stored filename on disk)."""
    # 读权限：public / 本人 / 授权用户（编排在 document_service）
    return await document_service.get_document_by_source(db, current_user, kb_id, source_filename)


@router.get("/{doc_id}/content")
async def get_document_content(
    kb_id: int,
    doc_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full text content of a document for viewer display."""
    # 读权限：public / 本人 / 授权用户（编排在 document_service）
    return await document_service.get_document_content(db, current_user, kb_id, doc_id)


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
    # 重命名是写操作，仅 owner / admin（编排在 document_service）
    return await document_service.rename_document(db, current_user, kb_id, doc_id, req.filename)

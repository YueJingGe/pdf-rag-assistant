"""Document upload, list, and delete API routes."""

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, Form, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.user import User
from app.core.auth import require_user
from app.services import category_service, document_service

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
    source: str = "upload"
    category_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=DocumentResponse)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    category_id: int | None = Form(None),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    # 上传是写操作，仅 owner / admin；不存在 404，无权限 403（编排在 document_service）
    # P0-4：category_id 可选，上传前挂载到 KB 内目录
    content = await file.read()
    doc = await document_service.upload_document(
        db, current_user, kb_id, filename=file.filename or "document", content=content,
        category_id=category_id,
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


# ---------------- P0-4：在线创作 / 内容保存 / 目录挂载 ----------------

class OnlineDocumentCreateRequest(BaseModel):
    title: str
    content: str = ""
    category_id: int | None = None


@router.post("/online", response_model=DocumentResponse)
async def create_online_document(
    kb_id: int,
    req: OnlineDocumentCreateRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """新建在线文档（P0-4）：content 为真相源，走与上传一致的入库管道（编排在 document_service）。"""
    return await document_service.create_online_document(
        db, current_user, kb_id,
        title=req.title, content=req.content, category_id=req.category_id,
    )


class SaveContentRequest(BaseModel):
    content: str


@router.put("/{doc_id}/content", response_model=DocumentResponse)
async def save_document_content(
    kb_id: int,
    doc_id: int,
    req: SaveContentRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """保存在线文档内容（P0-4）：覆盖 .md + 更新 content 列 + 重建索引；非 ready 状态 409。"""
    return await document_service.save_online_content(
        db, current_user, kb_id, doc_id, content=req.content
    )


class MoveDocumentsRequest(BaseModel):
    document_ids: list[int]
    category_id: int | None = None


@router.post("/move")
async def move_documents(
    kb_id: int,
    req: MoveDocumentsRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """批量移动文档到目录（P0-4；category_id=None 移至根/未归类，编排在 category_service）。"""
    moved = await category_service.move_documents(
        db, current_user, kb_id,
        document_ids=req.document_ids, category_id=req.category_id,
    )
    return {"detail": f"{moved} documents moved", "moved_count": moved}

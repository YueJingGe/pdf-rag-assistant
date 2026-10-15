"""File utility functions."""

import os
import uuid
from pathlib import Path

from app.core.config import settings


def save_upload_file(file_content: bytes, filename: str, knowledge_base_id: int) -> Path:
    """Save uploaded file to the knowledge base's upload directory."""
    kb_dir = settings.upload_dir / str(knowledge_base_id)
    kb_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}_{filename}"
    file_path = kb_dir / unique_name
    file_path.write_bytes(file_content)
    return file_path


def slugify_title(title: str, max_len: int = 80) -> str:
    """标题 → 安全文件名：保留中英文数字与 -_，其余字符替换为 -，超长截断（P0-4）。"""
    chars = [
        ch if (ch.isalnum() or ch in "-_") else "-"
        for ch in title.strip().replace(" ", "-")
    ]
    slug = "".join(chars).strip("-")
    return slug[:max_len] or "untitled"


def save_text_as_md(title: str, text: str, knowledge_base_id: int) -> Path:
    """Save text content as a .md file (for online documents, P0-4)."""
    kb_dir = settings.upload_dir / str(knowledge_base_id)
    kb_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}_{slugify_title(title)}.md"
    file_path = kb_dir / unique_name
    file_path.write_text(text, encoding="utf-8")
    return file_path


def delete_upload_file(file_path: str):
    """Delete an uploaded file from disk."""
    path = Path(file_path)
    if path.exists():
        path.unlink()


def get_file_extension(filename: str) -> str:
    """Extract and normalize file extension."""
    return Path(filename).suffix.lower()


def get_file_size_str(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

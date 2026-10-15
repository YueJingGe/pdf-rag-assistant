"""Category data model — 知识库内目录树节点（P0-4）。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 库隔离：目录仅属于单一知识库
    kb_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("knowledge_bases.id"), nullable=False, index=True
    )
    # 父目录：NULL=根目录；单亲模型，留 M:N 扩展位
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 同级排序（P0 按默认序展示，P1 拖拽排序时启用写路径）
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

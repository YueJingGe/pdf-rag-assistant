"""Authentication and authorization utilities."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import get_db
from app.models.user import User, KnowledgeBasePermission
from app.models.knowledge_base import KnowledgeBase
from app.services.exceptions import NotFoundError, PermissionDeniedError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get current user from JWT token. Returns None if no token."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        user_id: int = int(payload.get("sub", 0))
        if not user_id:
            return None
    except JWTError:
        return None
    user = await db.get(User, user_id)
    if user and not user.is_active:
        return None
    return user


async def require_user(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """Require authenticated user."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    """Require admin user."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


ROLE_LEVELS = {"viewer": 1, "member": 2, "owner": 3}


async def _has_kb_permission(
    kb: KnowledgeBase,
    user: User,
    required_role: str,
    db: AsyncSession,
) -> bool:
    """KB 实体级权限判定（内部共享逻辑，供 has_kb_permission / get_kb_or_raise 复用）。"""
    if user.is_admin:
        return True

    is_owner = kb.user_id is not None and kb.user_id == user.id
    if required_role == "owner":
        return is_owner

    # 存量无主知识库视为公共可读；public 知识库所有登录用户可读
    if kb.user_id is None or kb.permission == "public" or is_owner:
        return True

    # 查询授权表：viewer/member/owner 任一授权角色均满足读权限，仅 owner 满足写
    result = await db.execute(
        select(KnowledgeBasePermission).where(
            KnowledgeBasePermission.user_id == user.id,
            KnowledgeBasePermission.knowledge_base_id == kb.id,
        )
    )
    permission = result.scalar_one_or_none()
    if not permission:
        return False
    return ROLE_LEVELS.get(permission.role, 0) >= ROLE_LEVELS.get(required_role, 1)


async def has_kb_permission(
    kb_id: int,
    user: User,
    required_role: str,
    db: AsyncSession,
) -> bool:
    """判定用户对指定 ID 的知识库是否具备 required_role 级别权限（纯判定，不抛异常）。

    - kb_id 不存在时返回 False；需要区分「不存在 / 无权限」时用 get_kb_or_raise
    - 读权限（viewer/member）= owner || admin || public || 存量无主 || 授权记录达标
    - 写权限（owner）= owner || admin
    """
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        return False
    return await _has_kb_permission(kb, user, required_role, db)


async def get_kb_or_raise(
    kb_id: int,
    user: User,
    required_role: str,
    db: AsyncSession,
) -> KnowledgeBase:
    """加载知识库并校验权限，抛领域异常（service 层统一入口，见 ADR-001 与 P0-2 D1）。

    - 知识库不存在：抛 NotFoundError（404，含防枚举语义）
    - 无所需权限：抛 PermissionDeniedError（403）
    - 通过则返回 KB 实体供调用方复用，不产生重复查询
    """
    kb = await db.get(KnowledgeBase, kb_id)
    if not kb:
        raise NotFoundError("Knowledge base not found")
    if not await _has_kb_permission(kb, user, required_role, db):
        raise PermissionDeniedError("No permission to access this knowledge base")
    return kb


async def ensure_kb_permission(
    knowledge_base_id: int,
    user: User,
    required_role: str,
    db: AsyncSession,
) -> KnowledgeBase:
    """路由层薄封装：语义同 get_kb_or_raise，但抛 HTTPException（404/403）。

    仅供路由层特殊场景使用（不走全局 ServiceError handler 的路径）；
    service 层禁止调用本函数（内部含 HTTPException，见 docs/rules/30-api-conventions.md）。
    """
    try:
        return await get_kb_or_raise(knowledge_base_id, user, required_role, db)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    except PermissionDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission to access this knowledge base",
        )

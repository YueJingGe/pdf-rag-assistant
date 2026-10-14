"""领域异常定义（service 层专用契约）。

约定（见 docs/rules/30-api-conventions.md）：
- service 层只抛本模块异常，禁止直接使用 HTTPException
- main.py 的全局 exception handler 将其统一转换为 HTTP 响应
- 本模块为零依赖纯契约，允许 core/auth.py 引用（分层规则唯一例外）
"""

from __future__ import annotations


class ServiceError(Exception):
    """领域异常基类，默认映射 HTTP 500。"""

    def __init__(self, message: str = "Internal service error"):
        self.message = message
        super().__init__(message)


class NotFoundError(ServiceError):
    """资源不存在，映射 404（含防枚举的「他人私有资源」场景）。"""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class PermissionDeniedError(ServiceError):
    """已登录但无所需权限，映射 403。"""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(message)


class ValidationError(ServiceError):
    """业务校验失败，映射 400。"""

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message)


class ConflictError(ServiceError):
    """资源状态冲突，映射 409（P1 授权管理预留）。"""

    def __init__(self, message: str = "Conflict"):
        super().__init__(message)

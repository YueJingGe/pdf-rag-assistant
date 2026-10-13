# Skill：新增一个 service 函数（add-service）

> P0-2 起业务逻辑统一进 `backend/app/services/`。前置阅读：`docs/rules/10-architecture.md`、`30-api-conventions.md`。

## 文件组织

- 按领域一文件：`kb_service.py` / `chat_service.py` / `document_service.py` / `feedback_service.py`
- 异常统一定义在 `services/exceptions.py`（ServiceError 基类 + NotFoundError / PermissionDeniedError / ValidationError）

## 签名规范（模板）

```python
from sqlalchemy.ext.asyncio import AsyncSession

async def update_kb(
    kb_id: int,                          # ① 入参显式：标量/Pydantic，不传 Request/Response
    payload: KBUpdate,                   # ② DB 会话由调用方传入
    db: AsyncSession,
    current_user: User,                  # ③ 归属校验在 service 内完成（has/ensure_kb_permission）
) -> KnowledgeBase:                      # ④ 返回 ORM 实体或 Pydantic，返回值类型必须标注
    """更新知识库基础信息（写权限仅 owner/admin）。"""
    kb = await ensure_kb_permission(kb_id, current_user, "owner", db)
    ...
    await db.commit()
    return kb
```

## 异常规范

- 只抛 `services/exceptions.py` 的 ServiceError 系列，**禁止 import HTTPException / Request / Response**
- 404/403 语义与路由层一致：不存在 → NotFoundError；无权限 → PermissionDeniedError

## 返回值规范

- 查询类：返回 ORM 实体（路由层 response_model 序列化）或 dict
- 写操作：返回更新后的实体；删除：返回 `None`（204 或 200 + message 由路由定）

## 禁止项

- ❌ 在 service 里解析 HTTP body / 拼 HTTP 响应
- ❌ 在 service 里 print（用 logger）
- ❌ 绕过 has/ensure_kb_permission 自行写归属判断

## 完成后

迁移路由内联逻辑时：路由改为一行调用 → curl 回归受影响端点 → changelog 追加。

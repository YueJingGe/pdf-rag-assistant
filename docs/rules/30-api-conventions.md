# 30 API 接口约定（API Conventions）

## 路由层四件事（只许做这些）

```python
@router.post("", response_model=KBSchema)
async def create_kb(
    payload: KBCreate,                          # ① 参数校验（Pydantic）
    db: AsyncSession = Depends(get_db),         # ② 依赖注入（db / 当前用户）
    current_user: User = Depends(require_user),
) -> KBSchema:
    # ③ 调 service / 简单 CRUD（P0-2 后业务逻辑一律在 service）
    # ④ 组装响应
```

1. **参数校验**：Pydantic schema 声明，路由内不手写 if 校验请求体
2. **依赖注入**：`get_db` + `require_user` / `require_admin`
3. **调用下层**：P0-2 起新增/复杂业务必须先写 service 函数再由路由调用
4. **组装响应**：ORM → Pydantic response_model

## 鉴权挂载（P0-1 硬性成果，不可回退）

- **所有业务端点必须挂 `Depends(require_user)`**，仅 `/api/auth/register`、`/api/auth/login`、`/api/health` 公开
- KB 级权限校验（`core/auth.py` 三层拆分，P0-2 起生效）：
  - `has_kb_permission(kb_id, user, role, db) -> bool`：纯判定、无异常（kb_id 不存在返回 False），适合布尔场景
  - `get_kb_or_raise(kb_id, user, role, db) -> KnowledgeBase`：查询 + 校验，抛**领域异常**（NotFoundError / PermissionDeniedError），**service 层统一调用此函数**
  - `ensure_kb_permission(...)`：薄封装（内部调 get_kb_or_raise，将 ServiceError 转 HTTPException 404/403），**仅供路由层特殊场景**，service 禁止调用
  - 角色约定：读操作 → `"viewer"`；写操作 → `"owner"`
- 验证方式：`http://127.0.0.1:8000/docs` 中业务端点必须全部带锁图标

## 错误语义（安全相关，勿改）

| 场景 | 状态码 | 原因 |
|---|---|---|
| 未登录 / token 失效 | 401 | 前端拦截器统一清 token 弹登录框（登录/注册接口的 401 除外，属业务错误） |
| 知识库不存在 | 404 | kb_id 无对应记录 |
| 知识库存在但无权限（含他人私有库的读/写） | 403 | 权限判定不通过（读需 viewer 级，写需 owner 级） |
| 他人会话（读/删，无论是否存在） | 404 | **防枚举特例**：会话按归属一律 404，不区分“不存在”与“非本人” |

## 异常分层（P0-2 引入，先立规范）

```
services/exceptions.py
├── ServiceError(Exception)          # 基类，映射 500
├── NotFoundError(ServiceError)      # → 404
├── PermissionDeniedError(ServiceError)  # → 403
├── ValidationError(ServiceError)    # → 400
└── ConflictError(ServiceError)      # → 409（P1 授权管理预留）
```

- service **只抛 ServiceError 系列**，不碰 HTTPException；`core/auth.py` 的 `get_kb_or_raise` 同规则（抛领域异常，由全局 handler 转 HTTP）
- `main.py` 注册全局 exception handler 完成 ServiceError → HTTPException 转换（NotFoundError→404 / PermissionDeniedError→403 / ValidationError→400 / ConflictError→409 / 基类兜底→500）
- 过渡期（P0-2 完成 前）路由内 `HTTPException` 允许存在，但新增 service 函数内部禁止使用

## 前端配套

- 后端接口变更 → `api.ts` 同步新增/修改类型与请求函数 → `npx tsc -b` 通过才算完成

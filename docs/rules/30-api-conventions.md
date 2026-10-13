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
- KB 级端点用 `ensure_kb_permission(kb_id, user, role, db)`：
  - 读操作 → `"viewer"`；写操作 → `"owner"`
  - 不存在抛 404、无权限抛 403，通过后返回 KB 供路由复用（避免二次查询）
- 验证方式：`http://127.0.0.1:8000/docs` 中业务端点必须全部带锁图标

## 错误语义（安全相关，勿改）

| 场景 | 状态码 | 原因 |
|---|---|---|
| 未登录 / token 失效 | 401 | 前端拦截器统一清 token 弹登录框（登录/注册接口的 401 除外，属业务错误） |
| 资源不存在（含他人私有资源、他人会话） | 404 | **统一 404 防枚举探测**，不区分"不存在"与"无权知道" |
| 已登录但无权限（资源本身可见） | 403 | 如 viewer 尝试写公共库 |

## 异常分层（P0-2 引入，先立规范）

```
services/exceptions.py
├── ServiceError(Exception)          # 基类，映射 500
├── NotFoundError(ServiceError)      # → 404
├── PermissionDeniedError(ServiceError)  # → 403
└── ValidationError(ServiceError)    # → 400
```

- service **只抛 ServiceError 系列**，不碰 HTTPException
- `main.py` 注册全局 exception handler 完成 ServiceError → HTTPException 转换
- 过渡期（P0-2 完成 前）路由内 `HTTPException` 允许存在，但新增 service 函数内部禁止使用

## 前端配套

- 后端接口变更 → `api.ts` 同步新增/修改类型与请求函数 → `npx tsc -b` 通过才算完成

# P0-2 service 层抽取 + 异常分层

> 状态：**已确认**（2026-10-13 用户确认；D2/D3/D4/D5 按默认提案，D1/D6 按用户修正执行，见 §9）
> 约束声明：纯重构，本需求不触碰 RAG 禁区文件（loader/splitter/retrieval/vector_store/rag_chain）

## 1. 背景

- P0-1 已完成鉴权强制执行 + 数据归属：29 个端点全部挂载鉴权，`has_kb_permission` / `ensure_kb_permission` / `_get_own_conversation` 构成归属校验体系（见 ADR-001）
- **现状问题**：业务逻辑全部内联在 `app/api/*.py` 路由函数中（knowledge_bases 5 端点 / documents 7 端点 / chat 6 端点 / feedback 3 端点），路由既做 HTTP 层（参数校验、依赖注入、异常转换、SSE 组装）又做业务层（数据库操作、可见性过滤、会话管理）。这属于 P0-1 之前的过渡态，`docs/rules/10-architecture.md` 已声明新代码不得再往路由堆业务逻辑
- **为什么现在做**：P0-3（LLM 网关 + Agent 工具调用循环）的每个 Function Calling 工具，本质是"可被独立调用的业务函数"。不先抽 service 层，Agent 工具只能回调自身 HTTP 接口（自耦合 + 鉴权绕行 + 无事务边界）。P0-2 是 P0-3 的地基

## 2. 目标

1. 把业务逻辑从路由层下沉到 `app/services/`，路由回归薄层（参数校验 + 依赖注入 + 调 service + 组装响应）
2. 形成可被 Agent 工具直接调用的独立函数（工具友好签名）
3. **纯重构，行为零变化**——不新增功能、不改 API 路径、不改请求/响应结构、不改鉴权逻辑

## 3. 抽取范围

新建 `backend/app/services/` 目录：

| 文件 | 职责 | 承接自 |
|---|---|---|
| `exceptions.py` | 领域异常：`ServiceError`（基类）/ `NotFoundError` / `PermissionDeniedError` / `ValidationError` / `ConflictError` | 新增 |
| `kb_service.py` | 知识库 CRUD、可见性过滤（or_ 查询）、权限校验编排 | api/knowledge_bases.py（5 端点） |
| `document_service.py` | 文档上传、解析调度、删除（含 FAISS 索引与文件清理编排）、批量操作、重命名 | api/documents.py（7 端点） |
| `chat_service.py` | 会话创建、历史管理、消息持久化、会话归属校验（承接 `_get_own_conversation`） | api/chat.py（6 端点） |
| `retrieval_service.py` | 封装混合检索调用：包装 `rag_chain` 的检索入口，**不重写检索逻辑** | api/chat.py 内检索编排段 |
| `feedback_service.py` | 反馈创建、统计、导出 | api/feedback.py（3 端点） |
| `__init__.py` | 空 | 新增 |

**不在抽取范围**：`api/auth.py`（认证本身就是核心设施，无业务逻辑可抽）；`main.py`（仅新增 exception handler 注册）。

## 4. 明确不做的（本步严禁）

- ❌ 不改 `loader.py / splitter.py / retrieval.py / vector_store.py / rag_chain.py`（RAG 核心链路零改动，git diff 中不得出现）
- ❌ 不改任何 API 路径、请求体、响应体结构
- ❌ 不改 P0-1 的鉴权依赖注入——`Depends(require_user)` 保留在路由层；权限函数留在 `core/auth.py`；service 层仅调用 `has_kb_permission`（纯判定）和 `get_kb_or_raise`（抛领域异常），**禁止调用 `ensure_kb_permission`**（含 HTTPException，仅路由层特殊场景使用）。详见 §9 D1
- ❌ 不引入任何新依赖
- ❌ 不做工具注册表、不做 LLM 网关（P0-3 再做）
- ❌ 不做异步任务队列、不做缓存改造

## 5. Service 设计规范

（对齐 `docs/rules/30-api-conventions.md` 与 `.claude/skills/add-service.md`）

1. **工具友好签名**：不接收 `Request` / `Depends` / `BackgroundTasks` / `Response` 等 HTTP 层对象；只接收 `db: AsyncSession`、`user`（或 `user_id`）、原始类型参数、Pydantic schema
2. **返回值**：ORM 对象、Pydantic 对象、或结构化 dict；**不返回 `JSONResponse` / `StreamingResponse`**
3. **异常分层**：service 只抛 `exceptions.py` 的领域异常，**不抛 `HTTPException`**；路由层负责转 HTTP。推荐在 `main.py` 注册统一 exception handler（`ServiceError` 及子类 → 对应 HTTPException），避免每个路由写 try/except
4. **粒度**：模块级 async 函数即可，服务规模小时不强制 class
5. **归属校验**：service 内通过 `get_kb_or_raise`（core/auth.py，抛领域异常）与 `chat_service.get_own_conversation` 完成归属判断，禁止路由层与 service 各查一遍；**service 禁止调用 `ensure_kb_permission`**（它内部含 HTTPException，仅供路由层）

### 异常 → HTTP 映射（exception handler 统一转换）

| 领域异常 | HTTP |
|---|---|
| `NotFoundError` | 404 |
| `PermissionDeniedError` | 403 |
| `ValidationError` | 400 |
| `ConflictError` | 409 |
| `ServiceError`（基类兜底） | 500 |

404 防枚举语义不变（他人会话/他人私有库仍是 404）。

## 6. 为 P0-3 预留的接口

`retrieval_service.py` 必须暴露纯检索函数（Agent 工具将直接调用它）：

```python
async def search(kb_id: int, query: str, top_k: int = 5) -> list[dict]:
    """返回 [{content, source, page, score}, ...]，不生成回答。"""
```

P0-2 只做"封装与转发 + 归属校验编排"，检索算法本体留在禁区文件内。

## 7. 任务分解（实施轮次，每轮独立回归）

| 轮次 | 内容 | 回归重点 |
|---|---|---|
| 第 1 轮 | `exceptions.py` + 全局 handler + **core/auth.py 权限函数拆分（D1 修正）** + `retrieval_service.py`（提前，D6 修正：chat 的 RAG 链路依赖它，避免临时内联） + `kb_service.py` + knowledge_bases.py 路由切换 | 权限矩阵全跑（verify-change.md 第 4 节）+ search() 冒烟 |
| 第 2 轮 | `document_service.py` + documents.py 切换；`chat_service.py` + chat.py 切换（含 `_get_own_conversation` 下沉为 `get_own_conversation`） | 上传/删除/会话隔离 404 语义 |
| 第 3 轮 | `feedback_service.py` + feedback.py 切换 + 收尾（文档同步） | 反馈端点回归 + 全量权限矩阵终验 |

## 8. 验收标准

1. **行为零变化**：抽取前后导出 openapi.json，路径/方法/响应 schema 集合一致；curl 抽查各路由文件主路径响应体逐字段一致
2. 路由数量不变（29），锁图标数量不变（22）
3. `git diff --stat` 中**不出现**禁区 5 文件
4. `grep -r "HTTPException\|Request\|Response" backend/app/services/` 无业务命中（exceptions.py 的 handler 注册除外，位于 main.py）
5. 权限矩阵回归（verify-change.md 第 4 节）全绿；会话隔离 404、越权 403 语义不回退
6. `py_compile` + `tsc -b` 通过；前端预期零改动（api.ts 不动）
7. SSE 流式问答端到端可用（流式输出 + 引用溯源正常）
8. `scripts/smoke_test_services.py` 可执行：不经过 HTTP 层，直接 `from app.services.retrieval_service import search`，构造 db session 调用，返回结构化数据。作为 P0-3 Agent 工具的预演
9. P0-1 五项验收回归通过：①未登录 401 ②越权 403 ③会话隔离 404 ④存量数据归属完好 ⑤22 个业务端点 Swagger 锁图标不减少

## 9. 边界决策（已确认：2026-10-13）

> 确认结果：D2/D3/D4/D5 按默认提案；**D1/D6 按用户修正执行**（下表为修正后内容）。

| # | 决策点 | 最终方案 |
|---|---|---|
| D1 | 权限函数拆分（用户修正） | **core/auth.py 三层拆分**：①`has_kb_permission(kb_id, user, role, db) -> bool` 纯判定、无异常（kb_id 不存在时返回 False）；②`get_kb_or_raise(kb_id, user, role, db) -> KnowledgeBase` 查询+校验，抛领域异常（NotFoundError / PermissionDeniedError），**service 层统一调用此函数**；③`ensure_kb_permission(...)` 保留为薄封装，内部调 get_kb_or_raise 并将 ServiceError 转 HTTPException(404/403)，仅供路由层特殊场景。get_kb_or_raise 抛的领域异常由全局 exception handler 统一转 HTTP |
| D2 | `_get_own_conversation` | 下沉为 `chat_service.get_own_conversation`，404 防枚举语义不变（已确认） |
| D3 | SSE 端点拆分边界 | 检索编排/会话管理/消息持久化进 service；SSE 生成器与事件格式组装留在路由层（已确认） |
| D4 | `ConflictError` 映射 | 409（为 P1 授权管理预留）（已确认） |
| D5 | service 函数粒度 | 模块级 async 函数，不建 class（已确认） |
| D6 | 实施顺序（用户修正） | 第 1 轮 exceptions + retrieval_service + kb_service；第 2 轮 documents + chat；第 3 轮 feedback（retrieval 提前，避免 chat 轮次出现空 service 依赖或临时内联），每轮结束单独回归并追加 changelog |

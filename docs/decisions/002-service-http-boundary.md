# ADR-002：Service 层与 HTTP 层的边界

- **编号**：002
- **日期**：2026-10-14
- **状态**：已采纳（随 P0-2 三轮落地并全量终验）
- **关联**：docs/requirements/P0-2-service-layer.md（§4 规范、§9 决策 D1/D3）、docs/decisions/001-service-layer-exception.md（前置演进）、docs/changelog/P0-2-service-layer.md（实施证据）

## 背景

P0-2 把业务逻辑从 api/*.py 路由函数下沉到 services/ 层（kb / retrieval / document / chat / feedback 五个模块）。下沉过程中有三个问题必须给出明确答案，否则后续每加一个端点都要重新争论一次：

1. **权限校验放哪**：ADR-001 的 `has_kb_permission` / `ensure_kb_permission` 都在 core 层，service 层能直接用哪个？（ensure 抛 HTTPException，会污染 service 纯度）
2. **SSE 流式端点怎么拆**：chat/stream 的事件组装（token/citations/retrieval_debug/done）是"协议细节"还是"业务逻辑"？
3. **分层依赖方向**：service 需要抛"领域异常"，而异常到 HTTP 状态码的转换注册在 main.py——core→services 反向 import 是否允许？

## 决策

四条边界规则（未来重构 service 层时必须维持）：

### 规则 1：权限函数三层拆分（D1 演进版）

```python
# core/auth.py 三层，各司其职：
_has_kb_permission(kb, user, role, db)   # 内部共享：KB 实体级判定
has_kb_permission(kb_id, ...) -> bool     # 纯判定：不抛异常（批量预检/展示判定用）
get_kb_or_raise(kb_id, ...) -> KB         # service 层统一入口：抛领域异常（NotFound/PermissionDenied）
ensure_kb_permission(...) -> KB           # 薄封装转 HTTPException：仅供路由层，service 禁止调用
```

### 规则 2：service 只抛领域异常，HTTP 转换集中在 main.py 全局 handler

service 层只 `raise services.exceptions.ServiceError` 系列（NotFound→404 / PermissionDenied→403 / Validation→400 / Conflict→409 / 基类→500），响应体保持 `{"detail": ...}`。**service 内禁止出现 HTTPException / fastapi 任何符号**（审计口径见 P0-2 验收第 4 条）。

### 规则 3：任何 `except Exception` 兜底前必须先透传领域异常

```python
try:
    ...
except (NotFoundError, PermissionDeniedError, ValidationError, ConflictError):
    raise  # 领域异常透传，保持 404/403 语义
except Exception as exc:
    raise ServiceError(...)  # 其余包装为 500
```

否则兜底会把 404/403 吞成 500（P0-2 第 2 轮修正 2 实证过的坑）。

### 规则 4：SSE 生成器留路由层（D3）

`chat/stream` 的 event_generator 与事件组装格式（conversation/token/citations/retrieval_debug/done）留在路由层；权限校验、会话获取/创建、历史加载、消息持久化下沉 chat_service（prepare_chat / save_user_message / save_assistant_message 三函数）。同理 `/api/chat/upload-file` 保留路由层（纯外呼编排 + 502 语义不在领域异常体系，见 changelog 第 2 轮例外登记）。

## 理由

- service 函数必须能**不经 HTTP 层直接调用**（P0-3 Agent 工具基座的硬前提，smoke_test_services.py 即预演）；HTTPException/fastapi 符号进 service 会把这个前提破坏掉
- 领域异常 + 全局 handler 让"错误语义"只有一处实现；路由层函数因此能压到 ≤15 行（AST 统计脚本验收）
- SSE 事件格式是前后端契约（前端 useSSE 按事件名分发），放 service 会让 service 承担协议序列化职责，且 EventSourceResponse 本身就是 HTTP 概念

## 影响

- ✅ 正面：五个 api 文件全部薄路由化（feedback.py 123→82 行等）；service 可独立测试；错误码语义单点维护
- ✅ 正面：`services.exceptions` 是 core→services 反向 import 的**唯一例外**（零依赖纯契约，10-architecture.md 已登记条款）
- ⚠️ 注意：新增端点时按"路由 ≤15 行 + service 无 HTTP 符号"自查；SSE 类端点参考 chat/stream 的拆分模板
- ⚠️ 注意：行数豁免清单（auth 两个函数不在抽取范围、chat_stream/upload_file 例外）见 P0-2 changelog 第 3 轮终验记录

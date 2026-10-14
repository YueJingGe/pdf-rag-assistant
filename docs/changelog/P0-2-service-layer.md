# P0-2 Changelog：service 层抽取 + 异常分层

> 规则：一任务一文件、时间倒序追加（见 docs/rules/90-workflow.md）

---

## 2026-10-13 · 第 1 轮：异常分层 + 权限三层拆分（D1）+ retrieval/kb service + kb 路由切换

- **改动摘要**：建立 `app/services/` 层——领域异常 + 全局 handler；core/auth.py 权限函数按 D1 三层拆分；新建 retrieval_service（P0-3 工具预演入口 `search`）与 kb_service；knowledge_bases.py 5 端点全部切换为薄路由（170 行 → 101 行）；新增 service 层冒烟脚本
- **diff 摘要**：
  - `backend/app/services/exceptions.py`（新建，+45）：ServiceError 基类 + NotFound/PermissionDenied/Validation/Conflict 四子类
  - `backend/app/services/__init__.py`（新建）
  - `backend/app/core/auth.py`（+48/-15）：原 `has_kb_permission`（KB 对象版）→ 内部 `_has_kb_permission`；新增公开 `has_kb_permission(kb_id, ...)`（纯判定，kb_id 不存在返回 False）、`get_kb_or_raise(kb_id, ...)`（抛领域异常，service 统一入口）；`ensure_kb_permission` 改为薄封装（调 get_kb_or_raise，ServiceError→HTTPException 404/403），签名与对外行为不变，documents/chat/feedback 无需改动
  - `backend/app/services/retrieval_service.py`（新建，+45）：`search(kb_id, query, top_k=5, *, db, user)`——先 get_kb_or_raise 校验 viewer 读权限，再转发 `rag_chain.retrieve_with_strategy`（禁区文件零改动），返回 `[{content, source, page, score}]`
  - `backend/app/services/kb_service.py`（新建，+114）：create_kb / list_visible_kbs / get_kb_detail / update_kb / delete_kb，可见性 or_ 过滤与 ready 文档计数原样下沉
  - `backend/app/api/knowledge_bases.py`（+16/-85）：5 端点全部改为一行 service 调用 + 响应组装；移除 ensure_kb_permission / vector_store_manager / ORM 查询 import
  - `backend/app/main.py`（+28/-1）：注册 `@app.exception_handler(ServiceError)`，isinstance 链映射 404/403/400/409/500，响应体保持 `{"detail": ...}` 格式
  - `scripts/smoke_test_services.py`（新建，+71）：验收第 8 条，不经 HTTP 层直接调用 service
  - `docs/rules/10-architecture.md`：分层表补 services.exceptions 唯一例外条款；现状声明更新（services 已建立）
  - `docs/rules/30-api-conventions.md` + `.claude/skills/verify-change.md`：错误语义表/权限矩阵与实测对齐修正（KB 存在但无权限=403，仅会话走 404 防枚举——搭规范时的笔误，本轮 curl 实证后修正）
- **验收结果**：
  - `python3 -m py_compile` 全部通过；`from app.main import app` 加载 29 路由（数量不变 ✓）
  - 禁区核查：`git diff --stat` 中 loader/splitter/retrieval/vector_store/rag_chain 零出现 ✓
  - 分层纪律：`grep "HTTPException|fastapi|Request|Response" app/services/` 仅命中 2 处注释文字，无代码引用 ✓
  - 后端重启成功（/api/health 200，启动日志无 ERROR）✓
  - 验收⑤：openapi.json 带锁端点 22/25，与 P0-1 一致 ✓
  - 验收①：无 token GET /api/knowledge_bases → 401 ✓
  - 验收④：owner 账号（18838166792）可见 3 KB（金融/司库奇尤单抗注射液说明书/通信，各 1 篇 ready），存量归属完好 ✓
  - CRUD 主路径（走新 service 链路）：create kb_id=4 → get → put 改名 → 响应体字段逐项一致 ✓（临时库已删，清理复核 0 条）
  - 验收②：testuser_a GET/PUT/DELETE 他人私有库 kb_1 → 全部 403 ✓
  - 不存在：GET kb_999999 → 404 ✓
  - 验收③：testuser_a GET 他人会话 → 404（防枚举语义不回退）✓
  - 验收⑧：`python3 scripts/smoke_test_services.py 18838166792` —— list_visible_kbs 返回 3 库；`retrieval_service.search` 返回 2 个结构化片段（content/source/page/score 齐全）；不存在 kb_id 抛 NotFoundError ✓（P0-3 Agent 工具预演跑通）
  - 验收⑨（P0-1 五项）：①401 ②403 ③404 ④存量归属 ⑤22 锁图标——本轮全部复验通过 ✓
  - 验收⑥：tsc -b 无需跑（前端零改动）；api.ts 未动 ✓
  - 验收⑦：SSE 全路径属第 2 轮 chat_service 范围，本轮未触碰 chat 链路（ensure 行为不变，风险已覆盖）
- **遗留事项**：
  - 第 2 轮待做：document_service + documents.py 切换；chat_service + chat.py 切换（get_own_conversation 下沉）
  - 第 3 轮待做：feedback_service + feedback.py 切换 + 全量终验 + 文档同步（README/重难点）
  - tsc -b 将在第 3 轮收尾统一执行（本轮前端零改动）

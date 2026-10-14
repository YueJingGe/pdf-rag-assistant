# P0-2 Changelog：service 层抽取 + 异常分层

> 规则：一任务一文件、时间倒序追加（见 docs/rules/90-workflow.md）

---

## 2026-10-14 · 第 3 轮（收尾）：feedback_service + /feedback 权限补齐 + 全量终验 + 文档同步

### 3a 纯重构（零行为变化）

- **改动摘要**：feedback.py 3 端点切薄（123 → 82 行）；`feedback_service.py` 新建（create/get_stats/export）；冒烟脚本追加 ⑧ 段（临时库反馈全链路 + admin 内存标记验证导出）
- **回归证据**：A POST 自己库 200 / 未登录 401 / stats 计数与 rate 逐字段一致 / B stats 403 / A（owner 非 admin）export 403「Admin required」/ 不存在 kb 404 detail 原样；冒烟 ⑧ 全绿（含 admin 绕过 owner 判定验证，is_admin 复核全部还原为 0）
- **路由行数修正**：`create_feedback` 初版 16 行超限，参数合并压缩至 13 行（AST 统计通过）；终验额外项还发现首版统计脚本装饰器判断错误导致假阴性，修正后真实统计 24 个路由函数

### 3b 安全修复（P0-1 遗留，经用户确认的例外；单独提交）

- **问题**：`POST /api/feedback` 只校验登录、不校验 KB 权限——任何登录用户可对他人私有库写入反馈（污染 reranker 训练集）。git 考古确认 f575eba 基线即如此
- **修复**：`feedback_service.create_feedback` 前置 `get_kb_or_raise(kb_id, user, "viewer", db)`
- **回归证据**：B 对 A 私有库 POST → 403（修复前 200）；不存在 kb → 404；本人 → 200；测试脏数据（含修复前误写的越权行）已用 sqlite 清理并复核 0 残留

### 全量终验（9+2 项，一次性，真命令真输出）

| # | 项 | 结果 |
|---|---|---|
| 1 | openapi 模型类零改动 + paths 集合与基线一致（21 条） | ✅ |
| 2 | 路由 29 不变 / 带锁端点 22/25 不变 | ✅ |
| 3 | 禁区 5 文件累计 diff（4187ac4→HEAD）为空 | ✅ |
| 4 | services 无 HTTP 符号（仅 exceptions.py 文档注释命中） | ✅ |
| 5 | 权限矩阵 401/403/404 核心链回归 | ✅ |
| 6 | py_compile 全量 + 前端零改动 + tsc exit=0 | ✅ |
| 7 | SSE 端到端 conversation→retrieval_debug→token×40→citations→done | ✅ |
| 8 | 冒烟 8 段全用例（kb/retrieval/document/chat/feedback） | ✅ |
| 9 | P0-1 五项（401/登录路由/存量 3 库/CRUD/403） | ✅ |
| 额外1 | 路由函数 ≤15 行（AST 统计 24 函数；豁免：auth×2 不在抽取范围、chat_stream D3 钦点、upload_file 已登记例外） | ✅ |
| 额外2 | services import 审计同第 4 项 | ✅ |

### 文档同步

- README：核心亮点补「Service 分层」；目录结构补 services/ 六模块与 smoke 脚本
- 重难点以及遇到的问题.md：新增「九、Service 层抽取改造」章节（动机/边界规则/4 个坑/终验方式）
- AGENTS.md + 00-project-context：P0-2 ✅ 完成，P0-3 待启动（标注 service 层已就绪）
- 10-architecture：现状声明更新为全部完成态（含 upload-file/auth 例外）
- 新增 ADR-002（docs/decisions/002-service-http-boundary.md）：Service/HTTP 边界四条规则；ADR-003（双 commit 策略）经评估不写——一次性流程决策，changelog 分节已足够

### P0-2 整体收尾摘要（三轮累计）

- **services/ 六模块**：exceptions / kb_service / retrieval_service / document_service / chat_service / feedback_service
- **四个路由文件切薄**：knowledge_bases 170→101、documents 279→125、chat 317→220、feedback 123→82
- **禁区零改动**：loader/splitter/retrieval/vector_store/rag_chain 累计 diff 为空（4187ac4→HEAD）
- **安全修复 2 处**（均独立 commit）：/api/chat/query 会话归属校验、POST /api/feedback KB 读权限
- **关键决策**：D1-D6 全部落地；ADR-002 沉淀边界规则
- **遗留（登记不处理）**：delete_kb 空目录残留；B 双禁区场景 403 先于 404（与原顺序一致）
- **commit 链**：4187ac4（需求基线）→ ad93187（第 1 轮）→ 028f81a（第 2 轮重构）→ db965ab（第 2 轮安全修复）→ 本轮

## 2026-10-14 · 第 2 轮：document_service + chat_service + documents/chat 路由切换

### 2a 纯重构（严格零行为变化）

- **改动摘要**：documents.py 7 端点、chat.py 6 端点中 5 个切薄；`_rebuild_kb_index` 编排下沉 document_service；`_get_own_conversation` 下沉为 `chat_service.get_own_conversation`（D2，404 防枚举语义不变）；SSE 生成器与事件组装（token/citations/retrieval_debug/done）按 D3 留在路由层
- **diff 摘要**：
  - `backend/app/services/document_service.py`（新建，+219）：upload_document（签名 `(db, user, kb_id, *, filename, content)`，bytes 传参，UploadFile 读取留路由）/ list / delete / batch_delete / get_by_source / get_content / rename + 内部 `_rebuild_kb_index`（load/split/vector_store.rebuild_index + semantic_cache.invalidate，`except: pass` 容错原样）
  - `backend/app/services/chat_service.py`（新建，+190）：prepare_chat（权限+会话获取/创建+近 10 条历史）/ save_user_message / save_assistant_message / get_own_conversation / list_conversations / get_messages / delete_conversation / query_rag
  - `backend/app/api/documents.py`（279 → 125 行）：7 端点一行 service 调用；移除 Document/select/loader/splitter/vector_store/file_utils/ensure/HTTPException import
  - `backend/app/api/chat.py`（317 → 220 行）：5 端点切薄；SSE 生成器原样保留；`/upload-file` 不下沉（例外，见下）
  - `scripts/smoke_test_services.py`（+65）：追加 ⑤document 全链路冒烟（临时库上传→检索→改名→清理）⑥chat 会话生命周期 ⑦404 防枚举（他人会话/不存在 id 兜底）
- **例外登记（经用户确认）**：`POST /api/chat/upload-file` **不下沉 service**，保留路由层——理由：纯外呼编排（智谱文件抽取，无 DB/归属概念），且 502 网关错误语义不在领域异常体系（400/403/404/409/500），强行下沉会把 502 变 500，违反行为零变化。P0-3 检索此决策时以本条为依据
- **修正 3 验证（OCR 分支）**：loader 依赖检查——`load_document(file_path)` 仅收磁盘路径，`save_upload_file` 本就收 bytes，改造不影响 loader 行为；构造无文本层图像 PDF 实测：上传 → PyPDFLoader 空文本 → `_ocr_pdf`（tesseract chi_sim+eng）→ status=ready 1 chunk（4.5s）→ OCR 内容可检索命中 ✓
- **回归证据（全绿）**：
  - document：文本 PDF 上传 ready 16 chunks → 检索 4 citations → B 越权 list 403 → rename/by_source/content 正常 → 删除后索引收缩（空库 rebuild 不崩、无命中）→ 非法扩展名 400 detail 原样 → 不存在文档 404 detail 原样
  - chat/SSE：RAG 流 `conversation → retrieval_debug → 75×token → citations(4) → done` 事件序列完整；新会话自动创建；续聊历史加载（复述上轮问题）；消息持久化 4 条 + citations 落库；plain chat（kb=0）conversation→token→done 正常
  - 会话隔离：B 读/删 A 会话 → 404（防枚举）；B 在 A 会话续聊 → 403（KB 权限校验先行，与原代码顺序一致）；B stream A 私有库 → 403；A 删本人会话 → 200 且级联删消息（再读 404）
  - 分层纪律：禁区 5 文件 diff 空；services/ 无 HTTPException/fastapi/Depends 代码引用；无 ensure_kb_permission 调用
  - 冒烟：`smoke_test_services.py` ⑦段完整通过（upload ready 1 chunk → 检索命中 → rename → 临时库清理；会话创建/归属/删除；404 防枚举）
  - P0-1 五项：401 ✓ / 登录路由可达 ✓ / 存量 3 库 ✓ / CRUD 主路径（本轮全覆盖）✓ / 越权 403 ✓；openapi 带锁端点 22/25 与前两轮一致 ✓；前端零改动（git diff 空）

### 2b 安全修复（P0-1 遗留，经用户确认的例外，区别于重构；单独提交）

- **问题**：`POST /api/chat/query` 中 `req.conversation_id` 直接加载历史，未校验会话归属（stream 端点有校验、query 没有）——B 可用 A 的 conversation_id 把 A 的对话历史注入自己的查询上下文
- **修复**：`chat_service.query_rag` 在 conversation_id 分支前置 `get_own_conversation`（不存在/他人会话一律 404 防枚举）；同一函数内 `try/except` 先透传领域异常（保持 404/403）再包装其余异常为 ServiceError（修正 2，防止校验异常被吞成 500）
- **回归证据**：A 用不存在会话 query → 404；A 本人会话 query → 200；B（对 public 库有读权限）用 A 会话 query → 404（修复前会静默使用 A 的历史；private 库场景 B 先被 403 拦截，与错误语义矩阵一致）；临时库/会话已清理

### 本轮遗留事项

- `delete_kb` 删除库后 `data/uploads/{kb_id}/` 空目录残留（文件已清理，目录保留）——既有行为非本轮引入，登记待后续小轮处理
- B 同时触碰他人私有库+他人会话时 403 先于 404（权限校验顺序与原代码一致，非回退）
- 第 3 轮待做：feedback_service + feedback.py 切换 + 全量终验 + 文档同步（README/重难点）

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

# P0-3a Agent 工具基座（意图识别 + Function Calling + 工具调用循环）

> 状态：**已确认**（2026-10-14 用户 review 通过：deep_qa 砍除 + 老端点回归口径明确化 + §12 增加白名单审计第 14 条 + §13 决策留痕规则；第 1 轮已实施，见 changelog；第 3 轮前用户拍板修订：§12.4 扩为 12 用例（+2 plain）、§8 补"轮次 vs 单轮 tool_calls 数"语义）
> 约束声明：本需求不触碰 RAG 禁区文件（loader/splitter/retrieval/vector_store/rag_chain），零新依赖

## 1. 背景

- P0-2 已完成 service 层抽取：6 个 service 模块、17 个公开函数全部符合工具友好签名（db/user/原始类型/Pydantic），`retrieval_service.search()` 已通过冒烟验证可脱离 HTTP 独立调用——Agent 工具基座的地基已就绪
- **现状缺口**：系统只有固定链路（RAG 问答 / 普通聊天），无法响应"算一下 (3+5)*12/2"、"现在几点"这类非检索问题，也不具备"多步工具协作"能力
- **为什么拆 3a/3b**：P0-3 原始范围包含"LLM 网关统一 + Agent 工具基座"两类改动，前者要动禁区 `rag_chain.py`（严格说理 + RAGAS 回归），后者只依赖 service 层（低风险）。混在一轮会让"禁区改动需严格说理"的约束失去意义，故拆分：**3a = 工具基座（零禁区改动）**；3b = LLM 网关统一（独立任务，走禁区改动流程，前置需求见 §14）

## 2. 目标

1. 新建 `services/agent_service.py`：意图分类 + 工具注册表 + bind_tools 手写循环
2. 新增端点 `POST /api/chat/agent/stream`（SSE），不动现有 `/api/chat/stream`
3. 工具集：service 只读工具 4 个 + 外部工具 3 个，共 **7 个**（见 §6）
4. 附带项：admin 机制（`ADMIN_USERNAMES` 配置化，解决 P0-2 演示环境无 admin 遗留）
5. 前端最小改造：工具调用日志面板（最小展示，完整可视化归 P1）

## 3. 范围

**做**：意图识别（3 分类：rag/tool/plain）+ 只读工具包装 + calculator/current_time/simulate_order_query + Agent SSE 端点 + 可观测日志 + admin 附带项 + 前端最小日志面板 + 冒烟 ⑨ 段。

**明确不做（本步严禁）**：

- ❌ **不做写操作工具**：create_kb / upload_document / delete_* / rename / export_feedback 一律不暴露（Agent 自动写数据需"人工确认"机制，属产品设计问题，3a 不引入）
- ❌ **不做 RAG 接管**：RAG 类问题继续走现有 `rag_stream` 全链路（引用溯源/语义缓存/HyDE 保全），Agent 不复用 rag_stream/hybrid_retrieve，需要知识库内容时调 `search` 工具（retrieval_service 只读转发，P0-2 已验证的合法依赖方向）
- ❌ **不做 LLM 网关统一**（P0-3b 独立任务，见 §14）
- ❌ 不改禁区 5 文件；不改现有 `/api/chat/stream` 端点行为；不引入新依赖（langgraph/bind_tools 均由现有 langchain-core 0.3.12 提供）
- ❌ 不做 prompt 模板管理机制（当前仅分类/Agent 两个 prompt，模块常量即可；P1 工具增多再演进）
- ❌ 不做多 Agent / 图谱编排（P2）

## 4. 关键约束（按优先级排序）

1. **【头号安全约束】工具身份只从 contextvar 注入，禁止任何身份参数走 LLM**：
   - 工具函数签名**禁止接收 `user_id` / `db` 参数**（含 schema 定义——LLM 可见的参数 schema 中同样不得出现）
   - `db: AsyncSession` + `user: User` 由路由层 SSE 生成器（HTTP 鉴权上下文已建立处）通过 `contextvars.ContextVar` 注入，工具包装层统一从 contextvar 取
   - 这是 Agent 路径**不能绕过 P0-1 权限体系的唯一保险**：若允许 LLM 传 user_id，B 可伪造身份访问 A 的私有库，P0-1 的 403/404 防线对 Agent 路径全部失效
2. **禁区零改动**：`git diff` 中不得出现 loader.py / splitter.py / retrieval.py / vector_store.py / rag_chain.py
3. **零新依赖**：工具协议用现有 langchain-core 的 `StructuredTool` + `bind_tools`；`contextvars` 为 Python 标准库
4. **分层纪律延续 P0-2**：agent_service 不 import 任何 fastapi HTTP 符号（Request/Response/HTTPException/Depends）；不 import 禁区私有函数（`_get_llm`/`_get_chat_llm`）；路由 ≤15 行；service 只抛领域异常
5. **老端点零回归**：`/api/chat/stream` 的事件序列、行为、权限语义逐字节不变

## 5. 架构设计

### 5.1 模块结构（新建文件）

| 文件 | 职责 |
|---|---|
| `services/agent_service.py` | contextvar 定义 + 模型工厂 `_get_agent_llm()`（读 `settings.AGENT_MODEL`/`AGENT_MODEL_BASE_URL`/`AGENT_MODEL_API_KEY`，可配置，默认 DeepSeek）+ `classify_intent()` + 工具包装工厂 `_wrap_service_tool()` + 工具注册表 `AGENT_TOOLS` + `run_agent_loop()`（async generator，产出事件） |
| `api/chat.py` 追加 | 仅 `POST /agent/stream` 端点（≤15 行）：require_user + contextvar set + 调 `run_agent_loop` + SSE 组装（沿用 D3 边界：生成器与事件组装留路由） |
| `core/config.py` 追加 | `AGENT_MODEL` / `ADMIN_USERNAMES`（逗号分隔）等配置项（config.py 非禁区） |
| `main.py` 追加 | 启动钩子：按 `ADMIN_USERNAMES` 升权（仅升不降，见 §10） |
| 前端 | `api.ts` 新事件类型 + `ChatWindow` 处理 3 个新事件 + 最小日志面板组件 |

### 5.2 contextvar 方案（安全约束 1 的实现）

```python
# services/agent_service.py
_agent_db = ContextVar("agent_db", default=None)    # AsyncSession
_agent_user = ContextVar("agent_user", default=None)  # User（鉴权后的 current_user）

def _wrap_service_tool(name, description, args_model, coro) -> StructuredTool:
    async def _run(**kwargs):  # LLM 只见 kwargs 中的业务参数
        return await coro(_agent_db.get(), _agent_user.get(), **kwargs)
    return StructuredTool(name=name, description=description, args_schema=args_model, coroutine=_run)
```

路由层 SSE 生成器内 `token = _agent_db.set(db); _agent_user.set(current_user)`，finally 中 reset。

### 5.3 SSE 事件协议（新增事件，老事件不变）

| 事件 | data | 说明 |
|---|---|---|
| `intent` | `{"intent": "rag"|"tool"|"plain"}` | 分类结果，首个事件 |
| `tool_call` | `{"name", "args_summary"}` | 工具开始执行 |
| `tool_result` | `{"name", "status", "duration_ms", "result_summary"}` | 工具结束（result_summary 截断） |
| `token` | 现有格式 | Agent 最终回答流式输出 |
| `done` | 现有格式 | 结束 |

### 5.4 Agent 模型策略

需求层面**可配置**（`settings.AGENT_MODEL`，默认押 DeepSeek）；实施首日双模型（DeepSeek / 智谱）各跑 10 次工具调用冒烟，对比 function calling 成功率与参数解析质量后定默认值，结论写入 changelog。

## 6. 工具清单

| 工具名 | 来源 | 参数（LLM 可见 schema） | 说明 |
|---|---|---|---|
| `search_knowledge_base` | retrieval_service.search | `kb_id: int, query: str, top_k: int=5` | ★知识库检索，返回片段列表 |
| `list_knowledge_bases` | kb_service.list_visible_kbs | 无参数 | 列出当前用户可见知识库 |
| `get_feedback_stats` | feedback_service.get_feedback_stats | `kb_id: int` | 检索质量统计 |
| `get_conversation_history` | chat_service.get_messages | `conversation_id: int` | 读会话历史 |
| `calculator` | 新增（ast 白名单求值：BinOp/UnaryOp/Constant/Compare，禁止名称调用与属性访问） | `expression: str` | 安全数学求值，零依赖 |
| `current_time` | 新增（datetime + zoneinfo） | `timezone: str="Asia/Shanghai"` | 当前日期时间 |
| `simulate_order_query` | 新增（内存 mock dict） | `order_id: str` | **Demo 叙事用，非核心**；展示"接入企业内部 API"的泛化性，时间紧可砍 |

写操作工具（建库/上传/删除/重命名/反馈导出）**全部不暴露**（§3）。

**deep_qa（包装 query_rag）不纳入**（用户确认，2026-10-14）：Agent 内嵌完整 RAG 链会让 LLM 倾向偷懒直接调用，绕过自身规划，使 P0-3a「验证 Agent 行为」的核心目标失效；知识库内容供给由 `search_knowledge_base` 承担（Agent 拿片段自己组织答案）。若未来需重新评估，须标「实验性 + 默认不注册 + 显式开关」。

## 7. 意图识别设计

- `classify_intent(db, user, question, knowledge_base_id) -> Literal["rag","tool","plain"]`：独立 service 函数（路由与冒烟可直接调用），单次 LLM 结构化调用（枚举三选一 + few-shot 示例）
- **few-shot 偏置**：包含"已选知识库 + 事实性问题 → rag"、"选了库但问时间/计算 → tool"的正反例（已拍板：不跳过分类，即使带 kb_id）
- **降级策略（补充 B）**：分类超时（3s）或返回格式异常 → **默认 `rag`**（安全兜底，RAG 链路最成熟）；分类器独立于 Agent 循环，失败不影响主链路；每次分类结果落日志（question 摘要 + intent + 耗时），作为后续优化 prompt 的观测数据

## 8. 循环终止条件（补充 D，5 种场景）

| # | 场景 | 行为 |
|---|---|---|
| 1 | LLM 返回文本（无 tool_calls） | 结束，文本流式输出（token 事件 + done） |
| 2 | 有 tool_calls → 执行工具 → 结果作为 ToolMessage 回传 → LLM 再决策 | 继续循环 |
| 3 | 达到循环上限（**3 轮**）仍未收敛 | 强制终止，返回"无法完成该请求，请重新表述问题"（done 前发终止说明） |
| 4 | 工具抛领域异常（NotFound/PermissionDenied 等） | **异常信息转述给 LLM 作为观察结果**（让 LLM 决定下一步，如换参数重试或告知用户无权限）；**连续 2 次同类错误强制终止**（终止场景 3 行为） |
| 5 | 单工具执行超时（**10s**，asyncio.wait_for） | 超时转述"工具执行超时"给 LLM 作为观察结果，由 LLM 决定下一步；超时也计入场景 4 的同类错误计数 |

> **语义澄清（第 3 轮前修订，D16）**："3 轮上限"指 **LLM 决策轮次上限**（`MAX_TOOL_ROUNDS=3`），不是工具调用次数上限；单轮返回的 `tool_calls` 数上限为 **10**（`MAX_TOOL_CALLS_PER_ROUND=10`）——超出时本轮只执行前 10 个，其余不执行并向 LLM 回填"调用数超限未执行"（ToolMessage，满足协议中每个 tool_call 必须有响应的约束）。最坏耗时受三层封顶：3 轮 × 10 次 × 单工具 10s ≈ 300s（正常 LLM 行为每轮 1~2 个工具，实际远低于此）。第 2 轮场景③实测：3 轮决策内 LLM 并发调用 24 次工具，印证需要单轮调用数上限。

每轮工具调用与终止原因均落可观测日志（§9）。

## 9. 可观测性（补充 C，3a 最小化）

- **实现**：日志文件（复用 `app/utils/logging.py` 的 logger，单行结构化 JSON），**不建表**（P1 评估升级）
- **字段**：`tool_name` / `params_hash`（参数摘要哈希，避免敏感内容入日志）/ `duration_ms` / `status`（success/timeout/denied/error）/ `user_id` / `round`（第几轮）
- **用途**：调试 Agent 多轮循环（不看日志无法定位）+ 面试可讲"如何观测 Agent 行为" + P1 LLM 网关数据复用
- 意图分类同样落日志（§7）

## 10. 附带项：admin 机制

- `.env` 新增 `ADMIN_USERNAMES=admin`（逗号分隔，可多个）；`.env.example` 同步
- **落点**：`main.py` 启动钩子扫描该列表，执行 `UPDATE users SET is_admin=1 WHERE username IN (...)`——**只升权不降权**（列表外用户不动，避免抹掉演示环境手工标记）
- 现状收益：库中 4 个用户 `is_admin` 全 0（含 `username='admin'`），P0-2 的 export admin 路径只能用内存临时标记验证——本项落地后该验证改为真实数据
- 涉及文件：main.py / core/config.py（均非禁区）

## 11. 任务分解（3 轮，每轮独立回归 + changelog）

| 轮次 | 内容 | 回归重点 |
|---|---|---|
| 第 1 轮 | agent_service 骨架：contextvar + 模型工厂 + `classify_intent` + 工具包装工厂 + 7 个工具注册 + calculator/current_time/simulate_order_query 实现；冒烟 ⑨ 段（不经 HTTP 直接调分类与工具）；**双模型 10 次工具冒烟对比**定 AGENT_MODEL（轮末必须给出结论写入 changelog） | 工具单测冒烟全绿 + contextvar 未 set 时工具报明确错误（防误用）+ 禁区 diff 空 |
| 第 2 轮 | `run_agent_loop`（5 种终止场景 + 10s 超时 + 3 轮上限 + 连续 2 次同类错误终止）+ `/api/chat/agent/stream` 端点 + SSE 新事件 + 可观测日志 + admin 附带项 + 老端点零回归验证 | 负向权限用例（B 调 search A 私有库）+ 5 终止场景各 1 用例 + `/api/chat/stream` 事件类型序列+关键字段结构一致（口径同 §12.7）+ admin 升权生效 |
| 第 3 轮 | 前端：api.ts 新事件类型 + ChatWindow 日志面板（工具名/参数摘要/耗时/状态）+ 收尾（文档同步：README/重难点/模型清单/AGENTS.md） | tsc 通过 + 面板展示工具过程 + P0-2 全量终验 9 项子集回归 |

## 12. 验收标准（终验一次性真跑，参照 9+2 模式）

1. **禁区零改动**：`git diff --stat` 自基线 commit 起，禁区 5 文件不出现
2. **contextvar 安全约束落地（补充 A 审计）**：AST/grep 审计工具函数签名与 args_schema——**无任何 `user_id` / `db` 参数**；7 个工具全部经 `_wrap_service_tool` 从 contextvar 取上下文
3. **负向权限用例（P0-1 防线不旁路）**：B 身份经 Agent 端点提问并诱导调用 search 访问 A 的私有库 → 工具返回 403 语义（PermissionDeniedError）→ tool_result status=denied → Agent 最终回答不泄露 A 库任何内容
4. **意图识别准确性**：12 用例（5 RAG + 5 工具 + 2 plain，含"带 kb_id 问时间"偏置用例与"无 kb_id 需查资料"裸问题边界用例）≥ 11/12 正确（等比于原 ≥9/10），用例清单入实施记录
5. **工具端到端**：calculator / current_time / search_knowledge_base / simulate_order_query 各 1 条 SSE 全链路，事件序列含 `intent → tool_call → tool_result → token → done`
6. **循环终止**：5 种场景各 1 个实测用例（上限场景用"反复调用工具不要停"类 prompt 构造）
7. **老端点零回归**：`/api/chat/stream` 事件**类型序列**与实施前一致（conversation → retrieval_debug → token×N → citations → done）+ **关键字段结构**一致（事件名、payload key 集合、citations 数组长度）+ 首尾 token 内容一致；**不要求逐字节一致**（SSE 天然时序抖动，逐字节标准会误报）；P0-2 冒烟 8 段全绿
8. **分层纪律**：agent_service 无 fastapi HTTP 符号（grep 审计）；`/agent/stream` 路由 ≤15 行（AST 脚本，先自证统计对象数 > 0——90-workflow 新规则）
9. **admin 附带项**：启动后列表内用户 `is_admin=1`，列表外不降权；`/feedback/{kb_id}/export` 真实 admin 数据跑通（替代 P0-2 内存标记方案）
10. **双模型对比报告**：各 10 次工具调用成功率对比，AGENT_MODEL 默认值有据可查
11. 前端 `tsc -b` 通过；日志面板可见工具调用过程（最小展示）
12. 零新依赖：requirements.txt 无新增
13. P0-1 五项验收回归通过（401/403/404/存量归属/22 锁图标）
14. **AGENT_TOOLS 白名单审计**：显式验证 `create_kb / update_kb / delete_kb / upload_document / delete_document / batch_delete_documents / rename_document / export_feedback` 均不在 `AGENT_TOOLS` 中（防实施时误注册写操作工具）

## 13. 边界决策

**已确认（2026-10-14 用户拍板）**：

| # | 决策点 | 结论 |
|---|---|---|
| D1 | Agent 模型 | 可配置，默认押 DeepSeek；实施首日双模型各 10 次冒烟对比后定（§5.4） |
| D2 | 端点策略 | 新增 `/api/chat/agent/stream`，不动现有 `/stream` |
| D3 | 写操作工具 | 3a 完全不暴露 |
| D4 | 意图分类触发 | 不跳过（带 kb_id 也分类），分类 prompt 加 few-shot 偏置 |
| D5 | 前端边界 | 最小展示——日志面板，完整可视化归 P1 |
| D6 | admin 机制 | 纳入 3a 附带项，`ADMIN_USERNAMES` 配置化，只升权不降权 |
| D7 | simulate_order_query | 加，标注 Demo 叙事用非核心，时间紧可砍 |
| D8 | 循环上限 | 3 轮；工具超时 10s；连续 2 次同类错误强制终止（§8） |

**实施中发现的补充决策**：实施过程中如产生新的边界决策，登记在 changelog 对应轮次的「决策补充」节，D 编号延续 §13（D9、D10...）；发现问题先问用户，不擅自扩大范围。

## 14. P0-3b 前置需求清单（需动禁区，3a 不处理）

| # | 需求 | 触发的禁区改动 | 3a 的临时替代 |
|---|---|---|---|
| 1 | LLM 网关统一 | rag_chain.py（`_get_llm`/`_get_chat_llm`）+ retrieval.py（`_get_llm`）三处收敛至 core/llm_gateway.py | agent_service 自建 `_get_agent_llm`（读独立配置，与禁区零耦合；此重复是 3b 论据之一） |
| 2 | Agent 内嵌"引用溯源式"流式回答 | rag_chain.rag_stream 需暴露可组合子事件 | 3a 用 search 片段转述，引用以 tool_result 事件呈现（非 citations 格式） |
| 3 | 意图分类/Agent 复用网关模型配置 | 模型工厂公开化 | 同 1 |

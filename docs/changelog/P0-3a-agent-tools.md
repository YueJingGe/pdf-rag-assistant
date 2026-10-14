# P0-3a Agent 工具基座 · 改动日志

> 需求文档：`docs/requirements/P0-3a-agent-tools.md`（v1.1：deep_qa 砍除后 7 工具定稿）
> 基线 commit：`7cfd5c5`

## 2026-10-14 · 第 1 轮：agent_service 骨架（contextvar + 模型工厂 + 意图分类 + 7 工具注册）

**改动摘要**

- 新建 `backend/app/services/agent_service.py`（273 行）：
  - contextvar 注入：`set_agent_context` / `reset_agent_context` / `_require_agent_context`（未注入时抛 ValidationError 防误用——头号安全约束唯一实现点）
  - 模型工厂 `_get_agent_llm()`：读 `agent_model_*` 三项配置，**留空回退 DeepSeek**；不 import 禁区私有 `_get_llm`（短期重复即 P0-3b 网关动机）
  - `classify_intent()`：rag/tool/plain 三分类 + few-shot 偏置（带 kb_id 优先 rag，问时间/算数/订单判 tool）+ 补充 B 降级（3s 超时/格式异常/调用失败统一兜底 rag + 结果落日志）
  - `calculator`：ast 白名单求值（BinOp/UnaryOp/Constant/单层 Compare），注入表达式拒绝（Call/Name/Attribute 节点）
  - `current_time`（zoneinfo + 中文星期）、`simulate_order_query`（Demo mock，SO-1001~1003）
  - `_wrap_tool` 包装工厂：LLM 可见 schema 仅业务参数；结果 JSON 序列化（ensure_ascii=False）
  - `AGENT_TOOLS` 注册表：7 工具（search_knowledge_base / list_knowledge_bases / get_feedback_stats / get_conversation_history / calculator / current_time / simulate_order_query）
- `backend/app/core/config.py`（+5）：`agent_model_name / agent_model_base_url / agent_model_api_key`（留空回退 DeepSeek）
- `scripts/smoke_test_services.py`（+78）：追加 ⑨ 段——注册数断言（≠7 即 fail）/ contextvar 防误用 / 外部工具直调 / 注入拒绝 / service 工具直调 / 越权负例 / 意图分类 4 用例（含偏置反例）

**diff 摘要**：`agent_service.py` 新建 +273；`config.py` +5；`smoke_test_services.py` +78；禁区 5 文件 **0**；`api/` **0**；`requirements.txt` **0**

**验收结果**（全部真跑）

| # | 项 | 结果 |
|---|---|---|
| 1 | `py_compile`（agent_service / config / smoke） | ✅ |
| 2 | `AGENT_TOOLS` 长度 = 7（deep_qa 未注册，白名单终验 §12.14 前置确认） | ✅ |
| 3 | 冒烟 ①-⑨ 全绿（`python3 scripts/smoke_test_services.py 18838166792`） | ✅ ⑨ 段 9 项：contextvar 防误用 / calculator=48.0 / 注入拒绝（Call 节点）/ current_time / order / list_kbs=3 / stats / search=3 条 / 越权 search → PermissionDeniedError（**contextvar 身份生效铁证**） |
| 4 | 意图分类冒烟 4/4（含偏置用例"带 kb_id 问时间 → tool"） | ✅ |
| 5 | 分层审计：`grep -E "from fastapi\|HTTPException\|Depends"` 代码零命中（唯一命中为注释） | ✅ |
| 6 | 禁区审计：`git diff 7cfd5c5` 禁区 5 文件零出现；`api/` 零改动 | ✅ |
| 7 | 零新依赖：requirements.txt 零 diff | ✅ |
| 8 | 路由数回归（三口径）：`len(app.routes)=29` / `APIRoute=25` / openapi 带锁 22 | ✅ 与 P0-2 基线完全一致（本轮零路由改动佐证） |
| 9 | 后端重启生效 + 401 探测（90-workflow 新规则：先证明打到新代码） | ✅ 新进程 75194，`GET /api/knowledge_bases` 未登录 → 401 |

**双模型工具调用对比（D1 结论，轮末必答项）**

- 方法：临时脚本 bakeoff（未入库、已删除），10 用例覆盖 7 工具（calculator×2 / current_time×2 / search_knowledge_base×2 / simulate_order_query / list_knowledge_bases / get_feedback_stats / get_conversation_history）；判定 = `tool_calls[0]` 名称匹配 + 关键参数正确（kb_id==1、expression 含操作数、order_id 精确匹配等）
- **DeepSeek**（deepseek-v4-flash，.env 当前配置）：**10/10**，search 的 query 提炼与 calculator 表达式构造全部精确，top_k 显式传 5
- **智谱**（glm-4-flash-250414）：**10/10**，参数同样精确（top_k 省略，合法默认）
- **结论（平局判据）**：两者 function calling 均成熟且全对，无法从成功率区分；按需求 D1 用户默认押注——**AGENT_MODEL 默认回退 DeepSeek**（config 三项留空即生效，`.env` 无需新增任何配置）；glm-4-flash-250414 验证可用，作为**免费备选**（切换方式：`.env` 写 `AGENT_MODEL_NAME=glm-4-flash-250414` + `AGENT_MODEL_BASE_URL` + `AGENT_MODEL_API_KEY`）
- 附注：意图分类单次实测 0.5~2s（DeepSeek），3s 超时阈值合适

**决策补充（延续需求 §13 编号）**

- **D9**：AGENT_MODEL 默认值采用「config 留空回退 DeepSeek」实现（而非 .env 显式写值）——零配置生效 + 保持可切换（智谱备选已验证）

**遗留 / 注意**

- 首跑两处小失误已修：agent_service 漏 import logger（NameError）；smoke ⑨ 段初版缩进错误（写在 async with 块外，db session 已关闭）
- 环境探测路径注意：业务路由前缀是 `/api/knowledge_bases`（下划线）非连字符——404 是路径错非代码回归
- zoneinfo 依赖系统 tzdata（macOS 自带）；Docker slim 镜像若缺 tzdata，`current_time` 会转 ValidationError（P1 部署时留意）

## 2026-10-14 · 第 2 轮：run_agent_loop + 三意图分支接力 + 双超时 + admin 机制（基线 `6973111`）

**改动摘要**

- `backend/app/services/agent_service.py`（+138，共约 409 行）：追加 `run_agent_loop()`（async generator，产出 `(事件类型, payload)` 元组）
  - 5 种终止场景全覆盖：①无 tool_calls 直接回答（伪流式）②多轮工具 ③3 轮上限 FORCED_STOP ④连续 2 次同类错误 FORCED_STOP（跨轮保留计数，成功归零）⑤单工具 10s 超时转述 LLM
  - 双超时：`TOOL_TIMEOUT_S=10`（每工具独立 wait_for）+ `LLM_TIMEOUT_S=15`（决策 ainvoke wait_for）；两者超时均计入连续同类错误计数（提醒 2 完整落地）
  - 工具可观测日志：单行 JSON `[agent_tool] {tool_name, params_hash(md5 8位), duration_ms, status, user_id, round}`（§9，不建表）
  - 伪流式：最终答案按 24 字符切块 yield `token`（D10，前端协议零改动）
  - `_error_status()`：PermissionDenied→denied / NotFound→not_found / ValidationError→validation / 兜底 error
- `backend/app/api/chat.py`（+129/-43）：**三意图分支接力**（零重复实现）
  - 提取模块级 `_chat_sse_events()`：原老端点闭包逐行平移，plain/rag 事件组装逻辑两端点共用
  - 老端点 `chat_stream`：55 行 → 11 行（P0-2 的 D3 豁免解除），行为零变化
  - 新端点 `agent_stream`：函数体 6 行（≤15 达标）——prepare_chat/save_user_message 后返回 `_agent_sse_events()`
  - `_agent_sse_events()`：classify_intent → 首发事件 `intent`；plain/rag 分支转发 `_chat_sse_events`（自带 conversation）；tool 分支单发 conversation → contextvar set/reset 成对包 try/finally（提醒 1：generator 被客户端中断也不泄漏）→ 消费 `run_agent_loop` → done 路由层统一收尾 → save_assistant_message
- `backend/app/main.py`（+18）：lifespan 启动钩子 admin 升权——`UPDATE users SET is_admin=1 WHERE username IN (...) AND is_admin==false()`，**只升不降**（§10）
- `backend/app/core/config.py`（+3）：`admin_usernames`（逗号分隔）；`.env.example` 同步 `ADMIN_USERNAMES=admin` 示例
- `scripts/agent_loop_cases.py` 新建（93 行）：5 终止场景 service 层直调实测（场景⑤ monkeypatch 注入 11s 延迟，测完还原）
- `scripts/smoke_test_services.py`（⑨.4 修正 +6/-1）：负例选用户排除 `is_admin==1`（admin 机制落地后否则负例静默失效，D14）

**diff 摘要**：6 文件改动 + 1 新建脚本，+255/-43；禁区 5 文件 **0**；`requirements.txt` **0**；agent_service 无 fastapi 符号真实 import（grep 命中 2 行均为"不 import"的说明注释）

**tool_calls 格式验证结论（提醒 3 前置，写解析前真跑）**

- DeepSeek 返回 `AIMessage.tool_calls` **结构化字段**（`additional_kwargs` 里同时冗余原始格式，解析以结构化字段为准）
- `args` 已是 **dict**（无需 json.loads）；`tool_call_id` 存在，**必须回填**到 ToolMessage
- 意外发现：一次决策可返回 **2 个 tool_calls**（多工具并发真实存在）——证实"每工具独立 10s"而非轮级总超时的必要性

**验收结果**（全部真跑，本轮收尾重跑取新鲜证据）

| # | 项 | 结果 |
|---|---|---|
| 1 | 5 终止场景（`python3 scripts/agent_loop_cases.py`） | ✅ 5/5：①纯 token×2 ②calculator+current_time 双工具 success ③24 次 success 后轮尾 FORCED_STOP ④error×2 后 FORCED_STOP ⑤timeout×2 后终止 |
| 2 | 三分支 HTTP 端到端（`/api/chat/agent/stream`） | ✅ plain：`intent→conversation→token×16→done`；rag：`intent→conversation→retrieval_debug→token×738→citations→done`；tool：`intent→conversation→tool_call→tool_result(success)→token×2→done` |
| 3 | 老端点零回归（§12.7 口径） | ✅ `conversation→retrieval_debug→token×227→citations→done`，payload keys 集合一致，citations=4，首尾 token 正常 |
| 4 | 负向权限三段式 | ✅ HTTP 层 B+kb=1 → **403**（prepare_chat 先行拦截，SSE 未启动）；service 层完整链路：`search_knowledge_base→denied` → LLM 自主换 `list_knowledge_bases`（返回空）→ 诚实回答"无权限、不凭记忆作答"，文档实体级敏感词（货币政策司/反洗钱局/金融稳定局/条法司/国库局/国务院直属）**零命中**，无异常栈 |
| 5 | AST 路由审计 | ✅ 25 个路由函数自证>0；`agent_stream`=6 行、`chat_stream`=11 行（≤15）；超限仅剩 2 个已登记豁免（upload_file 63 / register 16） |
| 6 | 路由数三口径 | ✅ `len(app.routes)=30` / `APIRoute=26` / openapi paths=22——相对第 1 轮各 **+1**，唯一增量即 `/api/chat/agent/stream` |
| 7 | 禁区/依赖/分层审计 | ✅ 禁区 5 文件零 diff；requirements 零 diff；agent_service 无 fastapi 符号、无禁区私有 import |
| 8 | admin 升权实证 | ✅ 库中 `admin` 用户 is_admin=1、其余 3 人保持 0；smoke ⑧ 段 admin 分支走真实数据 export 通 |
| 9 | smoke ①-⑨ 全量 | ✅ 全绿（含 ⑨ 段 10 项 + 意图分类 4/4 + ⑨.4 负例修正后恢复 PermissionDeniedError） |

**实施中发现并修复**

- bug1：agent 链路缺 `done` 收尾事件（run_agent_loop 各终止路径只发业务事件）→ 路由层 `_agent_sse_events` 统一补发，格式与老端点一致
- bug2：plain/rag 分支 `conversation` 事件 ×2（转发目标自带 + 本层又发）→ conversation 移入分支：intent 保持首事件（§5.3），plain/rag 靠 `_chat_sse_events` 自带，tool 分支单发
- 一次操作失误即时恢复：SearchReplace 误删 classify_intent 调用行 → 立即补回并全量终验
- 断言方法修正：负向泄露判据从裸主题词（"货币政策"）改为**文档实体级**司局名——裸主题词在用户问题里就有，LLM 复述问题即命中，属假阳性；两轮实测回答均为干净拒绝话术，实体词零命中

**决策补充（延续 §13 编号）**

- **D10**：Agent 最终答案采用伪流式——`ainvoke` 一次性拿到完整回答后按 24 字符切块 yield `token`，前端 SSE 协议零改动（真流式留待 3b 网关统一 astream 时再评估）
- **D11**：双超时落地口径——单工具 10s（每工具独立 wait_for，多工具并发不叠加）+ LLM 决策整体 15s；**LLM 超时同样计入连续同类错误计数**（连续 2 次 LLM 超时也触发 FORCED_STOP）
- **D12**：事件顺序定稿——`intent` 恒为首事件；`conversation` 移入分支（plain/rag 复用 `_chat_sse_events` 自带、tool 由本层单发），避免 ×2
- **D13**：`done` 由路由层统一收尾——`run_agent_loop` 只发业务事件（token/tool_call/tool_result），覆盖场景①直接回答与③④强制终止两条路径，且格式与老端点一致
- **D14**：smoke 负例选用户排除 `is_admin=1`——admin 升权机制落地后，负例若取到 admin 会因 owner 判定恒过而静默失效
- **D15**：负向泄露断言用文档实体级敏感词——裸主题词复述用户问题即命中（假阳性），实体词（司局名等）只有真读到文档才会出现

**遗留 / 注意**

- 意图分类存在 LLM 波动：端到端用例"你好，请用一句话介绍这个项目"被判 rag（该句语义含糊）；误判时行为合法（完整 rag 序列、不崩），B 兜底（超时/异常默认 rag）本就是安全侧；分类准确率以第 1 轮冒烟 4/4 为准，P1 可观察线上误判率再调 few-shot
- 回归期间重置过 `18838166792` / `testuser_b` 密码，结束后已将 `18838166792` 恢复为账号.md 记录值（123456）并登录验证；`testuser_b` 现密码 `TestB123456`（仅本地测试用）
- 场景⑤的 monkeypatch 手法（替换 `AGENT_TOOLS[...].coroutine`）可复用为慢工具注入的标准测试姿势

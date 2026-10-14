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

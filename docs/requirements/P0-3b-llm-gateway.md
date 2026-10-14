# P0-3b 需求文档：LLM 网关统一（core/llm_gateway.py）

> 版本：v1.1（2026-10-14 review 修订：HyDE 独立回归 §7.6 / fallback 触发条件显式化 / 步 1 对拍一次性窗口 / §7.4 断言加强 / §3.6 双消费者登记）｜状态：**待用户确认，未进入实施**
> 性质：**全项目首次动 RAG 禁区文件**（rag_chain.py / retrieval.py），质量门槛高于 P0-2 / P0-3a
> 前置：P0-3a 已闭环（5 commit，`7cfd5c5...3e17d31`）；本需求对应 P0-3a 需求文档 §14 前置清单第 1 条

## 1. 背景

### 1.1 三处模型工厂的历史由来

- P0-2 之前，RAG 链路与普通聊天的模型构造散落在 `rag_chain.py`（`_get_llm` / `_get_chat_llm`）与 `retrieval.py`（`_get_llm`，与前者**同名不同参**）
- P0-3a 新增 `agent_service._get_agent_llm` 时，因"不 import 禁区私有符号"约束（3a §4.4）选择短期重复，注释明确"此重复即 3b 网关动机"（agent_service.py:73）
- 3b 统一目的：模型配置只有 settings 一个真相源，网关是唯一构造入口

### 1.2 侦察实证：实际是 5 处实例化点，不是 3 处（2026-10-14 用户拍板纳入全部）

| # | 位置 | 形态 | 模型（settings 字段） | 关键参数 | 分区 |
|---|---|---|---|---|---|
| 1 | rag_chain.py:114-126 `_get_llm` | 独立工厂 | `deepseek_model/api_key/base_url` | temp=0.3，streaming 参数化，无 max_tokens | 主路径（RAGAS 覆盖） |
| 2 | rag_chain.py:458-470 `_get_chat_llm` | 独立工厂 | `chat_model/api_key/base_url` | temp=0.7，max_tokens=4096 | 主路径（plain 回归覆盖） |
| 3 | rag_chain.py:591-598 **内联 ChatOpenAI** | 无工厂 | `chat_text_model/api_key/base_url` | temp=0.7，max_tokens=4096，streaming=True | **独立回归路径**（RAGAS 覆盖不到） |
| 4 | retrieval.py:20-32 `_get_llm` | 独立工厂（与 #1 同名！） | `deepseek_model/api_key/base_url` | temp=0.0，max_tokens=256 | 主路径（RAGAS 覆盖） |
| 5 | agent_service.py:77-84 `_get_agent_llm` | 独立工厂（非禁区） | `agent_model_*` 逐字段 or 回退 `deepseek_*` | temp 可覆盖（默认 0.0），streaming 参数化 | 非禁区，跟随主任务 |

**收敛范围 = 5 处**：主路径 3 处（#1/#2/#4，RAGAS 回归覆盖）+ 591 内联 1 处（#3，独立端到端回归）+ agent 1 处（#5，非禁区）。

### 1.3 遗留评估项（本需求只给框架，不拍板）

- **D19**（3a §13）：search 工具在分类器优先策略下为备用工具，"是否让 LLM 自主决定检索"待 3b 评估 → 第 9 节评估框架
- **RAG 真流式**（3a D10 伪流式的替代方案）→ 第 9.4 节单独登记，默认不做

## 2. 目标与范围

### 2.1 主任务（唯一主线）

新建 `backend/app/core/llm_gateway.py`（非禁区新文件），将 **5 处**模型实例化收敛为 `get_llm(role, streaming)` 单一入口：

1. settings 成为模型配置**唯一真相源**
2. 5 个能力角色（`rag_generate` / `hyde` / `chat_text` / `chat_multimodal` / `agent`），temperature/max_tokens 收编到网关角色注册表
3. `USE_LEGACY_LLM_FACTORY` 运行时回退开关（默认 False），开关逻辑在网关内部，调用点不感知

### 2.2 可选子任务（独立章节，不与主任务捆绑，默认不排期）

- 子任务 A：D19 意图分类权责评估（第 9 节框架，主任务完成后做对比实验拍板）
- 子任务 B：RAG 真流式（第 9.4 节，需单独论证 + 事件协议回归，本期不做）

## 3. 禁区改动清单（逐行级 justification）

> 审计口径：实施后 `git diff <baseline> -U0 -- backend/app/core/{rag_chain,retrieval}.py` 的每一处改动都必须能在本表找到对应行号区间，多余改动 = 违规。

### 3.1 rag_chain.py:114-126 `_get_llm`（DeepSeek，RAG 生成）

| 项 | 内容 |
|---|---|
| 改动内容 | 函数体替换为 `return llm_gateway.get_llm("rag_generate", streaming=streaming)`；签名 `(streaming: bool = False)` 保持不变；113 行上方 import 网关（+1 行） |
| 调用路径 | `rag_query`（:341，非流式 RAG 问答 `/api/chat/query`）→ LCEL `RAG_PROMPT \| llm`；`rag_stream`（:409，流式 RAG 问答 `/api/chat/stream` 带 kb_id）；`_get_chat_llm`（:462，CHAT_API_KEY 未配置时降级回退） |
| 为什么必须动 | 它就是收敛对象本体：DeepSeek 的 model/api_key/base_url/temperature(0.3) 在此硬编码拼装，网关化后若保留原实现，同一份 DeepSeek 配置存在两个构造入口（网关注册表 + 此函数），settings 新增全局项（如统一 timeout）时必然漂移 |
| 不动能不能实现 | 不能——"收敛"的定义就是消除它 |
| 风险评估 | 参数遗漏导致 RAG 回答风格漂移（temp 0.3→其他）→ RAGAS faithfulness/answer_relevancy 兜底；streaming 传递遗漏 → 流式端点退化为一次性输出 → SSE 事件序列回归兜底 |
| 回归 | RAGAS 四指标对比（§7.1）+ rag 流式端点事件序列零回归（§7.3） |

### 3.2 rag_chain.py:458-470 `_get_chat_llm`（GLM-4V-Flash，多模态）

| 项 | 内容 |
|---|---|
| 改动内容 | 函数体替换为 `return llm_gateway.get_llm("chat_multimodal", streaming=streaming)`；签名不变 |
| 调用路径 | `plain_chat_stream`（:587）images 非空分支 → 多模态消息（image_url content_parts）→ astream 流式输出。上游：`POST /api/chat/stream` 无 kb_id 且带图片 |
| 为什么必须动 | 同 3.1：GLM-4V-Flash 的 model/api_key/base_url/temp(0.7)/max_tokens(4096) 第二处硬编码；且其降级回退逻辑（:460-462 CHAT_API_KEY 空则回退 `_get_llm`）是跨工厂耦合，网关化后该回退语义由角色注册表 `fallback` 字段声明（见 §5.2），原地保留会造成"回退逻辑一处网关一处工厂"的双轨 |
| 不动能不能实现 | 技术上能（只收敛 #1/#4 也能跑），但回退耦合使"配置单真相源"目标落空，且 #2 与 #3（591 内联）参数高度重合，不收敛则同函数内三路路由出现"两处网关一处内联"的割裂 |
| 风险评估 | 回退语义走样（原回退后 temp=0.3 且**无** max_tokens，见 :462 调 `_get_llm`）→ 网关 fallback 实现"整角色切换"（用 rag_generate 角色全部参数）精确保持，回归用带图 plain 请求验证 |
| 回归 | 带图 plain chat 端到端（SSE 序列 + 回答非空）+ CHAT_API_KEY 置空时降级路径冒烟 |

### 3.3 rag_chain.py:591-598 内联 ChatOpenAI（GLM-4-Flash-250414，纯文本）——独立 commit

| 项 | 内容 |
|---|---|
| 改动内容 | :591-598 的 8 行内联 `ChatOpenAI(...)` 替换为 `llm = llm_gateway.get_llm("chat_text", streaming=True)`（1 行）；净减 7 行 |
| 调用路径（用户拍板必须写清） | `plain_chat_stream`（:543）三路路由的 else 分支：`web_search=False 且 images 为空` → 走此内联。上游：`POST /api/chat/stream`（chat.py:77），进入条件 `is_plain_chat = req.knowledge_base_id is None or == 0`。**即：普通聊天模式 + 无图片 + 未开联网开关**的纯文本流式路径。同函数的联网搜索分支走智谱原生 httpx API（:473-540，不经 ChatOpenAI）、带图分支走 `_get_chat_llm`——**同一函数内一处工厂两处非工厂** |
| 历史遗留原因 | plain_chat_stream 三路路由逐步长出：带图分支复用了既有 `_get_chat_llm`，纯文本 LangChain 分支后加时未提工厂，直接内联 8 行参数拼装 |
| 为什么必须动 | 收敛后若保留，此 8 行成为全仓唯一残余的模型硬编码点：model/api_key/base_url/temperature/max_tokens 五项独立拼装，与网关 `chat_text` 角色注册表构成**第二份 chat_text 配置源**——settings 调整 GLM 计费档位/超时/全局 max_tokens 上限时此处漏改，纯文本聊天与其余四路径行为漂移；未来切换 chat_text 供应商需改两处 |
| 不动能不能实现 | 能跑（不收敛不影响功能），但违背主任务"settings 唯一真相源"目标，留下最典型的漂移样本 |
| 风险评估 | 替换为 1 行后参数遗漏风险同 3.2（temp 0.7/max_tokens 4096/streaming=True）；此路径 RAGAS 覆盖不到，靠独立端到端回归兜底（§7.4） |
| 回归 | **独立端到端回归**（§7.4，与主路径 RAGAS 解耦） |
| commit 约束 | **单独 commit，不与 3.1/3.2 混合**（用户拍板：便于独立 revert） |

### 3.4 retrieval.py:20-32 `_get_llm`（DeepSeek，HyDE 假想文档生成）

| 项 | 内容 |
|---|---|
| 改动内容 | 函数体替换为 `return llm_gateway.get_llm("hyde")`；调用点 `hyde_retrieve`（:46）不变 |
| 调用路径 | `hyde_retrieve`（:35-51）→ `HYDE_PROMPT \| llm` 生成假想文档段落 → 向量检索。上游：`retrieve_with_strategy`（rag_chain.py:316）`use_hyde=True` 时；HTTP 侧 `/api/chat/stream` 的 `use_hyde` 参数 |
| 为什么必须动 | 它与 #1 **同名不同参**（temp 0.0 vs 0.3、max_tokens 256 vs 无），是"同名双胞胎"最易混淆点——历史上任何"顺手统一"都会静默改变 HyDE 或 RAG 生成的行为；网关化后同名消除，角色名携带语义 |
| 不动能不能实现 | 不能（收敛对象本体，理由同 3.1） |
| 风险评估 | HyDE 对 temp/max_tokens 敏感（256 上限控制成本与假想文档长度）→ 参数走样会改变检索 query 质量 → RAGAS context_precision / context_recall 兜底；**本处最先实施**（最小、最独立，验证切换方法论） |
| 回归 | **§7.6 HyDE 独立回归**（10 题中取 3 题显式 use_hyde=True 对比 context_precision/recall；主 RAGAS 对比 use_hyde=False 覆盖不到本角色） |

### 3.5 agent_service.py:77-84 `_get_agent_llm`（非禁区，跟随主任务）

| 项 | 内容 |
|---|---|
| 改动内容 | 函数体替换为 `return llm_gateway.get_llm("agent", temperature=temperature, streaming=streaming)`（保留 temperature 覆盖签名）；:73 注释同步更新（"短期重复"承诺兑现） |
| 为什么必须动 | 3a 注释明确承诺 3b 收敛；agent 角色的"逐字段 or 回退"语义（:79-81）收编进网关后，AGENT_MODEL 换供应商只改 .env 一处 |
| 不动能不能实现 | 能，但 P0-3 系列的收敛目标不完整，且网关 agent 角色无人使用即成死代码 |
| 风险评估 | 低：非禁区文件，3a 回归体系（12 用例/5 终止场景/面板）完整兜底 |
| 回归 | P0-3a 回归子集：意图 12 用例 ≥11/12 + 5 终止场景 5/5 |

### 3.6 不纳入收敛的相邻点（显式登记，防"悄悄扩大"质疑）

| 位置 | 是什么 | 不纳入理由 |
|---|---|---|
| rag_chain.py:496-513 `_web_search_chat_stream` | 智谱原生 httpx API 直调（payload 内 `model=settings.chat_text_model`） | 不是 ChatOpenAI 实例化点（无第二配置源，字段已从 settings 读）；改动它将触碰联网搜索 payload 组装逻辑，收益仅为"形式统一"，风险（破坏 web_search 工具参数协议）大于收益。登记为 3c+ 候选 |
| `settings.chat_text_model` | 同源字段双消费者 | 消费者 1：网关 `chat_text` 角色；消费者 2：`_web_search_chat_stream` payload.model。两者同源合规（读同一 settings 字段，无漂移风险）；若未来需拆分（聊天用 A、搜索用 B），另开需求 |

## 4. 明确不做的（写死，实施中一律拒绝）

- ❌ 不改 retrieval.py 的检索算法：BM25/RRF/向量检索参数与逻辑一律不动（只动 :20-32 工厂与 :46 无关）
- ❌ 不改 rag_chain.py 的 prompt 组装（RAG_PROMPT/PLAIN_CHAT_SYSTEM_PROMPT_TEMPLATE 等）、引用溯源逻辑（_build_citations）、语义缓存机制
- ❌ 不改 SSE 事件协议（两端点事件名/payload key/顺序一字不动）
- ❌ 不改 D3 边界（SSE 生成器留路由层的 P0-2 决策）
- ❌ 不做 RAG 真流式替换（默认不做；如要做见 §9.4 单独论证，独立任务）
- ❌ 不动 `_web_search_chat_stream` 的原生 API 组装（§3.6）
- ❌ 零新依赖（langchain-openai/httpx/pydantic 均已有）

## 5. 架构设计

### 5.1 网关接口（角色制，2026-10-14 用户拍板）

```python
# backend/app/core/llm_gateway.py（新文件，非禁区）
"""LLM 网关：全项目唯一 ChatOpenAI 构造入口（P0-3b）。
settings 是唯一配置真相源；本模块只存"角色 → settings 字段名 + 采样参数"映射。
"""

@dataclass(frozen=True)
class RoleSpec:
    model_field: str        # settings 字段名（显式全名，不做前缀拼接魔法）
    api_key_field: str
    base_url_field: str
    temperature: float
    max_tokens: int | None
    fallback_role: str | None = None          # 整角色回退（精确复刻 _get_chat_llm:460-462 语义）
    fallback_trigger: str | None = None       # 回退触发条件："on_empty_api_key"=api_key 字段为空时触发；None=不触发
    per_field_fallback_prefix: str | None = None  # 逐字段回退（精确复刻 agent :79-81 or 语义）

_ROLES: dict[str, RoleSpec] = {
    # 角色            model 字段           key 字段             base_url 字段          temp  max_tokens  回退
    "rag_generate":    RoleSpec("deepseek_model", "deepseek_api_key", "deepseek_base_url", 0.3, None),
    "hyde":            RoleSpec("deepseek_model", "deepseek_api_key", "deepseek_base_url", 0.0, 256),
    "chat_multimodal": RoleSpec("chat_model", "chat_api_key", "chat_base_url", 0.7, 4096,
                                fallback_role="rag_generate", fallback_trigger="on_empty_api_key"),  # CHAT_API_KEY 空 → 整角色切 rag_generate（原 :460-462 语义）
    "chat_text":       RoleSpec("chat_text_model", "chat_api_key", "chat_base_url", 0.7, 4096),
    "agent":           RoleSpec("agent_model_name", "agent_model_api_key", "agent_model_base_url", 0.0, None,
                                per_field_fallback_prefix="deepseek"),  # 逐字段 or 回退（原 :79-81 语义）
}

def get_llm(role: str, streaming: bool = False, temperature: float | None = None) -> ChatOpenAI:
    """唯一构造入口。USE_LEGACY_LLM_FACTORY=true 时走 legacy 分支（网关内部复刻旧工厂逐字段行为）。

    回退判定顺序（精确对应 §5.2）：
    1. spec.fallback_trigger == "on_empty_api_key" 且 getattr(settings, spec.api_key_field) 为空
       → 整角色切 spec.fallback_role（按目标角色 RoleSpec 全套参数重新构造，streaming 透传）
    2. spec.per_field_fallback_prefix 非空 → model/api_key/base_url 三字段逐个 or 回退
    3. 两者均空 → 无回退，按本角色字段直接构造（api_key 缺失报错语义与原工厂一致）
    """
```

设计要点（用户三条附加条件的落实）：

1. **settings 唯一真相源**：注册表只存 settings **字段名**与采样参数，model/api_key/base_url 运行时经 `getattr(settings, spec.model_field)` 读取——注册表不是配置源，是"角色 → 配置字段"的路由表；后续新增供应商只改 .env +（必要时）注册表加角色
2. **角色按能力档位命名**，不按调用点命名：5 角色覆盖 5 处调用点；**591 内联复用 `chat_text` 角色**（其模型本就是 `chat_text_model`，调用路径分析见 §3.3，不单独造角色）
3. **legacy 开关在网关内部**：`get_llm` 入口检查 `settings.use_legacy_llm_factory`，调用点统一 `get_llm(role, ...)`，未来删开关不动任何调用点

### 5.2 回退语义与触发条件（易错点，重点评审）

| 原语义 | 原代码 | 网关实现 | 触发条件（与 §5.1 一致） |
|---|---|---|---|
| 整角色回退 | `_get_chat_llm`:460-462：CHAT_API_KEY 空则 `return _get_llm(streaming)`——**回退后 temp=0.3 且无 max_tokens**（连参数一起切） | `fallback_role="rag_generate"`：触发时按 rag_generate 的 RoleSpec **整套参数**重新构造，streaming 透传 | `fallback_trigger="on_empty_api_key"` 且 `getattr(settings, spec.api_key_field)` 为空 |
| 逐字段回退 | `_get_agent_llm`:79-81：`model = agent_model_name or deepseek_model` 等**三个字段各自 or**——可能"agent 模型名 + deepseek key"混搭 | `per_field_fallback_prefix="deepseek"`：三字段逐个 or，保持混搭语义 | `per_field_fallback_prefix` 非空即启用（逐字段判断，无额外触发条件） |
| 无回退 | rag_generate / hyde / chat_text 无回退逻辑 | 两者均空：按本角色字段直接构造（api_key 缺失报错语义与原工厂一致） | `fallback_trigger` 与 `per_field_fallback_prefix` 均为 None |

### 5.3 legacy 分支的行为等价声明

调用点只留 `get_llm` 后，legacy=true 时网关内部按**原工厂逐字段行为**构造（temp/max_tokens/回退逻辑与被替换的 5 处完全一致）。这不是 git revert 级回滚，而是"网关内复刻旧路径"——等价性由 §7.5 开关两态回归保证。彻底回滚 = revert 对应单 commit（§8）。

### 5.4 调用点替换对照

| # | 调用点（行号） | 改前 | 改后 |
|---|---|---|---|
| 1 | rag_chain.py:114-126 | 13 行拼装 | `return llm_gateway.get_llm("rag_generate", streaming=streaming)` |
| 2 | rag_chain.py:458-470 | 13 行拼装+回退 | `return llm_gateway.get_llm("chat_multimodal", streaming=streaming)` |
| 3 | rag_chain.py:591-598 | 8 行内联 | `llm = llm_gateway.get_llm("chat_text", streaming=True)` |
| 4 | retrieval.py:20-32 | 13 行拼装 | `return llm_gateway.get_llm("hyde")` |
| 5 | agent_service.py:77-84 | 8 行拼装+or 回退 | `return llm_gateway.get_llm("agent", temperature=temperature, streaming=streaming)` |

新增配置：`core/config.py` 加 `use_legacy_llm_factory: bool = False`（非禁区，3a 已有 config 改动先例）；`.env.example` 同步注释。

## 6. 实施步骤（commit 粒度：一处一 commit，591 强制独立）

| 步 | 内容 | commit | 产出物 | 通过标准 |
|---|---|---|---|---|
| 0 | **RAGAS 基线先行**（硬约束 3）：①验证 RAGAS judge LLM 可用（脚本默认走 OpenAI 兼容接口，先确认 judge 配置；不可用则先修 judge 配置，属评估基建非禁区改动）②定稿 10 题问题集 `docs/benchmarks/qa-pairs-p03b.json`（kb1 央行 4 题 / kb3 无人机 3 题 / kb2 药品 3 题，全部带 ground_truth，题面见附录 A）③跑基线落盘 `docs/benchmarks/P0-3b-baseline-{date}.md`（四指标 + 判定口径：**任一指标下降 >5% 即回滚**） | A | 基线文档 + qa json | 四指标数值落盘 |
| 1 | `llm_gateway.py` 新建（注册表 + 两种回退 + legacy 分支）+ 冒烟：直调 5 角色各构造一次，断言 model/temp/max_tokens 与原工厂一致（对拍脚本打印新旧实例参数 diff） | B（非禁区） | 网关 + 对拍输出（**对拍脚本必须在步 1 一次性覆盖 5 处；任一处不通过则停下修网关，不进入步 2**） | **5 处旧工厂 vs 新网关全量对拍零漂移（一次性窗口：步 2 起逐个替换旧工厂，此后再无对拍目标）** |
| 2 | retrieval.py 切换（#4，最小最独立，验证方法论） | C（禁区） | 3.4 完成 | RAGAS 对比（重点 context_precision/recall）≤5% 降 |
| 3 | rag_chain.py `_get_llm` 切换（#1） | D（禁区） | 3.1 完成 | RAGAS 全量 ≤5% 降 + rag 流式事件序列零回归 |
| 4 | rag_chain.py `_get_chat_llm` 切换（#2） | E（禁区） | 3.2 完成 | 带图 plain 端到端 + CHAT_API_KEY 置空降级冒烟 |
| 5 | rag_chain.py 591 内联切换（#3） | **F（禁区，独立 commit）** | 3.3 完成 | 纯文本 plain 独立端到端回归（§7.4） |
| 6 | agent_service 切换（#5，非禁区） | G | 3.5 完成 | P0-3a 回归子集（12 用例 ≥11/12 + 5 终止 5/5） |
| 7 | legacy 开关两态全回归 + 文档收尾（README/重难点/模型清单/AGENTS.md） | H | 收尾 | §7 全绿 |

**轮次划分**：第 1 轮 = 步 0-2（基线 + 网关 + 最小禁区）；第 2 轮 = 步 3-5（rag_chain 三处）；第 3 轮 = 步 6-7（agent + 开关 + 收尾）。每轮独立 changelog。

## 7. 验收标准

### 7.1 RAGAS 对比（硬闸门）

- 基线（步 0）vs 收尾（步 7 后）各跑一次全量 10 题
- 指标：faithfulness / answer_relevancy / context_precision / context_recall（ground_truth 全非空，四指标齐跑）
- **判定：任一指标下降 >5% → 回滚**（§8）
- 口径声明：10 题主对比 **use_hyde=False**（RAG 主路径）；hyde 角色参数不在本节覆盖内，由 §7.6 独立回归补位
- 每个禁区 commit（C/D/E/F）后同样全量对比，失败即 revert 该 commit 不带尾随

### 7.2 禁区改动精确匹配

- `git diff <baseline> -U0 -- backend/app/core/rag_chain.py backend/app/core/retrieval.py` 的 hunk 逐条对照 §3 清单：只允许出现 3.1/3.2/3.3/3.4 四处（+ 各自 import 行），任何额外 hunk = 违规即停

### 7.3 老端点零回归（P0-2 口径）

- `/api/chat/stream` RAG 分支：`conversation→retrieval_debug→token×N→citations→done` 序列一致
- `/api/chat/query` 正常返回

### 7.4 591 独立端到端回归（RAGAS 覆盖不到的路径，专用设计）

- 命中路径：登录 → `POST /api/chat/stream` body=`{"question":"你好呀今天心情不错","knowledge_base_id":null,"web_search":false}`（不带 images）→ plain_chat_stream else 分支（原 :591）
- 断言（temperature=0.7 生成有随机性，**不做逐字节对比**）：
  - 事件序列严格等于 `conversation→token×N→done`，首事件 conversation、尾事件 done
  - token 数 N 落在基线 3 次 run 的 **[min × 0.7, max × 1.3]** 区间
  - 回答长度 **≥ 15 字（中文）且含至少一个标点符号**
- 基线在步 0 与 RAGAS 基线同日落盘（同问题跑 3 次记录 N 的 min/max）

### 7.5 legacy 开关两态验证

- `USE_LEGACY_LLM_FACTORY=true` 重启 → RAG 流式 + 纯文本 plain + agent 12 用例抽样回归通过（行为等价旧路径）
- 切回 false 重启 → 同一回归集通过（网关主路径）
- 对拍证据：步 1 的参数 diff 报告 + 两态回归输出入 changelog

### 7.6 HyDE 独立回归（hyde 角色专用，主 RAGAS 覆盖不到）

- 取附录 A 10 题中 3 题（央行 1 + 无人机 1 + 药品 1），显式 `use_hyde=True` 各跑一次：**基线（步 0 同日）vs 收尾（步 7 后）**
- 对比指标：**context_precision / context_recall**（HyDE 只影响检索 query 质量，不直接改生成参数）
- 判定同 §7.1：任一指标下降 >5% → revert 对应 commit（步 2 retrieval.py 切换的直接验收依据）
- 注意：`retrieve_documents(kb_id, question)` 不接 use_hyde 参数，回归脚本需走 `retrieve_with_strategy(kb_id, question, use_hyde=True)`（rag_chain.py:316）取 contexts——步 0 基线脚本即按此接口落盘，避免基线/收尾两轮口径不一致

### 7.7 其他

- P0-3a 回归子集：意图 12 用例 ≥11/12、5 终止场景 5/5、AgentToolLog 面板可用
- 零新依赖：requirements.txt / package.json 零 diff
- 锁图标不减少（openapi security 计数 ≥23）

## 8. 回滚方案

| 场景 | 动作 |
|---|---|
| 某禁区 commit 后 RAGAS 降 >5% | `git revert` 该单 commit（步 2-5 一处一 commit 保证可独立 revert）；591 为独立 commit 可单独撤 |
| 运行时异常（RAGAS 未覆盖的路径出问题） | `.env` 设 `USE_LEGACY_LLM_FACTORY=true` + 重启——行为等价旧路径（§5.3），先恢复服务再排查 |
| 网关本身有 bug | legacy 开关同上；或 revert commit B（网关新建）连带 revert 依赖它的 C-G |
| 上线后长期观察期 | 开关保持可切；连续两个版本无问题后，单独 commit 删除 legacy 分支（调用点零改动） |

## 9. D19 评估框架（可选子任务 A，实施阶段拍板，需求不拍板）

### 9.1 三个可选方案

| 方案 | 内容 | 改动面 |
|---|---|---|
| A 保持分类器优先 | status quo；search 为混合任务备用（D19 现状） | 零 |
| B 调整 few-shot | 分类 prompt 增加混合任务 few-shot，引导"检索+计算"类进 tool | classify_intent prompt（非禁区） |
| C 去掉分类器 | 问题全量进 Agent 循环，由 LLM 自主决定是否检索 | agent_stream 路由（禁区外但动主链路，大） |

### 9.2 评估标准

- 数据：5 个混合任务用例（附录 B）× 3 方案
- 指标：①意图判定正确率（A/B 方案）或工具选择正确率（C 方案）②端到端结果正确性（回答含正确计算结果 + 正确检索要点）③分类/循环耗时
- 判定：正确率与结果正确性优先，耗时同量级前提下取高者；**实施阶段跑完对比实验后拍板，结论写入 changelog 决策补充（D20+）**

### 9.3 与主任务边界

主任务（网关）不依赖本评估结论；评估实验全部在非禁区文件（prompt/路由）进行，若 C 方案需动禁区另出需求。

### 9.4 可选子任务 B：RAG 真流式（默认不做，登记论证）

- 现状 D10：Agent 答案伪流式（24 字切块）；RAG 侧本就真流式（rag_stream astream）
- 若做：需 rag_chain 暴露可组合子事件（3a §14 第 2 条），触及 prompt 组装周边 + 事件协议扩展，独立于网关——**不在本需求范围**，仅登记为 P1 候选

## 10. 边界决策（待实施补充）

- D20+：实施中若产生新边界决策（如 RAGAS judge 配置方案、legacy 分支的清理时机），按惯例登记 changelog 决策补充并回填本节

## 11. 任务分解（3 轮）

| 轮 | 内容 | 回归重点 |
|---|---|---|
| 第 1 轮 | 步 0-2：judge 可用性 + 10 题定稿 + 基线落盘 → llm_gateway + 对拍 → retrieval 切换 | RAGAS 基线落盘质量（四指标齐全）；对拍零漂移；context 指标不降 |
| 第 2 轮 | 步 3-5：rag_chain 三处（_get_llm → _get_chat_llm → 591 内联独立 commit） | 每个 commit 后 RAGAS 全量；591 独立端到端；带图/降级冒烟 |
| 第 3 轮 | 步 6-7：agent 切换 → legacy 两态全回归 → （可选）D19 对比实验拍板 → 文档收尾 | P0-3a 子集；开关两态；四指标终验 ≤5% 降 |

---

## 附录 A：RAGAS 10 题问题集（草案，步 0 定稿）

> 全部带 ground_truth（从 document/ 测试文档人工提炼）；kb2 为药品说明书（3 题）、kb1 央行（4 题）、kb3 无人机（3 题）。ground_truth 与题面在步 0 落盘到 `docs/benchmarks/qa-pairs-p03b.json`，本附录只列题面骨架：
> 1-3. 司库奇尤单抗适应症/用法/储存（kb2）；4-7. 央行职能/机构设置/货币政策职责/反洗钱职责（kb1）；8-10. 无人机集群通信关键技术/组网方式/挑战（kb3）

## 附录 B：D19 评估 5 混合任务用例（草案）

> ①"先算 (3+5)*12/2，再查一下资料里反洗钱相关内容" ②"查一下央行职能，顺便现在几点" ③"计算 123*456" ④"总结央行主要职能" ⑤"你好呀最近怎么样"——期望行为逐例在实验脚本中定稿

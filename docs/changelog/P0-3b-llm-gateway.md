# P0-3b LLM 网关统一 — changelog

> 需求文档：docs/requirements/P0-3b-llm-gateway.md（v1.1）｜基线：docs/benchmarks/

## 步 0 review 整改（2026-10-15，用户 3 拍板 + 2 必做 + 1 建议 + 4 约束）

- **拍板 2 cwd 加固**（run_ragas_eval.py）：入口 faiss_index_dir 预检断言 / 每题 n_contexts>0 校验（空即 raise）/ 落盘前健康门槛（四指标全 0 或 faithfulness nan/<0.5 拒绝写入）
- **拍板 3**：requirements.txt 补 `nltk==3.9.2`（ragas 0.2.3 隐式依赖）
- **必做 1 kb1-01 nan 根因**（已坐实）：ragas faithfulness 只评以 `./。/!/！` 结尾的句子（`_faithfulness.py` sentences_with_index 过滤），kb1-01/kb1-02 的 answer 为全分号 markdown 列表（`1. **xxx**；`）→ 整篇被过滤 → 空 statements → nan；**nan 是概率性的**（最后一条是否句号收尾取决于 LLM 生成），与 judge/max_tokens 无关（512/1024 均复现）
- **4 约束归一化（约束 1 档位）**：必做档＝分号行尾→句号、无句读行尾补句号、剥 `[来源:...]`；剥 `**`/剥 `#` 经对照**切句结构 10/10 无变化，按"不变就不剥"未纳入**；纯规则实现无 LLM（约束 4）
- **约束 3**：v1 基线重命名 `*-v1-superseded.*` + 头部作废说明；v2 命名 `*v2-{date}.*`

## DeepSeek API 事故时间线（2026-10-14 晚—10-15 凌晨）

| 轮次 | 阶段 | 结果 | 防御拦截 |
|---|---|---|---|
| 1 | 在线收集 ✓ + evaluate | faithfulness 10 题全 TimeoutError（judge API 波动，拖 1:29） | 健康门槛拦截，未落盘 |
| 2 | RunConfig(timeout=300,retries=10) evaluate | 轻 job 21s 过，长 job 卡 100 分钟批量超时（retry 叠加放大） | 手动终止 |
| 3 | 在线收集 | rag_query kb1 TCP 挂起 3 小时（业务链路无 timeout） | kill -9；评估脚本加 wait_for |
| 4 | 在线收集（防御版） | kb2 rag_query 挂 180s | wait_for 打断 fail-fast ✓ |
| 5 | 在线收集（题级重试版） | kb1 三连挂 | 重试 3 次后 fail-fast ✓ |
| 6 | **--from-rows 离线 evaluate** | judge 40/40 全 503/超时，四指标全 nan | 健康门槛拦截，未落盘 ✓ |

**根因（服务端明牌）**：`503 Service is too busy. We advise users to temporarily switch to alternative LLM API service providers.`（DeepSeek 中转过载，官方建议换服务商）。**本次评估受阻基于"judge 服务不可用"这一外部事实，不是方案缺陷**；评审受挫期间防御体系（cwd 预检 / n_contexts 校验 / 健康门槛 ×3 / wait_for 挂起防御 / 题级重试 / RunConfig fail-fast）全部按设计工作，零垃圾基线落盘。

**衍生基建**：`--from-rows`（复用 v1 rows + 本地归一化，跳过 rag_query 收集）、`--dry-run`（固定假分数走健康门槛+落盘全链路，不依赖真实 API；已双组验证通过，并暴露修复 rows_source 作用域 bug）、RunConfig(timeout=120, retries=3, workers=8)、收集阶段 wait_for(180s) + 题级重试(3)。

## TODO（待 DeepSeek API 恢复）

> 执行（命令已验证至落盘全链路，仅依赖 judge API 可用）：
>
> ```bash
> python3 scripts/run_ragas_eval.py --qa-file docs/benchmarks/qa-pairs-p03b.json --group main --label baseline-main-v2 --from-rows docs/benchmarks/P0-3b-baseline-main-v1-superseded-2026-10-14.json
> python3 scripts/run_ragas_eval.py --qa-file docs/benchmarks/qa-pairs-p03b.json --group hyde --label baseline-hyde-v2 --from-rows docs/benchmarks/P0-3b-baseline-hyde-v1-superseded-2026-10-14.json
> ```
>
> 产出 `docs/benchmarks/P0-3b-baseline-{main,hyde}-v2-{date}.{json,md}`；通过健康门槛后 v2 为现行基线，v1 正式作废（P0-3b 步 2 起的 RAGAS 回归均以 v2 为基准）。

## 遗留问题（P1 评估）

> **遗留问题**：plain_chat_stream 三路路由的前置检查不一致——`_get_chat_llm`（带图）有 CHAT_API_KEY 空则回退 `_get_llm`；591 内联（纯文本）无前置检查，空 key 走构造层抛 OpenAIError（500）。P0-3b 保持精确复刻未统一；P1 评估是否统一三路前置检查。

## 步 1：llm_gateway.py 新建 + 5 处全量对拍（2026-10-15）

**网关落盘**：

- `backend/app/core/llm_gateway.py`（新建，197 行）：`RoleSpec` frozen dataclass 注册表（5 角色 → settings 字段名 + 采样参数，不存配置值）；`get_llm()` 判定链＝legacy 分支 → KeyError → 整角色回退（`on_empty_api_key`，复刻 rag_chain.py:460-462）→ 逐字段 or 回退（可混搭，复刻 agent_service.py:79-81）→ 无回退时 `raise_if_empty` 前置检查（复刻各旧工厂差异）；`_legacy_get_llm()` 字面复刻 5 处旧工厂（来源行号在注释），供 `USE_LEGACY_LLM_FACTORY=true` 回滚窗口
- `config.py` 新增 `use_legacy_llm_factory: bool = False`（默认 false，业务行为零变化）；`.env.example` 同步注释
- Python 3.9 兼容：函数签名注解统一 `Optional`（`X | None` 求值语法踩坑已在实现期修复）

**对拍结果（scripts/smoke_test_llm_gateway.py，23/23 通过零漂移）**：

| 场景 | 项数 | 内容 |
|---|---|---|
| 1 常规构造 | 8 | 5 角色 × streaming 变体 + agent temperature 覆盖 + 591 字面构造，6 字段 snap 对比（model_name/temperature/max_tokens/streaming/openai_api_key/openai_api_base，屏蔽 api_key vs openai_api_key 参数名别名） |
| 2 整角色回退 | 2 | CHAT_API_KEY 置空 → chat_multimodal 回退 rag_generate 全套参数（含 temp/max_tokens 连切，streaming 透传） |
| 3 逐字段回退 | 4 | agent 三字段分别置空 + 全空，混搭语义保持 |
| 4 缺失语义 | 3 | rag_generate ValueError 消息一致；hyde 双 raise；chat_text 双方构造层抛同类异常 |
| 5 legacy 两态 | 6 | `use_legacy_llm_factory=True` 下网关内部复刻 vs 旧工厂直调，含回退路径 |

**对拍期间的语义澄清**（已如实写入脚本注释）：初版场景 4 误设"chat_text 空 key 照样构造成功后对比参数"，实测 ChatOpenAI 在 api_key 为空时 validate_environment 直接抛 `OpenAIError` 构造不出实例——即 591 原内联在 CHAT_API_KEY 空时同样无法构造成功，其真实语义是"无前置检查、构造层抛 OpenAIError"（而非"不报错"）。用例已改为断言双方抛同类异常，网关 `chat_text` 角色保持 `raise_if_empty=False` 不做前置检查，精确复刻而非悄悄统一。

**边界**：对拍纯构造不调 LLM（ChatOpenAI 实例化不发网络请求），不受 DeepSeek 故障影响；禁区文件只读 import 未改动。步 1 完成，按用户指令停步，不进入步 2（等 v2 基线产出）。

### 等待期补强（2026-10-15，3 检查点 + 1 并行任务）

- **检查点 1 遗留登记**：见上方“遗留问题”节（plain_chat_stream 三路前置检查不一致，P1 评估统一）
- **检查点 2 dry-run 命名防混淆**：`_write_report` 加 dry_run 参数——产物文件名强制 `-dryrun` 后缀 + md 头部警示行 + meta.dry_run 标记。理由：固定假分数（0.9/0.8/0.7/0.6）能通过健康门槛，若沿用正式 label 落盘会产生“看起来像主基线”的混淆文件。实测（--dry-run + 故意用正式 label baseline-main-v2）落盘 `P0-3b-baseline-main-v2-dryrun-2026-10-15.{json,md}`，验证后已删除；`ls docs/benchmarks/` 确认仅 v1-superseded + 591 + qa-pairs，无混淆文件
- **检查点 3 复刻来源可追溯**：`_legacy_get_llm` docstring 增加来源表（角色 × 来源位置 × git blame commit，行号基准 ddaf841）：rag_generate←rag_chain.py:114-126（0e86d4f 初始提交）、chat_multimodal←458-470（f4ce9fe→9d84322→035fd31 三次演化）、chat_text←591-598（9d84322）、hyde←retrieval.py:20-32（0e86d4f）、agent←agent_service.py:77-84（6973111 P0-3a 第 1 轮）；删除 legacy 分支前先 blame 复核原工厂未被后续改动，再以 §7.5 两态回归兜底
- **并行任务 legacy 对拍扩展**：场景 5 从 6 项扩至 12 项——5.1 常规（5 角色 + streaming/temperature 变体）、5.2 整角色回退、5.3 逐字段回退（与场景 3 同 4 情形），全量 **29/29 通过零漂移**；边界：仅构造参数对拍，未跑 §7.5 完整两态回归（需真实 RAG 请求，留待 API 恢复后）


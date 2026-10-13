# pdf-rag-assistant 工程规范（主入口）

## 项目简介

多知识库 RAG 问答系统（PDF/DOCX/MD 上传 → 切分 → 向量化 → 混合检索 → 引用溯源问答），演进目标：**企业知识库智能客服 + Agent 平台**。
技术栈：FastAPI + SQLAlchemy 2 async + SQLite + LangChain + FAISS + BM25 ｜ React 18 + TS strict + Antd 5 + Vite ｜ DeepSeek / GLM 多模型。

## 当前进度

- ✅ **P0-1 鉴权强制执行 + 数据归属**（2026-10-13，基线 commit `f575eba`，范例：`docs/requirements/P0-1-auth.md`）
- ⬜ **P0-2 service 层抽取 + 异常分层**（待启动）
- ⬜ P0-3 LLM 网关统一 + Agent 工具基座

## 🔴 核心工作流（每次新任务必须执行，逐条写死不可裁剪）

1. **先写需求文档再动代码**：在 `docs/requirements/Px-y-slug.md` 写背景/目标/任务分解/验收标准，**用户确认后才能改代码**
2. **改动完成后写改动日志**：在 `docs/changelog/Px-y-slug.md` 追加本轮记录（每任务一个文件、时间倒序、不新建），必含：改动文件清单 / 关键 diff 摘要 / 验收结果 / 遇到的问题 / 遗留事项
3. **架构级决策写 ADR**：`docs/decisions/NNN-slug.md`（编号 + 标题 + 背景 + 决策 + 理由 + 影响）；写/不写边界见 `docs/decisions/README.md`
4. **RAG 核心链路改动必须先在需求文档说明理由**，用户确认后才改（禁区清单见下节）
5. **改动前 commit 基线、改动后 commit 收尾**：message 格式 `[P0-2] service 层抽取 - 新增 kb_service`；commit 前必须经用户交互确认 message

## 🔴 RAG 改动禁区（内联，防 AI 误改）

以下 5 个文件**任何改动**（含参数默认值、prompt、签名）都必须先在需求文档中说明理由并获用户确认：

```
backend/app/core/loader.py         # 文档解析
backend/app/core/splitter.py       # 文本切分
backend/app/core/retrieval.py      # 混合检索（向量+BM25+RRF）
backend/app/core/vector_store.py   # FAISS 多库隔离
backend/app/core/rag_chain.py      # LCEL 问答链 + SSE + 语义缓存 + HyDE
```

只读引用（import 调用其公开函数）不属于禁区。详细约束与调优基线见 `docs/rules/50-rag-chain.md`。

## 常用命令

```bash
# 后端（cwd: backend）
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload   # 启动（Swagger: /docs）
# 前端（cwd: frontend）
npx vite --port 3000        # 启动
npx tsc -b                  # 类型检查（交付必过）
# 迁移 / 运维（cwd: 项目根）
python3 scripts/migrate_add_user_id.py          # 幂等迁移（范例）
python3 scripts/reset_password.py <用户名> <新密码>   # 重置密码
python3 scripts/rebuild_index.py                # 重建向量索引
python3 scripts/run_ragas_eval.py               # RAGAS 评估（禁区改动后必跑）
# 编译检查
cd backend && python3 -m py_compile app/**/*.py
```

## 功能开发过程中，必须执行

1. 不要删除我的注释，如果注释功能已经不匹配了，可以更新我的注释

## 每次功能开发完成后，必须执行以下收尾动作：

1. **更新 README.md**：在"核心亮点"和相关章节中体现新功能，确保用户能从 README 了解到完整的功能列表
2. **检查 requirements.txt / package.json**：如果新增/移除了依赖，同步更新
3. **数据库迁移**：如果修改了数据模型，确保已执行 ALTER TABLE 或提供迁移脚本
4. **重启后端**：如果修改了后端代码（Python），必须自动重启后端服务让代码生效
5. **更新文档**：如果新增、修改、删除模型后请注意同步更新相关文档比如 readme.md、重难点以及遇到的问题.md 文档、汇总项目用到的模型.md；如果解决了一些我反馈的 bug 或者你做的优化都要同步的更新 readme.md、重难点以及遇到的问题.md 文档

## 代码规范：

- 所有敏感配置（API Key 等）只能写在 `.env` 中，代码中通过 `settings.xxx` 引用
- 前后端接口变更时，前端类型定义（`api.ts`）必须同步更新
- 新增的持久化字段，必须同时处理"写入"和"读取恢复"两个方向（避免刷新后数据丢失）

## 回复风格：

- 直奔主题，不要冗余解释
- 修改代码后给出简洁的验证方式

## 规范文档索引（docs/rules/，动手前按需读）

| 文件 | 何时读 |
|---|---|
| `docs/rules/00-project-context.md` | 不了解项目背景/进度时 |
| `docs/rules/10-architecture.md` | 涉及分层、import 方向、目录归属时 |
| `docs/rules/20-coding-style.md` | 写任何代码前 |
| `docs/rules/30-api-conventions.md` | 新增/修改 API 端点时 |
| `docs/rules/40-database.md` | 改模型、写迁移脚本、涉及 user_id 归属时 |
| `docs/rules/50-rag-chain.md` | 任何可能触碰 RAG 链路的场景 |
| `docs/rules/90-workflow.md` | 每个任务的留痕流程细节（changelog 追加规则等） |

## 操作手册与子代理模板（.claude/，@ 引用使用）

| 文件 | 用途 |
|---|---|
| `.claude/skills/add-api-endpoint.md` | 新增端点的 7 步清单 |
| `.claude/skills/add-service.md` | service 函数签名/异常/返回值规范 |
| `.claude/skills/add-db-migration.md` | 迁移脚本模板 |
| `.claude/skills/add-agent-tool.md` | Agent 工具接入（P0-3 细化） |
| `.claude/skills/verify-change.md` | 验证清单模板（功能/回归/边界/权限矩阵） |
| `.claude/agents/feature-dev.md` | 功能开发子代理角色约束 |
| `.claude/agents/code-reviewer.md` | 代码审查子代理检查项 |
| `.claude/agents/verification.md` | 验证子代理执行原则与报告格式 |

## 写 README.md 可以参考下面要求：

面向 GitHub 开源学习者的友好文档，重点是让新手能快速理解、搭建和学习。包括但不限于简单介绍、核心亮点、技术展、项目结构、系统架构、处理流程、功能清单、快速启动、常见问题、核心模块解读、进阶方向等，对学习者友好的，能快速帮助新手上手的

上面的不是固定一成不变的，要根据项目灵活的安排，只是提供了一些方向。

要让 GitHub 项目更容易被搜到，主要需要做以下几件事：

添加 Topics（标签） — GitHub 搜索权重最高的因素之一
完善 About 描述 — 仓库右侧的 Description
README 开头加关键词密度高的描述 — GitHub 搜索会索引 README
添加 LICENSE — 开源项目的标配，增加可信度

## 如何使用这套 Harness

**用户（发起任务）**：新任务直接说"请按 AGENTS.md 规范开始 P0-2"，并附一句任务目标。AI 会先产出 `docs/requirements/P0-2-xxx.md` 等你确认，不会直接动代码。

**AI 的加载行为**：
- **自动加载**：本文件（AGENTS.md）——每次会话生效，核心工作流与禁区无需手动引用
- **按需读取**：AI 按上面的索引表主动读 `docs/rules/*` 与涉及的任务文档
- **手动 @ 引用**（你希望 AI 严格对照某份手册时）：如 `@.claude/skills/add-service.md`、`@.claude/agents/code-reviewer.md`、`@docs/rules/50-rag-chain.md`
- **斜杠命令**：`.claude/skills/*` 目前是普通手册，不注册为斜杠命令；如需斜杠化，后续按 Qoder 原生 skill 格式（SKILL.md + frontmatter）改造

**典型一轮流程**：需求文档 → 你确认 → 基线 commit → 实施（可派子代理，用 agents 模板做 prompt 约束）→ changelog 追加 → （ADR 视情况）→ 收尾 commit。

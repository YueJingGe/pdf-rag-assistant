# 00 项目上下文（Project Context）

> AI 与协作者开始任何工作前先读本文，了解"我们做的是什么、走到哪了"。

## 一句话定位

**pdf-rag-assistant** 是一个多知识库 RAG 问答系统（文档上传 → 解析切分 → 向量化 → 混合检索 → 引用溯源回答），当前演进方向是**企业知识库智能客服 + Agent 平台**。

## 技术栈

| 端 | 技术 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2 (async) + SQLite (aiosqlite) + LangChain + FAISS + BM25 (rank_bm25) |
| LLM | DeepSeek（RAG 问答）/ GLM-4V-Flash（多模态）/ GLM-4-Flash-250414（联网），通过 langchain-openai 兼容接口接入 |
| 前端 | React 18 + TypeScript (strict) + Ant Design 5 + Vite + CSS Modules (less) |
| 部署 | docker-compose（nginx 反代 + 前后端双容器） |

## 路线图与当前阶段

- **P0 基础补强**（当前阶段）：把"能跑的 demo"补成"有工程底子的系统"
  - ✅ **P0-1 鉴权强制执行 + 数据归属**（2026-10-13 完成，基线 commit `f575eba`）
  - 🔨 **P0-2 service 层抽取 + 异常分层**（进行中）
  - ⬜ P0-3 LLM 网关统一 + Agent 工具基座
- **P1 产品完整**：知识库授权管理 API、会话历史完善、文档管理增强
- **P2 加分项**：RAGAS 评估自动化、多租户、缓存与性能

## 已完成模块索引

| 模块 | 关键文件 | 说明 |
|---|---|---|
| 认证与权限 | `backend/app/core/auth.py` | require_user / require_admin / has_kb_permission / ensure_kb_permission |
| 数据模型 | `backend/app/models/` | user / knowledge_base / document / conversation / feedback（均含 user_id 归属，feedback 除外） |
| API 路由 | `backend/app/api/` | 5 个 router 共 29 端点，全部挂载鉴权 |
| RAG 链路 | `backend/app/core/loader|splitter|retrieval|vector_store|rag_chain` | **改动禁区**，见 `50-rag-chain.md` |
| 运维脚本 | `scripts/` | migrate_add_user_id / reset_password / rebuild_index / run_ragas_eval |
| 前端 | `frontend/src/` | App.tsx（登录门 + 401 监听）、services/api.ts（401 拦截器）、hooks/useSSE.ts |

## 历史背景（为什么不走捷径）

- 项目经评估存在"认证工具已写好但业务路由零挂载"的缺陷 → P0-1 已修复
- 数据库选型维持 SQLite（个人/小团队部署简单），不用 Alembic，迁移走 `scripts/` 幂等脚本
- LLM 已统一 DeepSeek 为主问答模型，多模态/联网走 GLM 免费额度（见 `汇总项目用到的模型.md`）

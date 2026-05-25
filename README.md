# PDF RAG 智能问答系统 | PDF Knowledge Base QA with RAG

> 🚀 基于 DeepSeek + LangChain + FAISS 构建的**全栈 RAG（Retrieval-Augmented Generation）智能问答系统**，支持多知识库管理、混合检索、流式对话、OCR 扫描件识别，开箱即用的企业级文档问答解决方案。

[![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-blue?logo=react)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue?logo=typescript)](https://typescriptlang.org)
[![LangChain](https://img.shields.io/badge/LangChain-LCEL-orange)](https://langchain.com)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-purple)](https://deepseek.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**PDF RAG Assistant** 是一个面向学习者和开发者的开源 RAG 全栈项目，涵盖文档解析（PDF/DOCX/TXT/Markdown）、向量化存储（FAISS）、混合检索（向量 + BM25）、LLM 流式生成（DeepSeek/GLM）、多模态理解（图片/文件）、语义缓存、引用溯源等完整 RAG 工程实践。适合用于学习 LangChain、RAG 架构、向量数据库、Prompt Engineering、SSE 流式通信等技术。

**Keywords**: RAG, Retrieval-Augmented Generation, PDF问答, 知识库问答, LangChain, FAISS, DeepSeek, 向量检索, 文档智能, OCR, 混合检索, 流式对话, FastAPI, React, 全栈项目, AI应用开发, LLM应用

### 核心亮点

- 🔍 **混合检索**：向量相似度 + BM25 关键词检索，提升召回率
- 📊 **表格感知**：针对 PDF 中的表格数据优化解析，保留结构信息
- 🖼️ **OCR 支持**：扫描件 PDF 自动 tesseract 文字识别（本地处理，不消耗 token）
- 🌐 **联网搜索**：普通聊天模式支持一键开启联网搜索（glm-4-flash-250414 + web_search 工具），获取实时信息（免费）
- 📎 **文件理解**：上传 PDF/Word/Excel 等文件，智谱 AI 文件解析后直接问答（免费）
- 🖼️ **图片理解**：上传图片进行多模态对话，GLM-4V-Flash 免费图片识别
- 🤖 **智能路由**：自动根据输入类型选择最优模型（有图 → 多模态模型，纯文本 → 文本模型）
- 💬 **流式响应**：基于 SSE 实时流式输出，体验流畅
- 📖 **引用溯源**：回答关联原文段落，点击即可定位到源文档
- 💾 **语义缓存**：相似问题命中缓存，显著降低 API 调用成本
- 🔐 **多租户隔离**：每个知识库独立 FAISS 索引，数据互不干扰

## 技术栈

| 层级     | 技术                                       |
| -------- | ------------------------------------------ |
| 后端     | Python 3.9+ / FastAPI + Uvicorn            |
| RAG 编排 | LangChain + LCEL                           |
| LLM      | DeepSeek API（兼容 OpenAI 格式）           |
| 嵌入     | text-embedding-v3 / BAAI/bge-small-zh-v1.5 |
| 向量库   | FAISS（多知识库隔离）                      |
| 前端     | React 18 + TypeScript + Ant Design 5       |
| 通信     | RESTful API + SSE 流式响应                 |
| 认证     | JWT + OAuth2（可对接企业 SSO）             |
| 可观测性 | Langfuse + RAGAS                           |
| 部署     | Docker Compose + Nginx                     |

## 项目结构

```
pdf-rag-assistant/
├── backend/
│   ├── app/
│   │   ├── api/                    # API 路由层
│   │   │   ├── auth.py             # 用户认证（注册/登录/JWT）
│   │   │   ├── chat.py             # 问答接口（流式/非流式）
│   │   │   ├── documents.py        # 文档管理（上传/删除/重命名）
│   │   │   ├── feedback.py         # 检索反馈（统计/导出）
│   │   │   └── knowledge_bases.py  # 知识库 CRUD
│   │   ├── core/                   # 核心业务逻辑
│   │   │   ├── auth.py             # JWT 认证工具
│   │   │   ├── config.py           # 配置管理（读取 .env）
│   │   │   ├── embeddings.py       # 嵌入模型初始化
│   │   │   ├── loader.py           # 文档加载器（PDF/DOCX/TXT/MD + OCR）
│   │   │   ├── rag_chain.py        # RAG 链编排（LCEL）
│   │   │   ├── retrieval.py        # 混合检索（向量 + BM25）
│   │   │   ├── splitter.py         # 文本分块策略
│   │   │   └── vector_store.py     # FAISS 向量存储管理
│   │   ├── models/                 # 数据模型（SQLAlchemy ORM）
│   │   │   ├── conversation.py     # 对话/消息模型
│   │   │   ├── database.py         # 数据库连接
│   │   │   ├── document.py         # 文档元数据模型
│   │   │   ├── feedback.py         # 反馈数据模型
│   │   │   ├── knowledge_base.py   # 知识库模型
│   │   │   └── user.py             # 用户模型
│   │   ├── utils/                  # 工具函数
│   │   └── main.py                 # FastAPI 应用入口
│   ├── data/                       # 运行时数据（不提交到 Git）
│   │   ├── db.sqlite3              # SQLite 数据库
│   │   ├── faiss_indexes/          # FAISS 向量索引文件
│   │   └── uploads/                # 用户上传的原始文档
│   ├── .env.example                # 环境变量模板（带详细注释）
│   └── requirements.txt            # Python 依赖
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWindow/         # 聊天窗口（流式消息展示）
│   │   │   ├── CitationView/       # 引用来源展示
│   │   │   ├── DocumentUpload/     # 文档上传组件
│   │   │   ├── DocumentViewer/     # 文档内容查看（Drawer）
│   │   │   ├── FeedbackDashboard/  # 反馈统计面板
│   │   │   ├── KnowledgeBaseSidebar/ # 知识库侧边栏
│   │   │   ├── LoginModal/         # 登录/注册弹窗
│   │   │   └── RetrievalDebugPanel/# 检索调试面板
│   │   ├── hooks/
│   │   │   └── useSSE.ts           # SSE 流式连接 Hook
│   │   ├── services/
│   │   │   └── api.ts              # API 请求封装
│   │   ├── App.tsx                 # 主应用组件
│   │   └── index.tsx               # 入口文件
│   ├── package.json
│   └── vite.config.ts              # Vite 构建配置（含代理）
├── scripts/
│   ├── rebuild_index.py            # 重建向量索引
│   └── run_ragas_eval.py           # RAGAS 离线评估
├── .gitignore
└── README.md
```

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ ChatWindow│ │DocUpload │ │DocViewer │ │RetrievalDebug │  │
│  └─────┬────┘ └────┬─────┘ └────┬─────┘ └──────┬────────┘  │
└────────┼───────────┼────────────┼───────────────┼───────────┘
         │ SSE       │ REST      │ REST          │ REST
┌────────┼───────────┼────────────┼───────────────┼───────────┐
│        ▼           ▼            ▼               ▼            │
│                     FastAPI Backend                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   API Layer (Router)                  │    │
│  ├──────────┬──────────┬──────────┬──────────┬─────────┤    │
│  │  auth    │   chat   │   docs   │    kb    │feedback │    │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬────┘    │
│       │          │          │          │          │          │
│  ┌────▼──────────▼──────────▼──────────▼──────────▼────┐    │
│  │                  Core Layer                          │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │    │
│  │  │rag_chain │ │retrieval │ │    loader (OCR)    │  │    │
│  │  └────┬─────┘ └────┬─────┘ └────────┬───────────┘  │    │
│  │       │             │                │              │    │
│  │  ┌────▼─────┐ ┌────▼─────┐ ┌────────▼───────┐     │    │
│  │  │DeepSeek  │ │  FAISS   │ │  SQLite DB     │     │    │
│  │  │  API     │ │  Index   │ │  (metadata)    │     │    │
│  │  └──────────┘ └──────────┘ └────────────────┘     │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### RAG 处理流程

```
用户提问 → 历史上下文拼接(最近5轮) → 查询改写(HyDE可选)
    ↓
混合检索: FAISS向量相似度 + BM25关键词匹配
    ↓
语义缓存命中判断(余弦相似度 > 阈值则直接返回缓存)
    ↓
Top-K 文档片段 → Prompt 组装(System + Context + Question)
    ↓
DeepSeek API 流式生成 → SSE 推送到前端
    ↓
返回答案 + 引用来源(chunk metadata)
```

## 功能清单

### 用户认证

- **注册 / 登录**：JWT Token 认证，支持 Bearer Token 鉴权
- **RBAC 权限**：owner / member / viewer 三级角色控制

### 智能问答

- **多轮对话**：自动管理对话历史，Prompt 注入最近 5 轮上下文
- **普通聊天**：用 智谱 AI GLM-4V-Flash 处理多模态 + GLM-4-Flash-250414 支持联网搜索，不依赖知识库的通用对话能力，支持图片、文档上传
- **知识库问答**：基于上传文档的精准检索增强生成
- **HyDE 检索**：API 级别 `use_hyde` 参数，支持 A/B 测试对比
- **引用溯源**：点击引用段落 → 右侧 Drawer 打开文档并高亮定位
- **检索调优面板**：调试视图展示 top_k chunks、相关性评分、反馈导出
- **会话持久化**：刷新页面保留当前知识库和对话（localStorage）

### 文档管理

- **多格式支持**：PDF / DOCX / TXT / Markdown
- **扫描件 OCR**：pytesseract + pdf2image 本地识别（不消耗 token）
- **加密 PDF**：支持解密后解析（依赖 cryptography 包）
- **文档操作**：上传 / 重命名 / 删除，实时状态反馈（就绪/上传中/失败）

### 知识库管理

- 知识库 CRUD（新增 / 重命名 / 删除）
- 每个知识库独立 FAISS 索引，数据隔离

### 可观测性

- **Langfuse 追踪**：全链路请求追踪，检索效果可视化
- **RAGAS 评估**：离线评估检索质量和生成质量

## 快速启动

### 环境要求

- Python 3.9+
- Node.js 18+
- npm 9+

### 首次安装

```bash
# 后端依赖
cd backend
pip install -r requirements.txt
cp .env.example .env  # 编辑 .env 填入 API Key

# 前端依赖
cd ../frontend
npm install
```

### 启动前后端

```bash
# 启动后端（在项目根目录执行）
cd backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 启动前端（新开一个终端，在项目根目录执行）
cd frontend
npx vite --host 127.0.0.1 --port 3000
```

启动后访问：

- **前端页面**: `http://127.0.0.1:3000`
- **后端 API**: `http://127.0.0.1:8000`
- **API 文档**: `http://127.0.0.1:8000/docs`

### 重启后端

在终端里按 Ctrl+C 停止后端，然后重新启动：

```bash
cd /Users/a211026/Desktop/ai/pdf-rag-assistant/backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 后台启动（不占用终端）

```bash
# 后台启动后端
cd backend
nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > /tmp/backend.log 2>&1 &

# 后台启动前端
cd frontend
nohup npx vite --host 127.0.0.1 --port 3000 > /tmp/frontend.log 2>&1 &
```

### 停止服务

```bash
# 停止后端
pkill -f "uvicorn app.main"

# 停止前端
pkill -f "vite"

# 或一键停止前后端
pkill -f "uvicorn app.main"; pkill -f "vite"
```

### 重启服务

```bash
# 一键重启前后端
pkill -f "uvicorn app.main" 2>/dev/null; pkill -f "vite" 2>/dev/null; sleep 2
cd backend && nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > /tmp/backend.log 2>&1 &
cd ../frontend && nohup npx vite --host 127.0.0.1 --port 3000 > /tmp/frontend.log 2>&1 &
```

### 查看日志

```bash
# 后端日志
tail -f /tmp/backend.log

# 前端日志
tail -f /tmp/frontend.log
```

### Docker 部署

```bash
cp backend/.env.example backend/.env  # 编辑填入 API Key
docker-compose up -d
# 访问 http://localhost
```

## API 概览（23 个端点）

| 方法   | 路径                                           | 说明                             |
| ------ | ---------------------------------------------- | -------------------------------- |
| POST   | `/api/auth/register`                           | 用户注册                         |
| POST   | `/api/auth/login`                              | 用户登录（返回 JWT）             |
| GET    | `/api/auth/me`                                 | 获取当前用户信息                 |
| POST   | `/api/knowledge_bases`                         | 创建知识库                       |
| GET    | `/api/knowledge_bases`                         | 列出所有知识库                   |
| DELETE | `/api/knowledge_bases/{id}`                    | 删除知识库                       |
| POST   | `/api/knowledge_bases/{id}/documents`          | 上传文档                         |
| GET    | `/api/knowledge_bases/{id}/documents`          | 文档列表                         |
| DELETE | `/api/knowledge_bases/{id}/documents/{doc_id}` | 删除文档                         |
| POST   | `/api/chat/stream`                             | 流式问答（SSE，支持 `use_hyde`） |
| POST   | `/api/chat/query`                              | 非流式问答（A/B 测试）           |
| GET    | `/api/chat/conversations/{kb_id}`              | 对话列表                         |
| GET    | `/api/chat/messages/{conversation_id}`         | 消息历史                         |
| DELETE | `/api/chat/conversations/{id}`                 | 删除对话                         |
| POST   | `/api/feedback`                                | 提交检索相关性反馈               |
| GET    | `/api/feedback/stats/{kb_id}`                  | 反馈统计                         |
| GET    | `/api/feedback/export/{kb_id}`                 | 导出反馈数据                     |
| GET    | `/api/health`                                  | 健康检查                         |

## 辅助脚本

```bash
# 重建知识库索引（当向量索引损坏或需要重新分块时使用）
python scripts/rebuild_index.py [kb_id]

# RAGAS 离线评估（评估检索质量和生成质量）
python scripts/run_ragas_eval.py <kb_id> [qa_pairs.json]
```

## 关键设计决策

### 为什么选择 FAISS 而非 Chroma / Milvus？

- **轻量级**：无需额外部署数据库服务，单文件索引即可运行
- **性能优秀**：百万级向量毫秒级检索，对中小规模知识库绰绰有余
- **多知识库隔离**：每个知识库一个独立索引文件，删除/重建互不影响

### 为什么选择 DeepSeek？

- **性价比极高**：中文理解能力强，价格远低于 GPT-4
- **兼容 OpenAI 格式**：可无缝替换为其他兼容 OpenAI API 的模型
- **流式输出支持好**：原生支持 SSE 流式生成

### 嵌入模型选择

系统支持两种嵌入方案，在 `.env` 中配置切换：

| 方案 | 模型                   | 优缺点                                |
| ---- | ---------------------- | ------------------------------------- |
| 本地 | BAAI/bge-small-zh-v1.5 | ✅ 免费无限调用 ❌ 首次加载需下载模型 |
| API  | text-embedding-v3      | ✅ 效果略优 ❌ 按 token 计费          |

### Token 消耗说明

每次 RAG 问答约消耗 **2000-4000 tokens**，主要构成：

- System Prompt: ~200 tokens
- 检索上下文（top_k chunks）: ~1500-3000 tokens
- 用户问题 + 历史对话: ~300-800 tokens

**节省建议**：

- 开启语义缓存，相似问题直接返回缓存结果
- 适当减小 `CHUNK_SIZE` 和 `TOP_K` 参数
- 普通聊天不走 RAG 链，直接调用 LLM

## 数据存储说明

运行时产生的数据存储在 `backend/data/` 目录下（不提交到 Git）：

| 文件/目录             | 说明                                            | 丢失影响               |
| --------------------- | ----------------------------------------------- | ---------------------- |
| `data/db.sqlite3`     | SQLite 数据库（用户、知识库、对话、文档元数据） | 所有业务数据丢失       |
| `data/faiss_indexes/` | FAISS 向量索引文件                              | 需重新上传文档重建索引 |
| `data/uploads/`       | 用户上传的原始文档                              | 无法查看原文和重建索引 |

**数据何时会丢失？**

- 手动删除 `backend/data/` 目录
- 重装系统且未备份该目录
- Docker 容器删除且未挂载持久化卷

**备份建议**：定期备份整个 `backend/data/` 目录即可恢复所有数据。

## 常见问题

### Q: 上传 PDF 后显示"0 个文本块"？

这通常是扫描件 PDF（图片型），需要安装 OCR 依赖：

```bash
# macOS
brew install tesseract tesseract-lang poppler

# Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim poppler-utils
```

### Q: 启动后端报 `ModuleNotFoundError`？

确保在正确的虚拟环境中安装了依赖：

```bash
cd backend
pip install -r requirements.txt
```

### Q: 前端请求报 CORS 错误？

确认后端已启动且端口正确。Vite 开发服务器已配置代理（`vite.config.ts`），所有 `/api` 请求会自动转发到后端 `http://127.0.0.1:8000`。

### Q: 如何切换嵌入模型？

编辑 `backend/.env`：

```bash
# 使用本地免费模型（推荐学习阶段使用）
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5

# 或使用 API（效果更好但收费）
EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v3
```

> ⚠️ 切换嵌入模型后，需要重新上传文档以重建向量索引（维度不同，旧索引不兼容）。

### Q: 如何降低 API 费用？

1. 使用本地嵌入模型（`EMBEDDING_PROVIDER=huggingface`）
2. 开启语义缓存（默认已开启）
3. 减小 `TOP_K` 值（如从 5 改为 3）
4. 普通对话不选择知识库，走直接 LLM 调用

## 开发指南

### 添加新的文档格式

1. 在 `backend/app/core/loader.py` 中添加加载函数
2. 在 `load_document()` 中注册文件后缀映射
3. 前端 `DocumentUpload` 组件的 `accept` 属性中添加新后缀

### 添加新的 API 端点

1. 在 `backend/app/api/` 下创建新的路由文件
2. 在 `backend/app/main.py` 中注册路由 `app.include_router(...)`
3. 前端 `services/api.ts` 中添加对应请求函数

### 自定义 Prompt

编辑 `backend/app/core/rag_chain.py` 中的 `SYSTEM_TEMPLATE` 变量，可自定义：

- 回答风格（简洁/详细/学术）
- 引用格式要求
- 拒答策略（无相关信息时的行为）

## License

MIT

# 10 架构分层（Architecture）

## 目录结构（注释版）

```
backend/
├── app/
│   ├── api/            # 路由层：参数校验 + 依赖注入 + 调下层 + 组装响应（thin）
│   ├── services/       # 服务层：业务逻辑（P0-2 建立，当前不存在属过渡态）
│   ├── core/           # 核心设施：auth/config/embeddings/loader/splitter/retrieval/vector_store/rag_chain
│   ├── models/         # ORM 模型 + database.py（async engine/session）
│   ├── utils/          # file_utils / logging
│   └── main.py         # FastAPI 实例、router 注册、lifespan(init_db)
├── data/               # 运行时数据（git 忽略）：db.sqlite3、uploads/、faiss_indexes/
└── requirements.txt
frontend/
├── src/
│   ├── components/     # 每组件一个目录：index.tsx + index.module.less
│   ├── hooks/          # useSSE（原生 fetch 流式）
│   ├── services/       # api.ts：axios 实例 + 全部接口函数 + TS 类型
│   └── App.tsx         # 登录门、401 监听、tab 布局
scripts/                # 运维脚本：迁移/重置密码/重建索引/RAGAS 评估
docs/                   # 工程规范与任务留痕
```

## 分层职责与依赖方向

```
api ──▶ services ──▶ core ──▶ models
 │          │                      ▲
 │          └──────────────────────┘
 └──▶ core(auth) / models（过渡期直接访问，P0-2 后收敛到 services）
```

| 层 | 允许 import | 禁止 |
|---|---|---|
| `api/` | services、core.auth、models（仅过渡期）、Pydantic schemas | 直接写业务逻辑（超过 20 行的流转必须下沉 service） |
| `services/` | core、models | import api；操作 HTTP 对象（Request/Response/HTTPException） |
| `core/` | models、utils、第三方库、`services.exceptions`（唯一例外：零依赖纯契约，见下方说明） | import api / services（除上述例外） |
| `models/` | 仅 SQLAlchemy 与标准库 | import 任何上层（**铁律**） |

## 现状声明（避免 AI 误判"不一致"）

0. `services/exceptions.py` 是分层规则的**唯一例外**：它是零依赖纯契约模块（只定义异常类），`core/auth.py` 引用它以抛领域异常（P0-2 D1 决策）。除此之外 core 不得 import services。

1. `services/` 层已于 P0-2 三轮全部建立（exceptions / kb_service / retrieval_service / document_service / chat_service / feedback_service），kb/documents/chat/feedback 四个路由文件已全部切薄；例外：`/api/chat/upload-file` 保留路由层（纯外呼编排 + 502 语义不在领域异常体系，见 changelog 第 2 轮例外登记）、auth.py 未纳入抽取范围。新代码不得再往路由里堆业务逻辑。
2. `core/auth.py` 是鉴权依赖（Depends 注入用），路由直接 import 它**不算违规**——它本质是 API 层的基础设施。
3. 前端只有一个全局 api 实例（`services/api.ts`），新接口一律加在该文件，不另起 axios 实例（SSE 除外，走 `hooks/useSSE.ts` 的原生 fetch）。

## 后端启动与注册链

`app/main.py` 注册 5 个 router（auth/knowledge_bases/documents/chat/feedback）→ lifespan 内 `init_db()`（`create_all`，不会给存量表加列，见 `40-database.md`）。

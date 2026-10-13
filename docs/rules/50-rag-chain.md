# 50 RAG 核心链路（改动禁区）

## ⛔ 禁区文件清单（任何改动先走需求文档 + 用户确认）

| 文件 | 职责 | 不可逆风险 |
|---|---|---|
| `backend/app/core/loader.py` | PDF/DOCX/MD 解析与文本抽取 | 换解析器 → 全库 chunk 质量变化，已建索引失效 |
| `backend/app/core/splitter.py` | 文本切分 | chunk 参数变化 → 旧索引与新检索不一致 |
| `backend/app/core/retrieval.py` | 混合检索（向量 + BM25 + RRF 融合） | 检索质量是系统生命线，参数与算法耦合调优 |
| `backend/app/core/vector_store.py` | FAISS 多库隔离加载/持久化 | 索引结构变化 → 存量 faiss_indexes 全部不可读 |
| `backend/app/core/rag_chain.py` | LCEL 问答链 + SSE 流式 + 语义缓存 + HyDE | prompt/链结构变化 → 输出质量回归需重新评估 |

**边界说明**：
- "改动"包括签名变更、参数默认值变更、prompt 变更、依赖库版本变更
- 只读引用（import 后调用其公开函数）**不属于禁区**；新增文件调用它们是正常扩展
- 即使是"一行小修"，也必须先在 `docs/requirements/Px-y-xxx.md` 中写明理由并获用户确认

## 调优基线（防止无意回退，改动需重新评估）

- chunk：1200 / overlap 150
- 检索：top_k 4，向量 + BM25 双路召回 → RRF 融合
- 缓存：语义缓存命中直接返回（不进 LLM）
- HyDE：默认开启，假设文档扩展查询
- 模型：DeepSeek（`settings` 配置），temperature 见 rag_chain 内配置

## 评估方式

改动后运行 `python3 scripts/run_ragas_eval.py` 对比基线指标（faithfulness / answer_relevancy / context_precision），无恶化才允许合入。

# RAGAS 基线：baseline-hyde-2026-10-14

> **已作废（v1）**：answer 归一化口径变更，由 v2 基线取代：P0-3b-baseline-hyde-v2-2026-10-14

- 日期：2026-10-14｜组别：hyde｜use_hyde=True｜题数：3
- judge：deepseek-v4-flash (temperature=0, max_tokens=512)｜embeddings：EMBEDDING_PROVIDER=huggingface, 与 FAISS 索引同源
- contexts 口径：retrieve_with_strategy(use_hyde=True) hybrid（与 answer 生成同源）
- **self-judging bias**：RAG 生成与 judge 同为 DeepSeek，指标绝对值可能偏高，但基线与收尾同源偏差可抵消
- **judge 配置锁定**：收尾跑必须使用完全相同的 judge 配置与 embeddings/contexts 口径，任一变更即失去对比基准意义

## 聚合四指标

| 指标 | 数值 |
|---|---|
| faithfulness | 0.9500 |
| answer_relevancy | 0.9296 |
| context_precision | 1.0000 |
| context_recall | 0.8333 |

**判定口径：任一指标较基线下降 >5% 即回滚对应 commit（需求文档 §8）**

## 逐题明细

| kb | 问题 | faithfulness | answer_relevancy | context_precision | context_recall |
|---|---|---|---|---|---|
| 1 | 我国货币供应量分为哪几个层次？各层次的构成是什么… | 1.0000 | 0.8975 | 1.0000 | 1.0000 |
| 2 | 司库奇尤单抗是什么类型的药物？它的作用机制是什么… | 1.0000 | 0.9488 | 1.0000 | 0.5000 |
| 3 | 低空无人机自组网有哪些特点导致传统路由协议性能受… | 0.8500 | 0.9425 | 1.0000 | 1.0000 |

# RAGAS 基线：baseline-main-2026-10-14

> **已作废（v1）**：kb1-01/kb1-02 faithfulness=nan（ragas 切句缺陷 × 全分号 markdown 列表 answer，详见附录外根因说明），由 v2 基线取代：P0-3b-baseline-main-v2-2026-10-14
>
> **TODO（待 DeepSeek API 恢复，2026-10-15 登记）**：
> ① `python3 scripts/run_ragas_eval.py --qa-file docs/benchmarks/qa-pairs-p03b.json --group main --label baseline-main-v2 --from-rows docs/benchmarks/P0-3b-baseline-main-v1-superseded-2026-10-14.json`
> ② `python3 scripts/run_ragas_eval.py --qa-file docs/benchmarks/qa-pairs-p03b.json --group hyde --label baseline-hyde-v2 --from-rows docs/benchmarks/P0-3b-baseline-hyde-v1-superseded-2026-10-14.json`
> 产出 `docs/benchmarks/P0-3b-baseline-{main,hyde}-v2-{date}.{json,md}`；通过健康门槛后 v2 为现行基线，v1 正式作废。命令已验证至落盘全链路（--dry-run），仅依赖 judge API 可用。

- 日期：2026-10-14｜组别：main｜use_hyde=False｜题数：10
- judge：deepseek-v4-flash (temperature=0, max_tokens=512)｜embeddings：EMBEDDING_PROVIDER=huggingface, 与 FAISS 索引同源
- contexts 口径：retrieve_with_strategy(use_hyde=False) hybrid（与 answer 生成同源）
- **self-judging bias**：RAG 生成与 judge 同为 DeepSeek，指标绝对值可能偏高，但基线与收尾同源偏差可抵消
- **judge 配置锁定**：收尾跑必须使用完全相同的 judge 配置与 embeddings/contexts 口径，任一变更即失去对比基准意义

## 聚合四指标

| 指标 | 数值 |
|---|---|
| faithfulness | 0.9845 |
| answer_relevancy | 0.7579 |
| context_precision | 0.8750 |
| context_recall | 0.8833 |

**判定口径：任一指标较基线下降 >5% 即回滚对应 commit（需求文档 §8）**

## 逐题明细

| kb | 问题 | faithfulness | answer_relevancy | context_precision | context_recall |
|---|---|---|---|---|---|
| 1 | 中国人民银行的主要职责有哪些？ | — | 0.9125 | 1.0000 | 1.0000 |
| 1 | 中国人民银行设置了哪些内设机构？ | — | 0.7620 | 0.5000 | 1.0000 |
| 1 | 中央银行的货币政策工具有哪些？ | 0.9474 | 0.9210 | 1.0000 | 1.0000 |
| 1 | 我国货币供应量分为哪几个层次？各层次的构成是什么… | 1.0000 | 0.8251 | 1.0000 | 1.0000 |
| 2 | 司库奇尤单抗注射液适用于治疗哪些疾病？ | 1.0000 | 0.8983 | 1.0000 | 1.0000 |
| 2 | 成人斑块状银屑病患者使用司库奇尤单抗的推荐剂量和… | 0.9286 | 0.0000 | 0.5000 | 0.3333 |
| 2 | 司库奇尤单抗是什么类型的药物？它的作用机制是什么… | 1.0000 | 0.9380 | 1.0000 | 0.5000 |
| 3 | 这篇论文提出的低空无人机自组网路由优化方法是什么… | 1.0000 | 0.4365 | 1.0000 | 1.0000 |
| 3 | 仿真实验中该方法与哪些传统路由协议进行了对比？性… | 1.0000 | 0.9243 | 0.7500 | 1.0000 |
| 3 | 低空无人机自组网有哪些特点导致传统路由协议性能受… | 1.0000 | 0.9612 | 1.0000 | 1.0000 |

"""RAGAS offline evaluation script for RAG quality assessment.

P0-3b 步 0 评估基建（非禁区）。口径元信息（与需求文档 §7.1/§7.6 对应）：
- judge LLM: DeepSeek（temperature=0, max_tokens=512），与 RAG 生成同源。
  self-judging bias：RAG 生成与 judge 同为 DeepSeek，指标绝对值可能偏高，
  但基线与收尾同源偏差可抵消（两轮同口径对比有效）。
- embeddings: 与 FAISS 索引同源（EMBEDDING_PROVIDER，当前 huggingface 本地
  bge-small-zh-v1.5）。
- contexts: retrieve_with_strategy(use_hyde=False)（hybrid，BM25+向量融合），
  与 answer 生成（rag_query 内部）同源——取代旧版 retrieve_documents（纯向量，
  与生成不同源）。HyDE 组（use_hyde=True，内部纯向量）与基线组 contexts 必然
  不同源，这正是 HyDE 效果对比的设计意图，不是口径 bug。

用法：
  # 主基线：10 题全量, use_hyde=False
  python scripts/run_ragas_eval.py --qa-file docs/benchmarks/qa-pairs-p03b.json \
      --group main --label baseline-main
  # HyDE 基线：hyde_group 3 题, use_hyde=True（§7.6）
  python scripts/run_ragas_eval.py --qa-file docs/benchmarks/qa-pairs-p03b.json \
      --group hyde --label baseline-hyde
"""

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# settings 的 faiss_index_dir / upload_dir / env_file 均为相对 cwd 路径（后端进程 cwd=backend），
# 脚本必须切到 backend 运行，否则索引解析到 <root>/data（仅 .gitkeep）→ 检索空 → 指标全 0
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv

# config.py 的 env_file=".env" 相对 cwd（已 chdir 到 backend，此处为双保险）
load_dotenv(BACKEND_DIR / ".env")

from app.core.config import settings  # noqa: E402
from app.core.embeddings import get_embedding_model  # noqa: E402
from app.core.rag_chain import rag_query, retrieve_with_strategy  # noqa: E402

DOCS_BENCH = PROJECT_ROOT / "docs" / "benchmarks"


def _build_judge_and_embeddings():
    """DeepSeek judge（temperature=0, max_tokens=512）+ 与索引同源 embeddings。"""
    from langchain_openai import ChatOpenAI
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper

    judge_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0,
            max_tokens=512,
        )
    )
    judge_embeddings = LangchainEmbeddingsWrapper(get_embedding_model())
    return judge_llm, judge_embeddings


async def _collect_all(qa_pairs: list[dict], use_hyde: bool) -> list[dict]:
    """收集 question/answer/contexts/ground_truth（asyncio 域）。"""
    rows = []
    for pair in qa_pairs:
        kb_id = pair.get("kb_id")
        if kb_id is None:
            print(f"Missing kb_id in qa entry: {pair['question'][:30]}")
            sys.exit(1)
        question = pair["question"]
        print(f"\nProcessing [kb{kb_id}] use_hyde={use_hyde}: {question}")
        result = await rag_query(kb_id, question)
        docs = await retrieve_with_strategy(kb_id, question, use_hyde=use_hyde)
        rows.append(
            {
                "kb_id": kb_id,
                "question": question,
                "answer": result["answer"],
                "contexts": [d.page_content for d in docs],
                "ground_truth": pair.get("ground_truth", ""),
            }
        )
    return rows


def _write_report(label: str, group: str, use_hyde: bool, rows: list[dict], agg: dict, per_q: list[dict]) -> None:
    """JSON 原始值 + md 报告双落盘到 docs/benchmarks/。"""
    DOCS_BENCH.mkdir(parents=True, exist_ok=True)
    meta = {
        "label": label,
        "date": date.today().isoformat(),
        "group": group,
        "use_hyde": use_hyde,
        "n_questions": len(rows),
        "judge": f"{settings.deepseek_model} (temperature=0, max_tokens=512)",
        "embeddings": f"EMBEDDING_PROVIDER={settings.embedding_provider}, 与 FAISS 索引同源",
        "contexts": "retrieve_with_strategy(use_hyde=%s) hybrid" % use_hyde,
        "self_judging_bias": "RAG 生成与 judge 同为 DeepSeek，指标绝对值可能偏高，但基线与收尾同源偏差可抵消",
    }

    json_path = DOCS_BENCH / f"P0-3b-{label}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "aggregate": agg, "per_question": per_q, "rows": rows}, f, ensure_ascii=False, indent=2)

    lines = [
        f"# RAGAS 基线：{label}",
        "",
        f"- 日期：{meta['date']}｜组别：{group}｜use_hyde={use_hyde}｜题数：{len(rows)}",
        f"- judge：{meta['judge']}｜embeddings：{meta['embeddings']}",
        f"- contexts 口径：{meta['contexts']}（与 answer 生成同源）",
        f"- **self-judging bias**：{meta['self_judging_bias']}",
        "",
        "## 聚合四指标",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
    ]
    for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        if k in agg:
            lines.append(f"| {k} | {agg[k]:.4f} |")
    lines += [
        "",
        f"**判定口径：任一指标较基线下降 >5% 即回滚对应 commit（需求文档 §8）**",
        "",
        "## 逐题明细",
        "",
        "| kb | 问题 | faithfulness | answer_relevancy | context_precision | context_recall |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(per_q):
        q = rows[i]["question"][:24] + ("…" if len(rows[i]["question"]) > 24 else "")
        cells = " | ".join("—" if r.get(k) is None else f"{r[k]:.4f}" for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"))
        lines.append(f"| {rows[i]['kb_id']} | {q} | {cells} |")

    md_path = DOCS_BENCH / f"P0-3b-{label}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport saved to {json_path} and {md_path}")


def run_eval(qa_file: str, group: str, label: str) -> None:
    try:
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except ImportError:
        print("Please install ragas and datasets: pip install ragas datasets nltk")
        sys.exit(1)

    with open(qa_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 兼容两种顶层格式：裸 list 或 {"qa_pairs": [...]}（含元信息字段）
    qa_pairs = data["qa_pairs"] if isinstance(data, dict) else data

    use_hyde = group == "hyde"
    if use_hyde:
        qa_pairs = [p for p in qa_pairs if p.get("hyde_group")]
        if not qa_pairs:
            print("No qa entries marked hyde_group=true")
            sys.exit(1)

    # 1) 数据收集（asyncio 域，退出后不再有 running loop）
    rows = asyncio.run(_collect_all(qa_pairs, use_hyde))

    # 2) RAGAS 评估（同步域：ragas 内部自行跑事件循环，不可嵌在 running loop 内）
    dataset = Dataset.from_dict({k: [r[k] for r in rows] for k in ("question", "answer", "contexts", "ground_truth")})
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    judge_llm, judge_embeddings = _build_judge_and_embeddings()

    print("\nRunning RAGAS evaluation ...")
    result = ragas_evaluate(dataset, metrics=metrics, llm=judge_llm, embeddings=judge_embeddings)

    # ragas 0.2.3：result[metric_name] 返回逐题分数 list[float]（含 nan）；聚合用 nanmean
    import numpy as np

    metric_names = [m.name for m in metrics] if hasattr(metrics[0], "name") else list(result._repr_dict.keys())
    agg = {}
    per_q: list[dict] = [dict() for _ in rows]
    for k in metric_names:
        try:
            scores = list(result[k])
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] metric {k} unavailable: {exc}")
            continue
        agg[k] = float(np.nanmean(scores))
        for i, v in enumerate(scores):
            per_q[i][k] = None if v is None or str(v) == "nan" else float(v)

    print("\n=== RAGAS Evaluation Results ===")
    for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        if k in agg:
            print(f"  {k}: {agg[k]:.4f}")

    # 3) 双落盘
    _write_report(label, group, use_hyde, rows, agg, per_q)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAGAS offline evaluation")
    parser.add_argument("--qa-file", required=True, help="qa pairs json (entries need kb_id/question/ground_truth)")
    parser.add_argument("--group", choices=["main", "hyde"], default="main", help="main=全量 use_hyde=False; hyde=hyde_group 子集 use_hyde=True")
    parser.add_argument("--label", required=True, help="output label, e.g. baseline-main")
    args = parser.parse_args()

    # CLI 相对路径按项目根解析（脚本已 chdir 到 backend）
    qa_file = str(Path(args.qa_file) if Path(args.qa_file).is_absolute() else PROJECT_ROOT / args.qa_file)
    run_eval(qa_file, args.group, args.label)

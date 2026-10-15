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
- answer 归一化（纯规则，无 LLM）：ragas faithfulness 只评以 ./。/!/！结尾的句子
  （_faithfulness.py sentences_with_index 过滤），全分号 markdown 列表 answer
  会被整体过滤 → 空 statements → nan（v1 基线 kb1-01/kb1-02 实证）。
  必做档：分号行尾→句号、无句读行尾补句号、剥 [来源:...] 标记；
  剥 **/剥# 经对照切句结构 10/10 无变化，按“不变就不剥”未纳入（约束 1）。
  基线与收尾同规则 → 同口径对比。

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
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

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

# 归一化（约束 4：纯规则实现，禁用 LLM）
_SOURCE_TAIL = re.compile(r"\s*\[来源:[^\]]*\]\s*")
_PUNCT_END = ("。", ".", "!", "！", "?", "？", ":", "：")


def _normalize_answer_for_ragas(ans: str) -> str:
    """评估输入最小归一化（必做档，约束 1）。

    - 分号结尾行 → 句号（中文列表排版用分号，实为完整陈述）
    - 无句读结尾行 → 补句号（markdown 列表/标题行）
    - 剥 [来源: ...] 引用标记（非陈述内容，不应参与 faithfulness 评分）
    - 剥 ** 与 # 经对照验证不影响切句结构（10/10 题句数/边界/保留数全同），
      按“不变就不剥”未纳入；问号/冒号结尾行保持原样（问句/引导语非陈述）。
    """
    lines = []
    for line in _SOURCE_TAIL.sub(" ", ans).splitlines():
        t = line.strip()
        if not t:
            continue
        if t.endswith((";", "；")):
            t = t.rstrip(";；") + "。"
        elif not t.endswith(_PUNCT_END):
            t += "。"
        lines.append(t)
    return "\n".join(lines)


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


async def _with_timeout(coro, label: str, timeout_s: float = 180.0):
    """收集阶段防挂起：业务链路（rag_chain 的 ChatOpenAI）无内建 timeout，
    TCP 对端挂起时 rag_query 会无限等待（实测曾挂 3 小时）。评估基建侧
    包 wait_for 兜底；正常耗时几十秒，180s 给足余量。超时即失败不吊住。"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(f"{label} 超时 {timeout_s:g}s（链路挂起防御触发，拒绝继续）") from exc


async def _collect_one(kb_id: int, question: str, use_hyde: bool, attempts: int = 3):
    """题级重试：服务端间歇性不响应（TCP 挂起）时，wait_for 打断后重试——
    每次 rag_query 新建 ChatOpenAI 客户端/连接，新调用有机会拿到可用连接。
    attempts 次全挂才抛出，单题最坏 attempts×180s，不吊住不静默。"""
    last_exc: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            r = await _with_timeout(rag_query(kb_id, question), f"rag_query kb{kb_id}(第{i}次)")
            d = await _with_timeout(
                retrieve_with_strategy(kb_id, question, use_hyde=use_hyde),
                f"retrieve kb{kb_id}(第{i}次)",
            )
            return r, d
        except RuntimeError as exc:
            last_exc = exc
            if i < attempts:
                print(f"[retry] {exc}，5s 后重试")
                await asyncio.sleep(5)
    raise last_exc  # type: ignore[misc]


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
        result, docs = await _collect_one(kb_id, question, use_hyde)
        if not docs:
            # 拍板 2：contexts 为空说明索引解析/检索异常，立即失败，不允许产出全 0 基线
            raise RuntimeError(
                f"n_contexts=0 for kb{kb_id}: {question[:40]}…（疑似 cwd/索引问题，拒绝继续）"
            )
        answer_raw = result["answer"]
        rows.append(
            {
                "kb_id": kb_id,
                "question": question,
                "answer": _normalize_answer_for_ragas(answer_raw),
                "answer_raw": answer_raw,
                "contexts": [d.page_content for d in docs],
                "ground_truth": pair.get("ground_truth", ""),
            }
        )
    return rows


def _write_report(label: str, group: str, use_hyde: bool, rows: list[dict], agg: dict, per_q: list[dict], rows_source: str = "rag_query 在线收集") -> None:
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
        "rows_source": rows_source,
        "self_judging_bias": "RAG 生成与 judge 同为 DeepSeek，指标绝对值可能偏高，但基线与收尾同源偏差可抵消",
        "judge_lock": "收尾跑必须使用完全相同的 judge 配置与 embeddings/contexts 口径，任一变更即失去对比基准意义",
        "normalization": (
            "必做档（纯规则，无 LLM）：分号行尾→句号、无句读行尾补句号、剥 [来源:...] 标记；"
            "剥 **/剥# 经对照切句结构 10/10 无变化，按不变就不剥未纳入"
        ),
    }

    json_path = DOCS_BENCH / f"P0-3b-{label}-{meta['date']}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "aggregate": agg, "per_question": per_q, "rows": rows}, f, ensure_ascii=False, indent=2)

    lines = [
        f"# RAGAS 基线：{label}",
        "",
        f"- 日期：{meta['date']}｜组别：{group}｜use_hyde={use_hyde}｜题数：{len(rows)}",
        f"- judge：{meta['judge']}｜embeddings：{meta['embeddings']}",
        f"- contexts 口径：{meta['contexts']}（与 answer 生成同源）",
        f"- **self-judging bias**：{meta['self_judging_bias']}",
        f"- **judge 配置锁定**：{meta['judge_lock']}",
        f"- answer 归一化：{meta['normalization']}",
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

    # 附录 A：归一化规则与档位判定（约束 1）
    lines += [
        "",
        "## 附录 A：归一化规则与档位判定",
        "",
        "- **必做档（纳入）**：分号结尾行→句号、无句读结尾行→补句号、剥 [来源: ...] 引用标记",
        "  - 依据：ragas faithfulness 只评以 ./。/!/！结尾的句子（_faithfulness.py sentences_with_index 过滤），"
        "全分号 markdown 列表 answer 会被整体过滤 → 空 statements → nan（v1 基线 kb1-01/kb1-02 实证，kb1-02 同为留 0→19）",
        "- **剥 ** 加粗标记：未纳入** —— 对照 v1 十题 answer，剥/不剥的切句结构（句数/切分边界/句号过滤保留数）10/10 完全一致，按不变就不剥剔除；差异仅为句子文本少去标记本身",
        "- **剥 # 标题标记：未纳入** —— 同上，10/10 完全一致",
        "- 问号/冒号结尾行保持原样（问句/引导语非完整陈述，被 ragas 过滤合理）",
        "- 归一化为纯规则实现（正则+字符串处理，无 LLM 调用）",
    ]

    # 附录 B：归一化前后对照抽样（约束 2：只改格式未改语义的证据）
    changed = [
        (r.get("answer_raw", r["answer"]), r["answer"], r["question"])
        for r in rows
        if r.get("answer_raw") is not None and r["answer_raw"] != r["answer"]
    ]
    sample = changed[:3] if changed else [(rows[0].get("answer_raw", rows[0]["answer"]), rows[0]["answer"], rows[0]["question"])]
    lines += [
        "",
        "## 附录 B：归一化前后对照抽样",
        "",
        f"（全量 {len(changed)}/{len(rows)} 题发生变化；抽样 {len(sample)} 题。变化仅为：剥 [来源] 标记、分号/无句读行尾补句号、空行折叠——语义与内容零增删）",
        "",
    ]
    for raw, norm, q in sample:
        lines += [
            f"### {q[:36]}{'…' if len(q) > 36 else ''}",
            "",
            "归一化前：",
            "",
            "```text",
            raw,
            "```",
            "",
            "归一化后：",
            "",
            "```text",
            norm,
            "```",
            "",
        ]

    md_path = DOCS_BENCH / f"P0-3b-{label}-{meta['date']}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport saved to {json_path} and {md_path}")


def _health_gate(agg: dict) -> None:
    """拍板 2 落盘前健康门槛：崩溃报错优于静默产出垃圾基线。

    - 四指标不能全为 0（疑似检索空 / judge 全挂）
    - faithfulness 为 nan 或 < 0.5 视为异常，停下报用户不落盘
    """

    def _bad(v) -> bool:
        return v is None or (isinstance(v, float) and v != v)  # None 或 nan

    four = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
    vals = [agg.get(k) for k in four]
    if all(not _bad(v) and v == 0 for v in vals):
        print(f"[健康门槛未通过] 聚合值: {json.dumps(agg, ensure_ascii=False)}")
        raise RuntimeError("健康门槛：四指标全为 0，疑似 cwd/索引/judge 异常，拒绝写入基线")
    fa = agg.get("faithfulness")
    if _bad(fa) or fa < 0.5:
        print(f"[健康门槛未通过] 聚合值: {json.dumps(agg, ensure_ascii=False)}")
        raise RuntimeError(f"健康门槛：faithfulness={fa!r} 为 nan 或 <0.5，视为异常，停下报用户")


def run_eval(qa_file: str, group: str, label: str, from_rows: Optional[str] = None, dry_run: bool = False) -> None:
    try:
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
        from ragas.run_config import RunConfig
    except ImportError:
        print("Please install ragas and datasets: pip install ragas datasets nltk")
        sys.exit(1)

    # 拍板 2 预检：settings.faiss_index_dir 为相对 cwd 路径，解析失败时立即崩溃报错，
    # 而不是静默检索空 → 指标全 0 基线（首轮全 0 事故的防再发）
    index_dir = Path(settings.faiss_index_dir)
    assert index_dir.exists(), f"FAISS index dir not found: {index_dir} (cwd={os.getcwd()})"

    with open(qa_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 兼容两种顶层格式：裸 list 或 {"qa_pairs": [...]}（含元信息字段）
    qa_pairs = data["qa_pairs"] if isinstance(data, dict) else data

    use_hyde = group == "hyde"
    if use_hyde and not from_rows:
        qa_pairs = [p for p in qa_pairs if p.get("hyde_group")]
        if not qa_pairs:
            print("No qa entries marked hyde_group=true")
            sys.exit(1)

    # 1) 数据收集：在线（rag_query）或离线（--from-rows 复用既有 rows）。
    #    离线路径：answer 生成链路 v1→v2 未变过，v2 的定义只是评估输入归一化，
    #    复用 v1 answer（同配置同链路生成）口径等价，且同源 answer 让
    #    “归一化影响”对比唯一变量化（服务端间歇挂起时的替代路径）。
    if from_rows:
        src = json.loads(Path(from_rows).read_text(encoding="utf-8"))
        rows = []
        for r in src["rows"]:
            raw_answer = r["answer"]
            rows.append(
                {
                    "kb_id": r["kb_id"],
                    "question": r["question"],
                    "answer": _normalize_answer_for_ragas(raw_answer),
                    "answer_raw": raw_answer,
                    "contexts": r["contexts"],
                    "ground_truth": r["ground_truth"],
                }
            )
        rows_source = f"reused from {Path(from_rows).name}（收集复用，评估口径 v2）"
    else:
        rows = asyncio.run(_collect_all(qa_pairs, use_hyde))
        rows_source = "rag_query 在线收集"

    # 2) RAGAS 评估（同步域：ragas 内部自行跑事件循环，不可嵌在 running loop 内）
    dataset = Dataset.from_dict({k: [r[k] for r in rows] for k in ("question", "answer", "contexts", "ground_truth")})
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    judge_llm, judge_embeddings = _build_judge_and_embeddings()

    if dry_run:
        # 流程验证模式（不依赖真实 API）：跳过 evaluate，用固定假分数走
        # 健康门槛 + 双落盘全链路，验证 rows 归一化/报告模板/附录生成。
        # 产物仅供人工检查，跑完应删除，不得作为基线。
        print("\n[dry-run] 跳过 RAGAS evaluate，用固定假分数验证落盘流程 ...")
        import numpy as np

        metric_names = [m.name for m in metrics]
        base = {"faithfulness": 0.9, "answer_relevancy": 0.8, "context_precision": 0.7, "context_recall": 0.6}
        agg = {}
        per_q: list[dict] = [dict() for _ in rows]
        for k in metric_names:
            scores = [base[k]] * len(rows)
            agg[k] = float(np.nanmean(scores))
            for i, v in enumerate(scores):
                per_q[i][k] = float(v)
    else:
        print("\nRunning RAGAS evaluation ...")
        # RunConfig：默认 timeout=60s/max_workers=16，v2 首跑撞 judge API 波动时
        # faithfulness（输入最长：4 contexts 全文）10 题全 TimeoutError。
        # 参数哲学：正常窗口响应为秒级，超时/重试应收紧让坏窗口快速失败
        # （首跑 retry 叠加曾空转 100 分钟：timeout 300 × retries 10 × langchain 内部重试），
        # 而不是吊住等恢复。属评估基建健壮性（不改评估口径）。
        run_config = RunConfig(timeout=120, max_retries=3, max_wait=15, max_workers=8)
        result = ragas_evaluate(dataset, metrics=metrics, llm=judge_llm, embeddings=judge_embeddings, run_config=run_config)

        # ragas 0.2.3：result[metric_name] 返回逐题分数 list[float]（含 nan）；聚合用 nanmean
        import numpy as np

        metric_names = [m.name for m in metrics] if hasattr(metrics[0], "name") else list(result._repr_dict.keys())
        agg = {}
        per_q = [dict() for _ in rows]
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

    # 3) 健康门槛（拍板 2）：通过才允许落盘
    _health_gate(agg)

    # 4) 双落盘
    _write_report(label, group, use_hyde, rows, agg, per_q, rows_source)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAGAS offline evaluation")
    parser.add_argument("--qa-file", required=True, help="qa pairs json (entries need kb_id/question/ground_truth)")
    parser.add_argument("--group", choices=["main", "hyde"], default="main", help="main=全量 use_hyde=False; hyde=hyde_group 子集 use_hyde=True")
    parser.add_argument("--label", required=True, help="output label, e.g. baseline-main")
    parser.add_argument(
        "--from-rows",
        help="离线评估：复用既有基线 json 的 rows（answer 原文本地归一化），跳过 rag_query 收集",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="流程验证：跳过 evaluate 用固定假分数走健康门槛+落盘（不依赖真实 API，产物仅供检查后删除）",
    )
    args = parser.parse_args()

    # CLI 相对路径按项目根解析（脚本已 chdir 到 backend）
    qa_file = str(Path(args.qa_file) if Path(args.qa_file).is_absolute() else PROJECT_ROOT / args.qa_file)
    from_rows = str(Path(args.from_rows) if args.from_rows and Path(args.from_rows).is_absolute() else PROJECT_ROOT / args.from_rows) if args.from_rows else None
    run_eval(qa_file, args.group, args.label, from_rows, args.dry_run)

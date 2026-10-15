"""P0-3b §7.4 591 独立回归基线：纯文本 plain 聊天流跑 3 次，记录 token 数区间 [min, max]。

命中路径：登录 → POST /api/chat/stream（无 kb_id、无 images、web_search=false）
→ plain_chat_stream else 分支（原 rag_chain.py:591 内联 ChatOpenAI）。
断言口径（需求文档 §7.4）：事件序列 conversation→token×N→done；回答 ≥15 字中文且含标点。
token 区间断言 [min×0.7, max×1.3] 由收尾轮用本文件记录的区间执行。

用法：python3 scripts/baseline_591.py [--runs 3]
"""

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8000"
DOCS_BENCH = PROJECT_ROOT / "docs" / "benchmarks"

QUESTION = "你好呀今天心情不错"
# 与 P0-3a 终验一致的测试账号（非 admin）
USERNAME, PASSWORD = "18838166792", "123456"


def login() -> str:
    resp = requests.post(f"{BASE}/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=15)
    if resp.status_code != 200:
        resp = requests.post(f"{BASE}/api/auth/login", data={"username": USERNAME, "password": PASSWORD}, timeout=15)
    resp.raise_for_status()
    token = resp.json().get("access_token") or resp.json().get("token")
    if not token:
        raise RuntimeError(f"login response has no token: {resp.text[:200]}")
    return token


def stream_once(token: str) -> dict:
    """跑一次纯文本流式聊天，返回事件统计与回答文本。"""
    resp = requests.post(
        f"{BASE}/api/chat/stream",
        json={"question": QUESTION, "knowledge_base_id": None, "web_search": False},
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()

    events: list[str] = []
    answer_parts: list[str] = []
    for raw in resp.iter_lines(decode_unicode=True):
        line = (raw or "").strip("\r\n")
        if not line:
            continue
        if line.startswith("event:"):
            events.append(line.split(":", 1)[1].strip())
        elif line.startswith("data:"):
            payload = line.split(":", 1)[1].strip()
            # token 事件的 payload 是 {"content": "..."} JSON（增量文本）；done 事件是统计 JSON
            if events and events[-1] == "token":
                try:
                    obj = json.loads(payload)
                    answer_parts.append(str(obj.get("content", "")))
                except json.JSONDecodeError:
                    answer_parts.append(payload)

    n_tokens = sum(1 for e in events if e == "token")
    answer = "".join(answer_parts)
    has_punct = any(ch in answer for ch in "。，！？；：、,.!?;:")
    return {
        "events_head": events[:3],
        "events_tail": events[-3:],
        "first_is_conversation": bool(events) and events[0] == "conversation",
        "last_is_done": bool(events) and events[-1] == "done",
        "n_tokens": n_tokens,
        "answer": answer,
        "answer_len": len(answer),
        "has_punct": has_punct,
        "passes_min_len": len(answer) >= 15,
    }


def main(runs: int) -> None:
    token = login()
    print(f"login ok; question={QUESTION!r}; runs={runs}")

    results = []
    for i in range(runs):
        r = stream_once(token)
        results.append(r)
        print(f"run{i + 1}: n_tokens={r['n_tokens']} len={r['answer_len']} punct={r['has_punct']} "
              f"first={r['first_is_conversation']} last={r['last_is_done']} answer={r['answer'][:40]!r}")

    ns = [r["n_tokens"] for r in results]
    summary = {
        "label": "baseline-591",
        "date": date.today().isoformat(),
        "question": QUESTION,
        "runs": runs,
        "n_tokens": ns,
        "token_min": min(ns),
        "token_max": max(ns),
        "token_mean": round(statistics.mean(ns), 1),
        "assert_window": [int(min(ns) * 0.7), int(max(ns) * 1.3)],
        "results": results,
    }

    ok = all(
        r["first_is_conversation"] and r["last_is_done"] and r["passes_min_len"] and r["has_punct"] and r["n_tokens"] > 0
        for r in results
    )
    summary["baseline_healthy"] = ok
    print(f"\ntoken range: [{min(ns)}, {max(ns)}], assert window (min*0.7, max*1.3) = {summary['assert_window']}, healthy={ok}")

    DOCS_BENCH.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    json_path = DOCS_BENCH / f"P0-3b-baseline-591-{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    md = [
        f"# §7.4 591 独立回归基线（{today}）",
        "",
        f"- 路径：POST /api/chat/stream → plain_chat_stream else 分支（原 rag_chain.py:591）",
        f"- 问题文本锁定：`{QUESTION}`｜运行 {runs} 次",
        f"- 请求体锁定：knowledge_base_id=null、web_search=false、无 images",
        f"- 3 次 token 数：{ns}",
        f"- **收尾跑必须使用完全相同的问题文本与请求体**",
        f"- token 数区间：**[min={min(ns)}, max={max(ns)}]**，均值 {summary['token_mean']}",
        f"- 收尾断言窗口：[min×0.7, max×1.3] = **{summary['assert_window']}**",
        f"- 基线健康（事件序 conversation→token×N→done、回答≥15字含标点、N>0）：**{'是' if ok else '否'}**",
        "",
        "| run | token 数 | 回答长度 | 含标点 | 首事件 | 尾事件 |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results):
        md.append(f"| {i + 1} | {r['n_tokens']} | {r['answer_len']} | {r['has_punct']} | "
                  f"{r['events_head'][0] if r['events_head'] else '—'} | {r['events_tail'][-1] if r['events_tail'] else '—'} |")
    md_path = DOCS_BENCH / f"P0-3b-baseline-591-{today}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"saved: {json_path} and {md_path}")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    main(args.runs)

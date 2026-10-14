"""P0-3a 第 3 轮：意图分类 12 用例验收（§12.4 v1.2：5 RAG + 5 工具 + 2 plain，≥11/12）。

用法（项目根执行）：python3 scripts/agent_intent_cases.py
- 直调 agent_service.classify_intent（不经 HTTP），记录实际 intent 与分类耗时
- 覆盖边界：T3 带 kb_id 问时间（few-shot 偏置反例）、R4 含工具触发词但实际 RAG、R5 无 kb_id 裸问题
- P1 是第 2 轮端到端实测被判 rag 的已知案例，本轮重点观测
- 依赖真实 LLM 网络；单次运行约 30s
"""
import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.chdir(PROJECT_ROOT / "backend")

from sqlalchemy import select  # noqa: E402

from app.models.database import async_session_factory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import agent_service  # noqa: E402

PASS_THRESHOLD = 11  # §12.4 v1.2：≥11/12（等比于原 ≥9/10）

CASES = [
    # (编号, kb_id, question, expected)
    ("R1", 1, "总结一下中国人民银行的主要职能", "rag"),
    ("R2", 3, "低空无人机集群通信的关键技术有哪些？", "rag"),
    ("R3", 1, "文档里提到的机构设置是怎样的？", "rag"),
    ("R4", 1, "帮我搜索一下资料中关于反洗钱的内容", "rag"),   # 含工具触发词"搜索"，实际 RAG
    ("R5", None, "司库奇尤单抗注射液的适应症是什么？", "rag"),  # 无 kb_id 裸问题，需查资料
    ("T1", None, "现在几点了？", "tool"),
    ("T2", None, "计算 (3+5)*12/2 等于多少", "tool"),
    ("T3", 1, "现在北京时间几点？", "tool"),                    # §12.4 指定偏置用例
    ("T4", None, "帮我查一下订单 SO-1002 的状态", "tool"),
    ("T5", None, "先算 12 乘以 8，再告诉我今天星期几", "tool"),
    ("P1", None, "你好，请用一句话介绍这个项目", "plain"),      # 第 2 轮端到端被判 rag 的已知案例
    ("P2", None, "你好呀，最近怎么样？", "plain"),
]


async def main():
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.id == 2))).scalars().first()
        results, fails = [], []
        for cid, kb, q, expected in CASES:
            t0 = time.monotonic()
            intent = await agent_service.classify_intent(db, user, q, kb)
            dt_ms = (time.monotonic() - t0) * 1000
            ok = intent == expected
            results.append(ok)
            mark = "✓" if ok else "✗"
            print(f"{mark} {cid}: 期望 {expected:<5} 实际 {intent:<5} ({dt_ms:5.0f}ms)  [{q}]")
            if not ok:
                fails.append(cid)

    passed = sum(results)
    verdict = "✓ 通过" if passed >= PASS_THRESHOLD else "✗ 未达标（需修 few-shot prompt 后重跑，≤2 轮）"
    print(f"\n意图分类验收（§12.4 v1.2）：{passed}/{len(results)}，阈值 ≥{PASS_THRESHOLD} → {verdict}")
    if fails:
        print("判错用例:", ", ".join(fails))
    sys.exit(0 if passed >= PASS_THRESHOLD else 1)


if __name__ == "__main__":
    asyncio.run(main())

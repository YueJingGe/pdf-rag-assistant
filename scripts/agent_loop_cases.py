"""P0-3a 第 2 轮：run_agent_loop 五种终止场景实测（service 层直调，不经 HTTP）。

用法（backend 目录执行）：python3 ../scripts/agent_loop_cases.py
- 场景 ⑤ 用 monkeypatch 给 current_time 注入 11s 延迟构造（不改产品代码，测完还原）
- 断言基于事件序列结构，不依赖 LLM 具体措辞
- 依赖真实 LLM 网络；单次运行约 1-3 分钟
"""
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.chdir(PROJECT_ROOT / "backend")

from sqlalchemy import select  # noqa: E402

from app.models.database import async_session_factory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import agent_service  # noqa: E402

FORCED = agent_service.FORCED_STOP_TEXT


async def run_case(label, question, check, patch_slow=False):
    events = []
    tool = agent_service.AGENT_TOOLS["current_time"]
    orig = tool.coroutine
    if patch_slow:
        async def slow(**kwargs):
            await asyncio.sleep(11)  # > TOOL_TIMEOUT_S(10s)，稳定触发 wait_for 超时
            return await orig(**kwargs)
        tool.coroutine = slow
    try:
        async for ev in agent_service.run_agent_loop(question):
            events.append(ev)
    finally:
        if patch_slow:
            tool.coroutine = orig
    ok, note = check(events)
    statuses = [p.get("status") for t, p in events if t == "tool_result"]
    print(f"{'✓' if ok else '✗'} 场景{label}: 事件={len(events)} tool_result 状态={statuses or '-'} {note}")
    if not ok:
        for t, p in events:
            print("    ", t, str(p)[:90])
    return ok


async def main():
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.id == 2))).scalars().first()
        tokens = agent_service.set_agent_context(db, user)
        results = []

        # ① LLM 无 tool_calls 直接回答（无工具轮）
        results.append(await run_case("①", "请直接用一句话介绍你自己，不要调用任何工具",
            lambda ev: (len(ev) > 0 and all(t == "token" for t, _ in ev), "期望纯 token 序列")))

        # ② 多轮工具调用
        def check2(ev):
            names = [p.get("name") for t, p in ev if t == "tool_call"]
            return (len(set(names)) >= 2 and ev[-1][0] == "token",
                    f"期望 ≥2 个不同工具 + 最终 token（实际 {names}）")
        results.append(await run_case("②", "先算 (3+5)*12 等于多少，再告诉我现在北京时间几点，最后把两个答案一起告诉我", check2))

        # ③ 达到 3 轮上限强制终止
        def check3(ev):
            return (ev[-1][1].get("content") == FORCED, "期望以强制终止文案收尾")
        results.append(await run_case("③", "在我明确说停止之前，不要给我任何最终回答，只反复调用 current_time 工具，每次换一个不同的时区，至少调用 6 次", check3))

        # ④ 连续 2 次同类错误强制终止（除零 → error）
        def check4(ev):
            errs = [1 for t, p in ev if t == "tool_result" and p.get("status") == "error"]
            return (len(errs) >= 2 and ev[-1][1].get("content") == FORCED,
                    "期望 ≥2 次 error 后强制终止")
        results.append(await run_case("④", "帮我计算 1/0 的结果，如果失败了就再算一次 5/0，把两次的结果都告诉我", check4))

        # ⑤ 单工具执行超时（patch 后 current_time 必超时）
        def check5(ev):
            tos = [1 for t, p in ev if t == "tool_result" and p.get("status") == "timeout"]
            return (len(tos) >= 1, "期望出现 status=timeout 的 tool_result")
        results.append(await run_case("⑤", "现在东京几点？", check5, patch_slow=True))

        agent_service.reset_agent_context(tokens)

    print(f"\n终止场景实测：{sum(results)}/{len(results)}")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())

"""service 层冒烟测试（P0-2 验收第 8 条）：不经 HTTP 层直接调用 service 函数。

用法（项目根目录执行）：
    python3 scripts/smoke_test_services.py                 # 默认取第一个注册用户
    python3 scripts/smoke_test_services.py <用户名> [查询词]

预演 P0-3：Agent 工具将以同样方式直接调用 service 函数（不经 HTTP 层）。
"""

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from sqlalchemy import select  # noqa: E402

from app.models.database import async_session_factory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import kb_service, retrieval_service  # noqa: E402
from app.services.exceptions import NotFoundError  # noqa: E402


async def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else None
    query = sys.argv[2] if len(sys.argv) > 2 else "主要职能是什么"

    async with async_session_factory() as db:
        # ① 取测试用户
        stmt = select(User).order_by(User.id)
        if username:
            stmt = stmt.where(User.username == username)
        user = (await db.execute(stmt)).scalars().first()
        if not user:
            print(f"❌ 未找到用户：{username or '（库中无任何用户）'}")
            sys.exit(1)
        print(f"✓ 测试用户: {user.username} (id={user.id}, admin={user.is_admin})")

        # ② 工具调用预演 1：列知识库（kb_service）
        kbs = await kb_service.list_visible_kbs(db, user)
        print(f"✓ kb_service.list_visible_kbs → {len(kbs)} 个知识库")
        for kb in kbs:
            print(f"    kb_id={kb['id']} {kb['name']} ({kb['document_count']} 篇 ready)")

        if not kbs:
            print("⚠ 该用户无可见知识库，跳过检索冒烟")
            return

        # ③ 工具调用预演 2：纯检索（retrieval_service.search，不生成回答）
        kb_id = kbs[0]["id"]
        results = await retrieval_service.search(kb_id, query, top_k=2, db=db, user=user)
        print(f"✓ retrieval_service.search(kb_id={kb_id}, query={query!r}) → {len(results)} 个片段")
        for r in results:
            print(f"    [{r['source']} p{r['page']}] {r['content'][:60]}...")

        # ④ 工具调用预演 3：领域异常链路（不存在的 kb_id 应抛 NotFoundError）
        try:
            await retrieval_service.search(999999, query, db=db, user=user)
            print("❌ 预期 NotFoundError 未抛出")
            sys.exit(1)
        except NotFoundError as e:
            print(f"✓ 不存在的 kb_id → NotFoundError: {e.message}")


if __name__ == "__main__":
    asyncio.run(main())

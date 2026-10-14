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

from app.models.conversation import Conversation  # noqa: E402
from app.models.database import async_session_factory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import chat_service, document_service, feedback_service, kb_service, retrieval_service  # noqa: E402
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

        # ⑤ document_service 冒烟（P0-2 第 2 轮）：临时库全链路 上传→列表→检索→改名→清理
        temp_kb = await kb_service.create_kb(
            db, user, name="smoke-doc-temp", description="冒烟临时库", permission="private"
        )
        try:
            content = ("SMOKE_DOC_MARKER_P02：无人机集群协同通信冒烟测试内容。\n" * 5).encode("utf-8")
            doc = await document_service.upload_document(
                db, user, temp_kb.id, filename="smoke_doc.txt", content=content
            )
            print(f"✓ document_service.upload_document → doc_id={doc.id} status={doc.status} chunks={doc.chunk_count}")

            docs = await document_service.list_documents(db, user, temp_kb.id)
            print(f"✓ document_service.list_documents → {len(docs)} 篇")

            hits = await retrieval_service.search(
                temp_kb.id, "SMOKE_DOC_MARKER_P02 协同通信", top_k=2, db=db, user=user
            )
            print(f"✓ 新上传文档可检索 → {len(hits)} 个片段")

            renamed = await document_service.rename_document(
                db, user, temp_kb.id, doc.id, "smoke_renamed.txt"
            )
            print(f"✓ document_service.rename_document → {renamed.filename}")
        finally:
            await kb_service.delete_kb(db, user, temp_kb.id)
            print(f"✓ 临时库 {temp_kb.id} 已清理")

        # ⑥ chat_service 冒烟（P0-2 第 2 轮）：普通聊天会话生命周期 创建→归属校验→消息→清理
        conversation, chat_history = await chat_service.prepare_chat(
            db, None, "冒烟测试问题", None, user
        )
        print(f"✓ chat_service.prepare_chat（普通聊天）→ 新会话 id={conversation.id}")
        await chat_service.save_user_message(db, conversation.id, "冒烟测试问题", None, None)
        own = await chat_service.get_own_conversation(db, conversation.id, user)
        print(f"✓ chat_service.get_own_conversation → 会话 {own.id} 归属校验通过")
        await chat_service.delete_conversation(db, conversation.id, user)
        print(f"✓ chat_service.delete_conversation → 会话 {conversation.id} 已删除")

        # ⑦ 会话防枚举（D2）：他人会话/不存在会话一律 NotFoundError（404，而非 403）
        other = (
            await db.execute(
                select(Conversation).where(Conversation.user_id != user.id).limit(1)
            )
        ).scalars().first()
        probe_id = other.id if other else 999999
        label = f"他人会话（id={probe_id}）" if other else "不存在会话（id=999999）"
        try:
            await chat_service.get_own_conversation(db, probe_id, user)
            print("❌ 预期 NotFoundError 未抛出")
            sys.exit(1)
        except NotFoundError:
            print(f"✓ {label} → NotFoundError（404 防枚举）")

        # ⑧ feedback_service 冒烟（P0-2 第 3 轮）：临时库上 创建→统计→导出→清理
        from sqlalchemy import delete as sa_delete  # noqa: E402
        from app.models.feedback import RetrievalFeedback  # noqa: E402

        temp_kb2 = await kb_service.create_kb(
            db, user, name="smoke-fb-temp", description="反馈冒烟临时库", permission="private"
        )
        try:
            fb = await feedback_service.create_feedback(
                db, user,
                message_id=0,
                knowledge_base_id=temp_kb2.id,
                question="冒烟问题",
                chunk_content="冒烟片段",
                chunk_metadata=None,
                is_relevant=True,
            )
            print(f"✓ feedback_service.create_feedback → id={fb.id}")

            stats = await feedback_service.get_feedback_stats(db, user, temp_kb2.id)
            print(f"✓ feedback_service.get_feedback_stats → total={stats['total']} rate={stats['relevance_rate']}")

            rows = await feedback_service.export_feedback(db, user, temp_kb2.id)
            print(f"✓ feedback_service.export_feedback（owner）→ {len(rows)} 条")

            try:
                await feedback_service.get_feedback_stats(db, user, 999999)
                print("❌ 预期 NotFoundError 未抛出")
                sys.exit(1)
            except NotFoundError:
                print("✓ 不存在 kb 的 stats → NotFoundError（404）")

            # admin 身份导出（admin 对任意库 owner 判定恒过——export 双重校验的 service 侧验证）
            # 存量库可能无 is_admin 用户：用内存临时标记验证，不落库
            admin_user = (
                await db.execute(select(User).where(User.is_admin == True).limit(1))  # noqa: E712
            ).scalars().first()
            temp_flag = False
            if not admin_user:
                admin_user = (await db.execute(select(User).order_by(User.id).limit(1))).scalars().first()
                admin_user.is_admin = True  # 仅内存标记，不提交
                temp_flag = True
            admin_rows = await feedback_service.export_feedback(db, admin_user, temp_kb2.id)
            note = "，内存临时标记已还原" if temp_flag else ""
            print(f"✓ admin 身份 export_feedback → {len(admin_rows)} 条（admin 绕过 owner 判定{note}）")
            if temp_flag:
                admin_user.is_admin = False
        finally:
            await db.execute(sa_delete(RetrievalFeedback).where(RetrievalFeedback.knowledge_base_id == temp_kb2.id))
            await db.commit()
            await kb_service.delete_kb(db, user, temp_kb2.id)
            print(f"✓ 临时库 {temp_kb2.id} 及其反馈已清理")


if __name__ == "__main__":
    asyncio.run(main())

"""P0-4 零 LLM 冒烟测试：目录树 + 在线创作入库 + 更新生效 + 消息存为文档。

对应 docs/requirements/P0-4-lexiang-style-kb.md §5 验收标准 1/2/3/4/5/9 项：
全程不经 HTTP 层、零 LLM 调用，命中断言走 retrieval_service（FAISS 检索层）。

用法（项目根目录执行）：
    python3 scripts/smoke_test_p04.py              # 默认取第一个注册用户
    python3 scripts/smoke_test_p04.py <用户名>
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

from app.models.category import Category  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.models.database import async_session_factory  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import (  # noqa: E402
    category_service,
    chat_service,
    document_service,
    kb_service,
    retrieval_service,
)
from app.services.exceptions import (  # noqa: E402
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

MARKER_V1 = "P04冒烟标记甲：萤火虫发光原理是荧光素酶催化。"
MARKER_V2 = "P04冒烟标记乙：海马爸爸负责育儿袋孵化。"
SAVE_MSG_MARKER = "P04存档标记：这条回答被沉淀回知识库。"


def _check(cond: bool, label: str) -> None:
    """迷你断言：失败即退出（冒烟脚本 fail-fast）。"""
    print(f"{'✓' if cond else '❌'} {label}")
    if not cond:
        sys.exit(1)


async def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else None

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

        temp_kb = await kb_service.create_kb(
            db, user, name="smoke-p04-temp", description="P0-4 冒烟临时库", permission="private"
        )
        print(f"✓ 临时库就绪 kb_id={temp_kb.id}")

        temp_kb2 = None
        try:
            # ② 目录管理：新建根目录 A → 子目录 A1 → 重命名
            cat_a = await category_service.create_category(db, user, temp_kb.id, name="前端基础")
            cat_a1 = await category_service.create_category(
                db, user, temp_kb.id, name="JS", parent_id=cat_a.id
            )
            renamed = await category_service.rename_category(
                db, user, temp_kb.id, cat_a1.id, name="JavaScript"
            )
            _check(renamed.name == "JavaScript", "② 目录新建/子目录/重命名")
            try:
                await category_service.create_category(db, user, temp_kb.id, name="   ")
                _check(False, "② 空目录名应 ValidationError")
            except ValidationError:
                print("✓ 空目录名 → ValidationError（400）")

            # ③ 在线创作：新建 → 物理文件落盘 → status=ready → 检索命中
            online_doc = await document_service.create_online_document(
                db, user, temp_kb.id,
                title="萤火虫笔记", content=f"# 笔记\n\n{MARKER_V1}\n", category_id=cat_a.id,
            )
            _check(
                online_doc.status == "ready" and online_doc.source == "online"
                and online_doc.chunk_count > 0,
                f"③ 在线创作入库 status={online_doc.status} chunks={online_doc.chunk_count}",
            )
            _check(Path(online_doc.file_path).exists(), "③ 物理 .md 落盘（入库管道副产物）")
            hits = await retrieval_service.search(
                temp_kb.id, "萤火虫 冒烟标记甲", top_k=3, db=db, user=user
            )
            _check(
                any("冒烟标记甲" in r["content"] for r in hits),
                f"③ 新内容检索命中（{len(hits)} 片段，检索层断言）",
            )

            # ④ 树结构：目录 + 在线文档位置正确
            tree = await category_service.get_tree(db, user, temp_kb.id)
            tree_doc = next(d for d in tree["documents"] if d["id"] == online_doc.id)
            _check(
                tree_doc["source"] == "online" and tree_doc["category_id"] == cat_a.id
                and {c["id"] for c in tree["categories"]} >= {cat_a.id, cat_a1.id},
                "④ 树中目录/文档挂载正确",
            )

            # ⑤ 更新生效：旧 marker 不再命中、新 marker 命中（验收第 3 条，检索层断言）
            updated = await document_service.save_online_content(
                db, user, temp_kb.id, online_doc.id,
                content=f"# 笔记\n\n{MARKER_V2}\n",
            )
            _check(
                updated.status == "ready" and updated.content == f"# 笔记\n\n{MARKER_V2}\n"
                and Path(updated.file_path).read_text(encoding="utf-8") == updated.content,
                "⑤ 保存后 content 列与物理文件一致（真相源同步）",
            )
            hits_v2 = await retrieval_service.search(
                temp_kb.id, "冒烟标记乙 海马", top_k=3, db=db, user=user
            )
            _check(
                any("冒烟标记乙" in r["content"] for r in hits_v2),
                "⑤ 新内容命中",
            )
            _check(
                not any("冒烟标记甲" in r["content"] for r in hits_v2),
                "⑤ 旧内容不再命中（索引已重建）",
            )

            # ⑥ 非 ready 拒绝保存（409）+ 上传文档不支持在线保存（400）
            updated.status = "processing"
            await db.commit()
            try:
                await document_service.save_online_content(
                    db, user, temp_kb.id, online_doc.id, content="x"
                )
                _check(False, "⑥ 非 ready 保存应 ConflictError")
            except ConflictError:
                print("✓ 非 ready 状态保存 → ConflictError（409）")
            updated.status = "ready"
            await db.commit()

            upload_doc = await document_service.upload_document(
                db, user, temp_kb.id,
                filename="smoke_doc.txt",
                content=("P04 上传冒烟：斑马条纹有散热假说。\n" * 5).encode("utf-8"),
                category_id=cat_a1.id,
            )
            _check(upload_doc.category_id == cat_a1.id, "⑥ 上传挂目录（category_id 入库）")
            try:
                await document_service.save_online_content(
                    db, user, temp_kb.id, upload_doc.id, content="x"
                )
                _check(False, "⑥ 上传文档在线保存应 ValidationError")
            except ValidationError:
                print("✓ 上传文档不支持在线保存 → ValidationError（400）")

            # ⑦ 移动到：挂 A1 → 移根 → 移 A（验收第 4/1 条路径）
            moved_cnt = await category_service.move_documents(
                db, user, temp_kb.id, document_ids=[upload_doc.id], category_id=None
            )
            moved_doc = await db.get(Document, upload_doc.id)
            _check(moved_cnt == 1 and moved_doc.category_id is None, "⑦ 移动到根（未归类）")
            await category_service.move_documents(
                db, user, temp_kb.id, document_ids=[upload_doc.id], category_id=cat_a.id
            )
            moved_doc = await db.get(Document, upload_doc.id)
            _check(moved_doc.category_id == cat_a.id, "⑦ 移动到目录 A")

            # ⑧ 目录 404 / 串库 404
            try:
                await category_service.get_category_or_raise(db, temp_kb.id, 999999)
                _check(False, "⑧ 不存在目录应 NotFoundError")
            except NotFoundError:
                print("✓ 不存在目录 → NotFoundError（404）")
            temp_kb2 = await kb_service.create_kb(
                db, user, name="smoke-p04-temp2", description="串库校验临时库", permission="private"
            )
            cat_other = await category_service.create_category(db, user, temp_kb2.id, name="别库目录")
            try:
                await category_service.move_documents(
                    db, user, temp_kb.id, document_ids=[upload_doc.id], category_id=cat_other.id
                )
                _check(False, "⑧ 串库挂载应 NotFoundError")
            except NotFoundError:
                print("✓ 其他库的目录挂载 → NotFoundError（404，库隔离）")

            # ⑨ 权限负例：非 admin 他人对私有库写目录 → PermissionDeniedError
            other = (
                await db.execute(
                    select(User).where(User.id != user.id, User.is_admin == False).limit(1)  # noqa: E712
                )
            ).scalars().first()
            if other:
                try:
                    await category_service.create_category(db, other, temp_kb.id, name="越权目录")
                    _check(False, "⑨ 他人写私有库目录应 PermissionDeniedError")
                except PermissionDeniedError:
                    print(f"✓ 他人（{other.username}）写私有库目录 → PermissionDeniedError（403）")
            else:
                print("⚠ 库中无其他非 admin 用户，跳过写权限负例")

            # ⑩ 存消息为文档：本人消息入库可检索；他人/不存在消息 404 防枚举
            conversation, _ = await chat_service.prepare_chat(
                db, None, "萤火虫为什么发光？", None, user
            )
            user_msg = await chat_service.save_user_message(
                db, conversation.id, "萤火虫为什么发光？", None, None
            )
            assistant_msg = await chat_service.save_assistant_message(
                db, conversation.id, SAVE_MSG_MARKER, []
            )
            saved = await chat_service.get_own_message(db, assistant_msg.id, user)
            _check(saved[0].content == SAVE_MSG_MARKER, "⑩ 本人消息归属校验通过")
            saved_doc = await document_service.create_online_document(
                db, user, temp_kb.id,
                title=conversation.title[:50], content=saved[0].content, category_id=None,
            )
            hits_saved = await retrieval_service.search(
                temp_kb.id, "存档标记 沉淀", top_k=3, db=db, user=user
            )
            _check(
                any("存档标记" in r["content"] for r in hits_saved),
                "⑩ 存为文档后可检索（沉淀闭环）",
            )
            try:
                await chat_service.get_own_message(db, 999999, user)
                _check(False, "⑩ 不存在消息应 NotFoundError")
            except NotFoundError:
                print("✓ 不存在消息 → NotFoundError（404 防枚举）")
            await chat_service.delete_conversation(db, conversation.id, user)

            # ⑪ 删除目录：子目录上提为根、文档移至根、目录消失（验收第 1 条删除语义）
            await category_service.delete_category(db, user, temp_kb.id, cat_a.id)
            gone = await db.get(Category, cat_a.id)
            child = await db.get(Category, cat_a1.id)
            moved_doc = await db.get(Document, upload_doc.id)
            _check(
                gone is None and child.parent_id is None and moved_doc.category_id is None,
                "⑪ 删除目录 → 子目录上提为根、文档移至根（不删文档）",
            )

        finally:
            await kb_service.delete_kb(db, user, temp_kb.id)
            if temp_kb2 is not None:
                await kb_service.delete_kb(db, user, temp_kb2.id)
                print(f"✓ 临时库 {temp_kb2.id} 已清理")
            print(f"✓ 临时库 {temp_kb.id} 已清理")

    print("\n🎉 P0-4 冒烟全绿（零 LLM 调用，全部检索层/DB 层断言）")


if __name__ == "__main__":
    asyncio.run(main())

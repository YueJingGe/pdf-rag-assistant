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

from app.core.config import settings  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.models.database import async_session_factory  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.knowledge_base import KnowledgeBase  # noqa: E402
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
MARKER_KB2 = "P04冒烟标记丙：北极星指示正北方向。"
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
        temp_kb3 = None
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

            # ⑫ 多库信息源（P0-4 第二轮 §8）：检索合并 + SSE 协议 + 权限负例
            # 第二库塞不同 marker 的在线文档，形成跨库两库可检索格局
            doc_kb2 = await document_service.create_online_document(
                db, user, temp_kb2.id,
                title="北极星笔记", content=f"# 笔记\n\n{MARKER_KB2}\n",
                category_id=cat_other.id,
            )
            _check(doc_kb2.status == "ready", "⑫ 第二库在线文档入库 ready")

            merged = await chat_service.multi_kb_retrieve(
                [temp_kb.id, temp_kb2.id], "海马 北极星"
            )
            merged_texts = [d.page_content for d in merged]
            _check(
                any("冒烟标记乙" in t for t in merged_texts),
                "⑫ 跨库合并命中库 1 内容",
            )
            _check(
                any("冒烟标记丙" in t for t in merged_texts),
                "⑫ 跨库合并命中库 2 内容",
            )
            _check(
                all(
                    d.metadata.get("knowledge_base_id") in (temp_kb.id, temp_kb2.id)
                    for d in merged
                ),
                "⑫ 合并结果 metadata 标记来源库",
            )
            _check(
                len(merged) <= settings.retrieval_top_k,
                f"⑫ 合并结果截断 ≤ retrieval_top_k({settings.retrieval_top_k})",
            )

            # SSE 协议：网关替换为 FakeListChatModel（零真实 LLM），断言 chunk 序列与单库对齐
            from langchain_core.language_models.fake_chat_models import (  # noqa: E402
                FakeListChatModel,
            )
            original_get_llm = chat_service.get_llm
            chat_service.get_llm = (  # type: ignore[assignment]
                lambda *a, **k: FakeListChatModel(responses=["多库合并链路OK"])
            )
            try:
                events = []
                async for ev in chat_service.multi_kb_rag_stream(
                    [temp_kb.id, temp_kb2.id], "海马 北极星"
                ):
                    events.append(ev)
            finally:
                chat_service.get_llm = original_get_llm  # type: ignore[assignment]
            _check(
                events[0]["type"] == "retrieval_debug" and events[-1]["type"] == "done",
                "⑫ SSE 事件首=retrieval_debug、尾=done（协议对齐单库）",
            )
            _check(
                events[0]["content"]["strategy"] == "multi_kb",
                "⑫ retrieval_debug.strategy=multi_kb",
            )
            token_evs = [e for e in events if e["type"] == "token"]
            _check(
                len(token_evs) > 0
                and "".join(e["content"] for e in token_evs) == "多库合并链路OK",
                "⑫ token 事件来自 fake 网关（零 LLM）",
            )
            citations_ev = next(e for e in events if e["type"] == "citations")
            _check(
                isinstance(citations_ev["content"], list)
                and len(citations_ev["content"]) > 0,
                "⑫ citations 非空（引用组装复用禁区公开逻辑）",
            )

            # 权限负例：多库合并链任一库无读权限 → PermissionDeniedError（SSE 前拦截）
            if other:
                try:
                    await chat_service.check_multi_kb_access(
                        db, [temp_kb.id, temp_kb2.id], other
                    )
                    _check(False, "⑫ 他人多库合并链应 PermissionDeniedError")
                except PermissionDeniedError:
                    print("✓ 他人无读权限 → PermissionDeniedError（403，SSE 前拦截）")
            else:
                print("⚠ 无其他用户，跳过 ⑫ 权限负例")

            # ⑬ 删库级联清理（P0-4 修复回归）：delete_kb 后目录/文档/会话/KB 行/uploads 物理目录全无残留
            # （修复前仅删 KB 行 + FAISS，孤儿目录曾被后续新建的同 id 库认领——迁移时实证）
            kb2_id = temp_kb2.id
            await kb_service.delete_kb(db, user, kb2_id)
            temp_kb2 = None  # 已删，finally 跳过重复删除
            residual = (
                await db.execute(select(Category).where(Category.kb_id == kb2_id))
            ).scalars().all()
            residual_docs = (
                await db.execute(
                    select(Document).where(Document.knowledge_base_id == kb2_id)
                )
            ).scalars().all()
            residual_convs = (
                await db.execute(
                    select(Conversation).where(Conversation.knowledge_base_id == kb2_id)
                )
            ).scalars().all()
            _check(
                not residual and not residual_docs and not residual_convs
                and await db.get(KnowledgeBase, kb2_id) is None,
                "⑬ 删库级联：categories/documents/conversations/KB 行全清",
            )
            _check(
                not (settings.upload_dir / str(kb2_id)).exists(),
                "⑬ 删库级联：uploads 物理目录已删",
            )

            # ⑭ 文档级问答（P0-4 第三轮 §9 T8）：doc_retrieve 后过滤隔离 + doc_rag_stream SSE 协议
            # 干扰文档：同库不同 marker，验证 document_id 过滤的跨文档隔离
            interference_doc = await document_service.create_online_document(
                db, user, temp_kb.id,
                title="干扰文档", content="P04冒烟标记丁：这份文档仅用于文档级隔离测试。\n",
                category_id=None,
            )
            _check(interference_doc.status == "ready", "⑭ 干扰文档入库 ready")

            scoped = await chat_service.doc_retrieve(temp_kb.id, online_doc.id, "海马 育儿袋")
            _check(
                len(scoped) > 0
                and all(d.metadata.get("document_id") == online_doc.id for d in scoped),
                "⑭ doc_retrieve 全部命中目标文档（metadata.document_id 过滤）",
            )
            _check(
                any("冒烟标记乙" in d.page_content for d in scoped),
                "⑭ 目标文档内容命中",
            )
            _check(
                not any("冒烟标记丁" in d.page_content for d in scoped),
                "⑭ 跨文档隔离：干扰文档内容不出现",
            )
            _check(
                len(scoped) <= settings.retrieval_top_k,
                f"⑭ 截断 ≤ retrieval_top_k({settings.retrieval_top_k})",
            )

            # 不存在文档 id → 过滤后为空（上层 yield「未找到」提示，不进 LLM）
            empty_scoped = await chat_service.doc_retrieve(temp_kb.id, 999999, "海马")
            _check(empty_scoped == [], "⑭ 不存在文档 id → 候选过滤后为空")

            # 归属校验：不存在文档 404；他人无读权限 403
            try:
                await chat_service.check_doc_access(db, temp_kb.id, 999999, user)
                _check(False, "⑭ 不存在文档应 NotFoundError")
            except NotFoundError:
                print("✓ 不存在文档 → NotFoundError（404 防串库枚举）")
            if other:
                try:
                    await chat_service.check_doc_access(
                        db, temp_kb.id, online_doc.id, other
                    )
                    _check(False, "⑭ 他人访问私有库文档应 PermissionDeniedError")
                except PermissionDeniedError:
                    print("✓ 他人无读权限 → PermissionDeniedError（403）")
            else:
                print("⚠ 无其他用户，跳过 ⑭ 权限负例")

            # SSE 协议：fake 网关零 LLM，事件序列与 multi_kb 链对齐
            original_get_llm_14 = chat_service.get_llm
            chat_service.get_llm = (  # type: ignore[assignment]
                lambda *a, **k: FakeListChatModel(responses=["文档级链路OK"])
            )
            try:
                doc_events = []
                async for ev in chat_service.doc_rag_stream(
                    temp_kb.id, online_doc.id, "海马 育儿袋"
                ):
                    doc_events.append(ev)
            finally:
                chat_service.get_llm = original_get_llm_14  # type: ignore[assignment]
            _check(
                doc_events[0]["type"] == "retrieval_debug" and doc_events[-1]["type"] == "done",
                "⑭ SSE 首=retrieval_debug、尾=done（协议对齐 multi_kb）",
            )
            _check(
                doc_events[0]["content"]["strategy"] == "doc_scoped",
                "⑭ retrieval_debug.strategy=doc_scoped",
            )
            doc_tokens = [e for e in doc_events if e["type"] == "token"]
            _check(
                len(doc_tokens) > 0
                and "".join(e["content"] for e in doc_tokens) == "文档级链路OK",
                "⑭ token 事件来自 fake 网关（零 LLM）",
            )
            doc_citations = next(
                e for e in doc_events if e["type"] == "citations"
            )
            _check(
                isinstance(doc_citations["content"], list)
                and len(doc_citations["content"]) > 0,
                "⑭ citations 非空且仅含目标文档",
            )

            # 空候选分支：不存在文档 → 固定提示语直出，不调 LLM
            hint_events = []
            async for ev in chat_service.doc_rag_stream(temp_kb.id, 999999, "任意问题"):
                hint_events.append(ev)
            hint_tokens = [e for e in hint_events if e["type"] == "token"]
            _check(
                len(hint_tokens) == 1 and "未找到" in hint_tokens[0]["content"]
                and hint_events[-1]["type"] == "done",
                "⑭ 空候选 → 「未找到」提示直出（不进 LLM）",
            )

            # ⑮ 多范围信息源（P0-4 第五轮 §11 T6）：整库 + 文档级多选混合 → multi_scope 链
            # 第三库塞两个在线文档（目标+干扰），与库 1 的 online_doc（标记乙）/interference_doc（标记丁）
            # 组成「库 1 文档组 + 库 3 整库」混合范围格局
            temp_kb3 = await kb_service.create_kb(
                db, user, name="smoke-p04-temp3", description="多范围冒烟临时库", permission="private"
            )
            kb3_doc = await document_service.create_online_document(
                db, user, temp_kb3.id,
                title="萤火虫攻略", content="# 笔记\n\nP04冒烟标记戊：萤火虫的腹部有发光细胞。\n",
                category_id=None,
            )
            kb3_noise = await document_service.create_online_document(
                db, user, temp_kb3.id,
                title="干扰文档三", content="P04冒烟标记己：这份文档仅用于整库范围对照。\n",
                category_id=None,
            )
            _check(
                kb3_doc.status == "ready" and kb3_noise.status == "ready",
                "⑮ 第三库两份在线文档入库 ready",
            )

            # resolve_doc_scopes：跨库文档分组正确
            scopes_15 = await chat_service.resolve_doc_scopes(
                db, [online_doc.id, kb3_doc.id], user
            )
            _check(
                set(scopes_15.keys()) == {temp_kb.id, temp_kb3.id}
                and scopes_15[temp_kb.id] == [online_doc.id],
                "⑮ resolve_doc_scopes 跨库分组正确",
            )
            try:
                await chat_service.resolve_doc_scopes(db, [999999], user)
                _check(False, "⑮ 不存在文档应 NotFoundError")
            except NotFoundError:
                print("✓ 不存在文档 → NotFoundError（404）")
            if other:
                try:
                    await chat_service.resolve_doc_scopes(
                        db, [online_doc.id], other
                    )
                    _check(False, "⑮ 他人解析私有库文档应 PermissionDeniedError")
                except PermissionDeniedError:
                    print("✓ 他人无读权限 → PermissionDeniedError（403，SSE 前拦截）")
            else:
                print("⚠ 无其他用户，跳过 ⑮ 权限负例")

            # 混合范围检索：库 1 仅命中指定文档（隔离干扰文档丁）、库 3 整库全取
            mixed = await chat_service.multi_scope_retrieve(
                [temp_kb3.id], {temp_kb.id: [online_doc.id]}, "海马 萤火虫 冒烟"
            )
            mixed_texts = [d.page_content for d in mixed]
            _check(
                any("冒烟标记乙" in t for t in mixed_texts),
                "⑮ 混合范围命中库 1 指定文档（标记乙）",
            )
            _check(
                not any("冒烟标记丁" in t for t in mixed_texts),
                "⑮ 文档组隔离：库 1 未选中的干扰文档（标记丁）不出现",
            )
            _check(
                any("冒烟标记戊" in t or "冒烟标记己" in t for t in mixed_texts),
                "⑮ 混合范围命中库 3 整库候选",
            )
            _check(
                all(
                    d.metadata.get("knowledge_base_id") in (temp_kb.id, temp_kb3.id)
                    for d in mixed
                ),
                "⑮ 合并结果 metadata 标记来源库",
            )
            _check(
                len(mixed) <= settings.retrieval_top_k,
                f"⑮ 截断 ≤ retrieval_top_k({settings.retrieval_top_k})",
            )

            # 纯文档范围（kb_ids 为空）：仅命中指定文档
            doc_only = await chat_service.multi_scope_retrieve(
                [], {temp_kb.id: [online_doc.id]}, "海马 冒烟"
            )
            _check(
                len(doc_only) > 0
                and all(
                    d.metadata.get("document_id") == online_doc.id for d in doc_only
                ),
                "⑮ 纯文档范围仅命中指定文档",
            )

            # SSE 协议：fake 网关零 LLM，事件序列与 multi_kb 链对齐（strategy=multi_scope）
            original_get_llm_15 = chat_service.get_llm
            chat_service.get_llm = (  # type: ignore[assignment]
                lambda *a, **k: FakeListChatModel(responses=["多范围链路OK"])
            )
            try:
                scope_events = []
                async for ev in chat_service.multi_scope_rag_stream(
                    [temp_kb3.id], {temp_kb.id: [online_doc.id]}, "海马 萤火虫"
                ):
                    scope_events.append(ev)
            finally:
                chat_service.get_llm = original_get_llm_15  # type: ignore[assignment]
            _check(
                scope_events[0]["type"] == "retrieval_debug"
                and scope_events[-1]["type"] == "done",
                "⑮ SSE 首=retrieval_debug、尾=done（协议对齐 multi_kb）",
            )
            _check(
                scope_events[0]["content"]["strategy"] == "multi_scope",
                "⑮ retrieval_debug.strategy=multi_scope",
            )
            scope_tokens = [e for e in scope_events if e["type"] == "token"]
            _check(
                len(scope_tokens) > 0
                and "".join(e["content"] for e in scope_tokens) == "多范围链路OK",
                "⑮ token 事件来自 fake 网关（零 LLM）",
            )
            scope_citations = next(
                e for e in scope_events if e["type"] == "citations"
            )
            _check(
                isinstance(scope_citations["content"], list)
                and len(scope_citations["content"]) > 0,
                "⑮ citations 非空",
            )

        finally:
            await kb_service.delete_kb(db, user, temp_kb.id)
            if temp_kb2 is not None:
                await kb_service.delete_kb(db, user, temp_kb2.id)
                print(f"✓ 临时库 {temp_kb2.id} 已清理")
            if temp_kb3 is not None:
                await kb_service.delete_kb(db, user, temp_kb3.id)
                print(f"✓ 临时库 {temp_kb3.id} 已清理")
            print(f"✓ 临时库 {temp_kb.id} 已清理")

    print("\n🎉 P0-4 冒烟全绿（零 LLM 调用，全部检索层/DB 层断言）")


if __name__ == "__main__":
    asyncio.run(main())

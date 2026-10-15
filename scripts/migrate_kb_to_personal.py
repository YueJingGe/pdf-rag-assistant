"""P0-4 第二轮一次性迁移：用户名下多个知识库 → 一个「个人知识库」+ 同名目录。

背景：
    用户对照乐享纠正概念模型：通信/金融等应为「个人知识库」下的目录（分组），
    而非独立知识库。本脚本把指定用户名下的全部库合并进一个目标库。

脚本行为（默认 dry-run 只打印计划，--apply 才落库）：
    1. 定位用户（--user 按 username）与其名下全部知识库
    2. 目标库：名下已存在同名库（--target-name，默认「个人知识库」）则复用最早创建的，
       否则新建
    3. 每个源库 → 目标库下同名目录（与目标库现有目录重名时自动 -2/-3 后缀）：
       - 文档物理文件 uploads/{src}/ -> uploads/{dst}/（逐文件 move，相对 backend 解析）
       - documents: knowledge_base_id / category_id / file_path 更新（content 列随行）
       - conversations: knowledge_base_id 改指目标库（会话历史跟走）
       - 源库 FAISS 索引目录 faiss_indexes/{src} 删除
       - 源库行删除
    4. 打印收尾指引（重建索引 + 重启后端）

安全设计：
    - --apply 前自动备份 db.sqlite3 -> db.sqlite3.bak-p04r2
    - --apply 时若检测到 8000 端口有后端在跑，拒绝执行（避免 SQLite 并发写 +
      后端内存中 FAISS 缓存过期），请先停后端
    - 幂等：源库不存在自然跳过；目标库/目录按名复用，可重复执行
    - 索引重建不在本脚本内做（复用 scripts/rebuild_index.py，产生 embedding API 调用，
      由用户自行执行）

用法：
    cd <项目根>
    python3 scripts/migrate_kb_to_personal.py --user 18838166792              # dry-run
    python3 scripts/migrate_kb_to_personal.py --user 18838166792 --apply      # 执行
    python3 backend/scripts/rebuild_index.py <目标库ID>   # 见脚本输出指引（项目根下为 scripts/rebuild_index.py）
"""

import argparse
import shutil
import socket
import sys
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_DB = BACKEND_DIR / "data" / "db.sqlite3"
BACKUP_SUFFIX = ".bak-p04r2"
DEFAULT_TARGET_NAME = "个人知识库"


def resolve_db_path() -> Path:
    """从 backend/.env 的 DATABASE_URL 解析 SQLite 路径（相对路径相对 backend 解析）。"""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
                if not url.startswith("sqlite"):
                    print(f"⚠️  DATABASE_URL 非 SQLite（{url}），回退默认路径")
                    break
                raw_path = url.split("///", 1)[1] if "///" in url else ""
                if raw_path:
                    path = Path(raw_path)
                    if not path.is_absolute():
                        path = (BACKEND_DIR / path).resolve()
                    return path
                break
    return DEFAULT_DB


def backend_port_busy(port: int = 8000) -> bool:
    """检测本机端口是否有进程监听（后端在跑则拒绝 --apply）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def unique_name(existing: set, name: str) -> str:
    """目标库内目录重名时追加 -2/-3 后缀。"""
    if name not in existing:
        return name
    i = 2
    while f"{name}-{i}" in existing:
        i += 1
    return f"{name}-{i}"


def main() -> None:
    parser = argparse.ArgumentParser(description="多知识库合并为个人知识库+目录（P0-4 第二轮）")
    parser.add_argument("--user", required=True, help="按 username 定位库归属用户")
    parser.add_argument("--target-name", default=DEFAULT_TARGET_NAME, help=f"目标库名（默认 {DEFAULT_TARGET_NAME}）")
    parser.add_argument("--apply", action="store_true", help="真正执行（默认 dry-run 只打印计划）")
    args = parser.parse_args()

    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"❌ 数据库文件不存在：{db_path}")
        sys.exit(1)

    if args.apply and backend_port_busy():
        print("❌ 检测到 8000 端口有后端在运行。请先停后端再执行迁移（lsof -ti :8000 | xargs kill），")
        print("   迁移完成并重建索引后再启动后端。")
        sys.exit(1)

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    # ---- 1. 定位用户与库 ----
    user_row = session.execute(
        text("SELECT id, username, display_name FROM users WHERE username = :u"),
        {"u": args.user},
    ).fetchone()
    if not user_row:
        print(f"❌ 用户不存在：{args.user}")
        sys.exit(1)
    user_id, username, display_name = user_row
    print(f"用户：{username}（id={user_id}，{display_name}）")

    kbs = session.execute(
        text("SELECT id, name, description FROM knowledge_bases WHERE user_id = :uid ORDER BY id"),
        {"uid": user_id},
    ).fetchall()
    if not kbs:
        print("ℹ️  该用户名下没有知识库，无事可做。")
        return

    target = next((kb for kb in kbs if kb[1] == args.target_name), None)

    # ---- 2. 打印迁移计划 ----
    print(f"\n===== 迁移计划（{'APPLY' if args.apply else 'DRY-RUN'}）=====")
    if target:
        print(f"目标库：复用 #{target[0]}「{target[1]}」")
    else:
        print(f"目标库：新建「{args.target_name}」")
    for kb in kbs:
        if target and kb[0] == target[0]:
            continue
        doc_cnt = session.execute(
            text("SELECT COUNT(*) FROM documents WHERE knowledge_base_id = :k"), {"k": kb[0]}
        ).scalar()
        conv_cnt = session.execute(
            text("SELECT COUNT(*) FROM conversations WHERE knowledge_base_id = :k"), {"k": kb[0]}
        ).scalar()
        print(f"  源库 #{kb[0]}「{kb[1]}」：{doc_cnt} 文档, {conv_cnt} 会话 → 目录「{kb[1]}」")

    if not args.apply:
        print("\n（dry-run 未做任何改动；确认无误后加 --apply 执行）")
        return

    # ---- 3. 执行 ----
    backup_path = db_path.with_suffix(db_path.suffix + BACKUP_SUFFIX)
    shutil.copy2(db_path, backup_path)
    print(f"\n✅ 已自动备份：{backup_path}")

    moved_files: list[tuple[Path, Path]] = []  # (from, to) 供失败时人工恢复

    try:
        # 目标库
        if target is None:
            desc = "个人知识库：由 P0-4 第二轮迁移脚本创建"
            result = session.execute(
                text(
                    "INSERT INTO knowledge_bases (user_id, name, description, permission, created_at, updated_at) "
                    "VALUES (:uid, :name, :desc, 'private', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"uid": user_id, "name": args.target_name, "desc": desc},
            )
            dst_id = result.lastrowid
            print(f"✅ 新建目标库 #{dst_id}「{args.target_name}」")
        else:
            dst_id = target[0]

        # 目标库现有目录名（用于重名去重）
        existing_cat_names = {
            r[0]
            for r in session.execute(
                text("SELECT name FROM categories WHERE kb_id = :k"), {"k": dst_id}
            ).fetchall()
        }

        for kb in kbs:
            src_id, src_name = kb[0], kb[1]
            if target and src_id == dst_id:
                continue

            # 3.1 建目录
            cat_name = unique_name(existing_cat_names, src_name)
            existing_cat_names.add(cat_name)
            result = session.execute(
                text(
                    "INSERT INTO categories (kb_id, parent_id, name, sort_order, created_at, updated_at) "
                    "VALUES (:k, NULL, :name, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"k": dst_id, "name": cat_name},
            )
            cat_id = result.lastrowid
            print(f"✅ 目录「{cat_name}」(#id={cat_id}) 已建入目标库 #{dst_id}")

            # 3.2 迁移文档：物理文件 move + DB 更新
            docs = session.execute(
                text(
                    "SELECT id, file_path FROM documents WHERE knowledge_base_id = :k"
                ),
                {"k": src_id},
            ).fetchall()
            for doc_id, file_path in docs:
                rel = str(file_path)  # 形如 data/uploads/{src}/{uuid}_{filename}
                src_file = BACKEND_DIR / rel
                new_rel = rel.replace(f"data/uploads/{src_id}/", f"data/uploads/{dst_id}/", 1)
                dst_file = BACKEND_DIR / new_rel
                if src_file.exists():
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src_file), str(dst_file))
                    moved_files.append((src_file, dst_file))
                else:
                    print(f"  ⚠️  文档 #{doc_id} 物理文件缺失（继续迁移记录）：{rel}")
                session.execute(
                    text(
                        "UPDATE documents SET knowledge_base_id = :dst, category_id = :cat, "
                        "file_path = :fp WHERE id = :did"
                    ),
                    {"dst": dst_id, "cat": cat_id, "fp": new_rel, "did": doc_id},
                )
            print(f"  ✅ {len(docs)} 篇文档 → 目录「{cat_name}」")

            # 3.3 会话跟走
            conv_cnt = session.execute(
                text(
                    "UPDATE conversations SET knowledge_base_id = :dst WHERE knowledge_base_id = :src"
                ),
                {"dst": dst_id, "src": src_id},
            ).rowcount
            if conv_cnt:
                print(f"  ✅ {conv_cnt} 个会话改指目标库")

            # 3.4 删源库 FAISS 索引目录
            src_index_dir = BACKEND_DIR / "data" / "faiss_indexes" / str(src_id)
            if src_index_dir.exists():
                shutil.rmtree(src_index_dir)
                print(f"  ✅ 源库索引目录已删：{src_index_dir.name}/")

            # 3.5 删源库行（空 uploads/{src} 目录顺带清理）
            session.execute(text("DELETE FROM knowledge_bases WHERE id = :k"), {"k": src_id})
            src_upload_dir = BACKEND_DIR / "data" / "uploads" / str(src_id)
            if src_upload_dir.exists() and not any(src_upload_dir.iterdir()):
                src_upload_dir.rmdir()
            print(f"  ✅ 源库 #{src_id}「{src_name}」已删除")

        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"\n❌ 迁移失败已回滚 DB：{exc}")
        if moved_files:
            print("⚠️  以下物理文件已移动，需手动移回（或用备份恢复后重试）：")
            for src, dst in moved_files:
                print(f"    {src} -> {dst}")
        sys.exit(1)
    finally:
        session.close()
        engine.dispose()

    # ---- 4. 收尾指引 ----
    print(
        f"""
🎉 迁移完成。收尾两步（必须执行）：

  1. 重建目标库向量索引（会产生 embedding API 调用）：
     python3 scripts/rebuild_index.py {dst_id}

  2. 重启后端：
     cd backend && nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 &

如需回滚：cp {backup_path} {db_path}（物理文件需按上方 move 列表手动还原）
"""
    )


if __name__ == "__main__":
    main()

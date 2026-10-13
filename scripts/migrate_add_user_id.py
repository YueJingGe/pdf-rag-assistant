"""一次性迁移脚本：为 knowledge_bases / conversations 增加 user_id 字段并回填。

背景：
    项目未引入 Alembic（保持轻量），init_db() 的 create_all 只能建新表、
    不会给存量表加列，因此存量 SQLite 库需要本脚本做一次结构迁移。

脚本行为（幂等，可重复执行）：
    1. 内部自动备份：复制 db.sqlite3 -> db.sqlite3.bak（中途失败可直接回滚）
    2. ALTER TABLE 增加可空列 user_id INTEGER REFERENCES users(id)（已存在则跳过）
    3. 创建索引 ix_knowledge_bases_user_id / ix_conversations_user_id
    4. 回填存量数据 user_id，三级兜底：
       a. 优先取 is_admin=1 的最小用户 id
       b. 若无 admin，取 users 表最小 id（第一个注册用户接管）
       c. 若 users 表为空，保持 NULL，并提示"请先注册管理员账号后重跑此脚本"
    5. 打印迁移前后统计

用法：
    cd <项目根>
    python3 scripts/migrate_add_user_id.py
"""

import shutil
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_DB = BACKEND_DIR / "data" / "db.sqlite3"


def resolve_db_path() -> Path:
    """从 backend/.env 读取 DATABASE_URL，解析出 SQLite 文件路径。

    支持 "sqlite+aiosqlite:///./data/db.sqlite3" / "sqlite:///..." 两种写法；
    相对路径一律相对 backend 目录解析（与 uvicorn 启动目录一致）。
    读取失败或非 SQLite 配置时回退到默认路径。
    """
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
                if not url.startswith("sqlite"):
                    print(f"⚠️  DATABASE_URL 非 SQLite（{url}），本脚本仅支持 SQLite，回退默认路径")
                    break
                raw_path = url.split("///", 1)[1] if "///" in url else ""
                if raw_path:
                    path = Path(raw_path)
                    if not path.is_absolute():
                        path = (BACKEND_DIR / path).resolve()
                    return path
                break
    return DEFAULT_DB


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchone()
    return row is not None


def migrate() -> None:
    print("⚠️  执行前请确认已备份：cp backend/data/db.sqlite3 backend/data/db.sqlite3.bak")

    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"❌ 数据库文件不存在：{db_path}")
        sys.exit(1)

    # 内部双保险：迁移前自动复制一份，中途失败可用该文件回滚
    backup_path = db_path.with_suffix(db_path.suffix + ".bak")
    shutil.copy2(db_path, backup_path)
    print(f"✅ 已自动备份：{db_path} -> {backup_path}")

    # 同步驱动执行 DDL/DML（去掉 +aiosqlite 异步驱动标记）
    sync_url = f"sqlite:///{db_path}"
    engine = create_engine(sync_url)

    with engine.begin() as conn:
        # 1. 加列（幂等）
        for table in ("knowledge_bases", "conversations"):
            if not table_exists(conn, table):
                print(f"⏭️  表 {table} 不存在，跳过（新库由 create_all 直接建出带 user_id 的表）")
                continue
            if column_exists(conn, table, "user_id"):
                print(f"⏭️  {table}.user_id 列已存在，跳过 ALTER")
            else:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
                ))
                print(f"✅ ALTER TABLE {table} ADD COLUMN user_id")

            # 2. 建索引（幂等）
            index_name = f"ix_{table}_user_id"
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} (user_id)"
            ))
            print(f"✅ 索引 {index_name} 就绪")

        # 3. 三级兜底回填
        if not table_exists(conn, "users"):
            print("ℹ️  users 表不存在，跳过回填（保持 user_id 为 NULL）")
            fallback_user_id = None
        else:
            admin_row = conn.execute(
                text("SELECT MIN(id) FROM users WHERE is_admin = 1")
            ).scalar()
            if admin_row is not None:
                fallback_user_id = admin_row
                print(f"ℹ️  兜底策略 [1/3]：使用 admin 用户 id={admin_row}")
            else:
                first_row = conn.execute(text("SELECT MIN(id) FROM users")).scalar()
                if first_row is not None:
                    fallback_user_id = first_row
                    print(f"ℹ️  兜底策略 [2/3]：无 admin，使用第一个注册用户 id={first_row}")
                else:
                    fallback_user_id = None
                    print("ℹ️  兜底策略 [3/3]：users 表为空，保持 NULL")

        if fallback_user_id is not None:
            for table in ("knowledge_bases", "conversations"):
                if not table_exists(conn, table):
                    continue
                result = conn.execute(
                    text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                    {"uid": fallback_user_id},
                )
                print(f"✅ 回填 {table}: {result.rowcount} 行 -> user_id={fallback_user_id}")
        else:
            print("⚠️  请先注册管理员账号后重跑此脚本（python3 scripts/migrate_add_user_id.py）")

        # 4. 迁移后统计
        print("\n===== 迁移后统计 =====")
        for table in ("knowledge_bases", "conversations"):
            if not table_exists(conn, table):
                continue
            total = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            null_cnt = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL")
            ).scalar()
            print(f"{table}: 共 {total} 行，user_id 已归属 {total - null_cnt} 行，NULL {null_cnt} 行")

    engine.dispose()
    print("\n🎉 迁移完成。如中途失败，可用备份回滚：cp backend/data/db.sqlite3.bak backend/data/db.sqlite3")


if __name__ == "__main__":
    migrate()

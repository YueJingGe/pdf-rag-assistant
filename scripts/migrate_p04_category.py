"""P0-4 一次性迁移脚本：新增 categories 目录树表 + documents 扩展 3 列。

背景：
    P0-4「乐享式知识库」引入目录树组织（categories 单亲模型），并为
    documents 增加 来源（source）/ 目录归属（category_id）/ 在线文档正文
    （content）三列。项目未引入 Alembic，init_db() 的 create_all 只建新表、
    不给存量表加列，因此存量 SQLite 库需要本脚本做一次结构迁移。

脚本行为（幂等，可重复执行）：
    1. 内部自动备份：复制 db.sqlite3 -> db.sqlite3.bak（中途失败可直接回滚）
    2. CREATE TABLE IF NOT EXISTS categories（新库由 create_all 直接建出，此处兜底）
    3. documents 逐列检查并 ADD COLUMN：source / category_id / content
    4. 创建索引 ix_categories_kb_id / ix_documents_category_id
    5. 打印迁移后统计

语义约定（与 docs/requirements/P0-4-lexiang-style-kb.md §4.1 一致）：
    - documents.source：'upload'（存量行由列默认值补齐）/ 'online'
    - documents.category_id：NULL = 未归类（挂根），无需回填
    - documents.content：仅 online 文档有值，上传文档保持 NULL

用法：
    cd <项目根>
    python3 scripts/migrate_p04_category.py
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


def table_exists(conn, table: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).fetchone()
    return row is not None


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


CATEGORIES_DDL = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id),
    parent_id INTEGER REFERENCES categories(id),
    name VARCHAR(255) NOT NULL,
    sort_order INTEGER,
    created_at DATETIME,
    updated_at DATETIME
)
"""

# documents 新增列：每列独立幂等检查（source 用常量默认值，SQLite 允许）
DOCUMENT_NEW_COLUMNS = [
    ("source", "VARCHAR(16) NOT NULL DEFAULT 'upload'", "来源：upload/online"),
    ("category_id", "INTEGER REFERENCES categories(id)", "所属目录：NULL=未归类挂根"),
    ("content", "TEXT", "仅 online 文档：MD 原文真相源"),
]


def migrate() -> None:
    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"❌ 数据库文件不存在：{db_path}")
        sys.exit(1)

    # 内部双保险：迁移前自动复制一份，中途失败可用该文件回滚
    backup_path = db_path.with_suffix(db_path.suffix + ".bak")
    shutil.copy2(db_path, backup_path)
    print(f"✅ 已自动备份：{db_path} -> {backup_path}")

    # 同步驱动执行 DDL（去掉 +aiosqlite 异步驱动标记）
    sync_url = f"sqlite:///{db_path}"
    engine = create_engine(sync_url)

    with engine.begin() as conn:
        # 1. categories 表（幂等）
        if table_exists(conn, "categories"):
            print("⏭️  表 categories 已存在，跳过 CREATE TABLE")
        else:
            conn.execute(text(CATEGORIES_DDL))
            print("✅ CREATE TABLE categories")

        # 2. documents 扩展 3 列（逐列幂等）
        if table_exists(conn, "documents"):
            for col_name, col_ddl, col_desc in DOCUMENT_NEW_COLUMNS:
                if column_exists(conn, "documents", col_name):
                    print(f"⏭️  documents.{col_name} 列已存在，跳过")
                else:
                    conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_ddl}"))
                    print(f"✅ ALTER TABLE documents ADD COLUMN {col_name}（{col_desc}）")
        else:
            print("⏭️  表 documents 不存在，跳过加列（新库由 create_all 直接建出全列）")

        # 3. 索引（幂等）
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_categories_kb_id ON categories (kb_id)"))
        print("✅ 索引 ix_categories_kb_id 就绪")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_documents_category_id ON documents (category_id)"
        ))
        print("✅ 索引 ix_documents_category_id 就绪")

        # 4. 迁移后统计
        print("\n===== 迁移后统计 =====")
        if table_exists(conn, "categories"):
            total = conn.execute(text("SELECT COUNT(*) FROM categories")).scalar()
            print(f"categories: {total} 行")
        if table_exists(conn, "documents"):
            total = conn.execute(text("SELECT COUNT(*) FROM documents")).scalar()
            online = conn.execute(
                text("SELECT COUNT(*) FROM documents WHERE source = 'online'")
            ).scalar()
            categorized = conn.execute(
                text("SELECT COUNT(*) FROM documents WHERE category_id IS NOT NULL")
            ).scalar()
            print(f"documents: 共 {total} 行，online {online} 行，已挂目录 {categorized} 行")

    engine.dispose()
    print("\n🎉 迁移完成。如中途失败，可用备份回滚：cp backend/data/db.sqlite3.bak backend/data/db.sqlite3")


if __name__ == "__main__":
    migrate()

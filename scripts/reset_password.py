"""重置指定用户的登录密码（本地运维工具，无需登录态）。

用法（在项目根目录执行）：
    python3 scripts/reset_password.py <用户名> <新密码>

示例：
    python3 scripts/reset_password.py 18838166792 MyNewPass123
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

# 相对路径（./data/db.sqlite3、.env）均以 backend 目录为基准
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.auth import hash_password  # noqa: E402  复用业务侧 bcrypt 加密
from app.core.config import settings  # noqa: E402


def reset_password(username: str, new_password: str) -> None:
    # 同步驱动执行（去掉 +aiosqlite 异步驱动标记）
    sync_url = settings.database_url.replace("+aiosqlite", "")
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM users WHERE username = :u"),
            {"u": username},
        ).fetchone()
        if not row:
            print(f"❌ 用户不存在：{username}")
            sys.exit(1)
        conn.execute(
            text("UPDATE users SET hashed_password = :p WHERE username = :u"),
            {"p": hash_password(new_password), "u": username},
        )
    engine.dispose()
    print(f"✅ 已重置用户 {username}（id={row[0]}）的密码，请用新密码重新登录")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    reset_password(sys.argv[1], sys.argv[2])

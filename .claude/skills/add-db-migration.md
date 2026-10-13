# Skill：新增一个数据库迁移脚本（add-db-migration）

> 项目不用 Alembic（SQLite + create_all 不加列），改模型必须配套迁移脚本。范例：`scripts/migrate_add_user_id.py`。

## 脚本骨架（照抄结构）

```python
"""<迁移目的>。用法：python3 scripts/migrate_xxx.py"""
import os, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)                      # 相对路径（data/、.env）以 backend 为基准

from sqlalchemy import create_engine, text
from app.core.config import settings

def main() -> None:
    # ① 自动备份
    import shutil
    shutil.copy2(BACKEND_DIR / "data/db.sqlite3", BACKEND_DIR / "data/db.sqlite3.bak")
    print("已备份 → data/db.sqlite3.bak")

    engine = create_engine(settings.database_url.replace("+aiosqlite", ""))
    with engine.begin() as conn:
        # ② 幂等检查（PRAGMA）
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(target_table)"))]
        if "new_col" in cols:
            print("已迁移，跳过"); return
        # ③ 变更
        conn.execute(text("ALTER TABLE target_table ADD COLUMN new_col ..."))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ..."))
        # ④ 存量行兜底回填（三级：admin 最小 id → 第一个注册用户 → NULL+提示）
    engine.dispose()
```

## 三原则

1. **幂等**：跑两遍，第二遍必须输出"已迁移，跳过"
2. **自动备份**：内部 copy2 到 `.bak`（已在 .gitignore），打印提醒
3. **兜底回填**：NULL 语义按 `docs/rules/40-database.md`（NULL = 存量兼容 = 公共可读）

## 标准验证

```bash
python3 scripts/migrate_xxx.py    # 第 1 遍：执行
python3 scripts/migrate_xxx.py    # 第 2 遍：跳过
sqlite3 backend/data/db.sqlite3 "PRAGMA table_info(target_table);"
```

之后：重启后端 → 受影响端点 curl 回归 → changelog 追加。

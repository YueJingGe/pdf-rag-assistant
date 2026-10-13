# 40 数据库规范（Database）

## ORM 建模

- SQLAlchemy 2.0 `Mapped[]` 声明式写法；每个业务表模型一个文件，放 `app/models/`
- 归属字段统一：`user_id: Mapped[Optional[int]]` + `ForeignKey("users.id")` + `index=True`
- 时间字段 `DateTime` + `default=datetime.utcnow`

## user_id 归属规则（P0-1 核心，语义勿改）

| 判定顺序 | 规则 | 说明 |
|---|---|---|
| 1 | `user.is_admin` → 全部权限 | 管理直通 |
| 2 | `kb.user_id == user.id` → owner | 写权限仅 owner/admin |
| 3 | `kb.user_id IS NULL` → 公共可读 | **存量数据兼容约定**：老数据无归属，视为 public，可读不可写（写仅 admin） |
| 4 | `kb.permission == "public"` → 全员可读 | |
| 5 | 查 `kb_permissions` 表授权记录 | 按 ROLE_LEVELS（viewer=1/member=2/owner=3）比较是否达标 |

判定逻辑唯一实现处：`core/auth.py` 的 `has_kb_permission`（纯判定）/ `ensure_kb_permission`（强校验，见 ADR-001）。**其他代码不得自行实现归属判断**。

## 迁移脚本三原则（无 Alembic，脚本放 `scripts/`）

1. **幂等**：先 `PRAGMA table_info` 检查列/索引是否已存在，重复运行零副作用
2. **自动备份**：脚本内部 `shutil.copy2` 备份 `db.sqlite3` → `db.sqlite3.bak`，并打印备份路径提醒
3. **三级兜底回填**：存量行 user_id 回填顺序 —— ① 最小 id 的 admin → ② 第一个注册用户 → ③ 保持 NULL 并打印提示

**范例脚本**：`scripts/migrate_add_user_id.py`（P0-1 实测：3 KB + 32 会话回填，兜底策略 [2/3] 触发）。新迁移脚本照此结构写。

## SQLite 约束（踩过坑的）

- `init_db()` 的 `create_all` **不会给存量表加列** → 每次改模型必须配套写迁移脚本，否则线上表缺列直接 500
- 路径解析：`settings.DATABASE_URL` 是相对 `backend/` 的路径，独立脚本需 `os.chdir(BACKEND_DIR)` 或显式解析（见 reset_password.py 写法）
- async 驱动 `sqlite+aiosqlite`，同步脚本执行时去掉驱动标记换 `create_engine`
- 备份文件 `*.bak` 已加入 `.gitignore`，确认稳定后可手动删除

## 验证迁移的标准动作

```bash
python3 scripts/migrate_xxx.py        # 跑第 1 遍：执行变更
python3 scripts/migrate_xxx.py        # 跑第 2 遍：应输出"已迁移，跳过"
sqlite3 backend/data/db.sqlite3 "PRAGMA table_info(xxx);"   # 复核列结构
```

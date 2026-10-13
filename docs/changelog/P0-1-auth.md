# P0-1 Changelog：鉴权强制执行 + 数据归属

> ⚠️ 本文档为事后补写，用于建立留痕规范范例，非事前设计。
> 补写日期：2026-10-13
> 依据：P0-1 实施过程中的对话与代码 diff

---

## 2026-10-13 下午 · 第 2 轮：登录误弹修复 + 密码重置工具 + 存量归属划归

- **改动摘要**：修复登录密码错误时误弹「登录已过期」；新增密码重置脚本；把迁移时划给 id=1 的存量 3 KB + 32 会话划归给实际使用者 id=2
- **diff 摘要**：
  - `frontend/src/services/api.ts` (+6/-1)：401 拦截器排除 `/auth/login`、`/auth/register` 的业务性 401
  - `scripts/reset_password.py`（新建，+51）：免登录态重置指定用户密码（bcrypt，os.chdir 解决相对路径）
  - `backend/data/db.sqlite3`：UPDATE knowledge_bases / conversations 的 user_id（运行时数据不入库，仅记录操作）
  - `重难点以及遇到的问题.md` (+14)：新增 8.4 节记录根因与修复
- **验收结果**：
  - `npx tsc -b` exit=0
  - 脚本实测：testuser_a 重置后新密码登录返回 token，错误密码 401
  - `18838166792` 重置后登录成功；可见知识库 0 → 划归后 3 个（金融/司库奇尤单抗注射液说明书/通信），kb_1 历史会话可见

## 2026-10-13 上午 · 第 1 轮：P0-1 主体改造

- **改动摘要**：模型加 user_id 归属 → 迁移脚本回填 → 4 个路由文件全端点挂鉴权 → 权限核心重构 → 前端 401/登录门配合
- **diff 摘要**：
  - `backend/app/models/knowledge_base.py`、`conversation.py`：新增 `user_id` Mapped[Optional[int]] 外键索引
  - `backend/app/core/auth.py`（重构）：ROLE_LEVELS、has_kb_permission（纯判定，含 kb_permissions 授权查询）、ensure_kb_permission（404/403 强校验并返回 KB）
  - `backend/app/api/knowledge_bases.py`：5 端点，create 写 user_id，list 用 or_ 可见性过滤，get/update/delete 接 ensure
  - `backend/app/api/documents.py`：7 端点挂鉴权
  - `backend/app/api/chat.py`：6 端点 + `_get_own_conversation`（他人会话 404 防枚举）+ 会话列表过滤
  - `backend/app/api/feedback.py`：3 端点挂鉴权
  - `frontend/src/services/api.ts`：401 响应拦截器 + auth:unauthorized 广播
  - `frontend/src/hooks/useSSE.ts`：SSE 401 事件广播（不经 axios）
  - `frontend/src/App.tsx`：登录门（未登录渲染欢迎页）、401 监听、restoreVisibleKB
  - `scripts/migrate_add_user_id.py`（新建，158 行）：幂等 + 自动备份 + 三级兜底
  - `README.md` 4 处更新；`重难点以及遇到的问题.md` 新增第八章
- **验收结果**（19 步 curl 实测全通过）：
  - 401：无 token 访问业务接口全部 401 ✓
  - 403：普通用户更新他人库 → 403；删除 → 403 ✓
  - 会话隔离：B 访问 A 的会话 → 404 ✓
  - 存量回填：3 KB + 32 会话归属正确，兜底策略 [2/3]（第一个注册用户）触发 ✓
  - 锁图标：openapi.json 中 22 端点带 security，仅 register/login/health 公开 ✓
  - 迁移幂等：重复运行输出"已迁移，跳过" ✓
  - `python -m py_compile` 全通过、`from app.main import app` 加载 29 路由、`tsc -b` exit=0
- **遗留事项**：
  - 测试账号 testuser_a / testuser_b（id=3/4）留在库中待清理
  - kb_permissions 查询侧已就位，授权管理 API 留到 P1
  - db.sqlite3.bak 备份确认稳定后可删

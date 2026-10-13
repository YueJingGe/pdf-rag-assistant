# P0-1 鉴权强制执行 + 数据归属

> ⚠️ 本文档为事后补写，用于建立留痕规范范例，非事前设计。
> 补写日期：2026-10-13
> 依据：P0-1 实施过程中的对话与代码 diff

## 背景

项目评估发现：`core/auth.py` 已实现认证工具（require_user / require_admin），但**业务路由零挂载**——任何匿名请求都能增删任意知识库、查看任意会话。同时数据模型无归属字段，无法区分"谁的数据"。

## 目标

1. 所有业务 API 端点强制鉴权（仅注册/登录/健康检查公开）
2. KnowledgeBase / Conversation 增加 user_id 归属，按归属隔离数据
3. 存量数据平滑迁移（SQLite，无 Alembic）
4. 前端配合：未登录不发业务请求，401 统一处理

## 任务分解

| # | 任务 | 产出 |
|---|---|---|
| 1 | 模型层加 `user_id`（可空、外键、索引） | models/knowledge_base.py、conversation.py |
| 2 | 一次性幂等迁移脚本（方案 A，自备份 + 三级兜底回填） | scripts/migrate_add_user_id.py |
| 3 | 4 个 API 路由文件全部挂载鉴权 | api/ 下 4 文件（feedback 含 3 端点） |
| 4 | 权限判定落地：public 全员可读 / private 仅 owner+授权者 / 写仅 owner / 404-403 语义 | core/auth.py 重构 |
| 5 | 会话归属：列表/删除只操作本人数据 | api/chat.py |
| 6 | 前端：401 拦截器、登录门、selectedKB 可见性校验 | api.ts、useSSE.ts、App.tsx |

## 验收标准

1. 未登录访问任意业务接口 → 401
2. 无权限操作他人/私有资源 → 403
3. 用户 A 无法看到/操作用户 B 的会话 → 会话隔离
4. 存量数据迁移后归属正确（3 KB + 32 会话回填）
5. Swagger 文档中业务端点全部带锁图标（22 个锁定，3 个公开）

## 边界决策（实施中确认）

| 决策 | 内容 | 状态 |
|---|---|---|
| NULL 归属语义 | user_id 为 NULL 的存量数据视为 public 可读，写操作仅 admin | 用户确认采纳 |
| admin 直通 | is_admin 用户绕过全部归属检查 | 用户确认采纳 |
| 兜底回填顺序 | admin 最小 id → 第一个注册用户 → 保持 NULL 并提示 | 用户要求补充 |
| 权限函数拆分 | has_kb_permission（纯判定）+ ensure_kb_permission（强校验） | 可选项采纳，见 ADR-001 |
| 迁移备份 | 脚本内部 shutil.copy2 自动备份 db.sqlite3.bak | 用户要求补充 |
| 前端 selectedKB | 登录后校验恢复的选中库可见性，不可见回退第一个库 | 用户要求补充 |
| 他人会话状态码 | 统一 404（防会话 ID 枚举探测），非 403 | AI 提案默认 |

## 不改范围（约束）

- RAG 核心链路（loader/splitter/retrieval/vector_store/rag_chain）零改动
- 不引入 Alembic / Redis；API 路径不变（前端业务代码除配合项外不动）

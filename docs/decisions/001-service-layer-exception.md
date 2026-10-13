# ADR-001：check_kb_permission 拆分为「纯判定 + 强校验」两个函数

- **编号**：001
- **日期**：2026-10-13
- **状态**：已采纳（随 P0-1 落地）
- **关联**：docs/requirements/P0-1-auth.md

## 背景

原设计只有一个 `check_kb_permission(kb_id, user, role, db)`：内部查 KB → 判权限 → 不通过直接抛 HTTPException。实施中发现两个问题：

1. **查询浪费**：多数路由在权限检查后还需要 KB 对象本身（返回名称、更新内容），原设计抛异常路径还好，通过路径却让调用方二次 `db.get(KnowledgeBase)`，每个请求多一次 DB 往返。
2. **可组合性差**：列表页做可见性过滤、批量预检查等场景需要"只判定、不抛异常、拿到布尔结果"的能力，原设计做不到。

## 决策

拆分为两个函数（`backend/app/core/auth.py`）：

```python
async def has_kb_permission(kb, user, required_role, db) -> bool:
    """纯判定：不抛异常，返回布尔。admin 直通 → owner → NULL/public → kb_permissions 授权级别比较。"""

async def ensure_kb_permission(knowledge_base_id, user, required_role, db) -> KnowledgeBase:
    """强校验：不存在抛 404，无权限抛 403；通过则返回 KB 供路由复用。"""
```

- 常规端点用 `kb = await ensure_kb_permission(...)`，一次调用同时完成"检查 + 取实体"
- 需要布尔结果的场景（如列表过滤、前端展示判定）用 `has_kb_permission`
- 旧 `check_kb_permission` 删除（确认无调用者）

## 理由

- 消除通过路径的重复查询（性能）
- 判定与副作用（抛 HTTP）分离，函数职责单一，前端展示、批量校验、service 层（P0-2）都能复用布尔版
- 404/403 语义集中在 ensure 一处，路由层不再散落权限判断细节

## 影响

- ✅ 正面：路由代码显著变短（`ensure` 返回值直接复用）；P0-2 service 层可直接调 `has_kb_permission` 而不依赖 FastAPI
- ⚠️ 注意：**归属判定逻辑的唯一实现处**在这两个函数内，其他代码不得自行实现（见 docs/rules/40-database.md）；改动判定规则只需改 has_kb_permission 一处

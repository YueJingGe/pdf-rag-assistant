# Skill：新增一个 API 端点（add-api-endpoint）

> 操作手册。按顺序执行，全部完成才算交付。前置阅读：`docs/rules/30-api-conventions.md`。

## 步骤清单

1. **判断分层**：业务逻辑是否超过简单 CRUD？是 → 先完成 `add-service.md` 建 service 函数，本手册第 3 步只做调用
2. **定义 Schema**：在路由文件顶部（或 schemas 区）定义 Pydantic v2 请求/响应模型（`model_config = ConfigDict(from_attributes=True)`）
3. **写路由函数**：`async def`，只做参数校验 + 依赖注入 + 调下层 + 组装响应；补一行中文 docstring
4. **挂鉴权**（不可跳过）：
   - 通用：`current_user: User = Depends(require_user)`
   - KB 级：`kb = await ensure_kb_permission(kb_id, current_user, "viewer"|"owner", db)`
   - 会话级：走 `_get_own_conversation`（404 防枚举）
5. **前端同步**：`frontend/src/services/api.ts` 加类型 + 请求函数；`npx tsc -b` 必须通过
6. **验证**：
   - Swagger（`/docs`）确认新端点带锁图标
   - curl 实测：正常路径 + 未登录 401 + 越权 403/404
7. **留痕**：本轮 diff 摘要 + 验收结果追加到对应任务的 `docs/changelog/Px-y-slug.md`（时间倒序）

## 自检（交付前对照）

- [ ] 路由内无超 20 行业务逻辑
- [ ] 端点带锁图标，公开接口仅 register/login/health
- [ ] 错误语义符合 401/403/404 约定（30 规则的表）
- [ ] api.ts 类型已同步，tsc 无错
- [ ] changelog 已追加

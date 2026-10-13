# 20 代码风格（Coding Style）

## Python（后端）

### 异步与类型

- 路由与 DB 访问函数一律 `async def`；DB 会话通过 `Depends(get_db)` 注入（`AsyncSession`）
- ORM 模型必须用 SQLAlchemy 2.0 写法：

```python
user_id: Mapped[Optional[int]] = mapped_column(
    Integer, ForeignKey("users.id"), nullable=True, index=True
)
created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- Pydantic 用 v2（`ConfigDict(from_attributes=True)` 替代 v1 的 `orm_mode`）
- 函数签名带类型标注；公开函数写一行 docstring（中文）

### 配置与安全

- **所有敏感配置（API Key、SECRET_KEY）只写在 `backend/.env`**，代码中一律 `from app.core.config import settings` 引用，禁止硬编码
- 密码用 bcrypt（`app/core/auth.py` 的 `hash_password` / `verify_password`），禁止可逆加密或明文

### 注释与日志

- **不删除用户已有的注释**；注释语义与代码不匹配时，更新注释而非删除
- 注释密度对齐所在文件的周边代码（RAG 链路文件注释较密，路由文件较疏）
- 日志用 `app/utils/logging.py` 的 logger，禁止裸 `print`（`scripts/` 运维脚本例外，用 print 输出结果）

## TypeScript（前端）

- `tsconfig.json` 保持 `strict: true`，禁止 `any`（必要时用 `unknown` + 收窄）
- 接口类型与 API 函数**全部集中在 `src/services/api.ts`**；后端接口变更时此文件必须同步（工作流硬性要求）
- 组件采用目录式命名：`ComponentName/index.tsx` + `ComponentName/index.module.less`；导出组件用 PascalCase
- 样式用 CSS Modules（`.module.less`），全局样式只放 `global.less`
- SSE 流式走 `hooks/useSSE.ts`（原生 fetch + ReadableStream，不经过 axios，401 需单独广播）
- 新增持久化状态（localStorage）必须同时处理"写入"与"读取恢复"（防止刷新丢失，参考 App.tsx 的 `restoreVisibleKB`）

## 通用

- 新文件头部不写 AI 生成声明；给用户的交付说明里不贴大段代码（用户要求：修改代码后给简洁验证方式）
- 中文注释与报错文案；错误信息面向开发者（前端 message 文案面向用户）

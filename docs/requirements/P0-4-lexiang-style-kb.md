# P0-4 需求文档：乐享式知识库最小 demo（在线创作 + 目录树 + 沉淀闭环）

> 版本：v1.1｜状态：**v1.0 已确认实施完成（2026-10-15，commit 60059d1）；v1.1 第二轮待用户确认**
> 性质：纯增量功能开发。**承诺：RAG 禁区五文件（loader/splitter/retrieval/vector_store/rag_chain）零改动**，无需 RAGAS 回归（v1.1 多库合并链在 service 层实现，继续零改动）
> 调研依据：腾讯乐享官网 + 产品实际截图（2026-10-15 会话）；定位"个人知识体系"场景（前端程序员举例，领域无关）
> 与 P0-3b 关系：无冲突。P0 范围**零新增 LLM 调用**；P1 起 LLM 功能按 §3 成本纪律执行

## 1. 背景

### 1.1 现状与差距

当前系统是"RAG 问答工具"：上传文档 → 混合检索 → 引用问答。对照腾讯乐享（免费版功能基线：目录树 / 多维权限 / 多格式解析 / 指定知识域问答 / Agent 问答），缺"知识库产品"形态的三块地基：

1. **在线创作**：只能上传文件，不能在平台内写知识（写了即可被问答——乐享的灵魂）
2. **目录树**：知识库内扁平结构，无目录组织（个人知识体系：JS/React/浏览器 按目录+标签归类）
3. **产出回流**：AI 问答的回答无法一键沉淀回知识库（乐享"对话沉淀"）

### 1.2 目标场景

用户（如前端程序员）不定期上传技术文档（含 XMind 等格式）+ 在线创作笔记 → 目录树组织 → AI 问答（可结合/不结合知识库）→ 有价值的 AI 回答一键存回知识库。会计等角色同样适用（多知识库天然隔离领域）。

### 1.3 闭环定义（P0 验收主线索）

**存**（上传✅已有 + 在线创作🆕 + 消息存为文档🆕）→ **组织**（目录树🆕）→ **用**（问AI ✅已有）→ **再沉淀**（回答入库🆕）

## 2. 范围总览（四期）

| 期 | 主题 | 内容 |
|---|---|---|
| **P0（本期细化）** | 骨架闭环 | 布局改版、目录树、在线创作入库、消息存为文档、问AI 升级、上传挂目录 |
| P1 | 知识体验与治理 | 知识库主页、库管理-基本信息（图标=色板）、树拖拽、AI 体检（重复+冲突）、知识地图页（含力导图）、技能框架+4 内置技能（对话沉淀/知识概览/学习模式/知识图解）、文档页右侧问AI 侧栏、标签/搜索/模板/XMind、Agent 模式切换、知识范围多选 |
| P2 | 协作与安全 | 成员与权限（激活 KnowledgeBasePermission + role）、版本历史+回滚、收藏/点赞、我的页 |
| P3 | 可裁加分 | 发现页、评论、敏感信息正则扫描、快速访问、技能广场页 |

**明确不做**（均经用户确认或给出硬理由）：URL/网页收藏入库（用户拍板）、智能表格（Notion database 级工程量，MD 表格覆盖）、引用到（需 M:N 关联重构，移动到+复制到已覆盖）、Office 在线编辑（乐享付费功能，需协同引擎；走下载-修改-重传）、PPT 文件生成（排版非 LLM 强项，AI 总结走 MD）、定时任务（无调度基础设施，属 Agent 平台阶段）、审批流/敏感词定期检测/水印（企业合规场景）、企微/腾讯文档等生态对接（无外部系统可接）、培训/考试/论坛/积分（乐享独立付费产品线）、SSO/多租户。

## 3. LLM 成本纪律（用户明确要求，全程有效）

1. **P0 范围零新增 LLM 调用**：
   - 在线创作入库 = 纯文本管道（写文件 → 既有解析切分向量化），不调 LLM
   - "存为文档" = 直接保存 AI 已产出的回答文本为 MD（不做二次提炼；提炼属 P1 技能"对话沉淀"）
2. **开发与回归期间，AI 不主动发起任何真实 LLM 调用测试**。涉及 LLM 的功能验证一律交付 smoke/demo 脚本（沿用 `scripts/smoke_test_services.py` 模式），**由用户自行运行产生真实调用**
3. P1 起 LLM 功能（技能框架、AI 体检、知识概览）：实现 + 脚本就绪即视为完成开发；提供 mock/跳过路径保证结构可回归；真实效果由用户跑脚本验收
4. RAG 问答本身（用户自用）不计入开发成本；开发期回归用非 LLM 断言（HTTP 状态码、SSE 事件序列、DB 记录、FAISS 检索命中）

## 4. P0 任务分解

### 4.1 数据模型（新表 + 扩展列）

**Category（新表）**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | |
| kb_id | Integer FK→knowledge_bases.id, not null | 库隔离 |
| parent_id | Integer FK→categories.id, nullable | NULL=根目录；单亲模型，留 M:N 扩展位 |
| name | String(255), not null | |
| sort_order | Integer, default 0 | 同级排序 |
| created_at / updated_at | DateTime | |

**Document（扩展 3 列，幂等迁移）**

| 字段 | 类型 | 说明 |
|---|---|---|
| source | String(16), default 'upload' | `upload` / `online` |
| category_id | Integer FK→categories.id, nullable | NULL=未归类（挂根） |
| content | Text, nullable | 仅 online 文档：MD 原文，**真相源** |

迁移脚本：`scripts/migrate_p04_category.py`（幂等，参照 `migrate_add_user_id.py` 模式；SQLite ALTER TABLE ADD COLUMN + CREATE TABLE）。

### 4.2 后端 API（全部走 service 层规范 + require_user；写操作 owner/admin）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/knowledge_bases/{id}/categories` | POST | 新建目录（body: name, parent_id?） |
| `/api/knowledge_bases/{id}/tree` | GET | 目录+文档混合树（一次拉全量，前端组树；个人库规模小） |
| `/api/knowledge_bases/{id}/categories/{cid}` | PATCH | 重命名 |
| `/api/knowledge_bases/{id}/categories/{cid}` | DELETE | 删除目录（空目录才可删或级联策略：**移出文档至根**，不删文档） |
| `/api/knowledge_bases/{id}/documents/move` | POST | 文档移动到目录（body: document_ids, category_id?） |
| `/api/knowledge_bases/{id}/documents/online` | POST | 新建在线文档（body: title, category_id?, content?）→ 建 Document(source=online) + 写物理 .md + 入库索引 |
| `/api/documents/{id}/content` | PUT | 保存内容：覆盖写物理 .md → 走既有"删 chunks + 重建"路径；同时写 `content` 列 |
| `/api/chat/messages/{message_id}/save-to-kb` | POST | 消息存为文档（body: kb_id, category_id?）：校验消息归属（他人会话 404 防枚举，与现有一致）→ 生成 MD（标题=所属会话标题截断，正文=消息原文）→ 复用在线文档入库管道 |
| 现有上传接口 | 扩展 | `POST .../documents` 增加 `category_id` 可选参数 |

错误语义沿用现约定：库不存在 404 / 无权限 403（`get_kb_or_raise`）；目录不存在 404；文档状态非 ready 时保存内容 409。

### 4.3 在线文档入库管道（零禁区，核心设计）

```
保存(content, title) 
  → slug 化写物理文件 data/uploads/{kb_id}/{uuid}_{safe_title}.md   ← 既有 uploads 布局
  → 调用 document_service 既有"解析→切分→向量化"函数（与上传 .md 完全同路径）
  → 更新 Document.content / chunk_count / status
更新时：既有"删 chunks + 重建索引"路径（语义缓存按文档变更自动失效，rag_chain 既有机制，不感知来源）
删除时：复用既有文档删除链（chunks + 物理文件 + FAISS 清理）
```

- **Document.content 是真相源**，物理 .md 是入库管道副产物；前端展示在线文档直接用 content，**不读文件**（规避"查看类接口现场解析"性能坑）
- 上传文档与在线文档在检索/问答链路无差别（metadata 同构），**五禁区文件不感知 source 字段**

### 4.4 前端（React 18 + antd 5 + TS strict）

1. **布局改版**：现 `Sider(KB列表) + Tabs` → 乐享式布局：
   - 左侧导航栏：顶部库切换器（现 KB 列表收拢为 Select/下拉）+ `[+新建]` `[上传]` 按钮 + 导航项（问AI / 知识地图(P1 占位禁用) / 主页(P1 占位禁用)）+ **目录树** + 底部用户卡（登录态）
   - 中央内容区：问AI（现 ChatWindow）/ 文档工作台 二态切换（保留 Tabs 承载多文档）
2. **目录树组件**（新）：antd Tree；目录+文档混挂（图标区分）；节点 Dropdown 菜单：新建文档 / 新建子目录 / 重命名 / 移动到 / 删除；未归类文档挂虚拟"根"
3. **文档工作台**（新）：在线文档 = **md-editor-rc** 编辑器（工具栏+预览，手动保存按钮+保存态提示）；上传文档 = 现 DocumentViewer 只读复用；顶部：标题/来源标签/所属目录
4. **ChatWindow 升级**：assistant 消息操作栏加 **"存为文档"** 按钮 → Modal 选库+目录 → 成功 toast + 可跳转
5. **DocumentUpload 改造**：上传前可选目标目录
6. 类型同步：`api.ts` 新增 Category/TreeNode/在线文档 DTO（前后端接口变更必须同步，规范要求）

### 4.5 新依赖

- 前端：`@uiw/react-md-editor`（1 个；实施注记 2026-10-15：内网 npm 镜像无 md-editor-rc，经功能等价替换，工具栏+预览+手动保存能力一致）
- 后端：**0 个**

## 5. P0 验收标准

| # | 项 | 通过标准 |
|---|---|---|
| 1 | 目录管理 | 新建/子目录/重命名/删除（文档移至根）/移动到 全通过；他人库 403、不存在 404 |
| 2 | 在线创作 | 新建→编辑→保存→status=ready→树中可见→问AI 命中且引用溯源指向该文档 |
| 3 | 更新生效 | 编辑已入库文档再保存：旧内容不再命中、新内容命中（FAISS 检索断言，非 LLM） |
| 4 | 上传挂目录 | 上传时选目录，树中位置正确 |
| 5 | 存为文档 | 本人会话消息可存；他人会话 404；存后树中可见、可被检索 |
| 6 | 权限回归 | 现有 P0-1 权限矩阵不回归（负例脚本重跑） |
| 7 | 禁区零改动 | `git diff <baseline> -- backend/app/core/{loader,splitter,retrieval,vector_store,rag_chain}.py` 为空 |
| 8 | 质量门 | `python3 -m py_compile` 全过；`npx tsc -b` 过；迁移脚本幂等（跑两遍无错） |
| 9 | LLM 成本 | 验收流程零新增 LLM 调用（RAG 命中断言用检索层，不用生成层） |
| 10 | 收尾 | changelog 追加、README 核心亮点更新、requirements.txt/package.json 同步、后端重启生效 |

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| 标题作文件名含非法字符/超长 | slug 清洗（保留中英文数字-_，截断 80 字符）+ uuid 前缀 |
| 在线文档删除漏清物理文件/chunks | 复用既有删除链并加断言（删除后 docstore 无残留 metadata.source） |
| 大树一次拉取性能 | 个人库规模（百级节点）不构成瓶颈；P1 起再议懒加载 |
| SQLite 加列默认值限制 | 迁移脚本用 ADD COLUMN + 应用层默认，避免非常量默认 |
| md-editor-rc 与 antd 5 样式冲突 | 隔离容器样式；交付前 tsc + 手动视觉检查项列入 changelog |

## 7. 实施顺序（确认后执行）

1. 基线 commit（经用户确认 message）
2. 数据模型 + 迁移脚本
3. 后端 API（category/tree/online/save-to-kb/move）+ 零 LLM 自测脚本（`scripts/smoke_test_p04.py`：建目录→建文档→断言索引→更新→断言新旧内容→存消息→断言，全程检索层断言）
4. 前端布局 + 目录树 + 工作台 + 存为文档
5. 验收清单逐项跑 + changelog + 收尾 commit（经用户确认 message）

---

## 8. 第二轮需求（v1.1，2026-10-15）：概念对齐 + 管理页 + 对话内信息源

> 第一轮交付后，用户对照乐享实际页面提出三条交互纠偏（原 P1 部分 item 提前）：
> ① "通信/金融应是知识库下的目录，不是独立库"（概念模型对齐）；② 库名旁「⋯」hover 弹层 → 管理 → 独立页面 `/spaces`；③ 信息源移入对话输入区「+」弹层，默认选中个人知识库，支持多选知识范围。

### 8.1 T1 数据重组迁移（通信/金融等库 → 个人知识库的目录）

**最终形态**：每用户一个「个人知识库」，现有多个库降级为其下同名目录，文档、在线内容、会话历史全部跟走。

- **脚本**：`scripts/migrate_kb_to_personal.py`
  - `--user <username>`（必填）+ `--target-name`（默认"个人知识库"；已存在同名库则复用，否则新建）
  - 对该用户名下除目标库外的每个源库：目标库创建同名目录（重名加 `-2` 后缀）→ 文档迁移：物理文件 `uploads/{src}/` move 至 `uploads/{dst}/`、DB 更新 `kb_id/category_id/file_path`（在线文档 content 列随行）→ `conversations.kb_id` 改指目标库 → 源库 FAISS 索引目录删除 → 源库行删除
  - 迁移后目标库走既有 `_rebuild_kb_index` 重建（会产生 embedding API 调用，文档量小成本可忽略；脚本打印调用文档数）
  - **安全设计**：默认 `--dry-run` 只打印迁移计划；`--apply` 才执行；执行前自动备份 `db.sqlite3`；源库不存在自动跳过（幂等）
- **不做**：目录级检索过滤（乐享可勾目录粒度）需 chunks metadata 注入 category_id + retrieval 禁区过滤，列 P1；信息源多选粒度为**知识库级**

### 8.2 T2+T3 知识库管理入口与 /spaces 页面

- **入口**：左栏当前库名旁「⋯」（hover Dropdown）：分享（禁用占位）/ **管理** → `navigate('/spaces/:kbId')`；普通聊天态不显示
- **路由**：引入 `react-router-dom`（新前端依赖，先 `npm view` 验内网镜像存在）：`/` = 现主界面，`/spaces/:kbId` = 管理页；vite dev 自带 SPA fallback；`nginx/default.conf` 补 `try_files $uri /index.html`
- **管理页布局**（对齐乐享）：顶栏（← 返回 + 库名）+ 左侧菜单：**基本信息** / **目录与文档** / 成员与权限（禁用占位）/ 回收站（禁用占位）
  - 基本信息：库名称 + 简介编辑保存（复用既有 KB update 接口；简介字段若接口不支持则仅名称，实施时核实）
  - 目录与文档：复用 CategoryTree（canManage）+ DocumentUpload，左右布局
  - 权限：owner/admin 可编辑；viewer 只读提示
- 原 Select 切库器保留（多库仍是架构事实），仅新增管理入口

### 8.3 T4 对话内信息源（+ 弹层）

- **ChatWindow 输入区**左下「+」按钮 → Popover 弹层（对齐乐享）：
  - 顶部 Segmented「问答模式 | Agent模式」（替代现 header 的 Agent Switch）
  - **信息源**行（显示已选数）→ 展开选择面板：「全部知识」快捷项（=全选我的库）+ 库列表多选 Checkbox（默认勾选当前库）+ 确认
  - 上传图片 / 上传文件 入口并入（普通聊天态）
- **状态**：`sourceKbIds: number[]` 内部 state（默认 `[当前选中库]`）；`sourceKbIds.length === 0` 即普通聊天；HyDE/调试开关保留 header；会话归属第一个选中库（主库）
- **后端**（向后兼容）：`/chat/query` 增可选 `knowledge_base_ids` 数组参数（每个库校验读权限）
  - **单库/空 = 现有链路字节不变**（HyDE/语义缓存/Agent 全量能力）
  - **多选 = service 层"多库合并链"**：逐库调 retrieval_service 现有检索 → 按归一化分数合并重排截断 top_k → `llm_gateway` rag_generate 生成 + 引用组装，SSE 事件结构与单库一致（前端无感）；**多选模式不支持 HyDE/语义缓存（界面标注）；Agent 模式多选时作用于主库（Tooltip 说明）**
  - **禁区声明：方案甲，五文件零改动**。理由：rag_chain 支持 kb_ids 属禁区改动，须 RAGAS 回归，当前 judge API 不可用会阻塞交付；合并链在 chat_service/retrieval_service 层新增编排，检索原语复用禁区公开函数。风险：合并链与主链路 prompt 存在副本维护成本（注明来源行号，P1 收敛）
- 验收断言全程检索层/HTTP 层，零新增 LLM 调用（多库合并链的生成层断言用 mock/SSE 事件序列）

### 8.4 第二轮验收标准

| # | 项 | 通过标准 |
|---|---|---|
| 1 | 数据迁移 | dry-run 打印计划不落库；apply 后单「个人知识库」含同名目录、文档归位、检索命中、引用溯源指向正确文件；会话历史可见；源库删除；重复执行幂等跳过 |
| 2 | 管理入口 | 「⋯」hover 弹层 → 管理 → `/spaces/:kbId`；基本信息保存生效；目录与文档可管理；刷新直链可打开（nginx try_files） |
| 3 | 信息源 | 默认勾选当前库；多选两库提问，citations 来自两库（SSE 结构与单库一致）；单库问答能力不回归；Agent+多选作用于主库 |
| 4 | 禁区 | 五文件 diff 仍为空 |
| 5 | 质量门 | py_compile / tsc -b 过；smoke_test_p04 回归绿；迁移脚本 dry-run/幂等验证 |
| 6 | 收尾 | changelog 第二轮追加、README/重难点同步、package.json（react-router-dom）登记、后端重启 |

### 8.5 第二轮实施顺序

1. 基线 commit（经用户确认 message）
2. T1 迁移脚本（dry-run 验证 → **用户执行 apply**，涉及 embedding 调用与数据变更）
3. T2 路由 + T3 管理页
4. T4 信息源（前端弹层 + 后端多库合并链 + 冒烟扩展）
5. 验收清单 + changelog 第二轮 + 收尾 commit（经用户确认 message）

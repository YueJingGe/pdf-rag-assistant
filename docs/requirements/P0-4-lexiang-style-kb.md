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

## 9. 第三轮需求（v1.2，2026-10-15）：文件管理收拢 + 乐享式历史浮层

### 9.0 背景（用户原始反馈）

1. 「目录怎么没办法操作呢」——目录树节点 hover「···」入口不可见/不可用（第一轮功能回归或 CSS hover 微交互问题，根因待浏览器实测）
2. 「知识库的新建上传按照乐享的来」——侧栏顶部改「+ 新建」「上传」双按钮 + 下拉菜单（对照乐享截图）
3. 「文档管理都收到左侧目录文件管理里」——移除「文档管理」独立 tab；点击目录 → 主区域打开目录视图（乐享文件夹页形态）
4. 补充交互图——问AI 顶栏「历史/新对话」icon → 点击出现左侧历史浮层（新会话 + 历史对话按时间分组 + 「<<」收起）；文档「⋯」菜单「保留重命名删除即可」；多选模式「只要删除即可」

### 9.1 范围总览

前端为主；**后端仅 T8 一处增量**（文档级问答：chat 端点加可选参数 + chat_service 新增两个非禁区函数），**RAG 禁区五文件仍零触碰**（文档过滤检索在 service 层做后过滤实现）。

| 任务 | 内容 | 涉及 |
|---|---|---|
| T1 | 树节点「···」操作入口修复（bug） | CategoryTree + 浏览器实测 |
| T2 | 目录行「+」菜单承载新建/上传（修订：顶部双按钮取消） | CategoryTree、UploadModal |
| T3 | 移除「文档管理」tab；目录点击 → 目录视图 tab | MainPage、新 CategoryView |
| T4 | 节点菜单精简（文档仅 重命名/删除） | CategoryTree |
| T5 | 目录多选 → 批量删除 | CategoryTree |
| T6 | 历史记录常驻侧栏（修订：非浮层） | Sidebar、ChatWindow 事件联动 |
| T7 | 文档 tab 化（正文左 + 问AI右；信息源默认当前文档，面板无文档特殊化） | DocumentWorkbench、新 DocChatPanel |
| T8 | 后端文档级问答流（检索后按 document_id 过滤） | chat.py、chat_service.py、冒烟 ⑭ |

### 9.2 任务分解

#### T1 树节点操作入口修复
- 现象：目录/文档节点 hover 未见「···」，无法操作。canManage 恒为 true（member 也算），非权限问题；CSS `.nodeMore{visibility:hidden}` + `:hover` 显示链路疑似失效（antd Tree DOM/伪类匹配待实测）
- 方案：浏览器实测定位根因；实现改用更稳的 `opacity + pointer-events` 方案（或 antd Button type=text），保证 hover 行内可见、点击弹菜单；目录与文档菜单均验证

#### T2 目录行「+」菜单承载新建/上传（修订：取消侧栏顶部双按钮）
- 用户修订反馈（2026-10-15 补充图）：侧栏顶部「+ 新建」「⬆ 上传」双按钮**不做**（「这个可以不设计了」），因为「目录」行「+」菜单已包含这些能力
- 落地形态：
  - 「目录」标题行 hover「+」菜单 = **新建在线文档 / 新建文件夹 / 上传文件**（挂根目录；上传经隐藏 input 选文件 → UploadModal 浮层，均内嵌在目录树组件内自足，主界面与 /spaces 管理页均可复用）
  - 侧栏仅保留：库切换行 / 导航 / 目录树 / 用户卡；原「上传文档」ghost 按钮一并移除
  - 目录视图（T3）内部的「+ 新建」「⬆ 上传」按钮保留（作用域为当前目录）

#### T3 目录视图 tab（乐享文件夹页）+ 移除「文档管理」tab
- 点击树目录节点 → 主区域打开/聚焦目录 tab（editable-card，key=`dir-{categoryId}`，可关闭，与文档工作台 tab 并存）
- 目录视图（新 CategoryView）：头部 = 文件夹图标 + 目录名（点击 inline 编辑=重命名，乐享同款）+ 右侧 `+ 新建`（菜单：新建在线文档/新建子目录）`⬆ 上传`（上传到当前目录）；内容列表 = 子目录（点击进入子目录视图）+ 文档（在线 → 工作台 tab，上传 → 只读查看器），行尾「⋯」（同 T4 菜单）；空状态「该文件夹暂无内容」
- MainPage：移除 `docs` tab 与 DocumentUpload 引用（tabs 只剩 问AI / 目录 tabs / 文档工作台 tabs / 检索调优）

#### T4 节点菜单精简
- 文档节点「⋯」：**仅 重命名 / 删除**（移除「移动到」，用户批注「保留重命名删除即可」）
- 目录节点「⋯」：新建文档 / 新建子目录 / 重命名 / 删除（维持现状，目录删除=文档移根不变）
- 「目录」分组标题行：hover 显示「+」（弹 T2 同款新建菜单）

#### T5 目录多选 → 批量删除
- 「目录」标题行 hover「···」（tooltip 多选）→ 进入多选模式：节点前出现 Checkbox（目录+文档均可选），顶部操作条「已选 N 项 [删除] [×]」
- 删除：文档循环 `documentApi.delete`、目录循环 `categoryApi.remove`（文档移根），完成后刷新退出；**不做移动/复制**（用户批注「只要删除即可」）；「×」或删除完成退出多选

#### T6 历史记录常驻侧栏（修订：不做浮层/icon）
- 用户修订反馈（2026-10-15 补充图）：历史记录**插在侧栏「问AI」项下方**常驻展示；乐享右上角「历史/新对话」icon 浮层**不做**（「这里可以不要」）；问AI 顶栏保留现有「+ 新对话」按钮（「这个位置展示新建对话按钮」）
- 落地形态：
  - 侧栏导航区：主页 / 问AI / **历史对话列表**（常驻，随选中库拉取 `chatApi.listConversations(kbId ?? 0)`）/ 目录
  - 列表行：标题省略显示，点击切换会话，hover 显示删除；「新对话」后列表自动刷新
  - 与 ChatWindow 的联动用轻量 window CustomEvent 总线（`p04:conv-switch` 侧栏→聊天窗；`p04:conv-list-changed` 聊天窗→侧栏），避免提升会话状态的侵入式重构
- 原方案的浮层/图标形态废弃

#### T7 文档 tab：正文 + 右侧问AI 面板（修订：面板本质就是问AI）
- 用户反馈：① 乐享文档页顶部一排分享/收藏/评论 icon「可以不要」；② 「文档能支持编辑就支持编辑，不支持编辑就展示即可」；③ 「点击文档右侧出现文档正文以及问ai」；④ 修订澄清：**「右侧本质上就是问ai，没有特别针对某个文档，只是选中了某个文档之后这里的信息源会默认为该文档而已，其他没有特殊的」**
- tab 化统一：树节点点击在线文档 → 工作台 tab（已有）；点击上传文档 → **也开 doc tab（只读正文展示，复用 DocumentViewer 渲染逻辑）**，不再走 Modal；问答引用跳转仍走 Modal 查看器（不回归）
- 布局：doc tab 内左右两栏——左正文（在线=MDEditor 可编辑保存，上传=只读）、右 DocChatPanel（宽约 360px，可收起）；工作台顶部保持现有 filename/保存状态/保存按钮，不加任何分享类 icon
- DocChatPanel = **问AI 同款问答流**（无文档专用 UI，无 chip/「已阅读」特殊标记）：信息源两档指示（默认 `当前文档`；可切 `全部知识`＝当前库全库检索），均为不落会话的轻流式；引用以「文档名 · 页码」简版展示；SSE chunk 协议与主问答一致
- 裁剪：乐享技能卡片（知识总结/PPT制作/思维导图/知识图解/学习模式）、知识概览、全网搜索、右上角 icon 组 → 不做（P1）

#### T8 后端：文档级问答流（禁区零触碰）
- 依据：chunk metadata 已含 `document_id`（document_service 入库/重建时写入）→ **service 层检索后过滤**实现文档限定，不动检索禁区文件
- chat.py：ChatRequest 加 `document_id: int | None = None`；/api/chat/stream 当 kb_id + document_id 同传时切文档级流
- chat_service 新增两函数（非禁区）：
  - `doc_retrieve(kb_id, doc_id, question)`：`retrieve_with_strategy(kb_id, question, use_hyde=False)` 取候选（top_k×3）→ 按 `metadata.document_id == doc_id` 过滤 → 截断 `settings.retrieval_top_k`；过滤后为空则返回空列表（上层提示「文档中未找到相关内容」）
  - `doc_rag_stream(kb_id, doc_id, question, chat_history=None)`：SSE 协议与 multi_kb_rag_stream 同款，strategy="doc_scoped"，不走语义缓存
- 权限：document_id 不属于该 kb → 404（防串库枚举，与既有边界一致）
- 冒烟 ⑭：FakeListChatModel 零成本断言文档过滤命中与跨文档隔离、SSE 事件序列

### 9.3 验收标准（v1.2 修订同步）

| # | 项 | 通过标准 |
|---|---|---|
| 1 | 树操作 | hover 目录/文档节点「···」可见可点，菜单动作全部生效（浏览器实测） |
| 2 | 新建/上传 | 「目录」行「+」菜单（新建在线文档/新建文件夹/上传文件）可用；侧栏无双按钮；上传直选文件→浮层进度→完成后树刷新；目录视图内「+ 新建」「⬆ 上传」（作用域当前目录）可用 |
| 3 | 目录视图 | 点目录开 tab；inline 改名（tab 标题同步）/新建/上传/子目录导航/文档打开/空态均可用；目录被删后 tab 自动关闭 |
| 4 | tab 收拢 | 顶部无「文档管理」tab；上传能力经目录行菜单/目录视图可达，不回归 |
| 5 | 菜单/多选 | 文档菜单仅重命名/删除；多选批量删除生效且目录删除后文档仍挂根可见 |
| 6 | 历史常驻 | 历史对话列表常驻侧栏（问AI 下方，随选中库拉取）；点击切换、hover 删除、新会话自动刷新、活跃项高亮；聊天窗顶栏保留「新对话」按钮，原历史浮层按钮移除 |
| 7 | 文档面板 | doc tab 两栏：左正文（在线可编辑/上传只读）、右问AI（信息源默认当前文档，可切全部知识，可收起）；引用点击开查看器；面板问答不落会话 |
| 8 | 文档级问答 | kb+document_id 同传走 doc_scoped 轻流式；串库 404、越权 403；冒烟⑭全绿 |
| 9 | 质量门 | tsc -b 零错误；py_compile 零错误；禁区五文件 diff 为空 |
| 10 | 收尾 | changelog 第三轮追加、README 交互说明同步、收尾 commit（经用户确认 message） |

### 9.4 实施顺序（确认后执行）

1. 基线 commit（经用户确认 message）
2. T1 修复（浏览器实测根因 → 修复 → 回归）
3. T2 UploadModal + 双按钮 → T3 CategoryView + tab 收拢 → T4/T5 树菜单与多选
4. T6 历史浮层
5. 验收清单 + changelog 第三轮 + 收尾 commit（经用户确认 message）

### 9.5 风险与裁剪

- 智能表格/从模板新建/引用知识/上传文件夹/HTML/导入/定时任务/技能广场 → 本轮不做（P1）
- CategoryTree 为主界面与 /spaces 管理页共用，T1/T4/T5 改动需两处回归
- DocumentUpload 组件退役属删除性改动，若 /spaces 或其他处有引用需先排查（当前已知仅 MainPage）
- 目录 tab 与多库信息源无耦合；多库提问仍走 ChatWindow「+」弹层，不受本轮影响

## 10. 第四轮需求（v1.3，2026-10-16）：主区域单视图 + 问AI 输入区对齐乐享

> 用户对照乐享真实截图（5 张）指出第三轮两处不对齐：① 顶部 tabs 不需要，主区域应单视图（无文档=问AI 空态页；开文档=文档正文+右侧问AI 面板）；② 信息源交互应在输入区（多选、默认随上下文、输入框上方显示 tags），而非右上角 Segmented；左侧树缺选中态。已澄清：不支持多开文档；信息源弹层支持多选；问答模式≈普通聊天（普通聊天不单独安置）；双按钮不要（维持目录行「+」菜单）。

### 10.1 范围总览（6 任务）

| # | 任务 | 类型 |
|---|---|---|
| T1 | 主区域单视图（移除 tabs） | 前端重构 |
| T2 | 问AI 空态页（笑脸+今天从哪里开始+输入区） | 前端新建 |
| T3 | 输入区「+」弹层重构（模式 Segmented + 信息源多选 + tags） | 前端重构 |
| T4 | 库切换器移除「普通聊天」选项 | 前端 |
| T5 | 左侧树选中态（打开文档高亮+自动展开） | 前端 |
| T6 | DocChatPanel 输入区化（顶部仅「问AI」，信息源入输入区） | 前端重构 |

后端预期**零改动**：document_id（T8 第三轮）/knowledge_base_ids 多选链（第二轮）/web_search/agent 端点均已支持；「无信息源直聊」复用现有 kb=0 直聊路径。

### 10.2 任务分解

**T1 主区域单视图（MainPage 重构）**
- 移除 antd Tabs 容器与「问AI」tab/文档 tabs/目录 tabs 的 tab 呈现；主区域改为单视图：`activeDoc === null` → 问AI 页（T2 空态 + ChatWindow 消息流），`activeDoc = doc` → DocumentWorkbench（左正文 + 右 DocChatPanel）
- **不支持同时打开多个文档**：点树/目录视图文档即替换；侧栏「问AI」或文档标题栏关闭 → 回问AI 页
- 目录点击仍开目录视图（CategoryView 全屏占主区域，沿用第三轮；从目录视图进入子目录/打开文档与单视图联动）——目录视图作为主区域的一种临时视图，选中文档后切到文档视图，返回入口保留（面包屑或关闭按钮，实现取简）
- 文档标题栏保留：文档名/来源标签/收起问AI 按钮

**T2 问AI 空态页**
- 空态（无消息时）居中：大笑脸 icon +「今天从哪里开始?」+ 底部大输入框（占主区域宽度约 60%，含「+」弹层/信息源 tags/模型名展示/发送按钮）
- 底部免责声明行「回答内容均由AI生成，仅供参考」
- **不做**：推荐问题卡片/换一换/Workbuddy 入口（用户批注：等后面有了技能再加）
- 空态默认**基于整个个人知识库提问**：信息源默认勾当前选中知识库，输入框上方显示「{库名} ×」tag
- placeholder：「基于当前知识库进行提问，shift+enter换行」

**T3 输入区「+」弹层重构（ChatWindow 与 DocChatPanel 共用）**
- 抽公共子组件（如 `InputPlusPopover`），主聊天窗与文档面板同构复用
- 第一级弹层：Agent模式/问答模式 Segmented + 以下项：
  - 问答模式：信息源（带已选数量）→ 二级；深度思考开关（映射现有 HyDE，复用 use_hyde 参数，不新建后端能力）
  - Agent模式：技能（置灰占位「敬请期待」）+ 信息源 + 上传图片（沿用现有上传）
- 二级弹层（信息源）：全网搜索开关（仅问答模式可用，复用现有 web_search 链）+ 知识范围多选列表：`全部知识`（=我有读权限的全部库，映射 knowledge_base_ids 多选链）/ 各知识库勾选 / 打开文档时追加「当前文档」项（默认勾选，映射 document_id）；「选择知识范围」占位不做
- 输入框上方渲染已选信息源 tags（× 可逐个移除）；**勾选为空 → 纯直聊**（=原普通聊天，走 kb=0 直聊路径）
- Agent 模式多选时仅作用首库（沿用现状 primary_kb_id=首个）
- 现有 ChatWindow 顶栏「+新对话」保留；HyDE 开关从顶栏移入弹层（顶栏简化）

**T4 库切换器移除「普通聊天」**
- Sidebar kbSwitcher 仅列知识库；左上角始终显示当前库名（对齐乐享「普通聊天不在左上角」）
- 「问AI」导航点击 → 主区域切问AI 页（activeDoc=null）
- 侧栏历史对话列表 = 当前选中库的会话；旧 kb=0 普通聊天会话暂不可见（存量迁移 P1）
- 「问答模式+无信息源=普通聊天」语义替代原普通聊天入口

**T5 左侧树选中态**
- 打开的文档在 CategoryTree 树节点高亮（乐享蓝底选中样式）+ 自动展开所在目录并滚动到可见
- CategoryView 文档行同样 active 高亮
- 打开/关闭文档 → 树选中态同步；打开非当前库文档不存在（单视图内文档均属当前库）

**T6 DocChatPanel 输入区化**
- 顶部仅「😊 问AI」标题 + 收起按钮（移除右上角 Segmented）
- 输入区用 T3 公共弹层组件；默认信息源=当前文档（tag 显示文档名），可勾选库/全部知识切换
- 仅问答模式（Agent 模式不进文档面板，Segmented 隐藏）；深度思考开关保留
- 消息空态提示文案改为「基于「{文档名}」提问，试试：这篇文档讲了什么？」（沿用现有）

### 10.3 验收标准

| # | 验收项 | 期望 |
|---|---|---|
| 1 | 无 tabs | 主区域顶部无 tab 条；问AI/文档/目录三态切换单视图 |
| 2 | 空态页 | 笑脸+「今天从哪里开始?」+大输入框+免责行；无卡片/换一换/Workbuddy |
| 3 | 输入区弹层 | 「+」→ 模式 Segmented + 信息源（数量）+ 深度思考；二级 = 全网搜索 + 范围多选（全部知识/各库/当前文档） |
| 4 | 信息源 tags | 输入框上方显示已选 tags（可×移除）；空=纯直聊；空态默认=当前库 tag；开文档默认=当前文档 |
| 5 | 树选中态 | 打开文档树高亮+自动展开；关闭取消 |
| 6 | 右面板 | 顶部仅「问AI」+收起；信息源交互在输入区 |
| 7 | 普通聊天 | 库切换器无「普通聊天」；问答模式清空信息源 = 直聊 |
| 8 | 质量门 | tsc -b 零错误 / py_compile / 禁区五文件 diff 空 / 冒烟全量绿 / 后端零改动确认 |

### 10.4 实施顺序（确认后执行）

1. 基线 commit（经用户确认 message）
2. T3 InputPlusPopover 公共组件（最核心，先立弹层契约）→ T2 空态页接入 → ChatWindow 顶栏简化
3. T6 DocChatPanel 接入同款弹层 → T1 MainPage 单视图重构 → T5 树选中态 → T4 库切换器
4. 验收清单 + changelog 第四轮 + README 同步 + 收尾 commit（经用户确认 message）

### 10.5 风险与裁剪

- 技能体系/深度思考（真正的 reasoning 模型链）/知识概览 AI 摘要卡/多文档多开 → 不做（P1）
- InputPlusPopover 状态与 ChatWindow 既有 sourceKbIds/agent 切换逻辑存在重叠，重构时以弹层组件为唯一真相源，避免双份状态漂移
- 目录视图与单视图的返回交互取最简实现（关闭按钮/面包屑），不做历史栈
- kb=0 旧会话不可见属预期行为，迁移脚本 P1
- CategoryTree 选中态需与 /spaces 管理页隔离（管理页无 activeDoc 概念，prop 可选化）

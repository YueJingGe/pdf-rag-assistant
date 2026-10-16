# P0-4 乐享式知识库最小 demo — changelog

> 需求文档：docs/requirements/P0-4-lexiang-style-kb.md（状态：已确认 2026-10-15；v1.1 增补第二轮 §8；v1.2 增补第三轮 §9）｜基线 commit：`ba6837d`（第一轮）/ `af72e3d`（第二轮，docs(p0-4): 需求文档 v1.1）/ `0b76011`（第三轮）

## 第三轮：文件管理收拢 + 文档 tab 内嵌问AI（2026-10-15）

按需求 §9（v1.2）实施：基线 commit `0b76011` → T1 树操作入口修复 → T2 目录行「+」菜单承载新建/上传 → T3 目录视图 tab → T4/T5 菜单精简+批量删除 → T6 历史常驻侧栏 → T7 文档 tab 两栏+DocChatPanel → T8 后端文档级问答流 → 冒烟⑭。**RAG 禁区五文件 diff 为空（git diff 复查），文档级检索落在 service 层后过滤，全程零新增 LLM 调用（生成走 P0-3b 网关）。**

### 改动文件清单

**前端（交互重构）**

| 文件 | 改动 |
|---|---|
| `frontend/src/components/KnowledgeBaseSidebar/` | 重写：删顶部「+新建/⬆上传」双按钮与新建 Modal/UploadModal 引用；问AI 导航下方新增**历史对话列表**（常驻，点击切换会话、悬停 Popconfirm 删除）；CustomEvent 四事件总线：p04:conv-switch（→聊天窗切换）/p04:conv-active（←聊天窗高亮）/p04:conv-list-changed（←刷新列表）/p04:conv-deleted（→删除的正是当前会话时清空消息） |
| `frontend/src/components/CategoryTree/` | 上传自足：headerPlusMenu 增「上传文件」项 + hidden input + UploadModal（挂根目录）；batchDelete 改 documentApi.batchDelete 真批量；文档点击统一 onOpenDoc |
| `frontend/src/components/CategoryView/` | 新建（441 行 + less）：目录视图 tab——头部 inline 改名、「+新建」菜单（在线文档/子目录）、「⬆上传」（挂当前目录）；子目录行（点击进入 + 文档计数 + rowMenu）+ 文档行（status Tag + docRowMenu 仅重命名/删除）+ 空态「该文件夹暂无内容」；onMissing 目录被删自动关 tab |
| `frontend/src/pages/MainPage/` | 移除「文档管理」tab 与 DocumentUpload 引用；新增目录 tabs（key=`dir-{id}`，去重打开/关闭分流/改名联动）；Sidebar 传参删 onGoUpload 加 onOpenCategory；Workbench 加 onCitationClick |
| `frontend/src/components/ChatWindow/` | 移除历史浮层（Dropdown/Popconfirm/MenuProps/conversations state/loadConversations/deleteConversation 全删）；改为双向事件联动：广播 conv-active + conv-list-changed，监听 conv-switch/conv-deleted |
| `frontend/src/components/DocumentWorkbench/` | 两栏化：左正文（在线 MDEditor 可编辑/上传只读）+ 右 DocChatPanel（360px，可收起）；引用点击经 onCitationClick 打开查看器 |
| `frontend/src/components/DocChatPanel/` | 新建（197 行 + less）：信息源 Segmented（当前文档/全部知识）+ 独立 useSSE 流式 + 消息列表/输入行 + CitationView 引用点击；scope=doc 时 send 传 documentId（不传 conversationId=轻流式不落会话）；docId/scope 变化清空会话 |
| `frontend/src/hooks/useSSE.ts` | SendOptions 增 `documentId`（入 body.document_id） |
| `frontend/src/pages/SpacesPage/` | 删 DocumentViewer 引用；文档点击统一 onOpenDoc 跳回主界面开 doc tab |
| `frontend/src/components/UploadModal/` | 修复 UploadingItem.status 三元推断类型标注（TS2345） |

**后端（T8 文档级问答流）**

| 文件 | 改动 |
|---|---|
| `backend/app/api/chat.py` | ChatRequest 增 `document_id`；chat_stream 前置文档级分支（check_doc_access → EventSourceResponse(_doc_sse_events)，**不落会话**）；新增 _doc_sse_events 生成器（retrieval_debug/token/citations/done 转发） |
| `backend/app/services/chat_service.py` | 新增三函数：check_doc_access（viewer 校验 + db.get(Document) 归属校验，串库 404 防枚举）/ doc_retrieve（retrieve_with_strategy 全库候选 → metadata.document_id 后过滤 → 截断 retrieval_top_k）/ doc_rag_stream（strategy="doc_scoped"；空候选 yield 固定提示语不进 LLM；citations/done 在流内 yield） |

**脚本与文档**

| 文件 | 改动 |
|---|---|
| `scripts/smoke_test_p04.py` | 追加 ⑭ 场景（11 断言）：干扰文档零泄漏 / doc_retrieve 全命中目标文档 / 跨文档隔离 / 截断 ≤top_k / 不存在 doc 空候选 / 404 / 403 / SSE 首尾 + strategy=doc_scoped / fake token / citations 非空 / 空候选提示直出 |
| `docs/requirements/P0-4-lexiang-style-kb.md` | §9.3 验收表同步 v1.2 措辞（10 条） |

### 关键设计摘要

- **文档级检索零禁区触碰**：chunk metadata 早已携带 document_id（入库时写入），service 层对 retrieve_with_strategy 的候选做后过滤即可；「候选量 = 策略默认返回（top_k=4 全库最优集）」是对禁区函数签名的忠实落地——需求 §9「top_k×3」的写法与实际 API 有出入，已在 §9 注明；如长文档多点命中出现候选稀疏漏检，需禁区支持 top_k 参数后放宽（P1）
- **事件总线选型**：侧栏/聊天窗为兄弟组件，引入状态管理成本高于收益，选 window CustomEvent 四事件轻量总线，命名统一 `p04:` 前缀防冲突
- **「文档面板本质就是问AI」**（用户原话定调）：DocChatPanel 与 ChatWindow 同一 useSSE、同一后端 /chat/stream，差异仅 scope=doc 时多传 document_id；不落会话（轻流式），docId/scope 变化即清空会话
- **上传文档统一 doc tab**：Workbench 本就支持只读渲染，树上/目录视图文档点击一律 onOpenDoc；onOpenViewer 从调用链全链路退役（DocumentViewer 保留给问答引用点击专用）
- **目录行「+」菜单承载新建/上传**（v1.2 修订核心）：侧栏双按钮取消，新建/上传收进「目录」标题行 hover「+」菜单；CategoryTree 内嵌 UploadModal 自足（挂根目录）

### 验收结果（需求 §9.3 对照）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 树节点「···」操作入口（hover 可达） | ✅ opacity+pointer-events 方案；浏览器 a11y 快照中「+」/「···」按钮均出现 |
| 2 | 侧栏无双按钮、目录行「+」菜单承载新建/上传 | ✅ 快照证实无双按钮；tsc 零错误 |
| 3 | 目录视图 tab（CategoryView） | ✅ tsc 零错误；目录点击开 tab / inline 改名 / 空态 / onMissing 关 tab |
| 4 | 「文档管理」tab 移除 | ✅ 快照：主区域仅「问AI」+ 动态 tabs |
| 5 | 菜单精简 + 多选批量删除 | ✅ 文档菜单仅 重命名/删除；CategoryTree/CategoryView 双入口走批量 API |
| 6 | 历史对话常驻侧栏 | ✅ 快照：18 条历史项 + delete icon 常驻；聊天窗无「历史」按钮、保留「+ 新对话」 |
| 7 | 文档 tab 两栏 + DocChatPanel | ✅ tsc 零错误；信息源两档（当前文档/全部知识）切换 |
| 8 | 文档级问答流（后端） | ✅ 冒烟⑭ 11 断言全绿（隔离/截断/404/403/SSE 协议/空候选直出） |
| 9 | 质量门 | ✅ tsc -b 零错误 / py_compile 全过 / 禁区五文件 git diff 为空 / 后端重启 OpenAPI 确认 document_id 进 schema |
| 10 | 集成面 | ✅ 冒烟全量 46 断言绿（原 35 + 新 11）；浏览器快照交互形态全部落地 |

### 遇到的问题

1. **chat_service SearchReplace 错位（最严重，git diff 抓出）**：为追加 doc_* 三函数做的尾部替换，误把 multi_kb_rag_stream 尾部 `yield citations/done` 裹进新函数形成重复；修复该「重复」时又把原函数的两行 yield 一并删掉，多库链 citations 断言将 StopIteration。以 `git show HEAD` 考古原结构归还两行 yield，最终 `git diff | grep "^-"` 为空验证纯新增。教训与第二轮一致：**批量替换后必以 git diff 为准，不信任工具「成功」文案**。
2. **uvicorn --reload 未生效**：chat.py 改动后 curl openapi 仍无 document_id——dev reload 对本轮改动未触发；kill 旧进程手动重启后确认 `document_id: True`。
3. **ChatWindow 删 state 后引用残留**：conversations/loadConversations 删除后，JSX 内历史 Dropdown 块与 setConversations 调用残留，tsc 三处报错；二轮补删（连带删除已无引用的 deleteConversation 与相关 import）。
4. **GetProblems 快照误报**：SearchReplace 成功后 Problems 面板仍报 MainPage/SpacesPage 旧错；以 `npx tsc -b` 实测为准（零错误）。

### 遗留事项（P1）

- **文档级检索候选稀疏风险**：候选量受 retrieve_with_strategy 默认 top_k=4 限制，长文档多点命中时可能漏检；禁区函数支持 top_k 参数后可放宽
- hover「···」/「+」菜单的**真实点击行为**（弹出/防抖）需用户浏览器配合实测，快照仅证明元素可达
- DocumentUpload 组件仍被 /spaces 管理页使用（需求 §9.5 风险条款：仅移除主界面 docs tab），全面退役留后续
- 事件总线为 window CustomEvent 轻量方案，组件层级再复杂化时可考虑收敛为状态管理
- 文档 tab 内 DocChatPanel 不落会话（轻流式），历史留痕需求出现时再议

## 第二轮：交互对齐乐享（2026-10-15）

按需求 §8 实施：基线 commit `af72e3d` → T1 数据迁移脚本 → T2 路由 → T3 /spaces 管理页 → T4 对话内信息源（前后端）→ 冒烟扩展。**RAG 禁区五文件 diff 为空（git diff 复查），多库合并链落在 service 层（方案甲），全程零新增 LLM 调用（生成走 P0-3b 网关）。**

### 改动文件清单

**T1 数据迁移（多库 → 个人知识库 + 目录）**

| 文件 | 改动 |
|---|---|
| `scripts/migrate_kb_to_personal.py` | 新建（280 行）：--user/--target-name/--apply，dry-run 默认；自动备份 .bak-p04r2；apply 前检测 8000 端口占用拒绝执行；文档物理文件 move + DB（documents/conversations 改指）+ 删源库 FAISS 目录 + 删源库行；失败回滚并打印已移动文件；幂等 |

**T2 路由 + T3 /spaces 管理页**

| 文件 | 改动 |
|---|---|
| `frontend/package.json` | + `react-router-dom ^7.18.4`（v7 兼容 v6 API） |
| `frontend/src/index.tsx` | BrowserRouter 包裹 ConfigProvider |
| `frontend/src/App.tsx` | 重写为路由容器（77 行）：登录门控 + Routes（"/"→MainPage、"/spaces/:kbId"→SpacesPage、"*"→Navigate）；登录页/LoginModal/401 listener 留此层 |
| `frontend/src/pages/MainPage/` | 新建（228 行）：承接原 App 主界面；新增 location.state.openDoc 消费（/spaces 点击在线文档跨页打开工作台，消费后清 state 防刷新重复） |
| `frontend/src/pages/SpacesPage/` | 新建（index.tsx 229 行 + less）：顶栏返回 + 左侧菜单（基本信息/目录与文档/成员与权限 disabled/回收站 disabled）+ 基本信息表单（403 特判提示）+ 目录与文档（CategoryTree + DocumentUpload 左右布局）+ 删除知识库 |
| `frontend/src/components/KnowledgeBaseSidebar/` | 「⋯」Dropdown 改 hover 触发 + 新增「管理」项 → navigate(`/spaces/${current.id}`) |

**T4 对话内信息源（乐享式「+」弹层）**

| 文件 | 改动 |
|---|---|
| `backend/app/api/chat.py` | ChatRequest 增 `knowledge_base_ids`（len>1 生效，向后兼容）；chat_stream 多库判定（primary_kb_id=首库，会话挂主库）+ SSE 前逐库读权限校验；_chat_sse_events 增多库分支（chunk 协议与单库一致）；agent 转发路径不受影响（primary_kb_id 缺省回落 req.knowledge_base_id） |
| `backend/app/services/chat_service.py` | 新增三函数：check_multi_kb_access（逐库 viewer 校验）/ multi_kb_retrieve（逐库 retrieve_with_strategy → metadata 标记来源库 → RRF 分数降序合并 → 去重 → 截断 retrieval_top_k）/ multi_kb_rag_stream（SSE chunk 协议对齐 rag_stream：retrieval_debug(strategy=multi_kb)/token/citations/done；不支持 HyDE/语义缓存；生成走 get_llm("rag_generate")） |
| `frontend/src/hooks/useSSE.ts` | SendOptions 增 `knowledgeBaseIds`（len>1 且非 Agent 才入 body） |
| `frontend/src/components/ChatWindow/` | sourceKbIds state（默认当前库，空=普通聊天）；「+」Popover（问答/Agent Segmented + 信息源多选 Checkbox.Group + 全部知识快捷 + 上传入口并入）；移除 header Agent Switch（入口移弹层）；多库信息源 Tag 行；HyDE 多库禁用；多库隐藏检索调试按钮 |

**冒烟扩展**

- `scripts/smoke_test_p04.py` 追加 ⑫ 场景（9 断言）：跨库合并命中两库内容 / metadata 来源库标记 / 截断 ≤ retrieval_top_k / SSE 事件序列首尾与 strategy=multi_kb / fake 网关 token（零 LLM）/ citations 非空 / 他人无读权限 403（SSE 前拦截）。全量 33 断言绿。

### 关键设计摘要

- **禁区零改动实现方式**：service 层直接 import 禁区公开函数（retrieve_with_strategy/RAG_PROMPT）与内部纯函数（_format_context/_build_citations/_trim_chat_history/_to_langchain_messages/_deduplicate_documents）——比需求 §8.3 预设的"prompt 副本"更优：零复制零漂移，副本维护成本 P1 风险直接消除；禁区文件本体一个字节未动
- **RRF 分数跨库直接可比**（同 rank 同分，RRF 设计优点），无需归一化；单库检索逻辑零复制
- **多库范围**：不支持 HyDE/语义缓存（前端禁用+后端忽略）；Agent 模式多选时仅作用主库（前端不传 ids，agent 端点天然兼容）
- **nginx 零改动**：需求原假设需补 try_files，核实生产 Dockerfile 也是 vite dev（proxy 直通），SPA fallback 由 vite 自带，需求假设修正

### 验收结果（需求 §8.4 对照）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | T1 迁移脚本安全验证 | ✅ py_compile / dry-run 计划正确 / apply 保护（8000 占用拒跑）三项过；**apply + rebuild_index 留用户执行** |
| 2 | 「⋯」hover 弹层 → 管理入口 → /spaces | ✅ tsc -b 零错误 |
| 3 | /spaces 管理页（基本信息/目录与文档/在线文档跨页打开） | ✅ tsc -b 零错误 |
| 4 | 对话「+」弹层（问答/Agent + 信息源多选） | ✅ tsc -b 零错误 |
| 5 | 多库合并链（检索层断言） | ✅ 冒烟 ⑫ 九断言全绿（跨库命中/来源标记/截断/SSE 协议对齐/citations/403） |
| 6 | 单库与普通聊天路径回归 | ✅ 冒烟全量 33 断言绿（原 24 + 新 9）；禁区五文件 git diff 为空 |
| — | 集成面 | ✅ 后端重启 /docs 200；tsc -b / py_compile 全过 |

### 遇到的问题

1. **SearchReplace 批量替换部分失败**：Sidebar 改造 4 个替换中 import 块因缩进不匹配失败，当时误判无需重试，tsc 报 `Cannot find name 'useNavigate'` 才暴露；修复后建立"批量替换后必跑 tsc"动作。
2. **P0-3b 网关已落地而 AGENTS.md 进度标注滞后**：llm_gateway.py 已存在且 rag_chain 内部工厂已收敛，多库链直接 get_llm("rag_generate")，无需自建实例化点。
3. **documents 表列名**：迁移脚本查询初版误用 kb_id（实际为 knowledge_base_id），PRAGMA 核实后修正。

### 遗留事项（P1）

- **T1 迁移 apply + rebuild_index 由用户执行**（涉及 embedding 调用，不自动跑）
- 多库会话挂主库：普通聊天页签发起的多库会话归主库页签，切页签可见性按页签库过滤（乐享式归属的固有行为）
- 多库 chunk 级反馈：多库时隐藏调试入口（避免 chunk 归属错库），按 metadata.knowledge_base_id 归属上报留 P1
- 信息源目录级粒度（选到目录而非库）需 metadata 注入 category_id + 禁区过滤参数，P1
- 多库 RAGAS 回归不适用：禁区零改动，无需基线对比

## 第二轮收尾补记：迁移 apply + 顺带修复两个存量 bug（2026-10-15）

### 迁移 apply 结果（用户执行）

新建目标库 **#4「个人知识库」**：目录「金融」(1 文档+11 会话)/「司库奇尤单抗注射液说明书」(1+3)/「通信」(1+5)；源库行与 FAISS 目录已删、物理文件已 move 至 `uploads/4/`；自动备份 `backend/data/db.sqlite3.bak-p04r2`。收尾：`rebuild_index.py 4` 重建索引（86 chunks：59/11/16），三文档检索精准命中；后端已重启（含本轮修复代码）。

### 修复 1：delete_kb 级联不完整（存量 bug，迁移核验时实证）

**现象**：`categories` 表存在 8 条孤儿行（历次冒烟临时库的「前端基础/JavaScript/别库目录」，delete_kb 仅删 KB 行 + FAISS），且临时库恰好复用过 id=4，孤儿目录被新建的「个人知识库」认领，直接出现在用户目录树；`uploads/4/` 混入 23 个冒烟残留文件。

**修复**：`kb_service.delete_kb` 改为级联清理——messages→conversations→categories→documents 行 + FAISS + `uploads/{kb_id}` 物理目录（先 DB commit 后物理删除，失败可重跑幂等）。冒烟新增 ⑬ 两断言（行全清 + uploads 目录已删），全量 35 断言绿。

**数据清理**：删除孤儿 categories 8 行、`uploads/4/` 与 `uploads/5/` 冒烟残留文件（按 `documents.file_path` 白名单精确保留 3 个迁移文档）。`uploads/1/88ae8fe...金融机构风险关联...docx` 为 DB 无引用的历史孤儿，**保守保留未删**（用户可自行处置）。

### 修复 2：rebuild_index.py 三处问题（收尾第 1 步执行时暴露）

1. `int | None` 注解在 Python 3.9 运行时求值报 TypeError → 加 `from __future__ import annotations`
2. 未注册 Category/User 模型 → `create_all` 时 documents/knowledge_bases 的 FK 解析失败 → 补 import
3. **最隐蔽**：无 `os.chdir(backend)`，而 .env 的 DATABASE_URL/索引路径均为相对路径 → 从项目根执行时误连新建的空库（“成功”打出 Done 但实际 0 文档），并在项目根误建 `data/db.sqlite3` → chdir 提到 import app 之前（engine 创建时即解析相对路径），误建空库已删

**教训**：scripts/ 下凡 import app 的脚本必须与 smoke 脚本同模式（chdir + sys.path 前置）；“Done.” 不等于生效，必须核验产物（索引文件存在 + 检索命中）。

## 第一轮：全量实施（2026-10-15）

按需求 §7 实施顺序一轮完成：基线 commit → 数据模型/迁移 → 后端 API → 零 LLM 冒烟 → 前端 → 收尾。**RAG 禁区五文件 diff 为空，P0 范围零新增 LLM 调用。**

### 改动文件清单

**数据模型与迁移**

| 文件 | 改动 |
|---|---|
| `backend/app/models/category.py` | 新建：Category（id/kb_id FK/parent_id FK 可空=根/name/sort_order/时间戳） |
| `backend/app/models/document.py` | 扩 3 列：`source`(String16 default "upload") / `category_id`(FK categories 可空, index) / `content`(Text 可空，在线文档真相源) |
| `backend/app/main.py` | `import app.models.category` 表注册 |
| `scripts/migrate_p04_category.py` | 新建：幂等迁移（自动备份→CREATE TABLE IF NOT EXISTS→documents 逐列 ADD COLUMN→两个索引→统计），已连续跑两遍验证 |

**Service 层**

| 文件 | 改动 |
|---|---|
| `backend/app/services/category_service.py` | 新建：get_category_or_raise（跨库/不存在 404）、create/rename/delete（子目录上提+文档移根，不删文档）、move_documents（批量）、get_tree |
| `backend/app/services/document_service.py` | 提取 `_ingest_document_record` 共用入库管道；upload 增 category_id；create_online_document（save_text_as_md→source="online"→入库）；save_online_content（**走 _rebuild_kb_index 重建**）；get_document_content 在线分支（直接读 content 列，page_count=1） |
| `backend/app/services/chat_service.py` | 新增 get_own_message（join Conversation 校验 user_id，否则 404 防枚举） |
| `backend/app/utils/file_utils.py` | 新增 slugify_title（中英文数字保留、空格转-、截断 80）与 save_text_as_md（`{uuid}_{slug}.md`） |

**API 层（7 个新端点）**

| 文件 | 端点 |
|---|---|
| `backend/app/api/knowledge_bases.py` | POST `/{kb_id}/categories`、GET `/{kb_id}/tree`、PATCH/DELETE `/{kb_id}/categories/{cid}` |
| `backend/app/api/documents.py` | POST `/{kb_id}/documents/online`、PUT `/{kb_id}/documents/{doc_id}/content`（非 ready 409）、POST `/{kb_id}/documents/move`；upload 增 `category_id` Form；DocumentResponse 增 source/category_id |
| `backend/app/api/chat.py` | POST `/messages/{message_id}/save-to-kb`（标题取 conversation.title[:50]） |

**冒烟脚本**

- `scripts/smoke_test_p04.py`（新建）：service 层直调零 LLM，24 断言，覆盖需求 §5 验收 2/3/4/6/7/8/9/10/11 全部后端项；含更新后"旧内容不命中/新内容命中"的 FAISS 检索层断言；临时库自清理。

**前端**

| 文件 | 改动 |
|---|---|
| `frontend/src/services/api.ts` | +CategoryInfo/TreeNodeDocument/TreeData/SaveMessageToKBResult 类型；+getTree/categoryApi/createOnline/saveContent/upload(categoryId)/saveMessageToKb |
| `frontend/src/components/CategoryTree/` | 新建：目录+文档混挂树（未归类虚拟组）、节点 Dropdown（新建文档/子目录/重命名/移动/删除）、单 Modal 五模式；导出 OpenableDoc 与 buildCategorySelectTree 供复用 |
| `frontend/src/components/DocumentWorkbench/` | 新建：在线文档 MDEditor 编辑+手动保存（dirty 标记/409 特判）；上传文档只读 ReactMarkdown 渲染 |
| `frontend/src/components/KnowledgeBaseSidebar/` | 重写为乐享式左导航：库切换器（普通聊天=0）→上传按钮→导航项（问AI/知识地图/主页占位）→CategoryTree→底部用户卡（角色+退出） |
| `frontend/src/App.tsx` | 重写：editable-card Tabs（hideAdd），动态文档工作台 tabs（key=`doc-{id}`，去重打开/关闭回退）；KB 切换清空 openDocs；onDocChanged 同时刷目录树与侧栏；onOpenViewer 复用 DocumentViewer；Header 移除用户下拉（已移左栏底部） |
| `frontend/src/components/ChatWindow/` | assistant 回答 footer 增「存为文档」：Modal 选库+目录 TreeSelect+内容预览；消息 id 经 getMessages 按内容匹配服务端解析后调 saveMessageToKb |
| `frontend/src/components/DocumentUpload/` | Dragger 上方「上传到目录」TreeSelect（getTree 加载，可清空=未归类）；表格增「来源」列（upload/online Tag） |
| `frontend/package.json` | + `@uiw/react-md-editor ^4.1.2`（无后端新依赖） |

### 关键设计摘要

- **content 列是真相源**：在线文档物理 .md 是副产物；保存 = 覆盖物理文件 + 更新 content + `_rebuild_kb_index`（删旧 chunks + 语义缓存失效 + 全库重建）
- **权限**：全部写操作 owner/admin（复用 get_kb_or_raise write 语义）；目录校验走 get_category_or_raise（库隔离，串库 404）；消息归属 join 校验 404 防枚举
- **删除目录级联策略**：子目录上提至被删者父级、文档移至根，绝不删文档

### 验收结果（需求 §5 对照）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 布局改版乐享式左栏 | ✅ tsc -b 零错误；库切换器+导航+目录树+用户卡 |
| 2 | 目录 CRUD | ✅ 冒烟（含空名 400、父目录校验） |
| 3 | 在线创作入库 | ✅ 冒烟（物理文件落盘 + 检索命中） |
| 4 | 内容更新生效 | ✅ 冒烟：V2 命中 + **V1 不再命中**（重建索引断言） |
| 5 | 非 ready 保存 | ✅ 冒烟 409 |
| 6 | 上传挂目录 | ✅ 冒烟 + 前端 TreeSelect |
| 7 | 移动到根/目录 | ✅ 冒烟 |
| 8 | 树接口 | ✅ 冒烟（目录嵌套+文档挂载+未归类） |
| 9 | 目录越权 404/403 | ✅ 冒烟（串库 404、他人写 403） |
| 10 | 消息存为文档 | ✅ 冒烟（归属校验+存后可检索） |
| — | 集成面 | ✅ 后端重启 /docs 200，openapi 28 paths（含 7 新端点）；401 负例正常；禁区 diff 空；迁移幂等双跑 |

### 遇到的问题

1. **save_online_content 旧 chunks 残留（真 bug，冒烟抓出）**：初版误走 `_ingest_document_record`（add_documents 只增不删），更新后旧内容仍可检索命中。修复：改调 `_rebuild_kb_index`；chunk_count 改为仅 split 计数（避免重建时重复 embedding）。冒烟 ⑤ 的"旧内容不命中"断言正是为此设计，验证有效。
2. **md-editor-rc 内网镜像 404**：npm 内网源（registry.anpm.alibaba-inc.com）无此包；改用功能等价的 `@uiw/react-md-editor@4.1.2`，需求 §4.5 已登记替换注记。
3. **冒烟脚本 temp_kb2 NameError 隐患**：临时库在 try 内创建、finally 无条件引用，中途失败会二次报错；修复为前置 None 初始化 + finally 判空。
4. **/health 路径不存在**：后端无 /health 端点（404），健康验证改用 /docs（200）+ openapi.json 路径数核对。

### 遗留事项（P1）

- 左栏「知识地图」「主页」导航项为禁用占位（需求 §6 已声明）
- 上传文档工作台仅只读渲染，可编辑/在线化（upload→online 转换）留 P1
- 存为文档的库选择无写权限预检（403 靠后端 detail 提示），可考虑 KB 列表携带 role 字段
- 前端工作台未保存内容切 tab/关 tab 无拦截提示（P1 加 beforeClose 确认）
- RAGAS 评估不适用：禁区零改动，无需回归基线

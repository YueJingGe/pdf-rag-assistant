# P0-4 乐享式知识库最小 demo — changelog

> 需求文档：docs/requirements/P0-4-lexiang-style-kb.md（状态：已确认 2026-10-15；v1.1 增补第二轮 §8）｜基线 commit：`ba6837d`（第一轮）/ `af72e3d`（第二轮，docs(p0-4): 需求文档 v1.1）

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

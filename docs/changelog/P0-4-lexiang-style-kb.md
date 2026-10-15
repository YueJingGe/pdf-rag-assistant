# P0-4 乐享式知识库最小 demo — changelog

> 需求文档：docs/requirements/P0-4-lexiang-style-kb.md（状态：已确认 2026-10-15）｜基线 commit：`ba6837d`（docs(p0-4): 需求文档 v1.0 定稿）

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

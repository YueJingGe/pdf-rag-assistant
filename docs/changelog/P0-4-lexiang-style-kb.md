# P0-4 乐享式知识库最小 demo — changelog

> 需求文档：docs/requirements/P0-4-lexiang-style-kb.md（状态：已确认 2026-10-15；v1.1 增补第二轮 §8；v1.2 增补第三轮 §9；v1.3 增补第四轮 §10；v1.4 增补第五轮 §11）｜基线 commit：`ba6837d`（第一轮）/ `af72e3d`（第二轮，docs(p0-4): 需求文档 v1.1）/ `0b76011`（第三轮）/ `39745f9`（第四轮）/ `5db38d1`（第五轮）

## 第五轮：UI 还原乐享 + 信息源文档级多选（2026-10-16）

按需求 §11（v1.4）实施：基线 commit `5db38d1` → T6 后端多范围链（document_ids + resolve_doc_scopes + multi_scope_retrieve/stream，冒烟⑮）→ T6 前端两栏信息源选择器 → T1 个人库保护（移除新建/删除入口）→ T2/T3 侧栏（新建对话上移 + 历史折叠）→ T4 消息形态（用户右气泡/AI 左纯文本）→ T5 圆角输入容器（+左下/发送右下）→ T7 placeholder 四态。**后端仅非禁区增量（chat.py/chat_service.py），RAG 禁区五文件 diff 为空，全程零新增 LLM 调用。**

### 改动文件清单

**后端（T6 多范围合并链，非禁区）**

| 文件 | 改动 |
|---|---|
| `backend/app/services/chat_service.py` | 尾部追加 115 行：`MAX_SCOPE_DOCS=20`；`resolve_doc_scopes`（文档 id 按库分组 + 逐文档 404/403 权限校验）；`multi_scope_retrieve`（同库整库优先、每库一次 `retrieve_with_strategy(use_hyde=False)`、文档组按 metadata.document_id 后过滤、RRF 合并去重截断 top_k）；`multi_scope_rag_stream`（SSE 协议对齐 multi_kb，strategy="multi_scope"，不走 HyDE/语义缓存） |
| `backend/app/api/chat.py` | ChatRequest 加 `document_ids: list[int] \| None`；路由判定链扩展（scope_doc_ids → resolve → doc_scopes → scope_primary，纯文档范围取首库挂会话）；`_chat_sse_events` 加 doc_scopes 参数（分支顺序：doc_scopes > multi_kb > 单库） |

**前端（T1-T5/T7 UI 还原 + T6 两栏弹层）**

| 文件 | 改动 |
|---|---|
| `frontend/src/components/InputPlusPopover/` | 重写（494 行 + less 289 行）：InputSourceValue 扩展 docIds；导出 MAX_SCOPE_DOCS/derivePlaceholder；两栏模式（左 kbPane：Checkbox 整库勾选+头像块+「当前」badge+箭头；右 treePane：antd Tree checkable，cat-*/doc-* key，目录勾选=collectDocIdsUnder 递归展开，跨库保留+上限 20）；allowDocScope=false 回退单列（DocChatPanel） |
| `frontend/src/components/ChatWindow/` | 消息形态乐享式（去 Avatar：用户右侧 #e8f3ff 气泡、AI 左侧纯文本，消息流 780px 居中限宽）；输入区圆角容器（inputCard 16px radius + 浅边框/阴影，内部附件预览→tags→无边框 TextArea→工具行左「+」右圆形发送/停止均带 Tooltip）；source 加 docIds、tags 行加「N 个文档」聚合 tag；placeholder=derivePlaceholder(source)；顶栏新对话按钮删除（移侧栏）；监听 p04:conv-new |
| `frontend/src/components/DocChatPanel/` | 同款消息形态+输入区布局；placeholder 换 derivePlaceholder；InputPlusPopover 传 allowDocScope={false}（轻流式不落会话约束，不引入文档级多选） |
| `frontend/src/components/KnowledgeBaseSidebar/` | 删「+新建知识库」按钮与「删除知识库」菜单项（个人库保护 T1）；nav 区顶部新建对话按钮（dispatch p04:conv-new，T2）；历史对话默认收起+箭头旋转展开（T3） |
| `frontend/src/pages/SpacesPage/` | 删除按钮包 `kb.name !== PERSONAL_KB_NAME` 条件（个人库保护） |
| `frontend/src/pages/MainPage/` | 删全局 Header（乐享式无顶栏），Layout 解构改 {Sider, Content} |
| `frontend/src/hooks/useSSE.ts` | SendOptions 加 documentIds（!useAgent 且非空时入 body.document_ids） |
| `frontend/src/services/api.ts` | 导出 `PERSONAL_KB_NAME = "个人知识库"`（识别锚点 migrate_kb_to_personal.DEFAULT_TARGET_NAME，纯 UI 约定） |

**脚本**

| 文件 | 改动 |
|---|---|
| `scripts/smoke_test_p04.py` | 追加⑮多范围信息源测试（128 行）：第三库两文档格局（标记戊/己）、resolve_doc_scopes 分组与 404/403、混合范围检索（命中指定文档+干扰文档隔离+整库候选）、纯文档范围、fake 网关 SSE 协议断言（strategy=multi_scope）、临时库 finally 清理 |

### 关键设计摘要

- **多范围合并链（禁区规避）**：复用第二轮 multi_kb 编排（每库一次检索 + RRF 跨库可比）+ 第三轮 doc_scoped 后过滤，`scoped_kbs = {kb: docs for kb not in kb_ids}`（同库整库优先）；多范围链不走 HyDE/语义缓存（延续 §8.3 约定）
- **目录勾选 = 前端展开**：chunk metadata 无 category_id，目录级检索过滤需禁区改造列 P1；前端 collectDocIdsUnder 递归展开为文档集合（上限 20，前后端一致）
- **antd Tree 受控勾选技巧**：checkedKeys 只传 doc-*，目录全/半选态由 antd 按子节点自动推导，无需手算 indeterminate
- **纯文档范围会话挂载**：scope_primary = multi_kb_ids[0] ?? doc_scopes 首库（next(iter)），避免误判 plain chat
- **个人库保护定位为 UI 约定**：个人知识库（名称锚点「个人知识库」）仅可重命名；后端已有 owner 隔离不做硬封禁（用户确认决策）
- **derivePlaceholder 四态**：当前文档 > 指定知识（docIds>0 或多库）> 当前知识库 > 直聊；ChatWindow/DocChatPanel 共用

### 验收结果（需求 §11.3 对照）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 个人库不可新建/删除 | ✅ 侧栏无新建库按钮/删除菜单项；SpacesPage 删除按钮对个人库隐藏 |
| 2 | 新建对话在问AI上方 | ✅ DOM 快照：plus 新建对话按钮位于问AI 导航上方，点击清空开新会话（p04:conv-new） |
| 3 | 历史对话折叠 | ✅ 默认收起 + right 箭头，点击展开/收起（旋转动画） |
| 4 | UI 还原乐享 | ✅ 样式计算断言：消息流 780px 居中、userBubble #e8f3ff 右对齐 70%、assistantBody 纯文本、全局无 Header |
| 5 | +左下/发送右下 | ✅ inputCard 780px/16px 圆角/浅边框阴影；inputActions space-between；发送/停止圆形+Tooltip |
| 6 | 信息源文档级多选 | ✅ 两栏弹层（kbRow 头像+「当前」badge+箭头；目录树 7 节点勾选→tags「个人知识库+1 个文档」）；冒烟⑮ 15 断言全绿（混合范围命中/隔离/strategy=multi_scope） |
| 7 | placeholder 区分 | ✅ 单库「基于当前知识库进行提问…」→勾文档后「基于指定知识进行提问…」（实测切换）；四态由 derivePlaceholder 统一 |
| 8 | 质量门 | ✅ tsc -b 零错误 / py_compile 过 / 禁区五文件 diff 空 / 冒烟全绿（46+15 断言） |

### 遇到的问题

1. **Sidebar JSX 括号闭合错**（历史折叠三元包裹少一个 `)`）：LSP 报「应为)」；中间态缓存导致 GetProblems 二次确认（实际修复后无错）
2. **less 批量替换第三个 original_text 传空串失败**：nav 系列/historyBlock 类被第一个替换连带删除；重读文件后以 historyTitle 锚点补回
3. **InputPlusPopover 重写后弹层内 docSummary 与输入区 tags 重复**：删除弹层内概要块，统一由输入区 tags 行渲染
4. **LSP 编辑中间态假错**（ChatWindow/DocChatPanel source 缺 docIds）：替换已成功执行，GetProblems 复验无错
5. **f-string 无插值瑕疵**（冒烟⑮）：改普通字符串
6. **浏览器点击/截图超时**（视口 hidden 环境限制）：改 evaluate_script 在 DOM 层触发 click/mouseover（antd hover Popover 需 mouseover 事件）+ 样式计算断言替代截图

### 遗留事项（P1）

- 目录级检索过滤（chunk metadata 无 category_id）→ 需禁区改造，P1
- 信息源选择弹层移动端适配/键盘导航未做（桌面优先）
- 文档级多选上限 20 为前后端各一份常量（产品化配置 P1）

## 第四轮：主区域单视图 + 问AI 输入区对齐乐享（2026-10-16）

按需求 §10（v1.3）实施：基线 commit `39745f9` → T3 InputPlusPopover 公共弹层 → T2 空态页+ChatWindow 顶栏简化 → T6 DocChatPanel 输入区化 → T1 MainPage 单视图 → T5 树选中态 → T4 库切换器 → 验收。**纯前端改动，后端 `backend/` 全量 diff 为空（本轮零改动），RAG 禁区五文件 diff 为空，全程零新增 LLM 调用。**

### 改动文件清单（全部前端）

| 文件 | 改动 |
|---|---|
| `frontend/src/components/InputPlusPopover/` | 新建（tsx 241 行 + less 159 行）：输入区「+」公共弹层——导出 `InputSourceValue{docSelected,kbIds}` 与 `EMPTY_SOURCE`；一级弹层（问答/Agent Segmented + 深度思考 Switch=HyDE 映射 + 技能置灰占位「敬请期待」+ 信息源行带数量 badge）；二级 hover 弹层（全网搜索 Switch 仅直聊可用 + 知识范围多选：全部知识/各库 Checkbox/当前文档项）；open 时懒加载 allKbs；ChatWindow 与 DocChatPanel 同构复用（唯一真相源） |
| `frontend/src/components/ChatWindow/` | 空态页（笑脸+「今天从哪里开始?」+输入区，隐藏 header）；HyDE Switch 从顶栏移入弹层（顶栏简化）；旧「+」Popover 116 行拆除接入 InputPlusPopover；信息源 tags 统一入输入框上方（可×移除，空=纯直聊）；placeholder 与免责行「回答内容均由AI生成，仅供参考」；tag 名 allKbs 异步加载前用 knowledgeBaseName prop 兼底防闪烁 |
| `frontend/src/components/DocChatPanel/` | 输入区化重写：顶部仅「问AI」；信息源入输入区（source 默认 `{docSelected:true,kbIds:[]}`）；InputPlusPopover 接入（showModeSegment=false，仅问答模式）；handleSend 三态（当前文档=documentId / 多库=knowledgeBaseIds / 空=直聊）；换文档重置默认勾选；免责行 |
| `frontend/src/pages/MainPage/` | 单视图重构：删 Tabs/openDocs/openCategories/activeTab 体系，`MainView` 四态 union（chat/feedback/category/doc）；不支持多开文档（点树即替换）；Workbench key=`${kbId}-${docId}` 强制重建；CategoryView/Workbench 加关闭回问AI；Sidebar 传 onGoFeedback/feedbackActive/activeDocId |
| `frontend/src/components/KnowledgeBaseSidebar/` | 库切换器移除「普通聊天」选项（仅列知识库，左上角始终库名）；导航增「检索调优」（仅 admin，tabs 移除后 FeedbackDashboard 新入口）；历史对话仅列当前选中库（kb=0 旧会话不可见，迁移 P1）；树区空态文案更新；activeDocId 透传 CategoryTree |
| `frontend/src/components/CategoryTree/` | 树选中态：activeDocId 可选 prop（/spaces 不传隔离）；文档节点蓝底高亮（自定义 nodeLabelActive 类）；activeDocId 变化自动展开所在目录链（含未归类）+ scrollIntoView 滚动到可见 |
| `frontend/src/components/CategoryView/` | onClose 关闭按钮（回问AI）；activeDocId 文档行高亮（单视图互斥下契约保留） |
| `frontend/src/components/DocumentWorkbench/` | onClose 关闭按钮（回问AI） |

### 关键设计摘要

- **InputSourceValue 统一信息源模型**：`{docSelected, kbIds}`，docSelected 与 kbIds 互斥（后端 document_id 优先，UI 强制互斥保证行为可预期）；**空 = 纯直聊**（=原普通聊天，kb=0 路径）；tags 渲染在输入框上方可逐个移除
- **深度思考开关 = 现有 HyDE 映射**（复用 use_hyde 参数，不新建后端能力）；`hydeDisabled = agentMode || docSelected || kbIds.length > 1`；全网搜索仅直聊可用（后端 web_search 链仅直聊路径处理）
- **MainView union 替代 Tabs**：`{type:'chat'|'feedback'|'category'|'doc'}` 条件渲染单视图；目录视图作为主区域临时视图（关闭回问AI）；命名联动 renameCategoryView/onMissing 保留
- **树选中态自定义高亮**：antd Tree `selectable={false}` 下受控 selectedKeys 不渲染选中样式（rc-tree 节点级 selectable 短路），故用 nodeLabel 自定义类方案；activeDocId 展开目录链用 guard Set 防环
- **「普通聊天」语义退役**：问答模式清空信息源 = 直聊（用户定调「问答模式其实就相当于是普通聊天」）；库切换器左上角始终显示库名

### 验收结果（需求 §10.3 对照）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 无 tabs，三态单视图 | ✅ DOM 快照：空态/文档视图两态 main 区域均无 tab 组件 |
| 2 | 空态页 | ✅ 笑脸+「今天从哪里开始?」+大输入框+免责行；无卡片/换一换/Workbuddy |
| 3 | 输入区弹层 | ✅ Segmented+深度思考+信息源（数量1）；二级=全网搜索（非直聊置灰✓）+范围多选（全部知识/各库，当前库默认勾） |
| 4 | 信息源 tags | ✅ 当前库 tag 常显可×；空=纯直聊；首帧库名闪烁已修 |
| 5 | 树选中态 | ✅ activeDocId 高亮+自动展开+滚动（代码路径+tsc 保障；视觉截图受环境限制见「遇到的问题」） |
| 6 | 右面板 | ✅ 顶部仅「问AI」；信息源交互入输入区 |
| 7 | 普通聊天 | ✅ 库切换器无「普通聊天」；检索调优对非 admin 隐藏（is_admin=False 实测）符合设计 |
| 8 | 质量门 | ✅ tsc -b 零错误 / py_compile 全过 / 禁区五文件+backend 全量 diff 空 / 冒烟全量 46 断言绿 |

### 遇到的问题

1. **MainPage→Sidebar 传 onGoFeedback 报 Props 不存在**：单视图重构先写 MainPage、Sidebar 改造后置导致的顺序性报错，T4 落地即消（预期内）
2. **CategoryView 块内 `view.type === 'doc'` TS 窄化报「无重叠」**：`view.type === 'category' && ...` 块内 view 已窄化为 category；单视图互斥下 activeDocId 恒空，调用侧不传（组件侧可选 prop 契约保留）
3. **JSX props 位置放 `{/* */}` 注释报语法错**：props 位置不支持 JSX 注释，删除注释改由代码注释承载
4. **信息源 tag 首帧闪「知识库N」**：tag 名查 allKbs（异步），加载完成前走 fallback；补 knowledgeBaseName prop 次级兼底（浏览器快照实测发现）
5. **环境杂音**：zsh `app/*.py` glob 无匹配（后端在 backend/ 下）；`python` 命令不存在用 `python3`；项目根 `npx tsc` 误装同名废弃包（须在 frontend/ 下跑）
6. **浏览器截图不可用**：take_screenshot 报 NATIVE_BROWSER_VIEWPORT_UNAVAILABLE（视口隐藏，环境限制非应用问题）；以 13 次 a11y DOM 快照替代验证全部交互点

### 遗留事项（P1）

- kb=0 旧普通聊天会话不可见（存量迁移脚本 P1）
- 技能体系（真技能卡）/真 reasoning 深度思考/知识概览 AI 摘要卡/推荐问题卡片/Workbuddy → 需求声明不做（P1）
- CategoryView activeDocId 契约保留未使用（若「关闭文档回目录视图」需求出现即启用）
- 树选中态视觉截图未留档（环境限制；DOM 快照已验证结构与类名逻辑）

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

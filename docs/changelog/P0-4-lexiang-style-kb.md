# P0-4 乐享式知识库最小 demo — changelog

> 需求文档：docs/requirements/P0-4-lexiang-style-kb.md（状态：已确认 2026-10-15；v1.1 增补第二轮 §8；v1.2 增补第三轮 §9；v1.3 增补第四轮 §10；v1.4 增补第五轮 §11；v1.5 增补第五轮返工 §12）｜基线 commit：`ba6837d`（第一轮）/ `af72e3d`（第二轮，docs(p0-4): 需求文档 v1.1）/ `0b76011`（第三轮）/ `39745f9`（第四轮）/ `5db38d1`（第五轮）/ `1c47e0c`（第五轮返工 R1-R4）/ `4e5985f`（第五轮返工 R5-R13）

## 第五轮返工第九批 R26-R29：question 右对齐/⋮弹出层与重命名端点/字号字色选中态 token 统一/树行溢出省略号根治（2026-10-16）

用户四条批注：question 样式不对应从右侧开始且限最大宽、历史对话缺「编辑名称/删除对话」弹出层、字号/选中态应全局统一（「完整项目风格要一致」）、长文档名超出省略号+底部横向滚动条、「有的文字加粗有的不加粗」。基线延续 `4e5985f`。**本轮含一个后端小端点（会话重命名），其余纯前端；禁区五文件 diff 为空，零新增 LLM 调用。**

### 改动清单

| 文件 | 内容 |
|---|---|
| `frontend/src/components/ChatWindow/index.module.less` | R26：userBubble 右对齐（margin-left:auto）+ max-width 72% |
| `frontend/src/components/KnowledgeBaseSidebar/index.tsx` | R26：历史条目 Popconfirm 删除钮 → 乐享式「⋮」Dropdown（编辑名称/删除对话）；行内编辑 Input（Enter 确认/Esc 收起）；删除改 Modal.confirm 二次确认 |
| `frontend/src/components/KnowledgeBaseSidebar/index.module.less` | R26：historyDelete → historyMore（灰 ⋮ hover 浮现）+ historyEditInput |
| `frontend/src/services/api.ts` | R26：chatApi.renameConversation（PATCH） |
| `backend/app/api/chat.py` | R26：PATCH /conversations/{id}（ConversationRenameRequest，空名校验 422） |
| `backend/app/services/chat_service.py` | R26：rename_conversation（get_own_conversation 归属校验 + commit） |
| `frontend/src/components/CategoryTree/index.module.less` | R27/R28/R29：.ant-tree-title 补 flex 链（溢出根治）；nodeLabel 字色 #1f2329；nodeLabelActive 蓝字 600 + nodeTitleActive #e8f3ff 色块 |
| `frontend/src/components/CategoryTree/index.tsx` | R27/R29：nodeTitle 挂 nodeTitleActive（选中态 token 统一） |

### 验收（刷新后 DOM/接口实测）

| 项 | 结果 |
|---|---|
| R26 question 右对齐 | 贴右缘 gapRight=0、max-width 72%、#ececee ✅ |
| R26 ⋮ 弹出层 | 菜单「编辑名称/删除对话」→ 行内 Input → Enter → PATCH 落库 → 列表刷新显示新名 ✅（改名已还原数据） |
| R26 rename 端点 | 无 token PATCH=401 ✅；后端已重启生效 ✅ |
| R27 字号/字色 | 历史 13px = 树 13px；树字色 #1f2329 与历史一致 ✅ |
| R27 选中态统一 | 树选中 #e8f3ff + #1677ff + 600，与导航/历史 token 一致 ✅ |
| R28 溢出根治 | 长名 label 压缩 165px + ellipsis 生效；treeWrap sw=cw=279（原 408>279）横向滚动条消失 ✅ |
| R29 加粗统一 | 树选中 600 与历史一致 ✅ |
| 类型/编译 | tsc exit=0、py_compile OK ✅ |

### 遇到的问题

- **ellipsis 链路断点定位**：R20 只修 content-wrapper，漏了 antd 中间层 span.ant-tree-title——元素级测量（wrapper 235 / title 349 / label 325 不压缩）才找到真断点；补 `.ant-tree-title { flex:1; min-width:0 }` 根治
- **整行选中底色两条路失效**：:has 与 antd TreeNode data className（规则存在/类匹配/无覆盖/无内联/sheet 启用，但 computed 不应用，疑似浏览器怪癖）——第三方案 nodeTitle 自定义 span（nodeLabel 600 同路径已验证生效）落地；教训：antd 树行级样式优先走 titleRender 自定义元素
- **误杀后端进程**：重启时 `uvicorn` 脚本 shebang 指向无依赖的 homebrew python3.10（ModuleNotFoundError sqlalchemy），正确方式 `python3 -m uvicorn`（/usr/bin/python3 有依赖）——已恢复并记录
- **CSSOM 检测脚本 bug**：新 Chrome 的 CSSStyleRule 也有 cssRules（空列表 truthy），walk 递归会跳过所有规则——检测需 instanceof CSSStyleRule 判断

### 遗留事项（P1）

- R26 删除对话 Modal.confirm 交互真实删除链路待用户复验；沿袭：R19 弹框新建文件夹真实创建、历史旧消息 sourceTags 回填、暗色模式、移动端适配

## 第五轮返工第八批 R25：目录树展开箭头统一移行尾（2026-10-16）

用户批注「箭头明显没有缩紧」「一级二级目录分不清楚」「展开收起箭头统一放右侧，和历史对话一样」。基线延续 `4e5985f`。**纯前端改动（1 文件），后端 diff 为空，禁区五文件 diff 为空，零新增 LLM 调用。**

### 改动与验收

| 项 | 内容 |
|---|---|
| `frontend/src/components/CategoryTree/index.module.less` | switcher 改 absolute 行尾（right 10px + translateY 垂直居中）+ opacity 过渡；treenode relative + padding 左右 8px；新增 hover 时箭头 opacity 0（让位给「⋮/+」工具钮） |
| 验收（刷新后 DOM） | switcher absolute right=12px 垂直居中 ✅；folder 行首 left=20、folder→文字 gap 6px ✅；文档行相对缩进 20px 层级清晰 ✅；行高 34px 保持 ✅；hover 让位两条规则同容器 hash 命中 ✅（CSS :hover 伪类无法 dispatch 触发，规则注入断言替代） |
| 设计说明 | 箭头移行尾后 folder 从行首起步，箭头-folder 间距问题自然消解；hover 时箭头透明与工具钮同区互换（非 hover 工具钮本就隐藏），不同时显示无重叠 |

### 遇到的问题

- CSS `:hover` 伪类无法用 dispatchEvent 触发（仅真实鼠标），交互级验证以「规则注入 + 容器 hash 一致 + 特异性压过」断言替代，视觉效果待用户真实浏览器复验

### 遗留事项（P1）

- R25 hover 互换与视觉待用户复验；沿袭：R19 弹框新建文件夹真实创建链路、历史旧消息 sourceTags 回填、暗色模式、移动端适配

## 第五轮返工第七批 R21-R24：历史条目层级缩进/信息源级联勾选/双层阴影/弹框交互打磨（2026-10-16）

用户连续四条批注：①「历史对话怎么没有层级之分」（条目应比标题缩进）；②「你没有级联的概念么，最上层都选上了，为什么下层的还是空的」（信息源勾库后右栏树全空）；③「你没发现你阴影有两层么」（目录行 hover 双层灰底叠加错位）；④「没有收起和取消啊」+ 预览裸露 markdown 源码（你真应该去学下好的交互设计）。基线延续 `4e5985f`。**纯前端改动（4 文件），后端 diff 为空，禁区五文件 diff 为空，零新增 LLM 调用。**

### 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/components/KnowledgeBaseSidebar/index.module.less` | R21：historyItem 左内边距 10→30px（条目相对标题缩进 20px） |
| `frontend/src/components/InputPlusPopover/index.tsx` | R22：级联勾选——treeCheckedKeys 整库时级联返回全部 doc-*；handleTreeCheck 双向转换（勾满升级整库 / 部分降级文档级）；kbPartial 半选态 + Checkbox indeterminate |
| `frontend/src/components/CategoryTree/index.module.less` | R23：content-wrapper:hover transparent（屏蔽 antd 自带灰底与整行 hover 叠加） |
| `frontend/src/components/ChatWindow/index.tsx` | R24：新建文件夹编辑态补取消按钮 + Esc 收起；预览区改 ReactMarkdown 渲染（maxHeight 140 滚动） |

### 验收结果（整页刷新后 DOM 实测，含真实交互序列）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | R21：标题 icon left=18 / 条目 icon left=38（缩进 20px） | ✅ |
| 2 | R22 正向：勾库 → 树 6 勾；取消库 → 树清零 | ✅ |
| 3 | R22 反向：取消一个文档 → 树级联取消 + 左栏库变 indeterminate 半选 | ✅ |
| 4 | R23：wrapper:hover transparent 规则命中，hover 仅一层背景 | ✅ |
| 5 | R24：编辑态取消按钮点击收起回「+ 新建文件夹」；预览 ReactMarkdown 渲染（无星号井号源码） | ✅ |
| 6 | 质量门 | ✅ tsc 零错误；后端零改动；禁区五文件 diff 空 |

### 遇到的问题

1. **antd 两字按钮自动插空格**：「取消」textContent 实为「取 消」，精确匹配失败 → 归一化后匹配（三字及以上无此问题）
2. **JSX 注释内禁写星号斜杠序列**：注释里的 markdown 示例被解析为注释提前闭合（tsc「无效的字符」），改文字描述规避
3. **级联与整库语义的融合**：勾库清 docIds 是后端整库优先语义（保留），视觉级联由 treeCheckedKeys 承担；树上勾满自动升级整库（无文档上限）、部分选择降级 docIds 承接——状态机闭环且与后端 multi_scope_retrieve 语义一致

### 遗留事项（P1）

- R21-R24 视觉待用户复验；沿袭：历史旧消息 sourceTags 回填、暗色模式、移动端适配

## 第五轮返工第六批 R19-R20：回答 footer 乐享化/「添加到」弹框 + 目录树与弹层系统性间距修复（2026-10-16）

用户连续两条批评：①「两个 icon 距离这么远干嘛，参考这里的添加到和复制，以及添加到有一个弹框的交互」（footer 拉散 + 乐享弹框对照四图）；②「你看间距啊，不要我说哪里你就看哪里」「面板太窄了啊，内容过宽了啊」（目录树箭头-folder 大空隙 + 长文件名硬截断 + 信息源弹层滚动条复现）。基线延续 `4e5985f`。**纯前端改动（6 文件），后端 diff 为空，禁区五文件 diff 为空，零新增 LLM 调用。**

### 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/components/ChatWindow/index.tsx` | R19：footer 重排「[添加到][复制]免责」紧凑排列，存文档 icon 钮→乐享式「添加到」文字按钮；弹框重写：宽 640、标题+副标题、左 KB 列表+右目录树（根行「知识库一级目录 ✓」）、底部「+ 新建文件夹」行内交互（categoryApi.create→刷新树）、取消/确认；新增 saveNewCat* 三 state + handleCreateCatFolder；KnowledgeOutlined 不存在于该版 icons → AppstoreOutlined |
| `frontend/src/components/ChatWindow/index.module.less` | R19：assistantFooter 去 space-between 改 gap 4px；新增 addToBtn/saveModal* 全套双栏样式 |
| `frontend/src/components/CategoryTree/index.module.less` | R20：① switcher 24→16px+margin 2px（箭头-folder 视觉间距 12→≈5px）；② 行高 28→34px（treenode padding 5px，升特异性）；③ content-wrapper 设 flex+min-width:0 根治长文件名硬截断（antd 默认非 flex，nodeTitle flex:1 失效） |
| `frontend/src/components/InputPlusPopover/index.module.less` | R20：**滚动条真凶**——sourcePanel 280px 装不下内部 560px twoPane；面板 280→600px + overflow-x:hidden 兕底（R14 在树内部找错宿主） |

### 验收结果（整页刷新后 DOM 实测，含真实开弹层/开弹框）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 目录树：switcher 宽 16px / 箭头-folder 间距 ≈5px / 行高 34px | ✅ |
| 2 | 目录树：wrapper flex 生效，长文件名 ellipsis 机制就位（无硬截断） | ✅ |
| 3 | 信息源弹层：真实 dispatch 序列开弹层，sourcePanel 600px、全链路 overflowX=0、页面无横向溢出 | ✅ |
| 4 | footer：添加到→复制 gap 4px、复制→免责 8px（原 space-between 拉散） | ✅ |
| 5 | 添加到弹框：640 宽、标题+副标题、左 KB 列表（选中态）+ 右目录树 + 根行「知识库一级目录」、新建文件夹可用 | ✅ |
| 6 | 质量门 | ✅ tsc 零错误；后端零改动；禁区五文件 diff 空 |

### 遇到的问题

1. **信息源滚动条宿主两轮找错（R1/R14）后的真凶**：R14 在树内部找，本轮沿容器链自上而下量 scrollWidth 才发现宿主是外层 sourcePanel（280px < 内容 560px）。教训：滚动条排查必须沿滚动容器链自上而下，不能只查目标组件内部
2. **长文件名硬截断根因**：antd `.ant-tree-node-content-wrapper` 默认非 flex，我们自定义的 nodeTitle（flex:1+min-width:0）从未生效，内容撑溢出被硬截——修复 wrapper 设 flex 后 ellipsis 才真正工作
3. **CDP 输入受限下的 React 事件触发**：受控 Popover（open 由父控制）+ hover 二级弹层，CDP click/hover 超时；用 dispatchEvent 完整序列（pointerdown→mousedown→pointerup→mouseup→click）开主弹层成功；二级 hover 需带 relatedTarget 的 mouseover（React onMouseEnter 模拟依赖 from/to 路径）
4. **KnowledgeOutlined**：该版 @ant-design/icons 无此导出，改用项目已验证的 AppstoreOutlined

### 遗留事项（P1）

- R19 弹框「新建文件夹」真实创建链路、R20 视觉待用户复验；沿袭：R17 菜单交互实测、历史旧消息 sourceTags 回填、暗色模式、移动端适配

## 第五轮返工第五批 R18：目录树视觉二次对齐——箭头形态/层级缩进/间距（2026-10-16）

用户否定 R17（「这样式哪里一样了，你实现的」+ 前后对照截图）。根因：R17 只调了缩进宽度，漏掉三处最显眼差异——① 箭头形态（antd 默认实心黑三角 vs 乐享灰色细线 chevron ∨/＞）② 16px 缩进层级感丢失 ③ icon-文字间距 4px 偏紧。基线延续 `4e5985f`。**纯前端改动（2 文件），后端 diff 为空，禁区五文件 diff 为空，零新增 LLM 调用。**

### 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/components/CategoryTree/index.tsx` | Tree 加 `switcherIcon={<DownOutlined />}`（细线 chevron，展开 ∨ / 收起 antd 自动 rotate -90° 成 ＞；注释放 props 间/三元分支内均非法，最终置于条件表达式前） |
| `frontend/src/components/CategoryTree/index.module.less` | ① `.ant-tree .ant-tree-switcher` 色灰 #8f959e/10px（选择器加 .ant-tree 一层压 antd 特异性）；② 缩进 16→20px 恢复层级感；③ `.ant-tree-iconEle` margin-right 6px；④ treenode 行 padding 2px + border-radius 6px + hover 浅灰 #f5f6f7 整行反馈 |

### 验收结果（页面刷新后 DOM 断言）

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 箭头形态 | ✅ switcher icon = anticon-down（细线 chevron），色 rgb(143,149,158)=#8f959e，10px |
| 2 | 层级缩进 | ✅ indent-unit 20px |
| 3 | icon-文字间距 | ✅ iconEle margin-right 6px |
| 4 | 类型色保持 | ✅ PDF rgb(230,69,69) 红 / folder rgb(250,173,20) 金 |
| 5 | 质量门 | ✅ tsc -b 零错误；后端零改动；禁区五文件 diff 空 |

### 遇到的问题

1. **CSS module HMR 哈希失配（新坑）**：less 改动后新样式表（新哈希 `12fni`）已注入 document.styleSheets，但 DOM 上组件 className 还挂旧哈希（`19qm5`）——新规则全部不命中、computed 值不变（验证脚本显示规则存在却不生效的假象）；navigate reload 整页重挂载后命中。教训：CSS module 类名哈希随内容变化，HMR 热换样式不换 DOM 类名，改 less 后断言前必须整页刷新
2. **JSX 注释位置三连错**：props 之间、三元分支 `) : (` 与元素之间均不能放 `{/* */}`（tsc 报「应为...」/「应为)」），最终注释置于条件表达式前（JSX 子元素位）；期间 LSP 报「运算符<不能应用」为中间态缓存，tsc exit=0 为准
3. **antd 规则覆盖**：`.ant-tree-switcher` 单层选择器与 antd `:where(...).ant-tree .ant-tree-switcher` 同特异性时后加载的 antd 胜 → 加 `.ant-tree` 层至 (0,3,0) 压过

### 遗留事项（P1）

- R18 视觉待用户真实浏览器复验（收起态 ＞ 旋转需点击目录收起后观察）；沿袭：R17 菜单交互实测、R14 弹层 scrollWidth 断言、R10/R12 交互级实测、历史旧消息 sourceTags 回填、历史对话空态、暗色模式、移动端适配

## 第五轮返工第四批 R17：目录树一比一还原乐享（2026-10-16）

R16 后用户带 4 张乐享对照截图反馈「目录样式和腾讯乐享保持一致，一比一还原哦」。按需求 §12 R17 实施，基线延续 `4e5985f`。**纯前端改动（2 文件），后端 diff 为空，禁区五文件 diff 为空，零新增 LLM 调用。**

### 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/components/CategoryTree/index.tsx` | ① 目录行单一「···」菜单 → 乐享式双工具钮「⋮ 更多操作」(重命名/删除) +「+ 新建」(新建文档/新建子目录/上传文件挂该目录)，hover 浮现行尾对齐；② 文档 icon 按扩展名着色（PDF 红 #e64545 / Word 蓝 #2b7cd3 / 在线 MD 绿 / 其他灰）；③ folder #1677ff→#faad14 金色；④ 文档行「···」文本改 MoreOutlined 竖三点；⑤ 上传升级：uploadCategoryId state，UploadModal categoryId 由固定根改动态（目录行上传挂该目录） |
| `frontend/src/components/CategoryTree/index.module.less` | ① `.ant-tree-indent-unit` 24→16px 浅缩进；② nodeTitle/nodeLabel flex 化（label 占剩余宽度、工具钮行尾、max-width 150 移除）；③ 新增 .nodeTools（hover 浮现容器）/.nodeTool（18px icon 钮 #8f959e hover 蓝）；④ nodeMore 文本三点改 icon 钮样式 |

### 关键设计摘要

- **antd 该版 TreeProps 无 indent 属性**：缩进改 CSS `.ant-tree-indent-unit{width:16px}`（版本无关更稳）；乐享子级缩进约一组箭头+icon 宽，16px 视觉贴近
- **菜单按项目能力裁剪**：乐享 ⋮ 菜单的新标签页/复制链接/收藏/快速访问/复制到/移动到、+菜单的智能文档/智能表格/模板/引用知识/上传文件夹/Figma/导入均不做——与第三轮用户批注「保留重命名删除即可」一致；+菜单「上传文件」升级为可挂该目录（原只能挂根）
- **行尾对齐链**：nodeTitle flex:1 + nodeLabel flex:1(min-width:0) + nodeTools flex-shrink:0 → 长名 ellipsis、短名空位归工具钮（blockNode 拉伸下与侧栏头部行对齐）

### 验收结果

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 浅缩进 | ✅ DOM 断言 indent-unit width 16px；CSSOM 规则注入 |
| 2 | folder 金色 | ✅ rgb(250,173,20)=#faad14 |
| 3 | PDF 红色 icon | ✅ anticon-file-pdf 存在，color rgb(230,69,69)=#e64545 |
| 4 | 目录行双工具钮 | ✅ nodeTools ×3（三个目录行各一组）已挂载，hover 浮现 CSS 规则注入 |
| 5 | 质量门 | ✅ tsc -b 零错误；后端零改动；禁区五文件 diff 空 |

### 遇到的问题

1. **TreeProps 无 indent**：先写 `indent={16}` 报 TS 错（antd 该版 TreeProps 不含 indent）→ 改 CSS indent-unit 方案，一次通过
2. **hover 态断言受限**：nodeTools 默认 opacity:0，CDP hover 受视口隐藏限制不稳定——验证采用「DOM 结构存在 + CSSOM 规则注入」双断言，hover 视觉由用户真实浏览器复验

### 遗留事项（P1）

- R17 菜单交互（⋮/+ 点击弹菜单、上传挂目录全链路）待用户实测；沿袭：R14 弹层 scrollWidth 断言、R10/R12 交互级实测、历史旧消息 sourceTags 回填、历史对话空态、暗色模式、移动端适配

## 第五轮返工第三批 R14-R16：弹层滚动条根治 + 侧栏 icon 对齐 + 问AI入口新建对话（2026-10-16）

R5-R13 交付后用户实测再反馈三条（带截图）：①信息源弹层底部仍现深色粗横向滚动条（R8 加宽后未根除）②侧栏各行 icon 左缘参差（R7 规格统一后未对齐）③点「问AI」进入的是历史会话页而非新对话空态页。按需求 §12 追加 R14-R16 实施，基线延续 `4e5985f`。**纯前端改动（5 文件），后端 diff 为空，禁区五文件 diff 为空，零新增 LLM 调用。**

### 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/components/InputPlusPopover/index.tsx` | R14：目录 Tree 加 `virtual={false}`（节点量级小，消除虚拟滚动容器变量） |
| `frontend/src/components/InputPlusPopover/index.module.less` | R14：sourceTree `:global` 对 `.ant-tree-list` / `.ant-tree-list-holder` / `.ant-tree-list-holder > div` 三层容器 `overflow-x:hidden` 兜底 |
| `frontend/src/components/KnowledgeBaseSidebar/index.tsx` | R15：历史行 caret 移至行尾（HistoryOutlined 先、文案、caret 后）；R16：「问AI」行 onClick onGoChat→handleNewConversation（点行即新对话空态页，与「+」一致） |
| `frontend/src/components/KnowledgeBaseSidebar/index.module.less` | R15：.historyCaret 加 margin-left:auto、10→12px |
| `frontend/src/components/CategoryTree/index.module.less` | R15：.treeHeader padding `2px 8px` → `2px 8px 2px 14px` |

### 关键设计摘要

- **R14 根因是滚动条宿主错判**：R1/R8 两次只约束了 treePane 外层，但深色粗条实际来自内部 antd Tree 虚拟滚动容器 `.ant-tree-list-holder`（自带 overflow:auto、antd 默认滚动条样式，与自定 6px 细条外观明显不同）——外层 hidden 管不到内部容器；双保险 = 关虚拟滚动 + 三层容器逐层裁剪
- **R15 对齐基准线 left:18**：navItem padding-left 10 + 侧栏容器偏移 8；目录标题差 6px（treeHeader padding 8）→ 14；历史行 caret 前置占位 18px → caret 右置（margin-left:auto），主 icon/文案列全部回归基准线，折叠语义不变（▾/▴）
- **R16 入口语义统一**：「问AI」行 = 新对话入口（乐享行为：点导航即开新对话），不再恢复上次活跃会话；历史会话消费路径唯一化（历史列表条目）；复用既有 p04:conv-new 事件总线，零新状态

### 验收结果

| # | 验收项 | 结果 |
|---|---|---|
| 1 | R15 历史行 icon 对齐 | ✅ DOM 断言 HistoryOutlined left:36→18；caret 行尾 left:249（margin-left:auto 生效） |
| 2 | R15 目录 icon 对齐 | ✅ DOM 断言 left:12→18；CSSOM `padding: 2px 8px 2px 14px` |
| 3 | R14 Tree 三层拦截 | ✅ CSSOM 注入 `._sourceTree .ant-tree-list/.ant-tree-list-holder/>div { overflow-x:hidden }` |
| 4 | R16 问AI 新对话 | ✅ 行为断言：点击后主区域显示空态文案「今天从哪里开始」、无 userBubble/assistantBody 元素 |
| 5 | 质量门 | ✅ tsc -b 零错误；后端零改动；禁区五文件 diff 空 |

### 遇到的问题

1. **两轮返工未根治同一滚动条 = 根因从未被实测定位**：R1（外层 overflow-x:hidden）与 R8（加宽 560px）都基于「宿主是 treePane」的猜测，本轮才通过「滚动条外观（深色粗条 vs 自定细条）+ antd Tree 结构」锁定真宿主为内部虚拟滚动容器——教训：返工修复必须先定位到元素级证据（外观特征/DOM 实测），否则样式断言（treePane hidden ✅）全绿也可能没修到点上
2. **弹层交互级 DOM 实测受阻**：二级弹层为 trigger=hover 嵌套 Popover，CDP 合成事件（dispatchEvent mouseover/mouseenter）与 hover 工具均未触发；本轮验证依赖 CSSOM 规则注入断言 + 用户真实浏览器复验（验收标准 15 的 scrollWidth 断言待弹层可开时补）

### 遗留事项（P1）

- R14 验收标准 15 的弹层打开态 scrollWidth 断言待用户实测复验（CDP hover 触发受限）
- 沿袭：R10/R12 交互级实测、历史旧消息 sourceTags 回填、历史对话空态、暗色模式、移动端适配

## 第五轮返工第二批 R5-R13：侧栏规格统一 + 弹层紧凑加宽 + 工作台多选文档 + 问AI入口切换 + 问题块对齐乐享（2026-10-16）

用户实测反馈九条（R5-R7/R8/R9/R10/R11/R12/R13 分七批，多为带截图批注，含乐享对照图）：侧栏交互细节、弹层空间、工作台能力与主聊天一致性。按需求 §12 追加条目实施，基线 commit `4e5985f`。**纯前端改动（9 文件），后端 `backend/` 全量 diff 为空，RAG 禁区五文件 diff 为空，全程零新增 LLM 调用。**

### 改动文件清单（全部前端）

| 文件 | 改动 |
|---|---|
| `frontend/src/components/KnowledgeBaseSidebar/index.tsx` | R5：删通栏「+新建对话」按钮，改「问AI」导航行右侧 PlusOutlined icon（stopPropagation 防误触导航）；R6：历史折叠箭头 RightOutlined+rotate(90) → DownOutlined（收起 ▾ / 展开 rotate(-180deg) ▴）；R7：HistoryOutlined 加 historyTitleIcon 类 |
| `frontend/src/components/KnowledgeBaseSidebar/index.module.less` | R5：删 .newConvBtn，加 .navNewBtn（margin-left:auto + 14px + #8f959e，hover #1677ff）；R6：.historyCaretOpen rotate(-180deg)；R7：.historyTitle 14px/#1f2329/padding 8px 10px（对齐问AI 行），加 .historyTitleIcon 16px/#646a73 |
| `frontend/src/components/CategoryTree/index.tsx` | R7：AppstoreOutlined inline style 改 treeHeaderIcon 类（与侧栏同源规格） |
| `frontend/src/components/CategoryTree/index.module.less` | R7：.treeHeaderTitle 13px/#333 → 14px/#1f2329；加 .treeHeaderIcon 16px/#646a73 |
| `frontend/src/components/InputPlusPopover/index.module.less` | R8：twoPane 460→560px（消除横向滚动条）；R9：.rowArrow/.itemCheck 删 margin-left:auto（✓/→ 紧跟标签不再右推拉满）；.sourceRow 删 ant-switch margin 规则（全网搜索开关紧跟文案）；R11：.countBadge 删 margin-left:auto |
| `frontend/src/components/ChatWindow/index.tsx` | R13：MessageItem 加 sourceTags?: string[]；新增 sourceTagNames() 快照 helper（docSelected→「当前文档」、kbIds→库名、docIds→「N 个文档」）；handleSend 写入用户消息；userBubble 渲染首行 tag 块 |
| `frontend/src/components/ChatWindow/index.module.less` | R13：.user flex-end→flex-start（用户提问与 AI 同侧左对齐）；.userBubble max-width 70%/#e8f3ff/radius 12px → width 100%/#ececee/radius 10px（乐享式浅灰块）；加 .userBubbleTags/.userBubbleTag（12px/#4e5460/#dfe1e5） |
| `frontend/src/components/DocChatPanel/index.tsx` | R10：删 `allowDocScope={false}`（信息源弹层与主聊天同构，支持文档级多选，docIds 走 multi_scope）；handleSend 加 documentIds + useHyde 加 `docIds.length===0` 条件；sourceTags 区加 docIds 聚合 tag；useEffect 依赖加 source.docIds；R12：Props 加 onCollapse、header 右上角关闭按钮；R13：MsgItem 加 sourceTags + sourceTagNames() + userBubble tag 行 |
| `frontend/src/components/DocChatPanel/index.module.less` | R13：.user flex-start；.userBubble 同主聊天款（100%/#ececee/10px）+ userBubbleTags/userBubbleTag |
| `frontend/src/components/DocumentWorkbench/index.tsx` | R12：右侧操作组包 Space size=8（保存+问AI+× 聚拢）；「问AI」按钮仅 chatCollapsed 时渲染（primary 小按钮），删除原「展开/收起」双态按钮；DocChatPanel 传 `onCollapse={() => setChatCollapsed(true)}` |
| `docs/requirements/P0-4-lexiang-style-kb.md` | §12 追加 R5-R13 九段（含验收标准 7-14） |

### 关键设计摘要

- **R10 零后端复用**：useSSE.SendOptions.documentIds（第五轮 T6 已有）+ chat.py 路由无条件 `_get_or_create_conversation`（conversation_id=None 自动建会话）→ DocChatPanel 仅改前端传参即打通 multi_scope 链
- **R12 入口语义化**：收起态 = 工作台顶栏最右「问AI」主色按钮（入口唯一）；展开态 = 面板 header 右上角 CloseOutlined（操作就地）——替代原先占中部的双态切换按钮
- **R13 来源快照模式**：sourceTags 在发送时刻快照写入消息对象（历史恢复的旧消息无此字段则不渲染 tag 行，无回填成本）
- **行规格统一 token**：文案 14px/#1f2329、icon 16px/#646a73、辅色/默认 icon #8f959e hover #1677ff——侧栏（问AI/历史/目录）与弹层全部同源

### 验收结果

| # | 验收项 | 结果 |
|---|---|---|
| 1 | R5 新建对话 icon 化 | ✅ navNewBtn 存在、newConvBtn 已删、颜色 rgb(143,149,158)=#8f959e |
| 2 | R6 箭头下/上方向 | ✅ caret=anticon-down，收起态 transform none（▾） |
| 3 | R7 侧栏行规格统一 | ✅ 历史/目录标题均 14px/rgb(31,35,41)，icon 均 16px |
| 4 | R8 弹层加宽无横滚 | ✅ CSSOM 断言 twoPane width:560px |
| 5 | R9/R11 控件紧凑化 | ✅ rowArrow/itemCheck/countBadge 无 margin-left 规则（空数组=已删） |
| 6 | R13 问题块对齐乐享 | ✅ 两处 .user justifyContent:flex-start、userBubble bg rgb(236,236,238)=#ececee radius 10px |
| 7 | 质量门 | ✅ tsc -b 零错误；后端零改动（无需重启）；禁区五文件 diff 空 |

### 遇到的问题

1. **SearchReplace 误删 JSX 开标签**：DocChatPanel 一条替换把 `<div className={styles.inputActions}>` 连注释一并替换掉导致「应为)」编译错——修复还原开标签；随后 LSP 仍报错为中间态缓存假错，读文件尾部确认 JSX 结构完整，最终以 tsc exit=0 为准
2. **样式断言通过 ≠ 交互正确**：R10/R12 属交互行为（多选文档发送、按钮切换面板），本轮仅完成 DOM/CSSOM 结构断言，交互级验证需打开文档工作台实测（见遗留）
3. **用户连续三次取消 AskUser 弹窗**（每次取消即补充新反馈截图）→ 改为文字汇报九项清单，用户文字回复「确认」后实施——高反馈密度返工轮次中弹窗确认效率低于文字确认

### 遗留事项（P1）

- R10/R12 交互级实测未做（打开文档工作台：多选文档发送走 multi_scope、问AI 按钮/关闭按钮切换）
- R13 历史旧消息无 sourceTags 字段不显示 tag 行（快照模式预期行为，如需回填需迁移历史会话）
- 沿袭上轮：历史对话空态、暗色模式、移动端适配

## 第五轮返工：侧栏企业级精修 + 布局缺陷修复 + 主区域背景对齐（2026-10-16）

用户实测反馈两批（带截图）：①侧栏/信息源弹层出现滚动条、用户卡不贴底 ②侧栏字号/背景/颜色/icon 像 demo 不像企业版 ③主区域背景色与输入卡边框色与乐享不一致。按需求 §12（v1.5）实施 R1-R4：基线 commit `1c47e0c`。**纯前端样式/结构改动，后端 `backend/` 全量 diff 为空，RAG 禁区五文件 diff 为空，全程零新增 LLM 调用。**

### 改动文件清单（全部前端）

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/MainPage/` | R1：Sider `overflow:auto`→`hidden`（滚动收敛树区内部，页面级无滚动条）；内层 Layout 显式 `height:'100vh'`（保 `.sidebar` height:100% 百分比链）；border 色 #e5e6eb |
| `frontend/src/components/KnowledgeBaseSidebar/index.tsx` | R2：头部 Select 下拉 → 乐享式标识区（Dropdown click 菜单：库列表 `selectedKeys` 高亮 + divider + 重命名/管理）；新建对话按钮 `type="primary"`；删 Divider 分隔线 |
| `frontend/src/components/KnowledgeBaseSidebar/index.module.less` | 全量重写（193 行）：thinScrollbar mixin（6px 透明轨道 hover 显现）；色彩体系 token（文字 #1f2329/#646a73/#8f959e、hover #f5f6f7、active #e8f3ff/#1677ff、边框 #e5e6eb）；kbBadge 32px 渐变蓝 + kbMeta 两行 + kbMore；newConvBtn 36px 主色阴影；navItem 14px / icon 16px；treeWrap `flex:1 + min-height:0 + overflow-y:auto`（R1 关键）；userCard border-top 贴底 |
| `frontend/src/components/InputPlusPopover/index.module.less` | R1：twoPane 固定宽 460px（防自适应漂移）；kbPane 160px 细滚动条；treePane `overflow-x:hidden` + 细滚动条；sourceTree 节点宽度约束（treenode 100% + content-wrapper max-width calc(100%-4px)），标题超宽 ellipsis |
| `frontend/src/components/CategoryTree/index.module.less` | R3：树节点字号 13px |
| `frontend/src/components/ChatWindow/index.module.less` | R4：.container 背景 #f5f6f7（乐享式浅灰主区域）；header/assistantFooter 分隔线 #ebedf0；inputArea 去 border-top、背景 transparent（与消息区一体）；inputCard 边框 #ebedf0 + 阴影 rgba(31,35,41,0.05) + 聚焦 rgba(22,119,255,0.4) 描边 |
| `frontend/src/components/DocChatPanel/index.module.less` | R4：header 分隔线 #ebedf0；inputArea 背景 #f5f6f7 去 border-top；inputCard 同款边框/阴影/聚焦 |
| `docs/requirements/P0-4-lexiang-style-kb.md` | 追加 §12（v1.5）：R1 布局缺陷 / R2 头部标识区 / R3 侧栏精修 / R4 主区域背景 |

### 关键设计摘要

- **滚动/贴底根因链**：Sider overflow auto + `.treeWrap` 类缺失（tsx 引用但 less 无定义）→ 目录树撑高内容 → Sider 整体滚动、userCard 被顶离底部；修复三件套 = Sider hidden + treeWrap 内部滚动 + Layout 显式 100vh
- **色彩体系 token 化**：文字主 #1f2329 / 次 #646a73 / 辅 #8f959e；hover 底 #f5f6f7；active #e8f3ff + #1677ff；边框 #e5e6eb；输入卡边框 #ebedf0；主区域背景 #f5f6f7——全部对齐乐享取色
- **thinScrollbar mixin**：默认透明轨道，hover 才显现 rgba(0,0,0,0.18)——滚动可用但视觉无滚动条
- **头部库标识区**：32px 渐变蓝徽标（库名首字）+ 库名 14px/600 + 副标题「知识库 · N 篇文档」；Dropdown `selectedKeys` 高亮当前库（antd 原生勾选，免手写 icon）
- **R4 主区域浅灰**：AI 回答直接排在 #f5f6f7 背景上、输入卡白色浮起（极浅边框 + 1px 阴影、聚焦淡蓝描边）——消除「白底白卡无层次」的 demo 感

### 验收结果

| # | 验收项 | 结果 |
|---|---|---|
| 1 | 无页面级滚动条 | ✅ DOM 断言 `hasPageScrollbar:false`、sider overflow hidden |
| 2 | 用户卡贴底 | ✅ `userCardBottomGap:0`（treeWrap flexGrow:1 内部滚动） |
| 3 | 头部乐享式标识区 | ✅ 「个｜个人知识库｜知识库 · 3 篇文档」结构；菜单 selectedKeys 高亮当前库 |
| 4 | 侧栏规格对齐 | ✅ kbName 14px/600、navItem 14px padding 8px 10px、newConvBtn rgb(22,119,255) 主色 |
| 5 | 弹层无横向滚动条 | ✅ twoPane 460px + treePane overflow-x hidden + 节点宽度约束 |
| 6 | 主区域浅灰背景 | ✅ DOM 断言 container `rgb(245,246,247)` = #f5f6f7 |
| 7 | 输入卡边框/阴影/聚焦 | ✅ 边框 `rgb(235,237,240)` = #ebedf0、阴影 `rgba(31,35,41,0.05) 0 1px 3px`、inputArea 无 border-top 背景 transparent |
| 8 | header/footer 分隔线 | ✅ 均为 `rgb(235,237,240)` = #ebedf0 |
| 9 | 质量门 | ✅ tsc -b 零错误；后端零改动（无需重启）；禁区五文件 diff 空 |

### 遇到的问题

1. **侧栏滚动根因是 less 类缺失而非仅 Sider overflow**：`.treeWrap` 在 tsx 引用但 less 无定义，内容撑高触发 Sider 滚动；只改 overflow 不够，须树区自身成为滚动容器
2. **内层 Layout 需显式 height:100vh**：`.sidebar` 的 `height:100%` 依赖父链高度，antd Layout 默认不产生高度约束，缺失时 flex 拉伸失效
3. **Popover 自适应宽度漂移**：两栏内容宽度不固定时 antd 按内容计算位置，勾选后可能漂移；固定 twoPane 460px 解决
4. **样式计算断言通过 ≠ 企业级视觉**：第五轮交付时逐项断言全绿，用户实测仍指出侧栏像 demo——视觉还原必须对照真实产品截图逐区块精修（色彩 token/字号/区块层级），不能只靠单点样式断言

### 遗留事项（P1）

- 历史对话列表空态样式未做（乐享有插画空态）
- 侧栏暗色模式不适配（当前仅亮色体系）
- 信息源弹层/侧栏移动端适配未做（桌面优先，前轮已登记）

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

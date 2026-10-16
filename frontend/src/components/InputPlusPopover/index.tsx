import React, { useEffect, useMemo, useState } from "react";
import {
  Popover,
  Segmented,
  Switch,
  Checkbox,
  Tree,
  Typography,
  Tooltip,
  Spin,
  Tag,
  message,
} from "antd";
import type { DataNode } from "antd/es/tree";
import {
  BulbOutlined,
  AppstoreOutlined,
  ApiOutlined,
  RightOutlined,
  GlobalOutlined,
  BankOutlined,
  FileTextOutlined,
  CheckOutlined,
  QuestionCircleOutlined,
  FolderFilled,
} from "@ant-design/icons";
import {
  knowledgeBaseApi,
  type KnowledgeBase,
  type TreeData,
  type CategoryInfo,
  type TreeNodeDocument,
} from "../../services/api";
import styles from "./index.module.less";

/** 文档级多选上限（与后端 chat_service.MAX_SCOPE_DOCS 一致，超出提示按库选） */
export const MAX_SCOPE_DOCS = 20;

/**
 * P0-4 第五轮（T6，§11）：输入区「+」弹层（乐享式两栏信息源），主聊天窗与文档问AI 面板共用。
 * 一级弹层：问答/Agent 模式 Segmented + 深度思考（映射 HyDE）+ 技能（置灰占位）+ 信息源入口；
 * 二级弹层：全网搜索开关（仅直聊）+ 知识范围——
 *   两栏模式（allowDocScope，默认）：左栏知识库列表（Checkbox 整库勾选 + 头像块 +「当前」标记 + 箭头
 *   进入右栏），右栏选中库的目录树（Checkbox 勾选目录/文档，目录勾选=其下全部文档递归展开）；
 *   单列模式（allowDocScope=false，DocChatPanel）：沿用第四轮「全部知识/当前文档/各库勾选」列表。
 * 信息源模型（对齐后端能力）：
 *   - docSelected「当前文档」：DocChatPanel 特例（document_id 单数轻流式，不落会话），与 kbIds/docIds 互斥
 *   - kbIds 整库范围与 docIds 文档范围可并存（后端 multi_scope 合并链，落会话；同库并存整库优先）
 *   - 全空 = 纯直聊（=原普通聊天）；「全部知识」= 一键勾所有库并清 docIds
 *   - 全网搜索仅直聊可用；深度思考仅单库检索可用（文档级/多范围/多库/Agent 禁用）
 */
export interface InputSourceValue {
  /** 勾选「当前文档」（仅 activeDoc 存在时有意义；与 kbIds/docIds 互斥） */
  docSelected: boolean;
  /** 整库范围（多选；与 docSelected 互斥） */
  kbIds: number[];
  /** 文档范围（目录勾选=前端展开的文档集合；与 kbIds 可并存=多范围合并链） */
  docIds: number[];
}

export const EMPTY_SOURCE: InputSourceValue = {
  docSelected: false,
  kbIds: [],
  docIds: [],
};

/**
 * P0-4 第五轮（T7）：placeholder 按信息源状态派生（ChatWindow/DocChatPanel 共用）。
 * 优先级：当前文档 > 指定知识（文档多选/多库）> 当前知识库 > 直聊。
 */
export function derivePlaceholder(source: InputSourceValue): string {
  if (source.docSelected) return "基于当前文档进行提问，shift+enter换行";
  if (source.docIds.length > 0 || source.kbIds.length > 1)
    return "基于指定知识进行提问，shift+enter换行";
  if (source.kbIds.length === 1) return "基于当前知识库进行提问，shift+enter换行";
  return "输入任何问题，shift+enter换行";
}

/** 收集目录下全部文档 id（含子目录递归）；categoryId=null 收集未归类（挂根）文档 */
function collectDocIdsUnder(
  categories: CategoryInfo[],
  documents: TreeNodeDocument[],
  categoryId: number
): number[] {
  const childrenOf = new Map<number, number[]>();
  for (const c of categories) {
    if (c.parent_id === null) continue;
    const arr = childrenOf.get(c.parent_id) ?? [];
    arr.push(c.id);
    childrenOf.set(c.parent_id, arr);
  }
  const catIds = new Set<number>();
  const stack = [categoryId];
  while (stack.length) {
    const cur = stack.pop()!;
    if (catIds.has(cur)) continue;
    catIds.add(cur);
    for (const child of childrenOf.get(cur) ?? []) stack.push(child);
  }
  return documents
    .filter((d) => d.category_id !== null && catIds.has(d.category_id))
    .map((d) => d.id);
}

/** 目录树节点：目录 key=cat-{id}（勾选时展开为文档集合），文档 key=doc-{id} */
interface SourceNode extends DataNode {
  key: string;
}

function buildSourceTree(tree: TreeData): SourceNode[] {
  const catMap = new Map<number, SourceNode>();
  const roots: SourceNode[] = [];
  for (const c of tree.categories) {
    catMap.set(c.id, {
      key: `cat-${c.id}`,
      title: (
        <span className={styles.treeCat}>
          <FolderFilled className={styles.folderIcon} />
          {c.name}
        </span>
      ),
      children: [],
    });
  }
  for (const c of tree.categories) {
    const node = catMap.get(c.id)!;
    const parent = c.parent_id === null ? null : catMap.get(c.parent_id);
    if (parent) parent.children!.push(node);
    else roots.push(node);
  }
  for (const d of tree.documents) {
    const docNode: SourceNode = {
      key: `doc-${d.id}`,
      title: <span className={styles.treeDoc}>{d.filename}</span>,
    };
    const parent = d.category_id === null ? null : catMap.get(d.category_id);
    if (parent) parent.children!.push(docNode);
    else roots.push(docNode);
  }
  return roots;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentMode: boolean;
  onAgentModeChange: (v: boolean) => void;
  /** 文档问AI 面板仅问答模式（隐藏 Segmented），默认展示 */
  showModeSegment?: boolean;
  source: InputSourceValue;
  onSourceChange: (v: InputSourceValue) => void;
  /** 当前打开的文档（有则展示「当前文档」信息源项） */
  activeDoc?: { id: number; name: string } | null;
  /** 当前选中知识库 id（左栏「当前」标记用，主聊天窗传入） */
  activeKbId?: number | null;
  /** 是否开放文档级多选（两栏目录树）；DocChatPanel 传 false 沿用单列模式 */
  allowDocScope?: boolean;
  useHyde: boolean;
  onHydeChange: (v: boolean) => void;
  useWebSearch: boolean;
  onWebSearchChange: (v: boolean) => void;
  children: React.ReactNode;
}

export default function InputPlusPopover({
  open,
  onOpenChange,
  agentMode,
  onAgentModeChange,
  showModeSegment = true,
  source,
  onSourceChange,
  activeDoc = null,
  activeKbId = null,
  allowDocScope = true,
  useHyde,
  onHydeChange,
  useWebSearch,
  onWebSearchChange,
  children,
}: Props) {
  const [allKbs, setAllKbs] = useState<KnowledgeBase[]>([]);
  const [loadingKbs, setLoadingKbs] = useState(false);
  // P0-4 第五轮（T6）：两栏目录树状态——右栏展示的库 + 已拉取的树缓存（docId→kbId 归属由此推导）
  const [treeKbId, setTreeKbId] = useState<number | null>(null);
  const [treeCache, setTreeCache] = useState<Record<number, TreeData>>({});
  const [loadingTree, setLoadingTree] = useState(false);

  // 打开弹层时懒加载知识库列表（避免冗余请求）
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingKbs(true);
    knowledgeBaseApi
      .list()
      .then(({ data }) => {
        if (!cancelled) setAllKbs(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoadingKbs(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // 进入右栏：拉取/复用该库目录树
  const handleEnterKb = async (kbId: number) => {
    setTreeKbId(kbId);
    if (treeCache[kbId]) return;
    setLoadingTree(true);
    try {
      const { data } = await knowledgeBaseApi.getTree(kbId);
      setTreeCache((prev) => ({ ...prev, [kbId]: data }));
    } catch {
      /* ignore：右栏展示空态 */
    } finally {
      setLoadingTree(false);
    }
  };

  const sourceCount =
    (source.docSelected ? 1 : 0) + source.kbIds.length + source.docIds.length;
  // 纯直聊：未勾任何信息源（=原普通聊天，全网搜索仅此模式可用）
  const directChat =
    !source.docSelected && source.kbIds.length === 0 && source.docIds.length === 0;
  // 深度思考（HyDE）仅单库检索可用：文档级/多范围/多库/Agent 均不支持
  const hydeDisabled =
    agentMode || source.docSelected || source.docIds.length > 0 || source.kbIds.length > 1;
  const allKbIds = allKbs.map((kb) => kb.id);
  const allSelected =
    !source.docSelected &&
    allKbIds.length > 0 &&
    source.kbIds.length === allKbIds.length;

  const handleToggleKb = (kbId: number, checked: boolean) => {
    const nextKbIds = checked
      ? [...source.kbIds, kbId]
      : source.kbIds.filter((id) => id !== kbId);
    // 整库勾选覆盖该库文档组（后端 multi_scope_retrieve 同库整库优先，这里同步清 UI 残留）
    const kbDocIds = new Set((treeCache[kbId]?.documents ?? []).map((d) => d.id));
    const nextDocIds = checked
      ? source.docIds.filter((id) => !kbDocIds.has(id))
      : source.docIds;
    onSourceChange({ docSelected: false, kbIds: nextKbIds, docIds: nextDocIds });
  };

  // 右栏目录树勾选：doc-* 直接收集，cat-* 展开为其下全部文档；跨库保留 + 上限 20
  // 返工 R22（v1.5 §12）：级联语义——全选该库全部文档 → 升级为整库勾选（kbIds 表达，无文档上限）；
  // 部分选择/清空 → 该库降级为文档级精确表达（从 kbIds 移除，docIds 承接）
  const handleTreeCheck = (
    kbId: number,
    checked: string[] | { checked: string[] }
  ) => {
    const keys = Array.isArray(checked) ? checked : checked.checked;
    const tree = treeCache[kbId];
    if (!tree) return;
    const docIdSet = new Set<number>();
    for (const key of keys) {
      if (key.startsWith("doc-")) {
        docIdSet.add(Number(key.slice(4)));
      } else if (key.startsWith("cat-")) {
        collectDocIdsUnder(tree.categories, tree.documents, Number(key.slice(4))).forEach(
          (id) => docIdSet.add(id)
        );
      }
    }
    const kbDocIds = new Set(tree.documents.map((d) => d.id));
    const otherKbDocIds = source.docIds.filter((id) => !kbDocIds.has(id));
    const allChecked =
      kbDocIds.size > 0 && [...kbDocIds].every((id) => docIdSet.has(id));
    if (allChecked) {
      const nextKbIds = source.kbIds.includes(kbId)
        ? source.kbIds
        : [...source.kbIds, kbId];
      onSourceChange({ docSelected: false, kbIds: nextKbIds, docIds: otherKbDocIds });
      return;
    }
    const nextKbIds = source.kbIds.filter((id) => id !== kbId);
    const merged = [...new Set([...otherKbDocIds, ...docIdSet])];
    if (merged.length > MAX_SCOPE_DOCS) {
      message.warning(`文档级多选最多 ${MAX_SCOPE_DOCS} 个，请勾选知识库整库检索`);
      return;
    }
    onSourceChange({ docSelected: false, kbIds: nextKbIds, docIds: merged });
  };

  // docId → kbId 归属（来自已缓存树），供右栏受控勾选态计算
  const docOwnerMap = useMemo(() => {
    const map = new Map<number, number>();
    for (const [kbId, tree] of Object.entries(treeCache)) {
      for (const d of tree.documents) map.set(d.id, Number(kbId));
    }
    return map;
  }, [treeCache]);

  const treeKb = allKbs.find((kb) => kb.id === treeKbId) ?? null;
  const sourceTreeData = useMemo(
    () => (treeKbId !== null && treeCache[treeKbId] ? buildSourceTree(treeCache[treeKbId]) : []),
    [treeKbId, treeCache]
  );
  // 该库受控勾选 keys：仅传 doc-*，目录全/半选态由 antd 按子节点自动推导
  // 返工 R22（v1.5 §12）：整库勾选 → 该库全部文档级联显示勾选（与左栏 checkbox 联动）
  const treeCheckedKeys = useMemo(() => {
    if (treeKbId === null) return [];
    if (source.kbIds.includes(treeKbId)) {
      return (treeCache[treeKbId]?.documents ?? []).map((d) => `doc-${d.id}`);
    }
    return source.docIds
      .filter((id) => docOwnerMap.get(id) === treeKbId)
      .map((id) => `doc-${id}`);
  }, [treeKbId, source.kbIds, source.docIds, docOwnerMap, treeCache]);

  // 返工 R22：左栏 KB checkbox 半选态（该库文档被部分勾选，未达整库）
  const kbPartial = (kbId: number) => {
    if (source.kbIds.includes(kbId)) return false;
    const docs = treeCache[kbId]?.documents ?? [];
    if (docs.length === 0) return false;
    const cnt = source.docIds.filter((id) => docs.some((d) => d.id === id)).length;
    return cnt > 0 && cnt < docs.length;
  };

  const kbName = (id: number) =>
    allKbs.find((kb) => kb.id === id)?.name ?? `知识库${id}`;

  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      trigger="click"
      placement="topLeft"
      arrow={false}
      content={
        <div className={styles.panel}>
          {showModeSegment && (
            <div className={styles.modeWrap}>
              <Segmented
                block
                value={agentMode ? "agent" : "qa"}
                options={[
                  { label: "问答模式", value: "qa" },
                  { label: "Agent模式", value: "agent" },
                ]}
                onChange={(v) => onAgentModeChange(v === "agent")}
              />
            </div>
          )}
          {!agentMode && (
            <Tooltip title={hydeDisabled ? "仅单库检索模式可用（文档级/多范围/多源/Agent 不支持）" : "检索前生成假想文档，加深召回（双倍 Token）"}>
              <div className={`${styles.row} ${hydeDisabled ? styles.rowDisabled : ""}`}>
                <BulbOutlined className={styles.rowIcon} />
                <span>深度思考</span>
                <Switch
                  size="small"
                  checked={useHyde}
                  disabled={hydeDisabled}
                  onChange={onHydeChange}
                />
              </div>
            </Tooltip>
          )}
          {agentMode && (
            <Tooltip title="技能体系规划中，敬请期待">
              <div className={`${styles.row} ${styles.rowDisabled}`}>
                <AppstoreOutlined className={styles.rowIcon} />
                <span>技能</span>
                <Tag style={{ marginRight: 0 }}>敬请期待</Tag>
              </div>
            </Tooltip>
          )}
          {/* 信息源入口：hover 展开二级（全网搜索 + 知识范围两栏/单列） */}
          <Popover
            trigger="hover"
            placement="rightTop"
            arrow={false}
            content={
              <div className={styles.sourcePanel}>
                <Tooltip title={directChat ? "" : "仅直聊（未选信息源）模式可用"}>
                  <div className={`${styles.sourceRow} ${directChat ? "" : styles.rowDisabled}`}>
                    <GlobalOutlined className={styles.rowIcon} />
                    <span>全网搜索</span>
                    <Switch
                      size="small"
                      checked={useWebSearch}
                      disabled={!directChat}
                      onChange={onWebSearchChange}
                    />
                  </div>
                </Tooltip>
                <div className={styles.sectionTitle}>
                  知识范围
                  <Tooltip title="勾选知识库整库检索；进入箭头可勾选目录/文档精确检索（最多 20 个文档）；全部清空则为直聊模式。">
                    <QuestionCircleOutlined className={styles.sectionHint} />
                  </Tooltip>
                </div>
                <div
                  className={styles.sourceItem}
                  onClick={() =>
                    onSourceChange({ docSelected: false, kbIds: allKbIds, docIds: [] })
                  }
                >
                  <BankOutlined className={styles.itemIcon} />
                  <span>全部知识</span>
                  {allSelected && <CheckOutlined className={styles.itemCheck} />}
                </div>
                {activeDoc && (
                  <div
                    className={styles.sourceItem}
                    onClick={() =>
                      onSourceChange({ docSelected: true, kbIds: [], docIds: [] })
                    }
                  >
                    <FileTextOutlined className={styles.itemIcon} />
                    <span className={styles.itemName} title={activeDoc.name}>
                      {activeDoc.name}
                    </span>
                    {source.docSelected && <CheckOutlined className={styles.itemCheck} />}
                  </div>
                )}
                {loadingKbs ? (
                  <Spin size="small" style={{ margin: "8px 12px" }} />
                ) : allowDocScope ? (
                  /* P0-4 第五轮（T6）：两栏（左库列表 + 右目录树），对齐乐享信息源选择器 */
                  <div className={styles.twoPane}>
                    <div className={styles.kbPane}>
                      {allKbs.map((kb) => (
                        <div
                          key={kb.id}
                          className={`${styles.kbRow} ${treeKbId === kb.id ? styles.kbRowActive : ""}`}
                          onClick={() => handleEnterKb(kb.id)}
                        >
                          <Checkbox
                            checked={source.kbIds.includes(kb.id)}
                            indeterminate={kbPartial(kb.id)}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => handleToggleKb(kb.id, e.target.checked)}
                          />
                          <span className={styles.kbAvatar}>{kb.name.slice(0, 1)}</span>
                          <span className={styles.kbRowName} title={kb.name}>
                            {kb.name}
                          </span>
                          {kb.id === activeKbId && (
                            <span className={styles.currentBadge}>当前</span>
                          )}
                          <RightOutlined className={styles.kbRowArrow} />
                        </div>
                      ))}
                    </div>
                    <div className={styles.treePane}>
                      {treeKbId === null ? (
                        <div className={styles.treePlaceholder}>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            点击右侧箭头查看知识库目录
                          </Typography.Text>
                        </div>
                      ) : loadingTree ? (
                        <div className={styles.treePlaceholder}>
                          <Spin size="small" />
                        </div>
                      ) : (
                        <>
                          <div className={styles.treeHeader} title={treeKb?.name}>
                            {treeKb?.name ?? `知识库${treeKbId}`}
                          </div>
                          <Tree
                            checkable
                            blockNode
                            defaultExpandAll
                            virtual={false}
                            className={styles.sourceTree}
                            treeData={sourceTreeData}
                            checkedKeys={treeCheckedKeys}
                            onCheck={(checked) =>
                              handleTreeCheck(
                                treeKbId,
                                checked as string[] | { checked: string[] }
                              )
                            }
                          />
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  /* 单列模式（DocChatPanel）：沿用第四轮库多选列表 */
                  <Checkbox.Group
                    className={styles.kbGroup}
                    value={source.kbIds}
                    onChange={(vals) =>
                      onSourceChange({ docSelected: source.docSelected, kbIds: vals as number[], docIds: [] })
                    }
                  >
                    {allKbs.map((kb) => (
                      <Checkbox key={kb.id} value={kb.id}>
                        <span className={styles.kbName}>{kb.name}</span>
                        <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 4 }}>
                          ({kb.document_count})
                        </Typography.Text>
                      </Checkbox>
                    ))}
                  </Checkbox.Group>
                )}
              </div>
            }
          >
            <div className={styles.row}>
              <ApiOutlined className={styles.rowIcon} />
              <span>信息源</span>
              {sourceCount > 0 && <span className={styles.countBadge}>{sourceCount}</span>}
              <RightOutlined className={styles.rowArrow} />
            </div>
          </Popover>
        </div>
      }
    >
      {children}
    </Popover>
  );
}

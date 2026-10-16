import React, { useEffect, useState } from "react";
import {
  Popover,
  Segmented,
  Switch,
  Checkbox,
  Typography,
  Tooltip,
  Spin,
  Tag,
} from "antd";
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
} from "@ant-design/icons";
import { knowledgeBaseApi, type KnowledgeBase } from "../../services/api";
import styles from "./index.module.less";

/**
 * P0-4 第四轮（T3）：输入区「+」弹层（乐享式），主聊天窗与文档问AI 面板共用。
 * 一级弹层：问答/Agent 模式 Segmented + 深度思考（映射 HyDE）+ 技能（置灰占位）+ 信息源入口；
 * 二级弹层（hover）：全网搜索开关 + 知识范围多选（全部知识 / 当前文档 / 各知识库）。
 * 信息源约束（对齐后端能力）：当前文档与知识库互斥（同选时后端 document_id 优先，UI 上强制互斥保证行为可预期）；
 * 勾选为空 = 纯直聊（=原普通聊天）；全网搜索仅直聊可用；深度思考仅单库检索可用（文档级/多库/Agent 禁用）。
 */
export interface InputSourceValue {
  /** 勾选「当前文档」（仅 activeDoc 存在时有意义；与 kbIds 互斥） */
  docSelected: boolean;
  /** 勾选的知识库（多选；与 docSelected 互斥） */
  kbIds: number[];
}

export const EMPTY_SOURCE: InputSourceValue = { docSelected: false, kbIds: [] };

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
  useHyde,
  onHydeChange,
  useWebSearch,
  onWebSearchChange,
  children,
}: Props) {
  const [allKbs, setAllKbs] = useState<KnowledgeBase[]>([]);
  const [loadingKbs, setLoadingKbs] = useState(false);

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

  const sourceCount = (source.docSelected ? 1 : 0) + source.kbIds.length;
  // 纯直聊：未勾任何信息源（=原普通聊天，全网搜索仅此模式可用）
  const directChat = !source.docSelected && source.kbIds.length === 0;
  // 深度思考（HyDE）仅单库检索可用：文档级链/多库合并/Agent 均不支持
  const hydeDisabled =
    agentMode || source.docSelected || source.kbIds.length > 1;
  const allKbIds = allKbs.map((kb) => kb.id);
  const allSelected = !source.docSelected && allKbIds.length > 0 && source.kbIds.length === allKbIds.length;

  const handleToggleKb = (kbId: number, checked: boolean) => {
    const next = checked
      ? [...source.kbIds, kbId]
      : source.kbIds.filter((id) => id !== kbId);
    onSourceChange({ docSelected: false, kbIds: next });
  };

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
            <Tooltip title={hydeDisabled ? "仅单库检索模式可用（文档级/多源/Agent 不支持）" : "检索前生成假想文档，加深召回（双倍 Token）"}>
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
          {/* 信息源入口：hover 展开二级（全网搜索 + 知识范围多选） */}
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
                  <Tooltip title="可多选；全部清空则为直聊模式。打开文档时默认基于当前文档提问。">
                    <QuestionCircleOutlined className={styles.sectionHint} />
                  </Tooltip>
                </div>
                <div
                  className={styles.sourceItem}
                  onClick={() => onSourceChange({ docSelected: false, kbIds: allKbIds })}
                >
                  <BankOutlined className={styles.itemIcon} />
                  <span>全部知识</span>
                  {allSelected && <CheckOutlined className={styles.itemCheck} />}
                </div>
                {activeDoc && (
                  <div
                    className={styles.sourceItem}
                    onClick={() => onSourceChange({ docSelected: true, kbIds: [] })}
                  >
                    <FileTextOutlined className={styles.itemIcon} />
                    <span className={styles.itemName} title={activeDoc.name}>
                      {activeDoc.name}
                    </span>
                    {source.docSelected && (
                      <CheckOutlined className={styles.itemCheck} />
                    )}
                  </div>
                )}
                {loadingKbs ? (
                  <Spin size="small" style={{ margin: "8px 12px" }} />
                ) : (
                  <Checkbox.Group
                    className={styles.kbGroup}
                    value={source.kbIds}
                    onChange={(vals) =>
                      onSourceChange({ docSelected: false, kbIds: vals as number[] })
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

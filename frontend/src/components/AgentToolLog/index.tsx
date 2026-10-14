import { useState } from "react";
import { Tag, Typography } from "antd";
import { ToolOutlined } from "@ant-design/icons";
import type { ToolTraceItem } from "../../services/api";
import styles from "./index.module.less";

// 状态 → 展示文案与颜色（与后端 _error_status 归类对齐）
const STATUS_META: Record<string, { color: string; text: string }> = {
  running: { color: "processing", text: "执行中" },
  success: { color: "success", text: "成功" },
  timeout: { color: "warning", text: "超时" },
  denied: { color: "error", text: "无权限" },
  not_found: { color: "error", text: "未找到" },
  validation: { color: "gold", text: "参数无效" },
  error: { color: "error", text: "出错" },
};

interface Props {
  items: ToolTraceItem[];
  /** 内嵌在流式气泡中时更紧凑且默认折叠 */
  compact?: boolean;
}

/**
 * P0-3a Agent 工具调用日志面板（最小展示：工具名 / 参数摘要 / 状态 / 耗时 / 轮次）
 * 完整可视化（参数详情展开 / 调用链 DAG / 历史持久化）归 P1
 */
export default function AgentToolLog({ items, compact = false }: Props) {
  const [expanded, setExpanded] = useState(!compact);
  if (items.length === 0) return null;

  return (
    <div className={styles.container} data-compact={compact || undefined}>
      <button
        type="button"
        className={styles.toggle}
        onClick={() => setExpanded(!expanded)}
      >
        <ToolOutlined style={{ marginRight: 4 }} />
        工具调用 {items.length} 次
        <span className={styles.arrow}>{expanded ? "▲" : "▼"}</span>
      </button>
      {expanded && (
        <ul className={styles.list}>
          {items.map((t, i) => {
            const meta = STATUS_META[t.status] ?? STATUS_META.error;
            return (
              <li key={i} className={styles.item}>
                <div className={styles.row}>
                  <Tag color={meta.color} style={{ marginRight: 6 }}>
                    {meta.text}
                  </Tag>
                  <Typography.Text code className={styles.name}>
                    {t.name}
                  </Typography.Text>
                  <span className={styles.meta}>第 {t.round} 轮</span>
                  {t.durationMs != null && (
                    <span className={styles.meta}>{t.durationMs}ms</span>
                  )}
                </div>
                {t.argsSummary && (
                  <div className={styles.args}>{t.argsSummary}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

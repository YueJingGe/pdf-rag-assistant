import React, { useEffect, useState } from "react";
import { Button, Tag, Typography, Space, Spin, message } from "antd";
import {
  SaveOutlined,
  FileMarkdownOutlined,
  FileTextOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import MDEditor from "@uiw/react-md-editor";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { documentApi } from "../../services/api";
import DocChatPanel from "../DocChatPanel";
import type { CitationClickInfo } from "../CitationView";
import styles from "./index.module.less";

interface Props {
  kbId: number;
  docId: number;
  filename: string;
  source: string;
  categoryName?: string;
  onSaved?: () => void;
  /** P0-4 第三轮（T7）：右侧问AI 面板引用点击 → 外层打开文档查看器 */
  onCitationClick?: (info: CitationClickInfo) => void;
}

/**
 * P0-4 文档工作台（第三轮 T7 两栏化）：
 * - 左栏正文：在线文档 MDEditor 编辑 + 手动保存（保存 = 覆盖 content 真相源 + 后端重建索引）；上传文档只读渲染
 * - 右栏 DocChatPanel：信息源默认当前文档（可切全部知识），本质就是问AI，可收起
 */
export default function DocumentWorkbench({
  kbId,
  docId,
  filename,
  source,
  categoryName,
  onSaved,
  onCitationClick,
}: Props) {
  const [content, setContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // P0-4 第三轮（T7）：右侧问AI 面板收起态（默认展开）
  const [chatCollapsed, setChatCollapsed] = useState(false);
  const isOnline = source === "online";
  const dirty = isOnline && content !== savedContent;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    documentApi
      .getContent(kbId, docId)
      .then(({ data }) => {
        if (!cancelled) {
          setContent(data.content);
          setSavedContent(data.content);
        }
      })
      .catch(() => {
        if (!cancelled) message.error("文档内容加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kbId, docId]);

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      await documentApi.saveContent(kbId, docId, content);
      setSavedContent(content);
      message.success("已保存并更新索引");
      onSaved?.();
    } catch (err: unknown) {
      const resp = (err as { response?: { status?: number; data?: { detail?: string } } })
        .response;
      if (resp?.status === 409) {
        message.error("文档未就绪（索引处理中），请稍后再试");
      } else {
        message.error(resp?.data?.detail || "保存失败");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.topbar}>
        <Space size={8} style={{ minWidth: 0 }}>
          {isOnline ? (
            <FileMarkdownOutlined style={{ color: "#52c41a", fontSize: 18 }} />
          ) : (
            <FileTextOutlined style={{ color: "#8c8c8c", fontSize: 18 }} />
          )}
          <Typography.Text strong ellipsis style={{ maxWidth: 320 }}>
            {filename}
          </Typography.Text>
          <Tag color={isOnline ? "green" : "blue"}>{isOnline ? "在线创作" : "上传文档"}</Tag>
          {categoryName && <Tag>{categoryName}</Tag>}
          {isOnline && dirty && <Tag color="orange">未保存</Tag>}
          {isOnline && !dirty && !loading && <Tag>已保存</Tag>}
        </Space>
        {isOnline && (
          <Button
            type="primary"
            size="small"
            icon={<SaveOutlined />}
            disabled={!dirty}
            loading={saving}
            onClick={handleSave}
          >
            保存
          </Button>
        )}
        <Button
          type={chatCollapsed ? "default" : "primary"}
          size="small"
          icon={<RobotOutlined />}
          onClick={() => setChatCollapsed(!chatCollapsed)}
        >
          {chatCollapsed ? "展开问AI" : "收起问AI"}
        </Button>
      </div>
      <div className={styles.body}>
        <div className={styles.contentPane}>
          {loading ? (
            <div className={styles.center}>
              <Spin />
            </div>
          ) : isOnline ? (
            <div data-color-mode="light" className={styles.editorWrap}>
              <MDEditor
                value={content}
                onChange={(v) => setContent(v ?? "")}
                preview="edit"
                visibleDragbar={false}
                height="100%"
              />
            </div>
          ) : (
            <div className={styles.readonly}>
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
                上传文档为只读模式；如需修改请下载后重新上传。
              </Typography.Text>
              <div className={styles.markdownContent}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
        {/* P0-4 第三轮（T7）：右侧问AI 面板（信息源默认当前文档，可切全部知识） */}
        {!chatCollapsed && (
          <div className={styles.chatPane}>
            <DocChatPanel
              kbId={kbId}
              docId={docId}
              docName={filename}
              onCitationClick={onCitationClick}
            />
          </div>
        )}
      </div>
    </div>
  );
}

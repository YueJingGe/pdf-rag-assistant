import React, { useEffect, useRef, useState } from "react";
import { Avatar, Button, Empty, Input, Segmented, Tooltip, Typography, message } from "antd";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  StopOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSSE } from "../../hooks/useSSE";
import CitationView, { type CitationClickInfo } from "../CitationView";
import type { Citation } from "../../services/api";
import styles from "./index.module.less";

interface MsgItem {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

interface Props {
  kbId: number;
  docId: number;
  docName: string;
  onCitationClick?: (info: CitationClickInfo) => void;
}

/**
 * P0-4 第三轮（T7）：文档右侧问AI 面板。
 * 修订口径：面板本质上就是问AI，无文档专用 UI——只是选中了某个文档后信息源默认为该文档；
 * 信息源两档（当前文档 / 全部知识），均走后端轻流式（不落会话，刷新即清）。
 */
export default function DocChatPanel({ kbId, docId, docName, onCitationClick }: Props) {
  const [scope, setScope] = useState<string>("doc"); // doc=当前文档 / all=全部知识
  const [messages, setMessages] = useState<MsgItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sse = useSSE();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sse.content]);

  // 切换文档/信息源 → 清空会话（轻流式本就不落会话，语义上开启新对话）
  useEffect(() => {
    setMessages([]);
    sse.setConversationId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId, scope]);

  // 流式结束后将 assistant 回复固化进消息列表（同 ChatWindow 收尾模式）
  useEffect(() => {
    if (!sse.loading && sse.content) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: sse.content,
          citations: sse.citations.length > 0 ? sse.citations : undefined,
        },
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sse.loading]);

  const handleSend = async () => {
    const question = inputValue.trim();
    if (!question || sse.loading) return;
    setInputValue("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    await sse.send({
      knowledgeBaseId: kbId,
      // 信息源=当前文档 → 后端 doc_scoped 轻流式；全部知识 → 不传 documentId（主链常规检索）
      documentId: scope === "doc" ? docId : undefined,
      question,
      useHyde: false, // 文档级链与多源语义下均不支持 HyDE
    });
  };

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <Typography.Text strong style={{ fontSize: 13 }}>
          问AI
        </Typography.Text>
        <Segmented
          size="small"
          value={scope}
          onChange={(v) => setScope(v as string)}
          options={[
            { label: "当前文档", value: "doc" },
            { label: "全部知识", value: "all" },
          ]}
        />
      </div>

      <div className={styles.messageList}>
        {messages.length === 0 && !sse.loading && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {scope === "doc"
                  ? `基于「${docName}」提问，试试：这篇文档讲了什么？`
                  : "已切换为全部知识，可跨库提问"}
              </Typography.Text>
            }
            style={{ marginTop: 48 }}
          />
        )}
        {messages.map((msg, idx) => (
          <div key={idx} className={`${styles.message} ${styles[msg.role]}`}>
            <Avatar
              size="small"
              icon={msg.role === "user" ? <UserOutlined /> : <RobotOutlined />}
              style={{
                backgroundColor: msg.role === "user" ? "#1677ff" : "#52c41a",
                flexShrink: 0,
              }}
            />
            <div className={styles.bubble}>
              <div className={styles.markdownContent}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
              {msg.citations && (
                <CitationView
                  citations={msg.citations}
                  onCitationClick={onCitationClick}
                />
              )}
            </div>
          </div>
        ))}
        {sse.loading && (
          <div className={`${styles.message} ${styles.assistant}`}>
            <Avatar
              size="small"
              icon={<RobotOutlined />}
              style={{ backgroundColor: "#52c41a", flexShrink: 0 }}
            />
            <div className={styles.bubble}>
              {sse.content ? (
                <div className={styles.markdownContent}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{sse.content}</ReactMarkdown>
                </div>
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  检索中…
                </Typography.Text>
              )}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className={styles.inputRow}>
        <Input.TextArea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={
            scope === "doc" ? "针对当前文档提问…" : "跨全部知识提问…"
          }
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={sse.loading}
          className={styles.input}
        />
        {sse.loading ? (
          <Tooltip title="停止">
            <Button icon={<StopOutlined />} danger size="small" onClick={sse.abort} />
          </Tooltip>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            size="small"
            shape="circle"
            disabled={!inputValue.trim()}
            onClick={handleSend}
          />
        )}
      </div>
      {sse.error && (
        <Typography.Text type="danger" style={{ fontSize: 12, padding: "0 4px" }}>
          {sse.error}
        </Typography.Text>
      )}
    </div>
  );
}

import React, { useEffect, useRef, useState } from "react";
import { Avatar, Button, Empty, Input, Tag, Tooltip, Typography } from "antd";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  StopOutlined,
  PlusOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSSE } from "../../hooks/useSSE";
import CitationView, { type CitationClickInfo } from "../CitationView";
import InputPlusPopover, { type InputSourceValue } from "../InputPlusPopover";
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
 * 第四轮（T6）乐享化改造：顶部仅「问AI」标题；右上角 Segmented 移除，
 * 信息源交互收敛到底部输入区「+」弹层（InputPlusPopover 公共组件，与主聊天同构）——
 * 默认信息源=当前文档（tag 展示），可切全部知识/各知识库（多选），清空=纯直聊。
 * 均走后端轻流式（不落会话，刷新即清）；文档面板仅问答模式（Agent 不进入）。
 */
export default function DocChatPanel({ kbId, docId, docName, onCitationClick }: Props) {
  // P0-4 第四轮（T6）：信息源状态与主聊天同构；打开文档时默认勾选「当前文档」
  const [source, setSource] = useState<InputSourceValue>({
    docSelected: true,
    kbIds: [],
  });
  const [useHyde, setUseHyde] = useState(false);
  const [useWebSearch, setUseWebSearch] = useState(false);
  const [messages, setMessages] = useState<MsgItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [composeOpen, setComposeOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sse = useSSE();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sse.content]);

  // 切换文档/信息源 → 清空会话（轻流式本就不落会话，语义上开启新对话）；换文档时重置默认勾选当前文档
  useEffect(() => {
    setMessages([]);
    sse.setConversationId(null);
    setSource({ docSelected: true, kbIds: [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  // 信息源变化 → 清空会话（docId 变化由上面分支处理）
  useEffect(() => {
    setMessages([]);
    sse.setConversationId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source.docSelected, source.kbIds]);

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
      // P0-4 第四轮（T6）：当前文档 → doc_scoped 轻流式；勾选库（可多选）→ 库检索链；清空 → 纯直聊
      knowledgeBaseId: source.docSelected ? kbId : source.kbIds[0] ?? null,
      knowledgeBaseIds: !source.docSelected && source.kbIds.length > 1 ? source.kbIds : undefined,
      documentId: source.docSelected ? docId : undefined,
      question,
      useHyde: !source.docSelected && source.kbIds.length <= 1 ? useHyde : false,
      webSearch: useWebSearch,
    });
  };

  return (
    <div className={styles.panel}>
      {/* P0-4 第四轮（T6）：顶部仅「问AI」（信息源交互移输入区；收起按钮在工作台顶栏） */}
      <div className={styles.header}>
        <Typography.Text strong style={{ fontSize: 13 }}>
          问AI
        </Typography.Text>
      </div>

      <div className={styles.messageList}>
        {messages.length === 0 && !sse.loading && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {source.docSelected
                  ? `基于「${docName}」提问，试试：这篇文档讲了什么？`
                  : "已切换为知识范围检索，可跨库提问"}
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

      <div className={styles.inputArea}>
        {/* P0-4 第四轮（T6）：信息源 tags（默认当前文档；× 可移除，清空=直聊） */}
        {(source.docSelected || source.kbIds.length > 0) && (
          <div className={styles.sourceTags}>
            {source.docSelected && (
              <Tag
                closable
                onClose={() => setSource({ ...source, docSelected: false })}
                style={{ marginRight: 0 }}
              >
                <FileTextOutlined /> {docName}
              </Tag>
            )}
            {source.kbIds.map((id) => (
              <Tag
                key={id}
                closable
                onClose={() =>
                  setSource({ ...source, kbIds: source.kbIds.filter((x) => x !== id) })
                }
                style={{ marginRight: 0 }}
              >
                知识库{id}
              </Tag>
            ))}
          </div>
        )}
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
              source.docSelected
                ? "针对当前文档提问…"
                : source.kbIds.length > 0
                ? "跨所选知识范围提问…"
                : "直聊模式，输入问题…"
            }
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={sse.loading}
            className={styles.input}
          />
          <div className={styles.inputActions}>
            <InputPlusPopover
              open={composeOpen}
              onOpenChange={setComposeOpen}
              agentMode={false}
              onAgentModeChange={() => undefined}
              showModeSegment={false}
              source={source}
              onSourceChange={setSource}
              activeDoc={{ id: docId, name: docName }}
              useHyde={useHyde}
              onHydeChange={setUseHyde}
              useWebSearch={useWebSearch}
              onWebSearchChange={setUseWebSearch}
            >
              <Tooltip title="信息源与深度思考">
                <Button icon={<PlusOutlined />} size="small" type="text" disabled={sse.loading} />
              </Tooltip>
            </InputPlusPopover>
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
        </div>
        <Typography.Text
          type="secondary"
          style={{ fontSize: 11, textAlign: "center", display: "block", padding: "2px 0 0" }}
        >
          回答内容均由AI生成，仅供参考
        </Typography.Text>
        {sse.error && (
          <Typography.Text type="danger" style={{ fontSize: 12, padding: "0 4px" }}>
            {sse.error}
          </Typography.Text>
        )}
      </div>
    </div>
  );
}

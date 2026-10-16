import React, { useEffect, useRef, useState } from "react";
import { Button, Empty, Input, Spin, Tag, Tooltip, Typography } from "antd";
import {
  SendOutlined,
  StopOutlined,
  PlusOutlined,
  FileTextOutlined,
  CloseOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSSE } from "../../hooks/useSSE";
import CitationView, { type CitationClickInfo } from "../CitationView";
import InputPlusPopover, {
  derivePlaceholder,
  type InputSourceValue,
} from "../InputPlusPopover";
import type { Citation } from "../../services/api";
import styles from "./index.module.less";

interface MsgItem {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  sourceTags?: string[]; // 返工 R13：发送时信息源快照（问题块首行 tag）
}

interface Props {
  kbId: number;
  docId: number;
  docName: string;
  onCitationClick?: (info: CitationClickInfo) => void;
  /** 返工 R12（v1.5 §12）：面板 header 右上角「关闭」→ 父级收起面板（展开态顶栏不再放按钮，对齐乐享） */
  onCollapse?: () => void;
}

/**
 * P0-4 第三轮（T7）：文档右侧问AI 面板。
 * 第四轮（T6）乐享化改造：顶部仅「问AI」标题；右上角 Segmented 移除，
 * 信息源交互收敛到底部输入区「+」弹层（InputPlusPopover 公共组件，与主聊天同构）——
 * 默认信息源=当前文档（tag 展示），可切全部知识/各知识库（多选），清空=纯直聊。
 * 均走后端轻流式（不落会话，刷新即清）；文档面板仅问答模式（Agent 不进入）。
 * 第五轮（T4/T5/T7）：消息形态与输入区布局对齐主聊天（用户右气泡/AI 左纯文本、
 * 圆角输入容器 + 左下「+」右下圆形发送）；placeholder 用 derivePlaceholder 统一四态。
 * 返工 R10（v1.5 §12）：放开文档级多选（allowDocScope 默认 true，与主聊天同构）——
 * docIds 非空走 documentIds 多范围合并链（useSSE 已支持，后端零改动）；当前文档轻流式与 docIds/kbIds 互斥不变。
 * 返工 R13：用户提问改乐享式浅灰块（首行来源 tag + 问题文字），与主聊天一致。
 */
export default function DocChatPanel({ kbId, docId, docName, onCitationClick, onCollapse }: Props) {
  // P0-4 第四轮（T6）：信息源状态与主聊天同构；打开文档时默认勾选「当前文档」
  const [source, setSource] = useState<InputSourceValue>({
    docSelected: true,
    kbIds: [],
    docIds: [],
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
    setSource({ docSelected: true, kbIds: [], docIds: [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  // 信息源变化 → 清空会话（docId 变化由上面分支处理）
  useEffect(() => {
    setMessages([]);
    sse.setConversationId(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source.docSelected, source.kbIds, source.docIds]);

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

  // 返工 R13：信息源快照（DocChatPanel 无库列表，库名用「知识库N」兜底，与侧栏 tags 行一致）
  const sourceTagNames = (): string[] => {
    const names: string[] = [];
    if (source.docSelected) names.push(docName);
    source.kbIds.forEach((id) => names.push(`知识库${id}`));
    if (source.docIds.length > 0) names.push(`${source.docIds.length} 个文档`);
    return names;
  };

  const handleSend = async () => {
    const question = inputValue.trim();
    if (!question || sse.loading) return;
    setInputValue("");
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: question,
        sourceTags: sourceTagNames(),
      },
    ]);
    await sse.send({
      // 返工 R10：当前文档 → doc_scoped 轻流式；docIds → multi_scope 合并链；勾选库（可多选）→ 库检索链；清空 → 纯直聊
      knowledgeBaseId: source.docSelected ? kbId : source.kbIds[0] ?? null,
      knowledgeBaseIds: !source.docSelected && source.kbIds.length > 1 ? source.kbIds : undefined,
      documentId: source.docSelected ? docId : undefined,
      documentIds: !source.docSelected && source.docIds.length > 0 ? source.docIds : undefined,
      question,
      useHyde:
        !source.docSelected && source.kbIds.length <= 1 && source.docIds.length === 0
          ? useHyde
          : false,
      webSearch: useWebSearch,
    });
  };

  return (
    <div className={styles.panel}>
      {/* 返工 R12（v1.5 §12）：header 右上角「关闭」收起面板（对齐乐享：展开态收起入口在面板内） */}
      <div className={styles.header}>
        <Typography.Text strong style={{ fontSize: 13 }}>
          问AI
        </Typography.Text>
        {onCollapse && (
          <Tooltip title="关闭">
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={onCollapse} />
          </Tooltip>
        )}
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
        {/* P0-4 第五轮（T4）：与主聊天同款消息形态——用户右侧气泡、AI 左侧纯文本 */}
        {messages.map((msg, idx) => (
          <div key={idx} className={`${styles.message} ${styles[msg.role]}`}>
            {msg.role === "assistant" ? (
              <div className={styles.assistantBody}>
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
            ) : (
              /* 返工 R13：乐享式问题块（首行来源 tag + 问题文字），与主聊天一致 */
              <div className={styles.userBubble}>
                {msg.sourceTags && msg.sourceTags.length > 0 && (
                  <div className={styles.userBubbleTags}>
                    {msg.sourceTags.map((t, i) => (
                      <span key={i} className={styles.userBubbleTag}>
                        {t}
                      </span>
                    ))}
                  </div>
                )}
                <Typography.Text style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>
                  {msg.content}
                </Typography.Text>
              </div>
            )}
          </div>
        ))}
        {sse.loading && (
          <div className={`${styles.message} ${styles.assistant}`}>
            <div className={styles.assistantBody}>
              {sse.content ? (
                <div className={styles.markdownContent}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{sse.content}</ReactMarkdown>
                </div>
              ) : (
                <Spin size="small" />
              )}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className={styles.inputArea}>
        {/* P0-4 第五轮（T5）：圆角输入容器（与主聊天同款：tags→无边框输入→左下「+」右下圆形发送） */}
        <div className={styles.inputCard}>
        {/* P0-4 第四轮（T6）：信息源 tags（默认当前文档；× 可移除，清空=直聊）；返工 R10 加 docIds 聚合 tag */}
        {(source.docSelected || source.kbIds.length > 0 || source.docIds.length > 0) && (
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
            {source.docIds.length > 0 && (
              <Tag
                closable
                onClose={() => setSource({ ...source, docIds: [] })}
                style={{ marginRight: 0 }}
              >
                <FileTextOutlined /> {source.docIds.length} 个文档
              </Tag>
            )}
          </div>
        )}
        <Input.TextArea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={derivePlaceholder(source)}
          autoSize={{ minRows: 2, maxRows: 6 }}
          disabled={sse.loading}
          className={styles.input}
        />
        <div className={styles.inputActions}>
          {/* 返工 R10（v1.5 §12）：放开文档级多选（allowDocScope 默认 true，与主聊天同构；docIds 走 multi_scope） */}
          <div className={styles.inputActionsLeft}>
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
          </div>
          {sse.loading ? (
            <Tooltip title="停止生成">
              <Button icon={<StopOutlined />} danger size="small" shape="circle" onClick={sse.abort} />
            </Tooltip>
          ) : (
            <Tooltip title="发送（Enter）">
              <Button
                type="primary"
                icon={<SendOutlined />}
                size="small"
                shape="circle"
                disabled={!inputValue.trim()}
                onClick={handleSend}
              />
            </Tooltip>
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

import React, { useState, useRef, useEffect } from "react";
import {
  Input,
  Button,
  Typography,
  Spin,
  Empty,
  Avatar,
  Switch,
  Tooltip,
  Space,
  Card,
  Dropdown,
  Popconfirm,
  message,
} from "antd";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  StopOutlined,
  ExperimentOutlined,
  BulbOutlined,
  PlusOutlined,
  HistoryOutlined,
  DeleteOutlined,
  PictureOutlined,
  FileOutlined,
  CloseCircleFilled,
  CopyOutlined,
  LoadingOutlined,
  PaperClipOutlined,
} from "@ant-design/icons";
import type { MenuProps } from "antd";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSSE } from "../../hooks/useSSE";
import CitationView, { type CitationClickInfo } from "../CitationView";
import RetrievalDebugPanel from "../RetrievalDebugPanel";
import {
  chatApi,
  type Citation,
  type RetrievalDebug,
  type ConversationInfo,
} from "../../services/api";
import styles from "./index.module.less";

const RAG_PROMPT_SUGGESTIONS = [
  "这篇文档的主要内容是什么？",
  "帮我总结一下文档中的关键要点",
  "文档中提到了哪些重要概念？",
  "请根据文档内容回答：核心结论是什么？",
];

const PLAIN_PROMPT_SUGGESTIONS = [
  "帮我解释一下什么是机器学习",
  "写一段 Python 快速排序代码",
  "今天心情不好，给我讲个笑话吧",
  "帮我翻译：Hello, how are you?",
];

interface PendingFile {
  filename: string;
  content: string; // extracted text from Zhipu API
  uploading?: boolean;
}

interface MessageItem {
  role: "user" | "assistant";
  content: string;
  images?: string[];
  fileName?: string; // attached file name for display
  citations?: Citation[];
  retrievalDebug?: RetrievalDebug | null;
}

interface Props {
  knowledgeBaseId: number | null | undefined;
  knowledgeBaseName: string;
  userRole?: string;
  onCitationClick?: (info: CitationClickInfo) => void;
}

/**
 * 对话框
 * 普通对话：isPlainChat 为 true，正常发送；隐藏 HyDE/调试按钮；提示语为通用聊天建议
 * @param param0
 * @returns
 */
export default function ChatWindow({
  knowledgeBaseId,
  knowledgeBaseName,
  userRole,
  onCitationClick,
}: Props) {
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [useHyde, setUseHyde] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const docInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sse = useSSE();

  const effectiveKbId = knowledgeBaseId ?? 0; // 普通聊天用 0 作为 kb_id

  const loadConversations = async () => {
    try {
      const { data } = await chatApi.listConversations(effectiveKbId);
      setConversations(data);
    } catch {
      /* ignore */
    }
  };

  const switchConversation = async (convId: number) => {
    try {
      const { data: msgs } = await chatApi.getMessages(convId);
      const restored: MessageItem[] = msgs.map((m) => ({
        role: m.role,
        content: m.content,
        images: m.images || undefined,
        fileName: m.file_name || undefined,
        citations: m.citations || undefined,
      }));
      setMessages(restored);
      sse.setConversationId(convId);
    } catch {
      /* ignore */
    }
  };

  const deleteConversation = async (convId: number) => {
    await chatApi.deleteConversation(convId);
    message.success("对话已删除");
    if (sse.conversationId === convId) {
      setMessages([]);
      sse.setConversationId(null);
    }
    loadConversations();
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages, sse.content]);

  // Persist conversationId to localStorage
  useEffect(() => {
    if (sse.conversationId) {
      localStorage.setItem(`conv_${effectiveKbId}`, String(sse.conversationId));
    }
  }, [sse.conversationId, effectiveKbId]);

  useEffect(() => {
    setMessages([]);
    setConversations([]);

    const loadHistory = async () => {
      setHistoryLoading(true);
      try {
        const { data: convs } = await chatApi.listConversations(effectiveKbId);
        setConversations(convs);

        // Try to restore the last conversation for this KB
        const savedConvId = localStorage.getItem(`conv_${effectiveKbId}`);
        const targetConvId = savedConvId
          ? Number(savedConvId)
          : convs.length > 0
          ? convs[0].id
          : null;
        const targetConv = targetConvId
          ? convs.find((c) => c.id === targetConvId)
          : null;

        if (targetConv) {
          const { data: msgs } = await chatApi.getMessages(targetConv.id);
          const restored: MessageItem[] = msgs.map((m) => ({
            role: m.role,
            content: m.content,
            images: m.images || undefined,
            fileName: m.file_name || undefined,
            citations: m.citations || undefined,
          }));
          setMessages(restored);
          sse.setConversationId(targetConv.id);
        } else if (convs.length > 0) {
          const { data: msgs } = await chatApi.getMessages(convs[0].id);
          const restored: MessageItem[] = msgs.map((m) => ({
            role: m.role,
            content: m.content,
            images: m.images || undefined,
            fileName: m.file_name || undefined,
            citations: m.citations || undefined,
          }));
          setMessages(restored);
          sse.setConversationId(convs[0].id);
        }
      } catch {
        // silently fail - just start fresh
      } finally {
        setHistoryLoading(false);
      }
    };
    loadHistory();
  }, [effectiveKbId]);

  const handleImageSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      if (!file.type.startsWith("image/")) {
        message.warning("仅支持图片文件");
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        message.warning("图片大小不能超过 10MB");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const dataUri = reader.result as string;
        setPendingImages((prev) => [...prev, dataUri]);
      };
      reader.readAsDataURL(file);
    });
    // Reset input so same file can be selected again
    e.target.value = "";
  };

  const removePendingImage = (index: number) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== index));
  };

  const handleDocSelect = () => {
    docInputRef.current?.click();
  };

  const handleDocChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    if (file.size > 50 * 1024 * 1024) {
      message.warning("文件大小不能超过 50MB");
      return;
    }

    setPendingFile({ filename: file.name, content: "", uploading: true });

    try {
      const { data } = await chatApi.uploadFile(file);
      setPendingFile({ filename: data.filename, content: data.content });
    } catch (err: unknown) {
      message.error("文件上传失败：" + ((err as Error).message || "未知错误"));
      setPendingFile(null);
    }
  };

  const handleSend = async () => {
    const question = inputValue.trim();
    if (!question || sse.loading) return;

    const imagesToSend = [...pendingImages];
    const fileToSend = pendingFile;
    setInputValue("");
    setPendingImages([]);
    setPendingFile(null);

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: question,
        images: imagesToSend.length > 0 ? imagesToSend : undefined,
        fileName: fileToSend?.filename,
      },
    ]);

    await sse.send({
      knowledgeBaseId: knowledgeBaseId ?? null,
      question,
      conversationId: sse.conversationId ?? undefined,
      useHyde,
      images: imagesToSend.length > 0 ? imagesToSend : undefined,
      fileContent: fileToSend?.content,
      fileName: fileToSend?.filename,
    });
  };

  useEffect(() => {
    if (!sse.loading && sse.content) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: sse.content,
          citations: sse.citations,
          retrievalDebug: sse.retrievalDebug,
        },
      ]);
    }
  }, [sse.loading]);

  const isPlainChat = !knowledgeBaseId;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          <RobotOutlined style={{ marginRight: 8 }} />
          {isPlainChat ? "普通聊天" : knowledgeBaseName || "智能问答"}
        </Typography.Title>
        <Space>
          <Tooltip title="新建对话（清除上下文，节省 Token）">
            <Button
              icon={<PlusOutlined />}
              size="small"
              onClick={() => {
                setMessages([]);
                sse.setConversationId(null);
              }}
              disabled={sse.loading || messages.length === 0}
            >
              新对话
            </Button>
          </Tooltip>
          <Dropdown
            trigger={["click"]}
            onOpenChange={(open) => {
              if (open) loadConversations();
            }}
            menu={{
              items:
                conversations.length === 0
                  ? [{ key: "empty", label: "暂无历史对话", disabled: true }]
                  : (conversations.map((conv) => ({
                      key: conv.id,
                      label: (
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            minWidth: 180,
                          }}
                        >
                          <span
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              maxWidth: 150,
                              fontWeight:
                                conv.id === sse.conversationId ? 600 : 400,
                            }}
                          >
                            {conv.title}
                          </span>
                          <Popconfirm
                            title="删除此对话？"
                            onConfirm={(e) => {
                              e?.stopPropagation();
                              deleteConversation(conv.id);
                            }}
                          >
                            <DeleteOutlined
                              style={{ color: "#ff4d4f", marginLeft: 8 }}
                              onClick={(e) => e.stopPropagation()}
                            />
                          </Popconfirm>
                        </div>
                      ),
                    })) as MenuProps["items"]),
              onClick: ({ key }) => {
                if (key !== "empty") switchConversation(Number(key));
              },
            }}
          >
            <Tooltip title="历史对话">
              <Button icon={<HistoryOutlined />} size="small">
                历史
              </Button>
            </Tooltip>
          </Dropdown>
          {!isPlainChat && (
            <Tooltip title="HyDE 假想文档检索（实验性，双倍Token）">
              <Switch
                checkedChildren="HyDE"
                unCheckedChildren="标准"
                checked={useHyde}
                onChange={setUseHyde}
                size="small"
              />
            </Tooltip>
          )}
          {!isPlainChat && (
            <Tooltip title="显示检索调试信息">
              <Button
                type={showDebug ? "primary" : "default"}
                icon={<ExperimentOutlined />}
                size="small"
                onClick={() => setShowDebug(!showDebug)}
              />
            </Tooltip>
          )}
        </Space>
      </div>

      <div className={styles.messageList}>
        {messages.length === 0 && (
          <div className={styles.promptGuide}>
            <BulbOutlined
              style={{ fontSize: 32, color: "#1677ff", marginBottom: 12 }}
            />
            <Typography.Text
              type="secondary"
              style={{ marginBottom: 16, display: "block" }}
            >
              {knowledgeBaseId
                ? "基于知识库问答，试试这样提问："
                : "当前为普通聊天模式，可以问我任何问题："}
            </Typography.Text>
            <div className={styles.promptCards}>
              {(knowledgeBaseId
                ? RAG_PROMPT_SUGGESTIONS
                : PLAIN_PROMPT_SUGGESTIONS
              ).map((prompt, index) => (
                <Card
                  key={index}
                  size="small"
                  hoverable
                  className={styles.promptCard}
                  onClick={() => {
                    setInputValue(prompt);
                  }}
                >
                  <Typography.Text>{prompt}</Typography.Text>
                </Card>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, index) => (
          <div key={index} className={`${styles.message} ${styles[msg.role]}`}>
            <Avatar
              size="small"
              icon={msg.role === "user" ? <UserOutlined /> : <RobotOutlined />}
              style={{
                backgroundColor: msg.role === "user" ? "#1677ff" : "#52c41a",
                flexShrink: 0,
              }}
            />
            <div className={styles.bubble}>
              {msg.role === "assistant" ? (
                <>
                  <div className={styles.markdownContent}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                  {msg.citations && (
                    <CitationView
                      citations={msg.citations}
                      onCitationClick={onCitationClick}
                    />
                  )}
                  {showDebug && msg.retrievalDebug && (
                    <RetrievalDebugPanel
                      debug={msg.retrievalDebug}
                      knowledgeBaseId={knowledgeBaseId!}
                      question={messages[index - 1]?.content || ""}
                      messageId={index}
                    />
                  )}
                  <div className={styles.assistantFooter}>
                    <Typography.Text
                      type="secondary"
                      className={styles.aiDisclaimer}
                    >
                      本回答由 AI 生成，内容仅供参考，请仔细甄别。
                    </Typography.Text>
                    <Tooltip title="复制回答">
                      <Button
                        type="text"
                        size="small"
                        icon={<CopyOutlined />}
                        className={styles.copyBtn}
                        onClick={() => {
                          navigator.clipboard.writeText(msg.content);
                          message.success("已复制到剪贴板");
                        }}
                      />
                    </Tooltip>
                  </div>
                </>
              ) : (
                <>
                  <Typography.Text style={{ whiteSpace: "pre-wrap" }}>
                    {msg.content}
                  </Typography.Text>
                  {msg.fileName && (
                    <div className={styles.fileAttachment}>
                      <PaperClipOutlined style={{ marginRight: 6 }} />
                      <span>{msg.fileName}</span>
                    </div>
                  )}
                  {msg.images && msg.images.length > 0 && (
                    <div className={styles.userImageList}>
                      {msg.images.map((src, imgIdx) => (
                        <img
                          key={imgIdx}
                          src={src}
                          alt={`user-img-${imgIdx}`}
                          className={styles.userImage}
                        />
                      ))}
                    </div>
                  )}
                </>
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
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {sse.content}
                  </ReactMarkdown>
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
        {/* File preview strip */}
        {pendingFile && (
          <div className={styles.filePreviewStrip}>
            <div className={styles.filePreviewItem}>
              <FileOutlined style={{ marginRight: 6 }} />
              <span className={styles.filePreviewName}>
                {pendingFile.filename}
              </span>
              {pendingFile.uploading ? (
                <LoadingOutlined style={{ marginLeft: 8 }} />
              ) : (
                <CloseCircleFilled
                  className={styles.imageRemoveBtn}
                  onClick={() => setPendingFile(null)}
                />
              )}
            </div>
          </div>
        )}
        {/* Image preview strip */}
        {pendingImages.length > 0 && (
          <div className={styles.imagePreviewStrip}>
            {pendingImages.map((img, idx) => (
              <div key={idx} className={styles.imagePreviewItem}>
                <img src={img} alt={`preview-${idx}`} />
                <CloseCircleFilled
                  className={styles.imageRemoveBtn}
                  onClick={() => removePendingImage(idx)}
                />
              </div>
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
              isPlainChat
                ? "输入问题，可附带图片或文件进行多模态对话..."
                : "输入您的问题，按 Enter 发送，Shift+Enter 换行..."
            }
            autoSize={{ minRows: 3, maxRows: 6 }}
            disabled={sse.loading}
            className={styles.input}
          />
          <div className={styles.inputActions}>
            {isPlainChat && (
              <div className={styles.fileActions}>
                <Tooltip title="上传文件（PDF/Word/Excel等）">
                  <Button
                    icon={<PaperClipOutlined />}
                    onClick={handleDocSelect}
                    disabled={sse.loading || !!pendingFile}
                  />
                </Tooltip>
                <Tooltip title="上传图片（支持多张）">
                  <Button
                    icon={<PictureOutlined />}
                    onClick={handleImageSelect}
                    disabled={sse.loading}
                  />
                </Tooltip>
              </div>
            )}
            {sse.loading ? (
              <Button icon={<StopOutlined />} onClick={sse.abort} danger>
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={!inputValue.trim()}
              >
                发送
              </Button>
            )}
          </div>
        </div>
        <input
          ref={docInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.xls,.xlsx,.ppt,.pptx,.csv,.txt,.md,.py,.png,.jpg,.jpeg,.bmp,.gif"
          style={{ display: "none" }}
          onChange={handleDocChange}
        />
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
      </div>
    </div>
  );
}

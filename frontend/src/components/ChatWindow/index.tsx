import React, { useState, useRef, useEffect } from "react";
import {
  Input,
  Button,
  Typography,
  Spin,
  Avatar,
  Tooltip,
  Space,
  Select,
  Modal,
  TreeSelect,
  Tag,
  message,
} from "antd";
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  StopOutlined,
  ExperimentOutlined,
  SmileOutlined,
  PlusOutlined,
  PictureOutlined,
  FileOutlined,
  CloseCircleFilled,
  CopyOutlined,
  LoadingOutlined,
  PaperClipOutlined,
  FileTextOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSSE } from "../../hooks/useSSE";
import CitationView, { type CitationClickInfo } from "../CitationView";
import RetrievalDebugPanel from "../RetrievalDebugPanel";
import AgentToolLog from "../AgentToolLog";
import { buildCategorySelectTree } from "../CategoryTree";
import InputPlusPopover, { type InputSourceValue } from "../InputPlusPopover";
import {
  chatApi,
  knowledgeBaseApi,
  type Citation,
  type RetrievalDebug,
  type ToolTraceItem,
  type KnowledgeBase,
  type TreeData,
} from "../../services/api";
import styles from "./index.module.less";

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
  toolTraces?: ToolTraceItem[]; // P0-3a：Agent 工具调用轨迹（后端未持久化，历史恢复时无此数据）
}

interface Props {
  knowledgeBaseId: number | null | undefined;
  knowledgeBaseName: string;
  userRole?: string;
  onCitationClick?: (info: CitationClickInfo) => void;
  /** P0-4：消息存入知识库成功后通知外层刷新目录树 */
  onDocSavedToKb?: () => void;
}

/**
 * 对话框（P0-4 第四轮 T2 乐享化）：
 * 空态 = 乐享式欢迎页（笑脸 + 「今天从哪里开始?」），隐藏顶栏；
 * 有消息后显示顶栏（新对话/调试）+ 消息流 + 底部输入区。
 * 信息源/深度思考/联网搜索全部收进输入区「+」弹层（InputPlusPopover 公共组件）。
 */
export default function ChatWindow({
  knowledgeBaseId,
  knowledgeBaseName,
  userRole,
  onCitationClick,
  onDocSavedToKb,
}: Props) {
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [useHyde, setUseHyde] = useState(false);
  const [useWebSearch, setUseWebSearch] = useState(false);
  const [useAgentMode, setUseAgentMode] = useState(false); // P0-3a：Agent 模式开关（默认关，实验性入口；P0-4 第二轮入口移入「+」弹层）
  // P0-4 第四轮（T3）：信息源状态收敛为 InputSourceValue（当前文档与库互斥；勾选为空 = 纯直聊）
  const [source, setSource] = useState<InputSourceValue>({
    docSelected: false,
    kbIds: knowledgeBaseId ? [knowledgeBaseId] : [],
  });
  // 知识库列表（供信息源 tags 显示库名；打开弹层时刷新）
  const [allKbs, setAllKbs] = useState<KnowledgeBase[]>([]);
  const [composeOpen, setComposeOpen] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const docInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sse = useSSE();

  // P0-4：存为知识库文档（问答沉淀闭环）
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveContent, setSaveContent] = useState("");
  const [saveKbList, setSaveKbList] = useState<KnowledgeBase[]>([]);
  const [saveTargetKbId, setSaveTargetKbId] = useState<number | null>(null);
  const [saveCatId, setSaveCatId] = useState<number | null>(null);
  const [saveCatTree, setSaveCatTree] = useState<TreeData | null>(null);
  const [saveCatLoading, setSaveCatLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const effectiveKbId = knowledgeBaseId ?? 0; // 普通聊天用 0 作为 kb_id

  // P0-4：知识库列表加载（打开弹层时刷新，供信息源 tags 显示库名）
  const loadAllKbs = async () => {
    try {
      const { data } = await knowledgeBaseApi.list();
      setAllKbs(data);
    } catch {
      /* ignore */
    }
  };

  // P0-4 v1.2：会话切换改为由侧栏历史列表触发（p04:conv-switch 事件），本组件不再维护历史下拉
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

  // P0-4 v1.2：会话状态变化广播给侧栏历史列表（活跃高亮 + 列表刷新：新会话落库等场景）；
  // 删除会话入口已移至侧栏历史列表（删除当前会话时经 p04:conv-deleted 通知本组件清空）
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("p04:conv-active", { detail: sse.conversationId })
    );
    window.dispatchEvent(new CustomEvent("p04:conv-list-changed"));
  }, [sse.conversationId]);

  // P0-4 v1.2：监听侧栏历史列表联动（切换会话 / 删除的正是当前打开的会话）
  useEffect(() => {
    const onSwitch = (e: Event) =>
      switchConversation((e as CustomEvent<number>).detail);
    const onDeleted = (e: Event) => {
      const convId = (e as CustomEvent<number>).detail;
      if (sse.conversationId === convId) {
        setMessages([]);
        sse.setConversationId(null);
      }
    };
    window.addEventListener("p04:conv-switch", onSwitch);
    window.addEventListener("p04:conv-deleted", onDeleted);
    return () => {
      window.removeEventListener("p04:conv-switch", onSwitch);
      window.removeEventListener("p04:conv-deleted", onDeleted);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sse.conversationId]);

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
    // P0-4 第四轮：切换知识库时信息源重置为当前库
    setSource({ docSelected: false, kbIds: knowledgeBaseId ? [knowledgeBaseId] : [] });

    const loadHistory = async () => {
      setHistoryLoading(true);
      try {
        const { data: convs } = await chatApi.listConversations(effectiveKbId);

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
      // P0-4 第二轮：会话挂主信息源（第一个选中库）；Agent 模式仅作用主信息源（不传 ids）
      knowledgeBaseId: primaryKbId,
      knowledgeBaseIds: !useAgentMode && isMultiKb ? source.kbIds : undefined,
      question,
      conversationId: sse.conversationId ?? undefined,
      useHyde: isMultiKb ? false : useHyde, // 多库合并链不支持 HyDE（需求 §8.3）
      images: imagesToSend.length > 0 ? imagesToSend : undefined,
      fileContent: fileToSend?.content,
      fileName: fileToSend?.filename,
      webSearch: useWebSearch,
      useAgent: useAgentMode,
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
          toolTraces: sse.toolEvents.length > 0 ? sse.toolEvents : undefined,
        },
      ]);
    }
  }, [sse.loading]);

  // ---- P0-4：消息存为知识库文档 ----
  const loadSaveCats = async (kbId: number) => {
    setSaveCatLoading(true);
    try {
      const { data } = await knowledgeBaseApi.getTree(kbId);
      setSaveCatTree(data);
    } catch {
      setSaveCatTree(null);
    } finally {
      setSaveCatLoading(false);
    }
  };

  const handleOpenSaveModal = (content: string) => {
    if (!sse.conversationId) {
      message.warning("消息尚未持久化，请稍后再试");
      return;
    }
    setSaveContent(content);
    setSaveTargetKbId(knowledgeBaseId ?? null); // 默认当前 KB
    setSaveCatId(null);
    setSaveCatTree(null);
    setSaveModalOpen(true);
    if (knowledgeBaseId) loadSaveCats(knowledgeBaseId);
    knowledgeBaseApi
      .list()
      .then(({ data }) => setSaveKbList(data))
      .catch(() => setSaveKbList([]));
  };

  const handleSaveKbChange = (kbId: number) => {
    setSaveTargetKbId(kbId);
    setSaveCatId(null);
    setSaveCatTree(null);
    loadSaveCats(kbId);
  };

  const handleSaveMessage = async () => {
    if (!saveTargetKbId) {
      message.warning("请选择目标知识库");
      return;
    }
    if (!sse.conversationId) {
      message.error("消息尚未持久化，无法保存");
      return;
    }
    setSaving(true);
    try {
      // 消息 id 需向服务端解析：按内容匹配当前会话中最后一条相同内容的 assistant 消息
      const { data: msgs } = await chatApi.getMessages(sse.conversationId);
      const target = [...msgs]
        .reverse()
        .find((m) => m.role === "assistant" && m.content === saveContent);
      if (!target) {
        message.error("未能在服务端定位该消息，请刷新历史后重试");
        return;
      }
      await chatApi.saveMessageToKb(target.id, saveTargetKbId, saveCatId);
      message.success("已存入知识库，可在文档管理中查看");
      setSaveModalOpen(false);
      onDocSavedToKb?.();
    } catch (err: unknown) {
      const resp = (
        err as { response?: { status?: number; data?: { detail?: string } } }
      ).response;
      message.error(resp?.data?.detail || "存入失败，请稍后再试");
    } finally {
      setSaving(false);
    }
  };

  // P0-4 第四轮：信息源语义（勾选为空 = 纯直聊/原普通聊天；主聊天窗无文档信息源）
  const isPlainChat = source.kbIds.length === 0;
  const isMultiKb = source.kbIds.length > 1;
  const primaryKbId = source.kbIds[0] ?? null;
  // 乐享式空态：无消息且非加载中 → 欢迎页（隐藏顶栏与消息流空态）
  const isEmptyHome = messages.length === 0 && !sse.loading && !historyLoading;

  return (
    <div className={styles.container}>
      {/* P0-4 第四轮（T2）：空态（乐享欢迎页）不渲染顶栏；HyDE 开关已移入「+」弹层（深度思考） */}
      {!isEmptyHome && (
        <div className={styles.header}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            <RobotOutlined style={{ marginRight: 8 }} />
            {knowledgeBaseName || "问AI"}
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
            {!isPlainChat && !isMultiKb && (
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
      )}

      <div className={styles.messageList}>
        {isEmptyHome && (
          <div className={styles.emptyHome}>
            <SmileOutlined className={styles.emptyFace} />
            <div className={styles.emptyTitle}>今天从哪里开始?</div>
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
                  {msg.toolTraces && <AgentToolLog items={msg.toolTraces} compact />}
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
                    <Tooltip title="存为知识库文档">
                      <Button
                        type="text"
                        size="small"
                        icon={<SaveOutlined />}
                        className={styles.copyBtn}
                        onClick={() => handleOpenSaveModal(msg.content)}
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
              {sse.toolEvents.length > 0 && (
                <AgentToolLog items={sse.toolEvents} compact />
              )}
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
        {/* P0-4 第四轮（T3）：信息源 tags（乐享式，输入框上方；× 可移除，清空 = 直聊） */}
        {(source.docSelected || source.kbIds.length > 0) && (
          <div className={styles.inputToolbar} style={{ alignItems: "center" }}>
            {source.docSelected && (
              <Tag
                closable
                onClose={() => setSource({ ...source, docSelected: false })}
                style={{ marginRight: 0 }}
              >
                <FileTextOutlined /> 当前文档
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
                {/* allKbs 异步加载完成前用 knowledgeBaseName prop 兼底，避免首帧闪烁「知识库N」 */}
                {allKbs.find((k) => k.id === id)?.name ??
                  (id === knowledgeBaseId && knowledgeBaseName
                    ? knowledgeBaseName
                    : `知识库${id}`)}
              </Tag>
            ))}
            {useAgentMode && source.kbIds.length > 1 && (
              <Typography.Text type="warning" style={{ fontSize: 12 }}>
                Agent 模式仅检索主信息源
              </Typography.Text>
            )}
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
                ? "基于当前知识库进行提问，shift+enter换行"
                : isMultiKb
                ? `已选 ${source.kbIds.length} 个信息源，输入问题跨库检索...`
                : "输入您的问题，按 Enter 发送，Shift+Enter 换行..."
            }
            autoSize={{ minRows: 3, maxRows: 6 }}
            disabled={sse.loading}
            className={styles.input}
          />
          <div className={styles.inputActions}>
            {/* P0-4 第四轮（T3）：「+」弹层（乐享式公共组件）——模式切换/深度思考/信息源多选 */}
            <InputPlusPopover
              open={composeOpen}
              onOpenChange={(open) => {
                setComposeOpen(open);
                if (open) loadAllKbs();
              }}
              agentMode={useAgentMode}
              onAgentModeChange={setUseAgentMode}
              source={source}
              onSourceChange={setSource}
              useHyde={useHyde}
              onHydeChange={setUseHyde}
              useWebSearch={useWebSearch}
              onWebSearchChange={setUseWebSearch}
            >
              <Tooltip title="模式与信息源">
                <Button
                  icon={<PlusOutlined />}
                  size="small"
                  type="text"
                  disabled={sse.loading}
                />
              </Tooltip>
            </InputPlusPopover>
            {/* P0-4 第四轮：直聊（未选信息源）时的多模态上传入口 */}
            {isPlainChat && (
              <>
                <Tooltip title="上传文件（文档理解）">
                  <Button
                    icon={<PaperClipOutlined />}
                    size="small"
                    type="text"
                    onClick={handleDocSelect}
                    disabled={!!pendingFile || sse.loading}
                  />
                </Tooltip>
                <Tooltip title="上传图片（多模态）">
                  <Button
                    icon={<PictureOutlined />}
                    size="small"
                    type="text"
                    onClick={handleImageSelect}
                    disabled={sse.loading}
                  />
                </Tooltip>
              </>
            )}
            {sse.loading ? (
              <Button icon={<StopOutlined />} onClick={sse.abort} danger size="small">
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={handleSend}
                disabled={!inputValue.trim()}
                size="small"
                shape="circle"
              />
            )}
          </div>
        </div>
        {/* P0-4 第四轮（T2）：乐享式免责声明 */}
        <Typography.Text
          type="secondary"
          style={{ fontSize: 12, textAlign: "center", display: "block", padding: "4px 0 2px" }}
        >
          回答内容均由AI生成，仅供参考
        </Typography.Text>
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

      {/* P0-4：存为知识库文档弹窗 */}
      <Modal
        title="存为知识库文档"
        open={saveModalOpen}
        onOk={handleSaveMessage}
        onCancel={() => setSaveModalOpen(false)}
        confirmLoading={saving}
        okText="存入"
        destroyOnClose
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
              目标知识库
            </Typography.Text>
            <Select
              style={{ width: "100%" }}
              placeholder="选择知识库"
              value={saveTargetKbId ?? undefined}
              onChange={handleSaveKbChange}
              options={saveKbList.map((kb) => ({ value: kb.id, label: kb.name }))}
            />
          </div>
          <div>
            <Typography.Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
              目标目录（可选）
            </Typography.Text>
            <TreeSelect
              style={{ width: "100%" }}
              treeData={buildCategorySelectTree(saveCatTree?.categories ?? [])}
              value={saveCatId ?? undefined}
              onChange={(v) => setSaveCatId(v ?? null)}
              placeholder="不选则存入「未归类」"
              treeDefaultExpandAll
              loading={saveCatLoading}
              allowClear
            />
          </div>
          <Typography.Paragraph
            type="secondary"
            ellipsis={{ rows: 3, expandable: true, symbol: "展开" }}
            style={{ background: "#fafafa", padding: 8, borderRadius: 6, marginBottom: 0 }}
          >
            {saveContent}
          </Typography.Paragraph>
        </div>
      </Modal>
    </div>
  );
}

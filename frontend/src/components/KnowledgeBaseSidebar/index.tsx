import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Input,
  Modal,
  Form,
  Typography,
  Dropdown,
  Avatar,
  Tooltip,
  Popconfirm,
  message,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  UserOutlined,
  LogoutOutlined,
  MessageOutlined,
  CompassOutlined,
  HomeOutlined,
  SettingOutlined,
  ToolOutlined,
  HistoryOutlined,
  BarChartOutlined,
  RightOutlined,
  EllipsisOutlined,
} from "@ant-design/icons";
import CategoryTree, { type OpenableDoc } from "../CategoryTree";
import {
  knowledgeBaseApi,
  chatApi,
  type KnowledgeBase,
  type UserInfo,
  type ConversationInfo,
} from "../../services/api";
import styles from "./index.module.less";

interface Props {
  selectedId: number | null;
  onSelect: (kb: KnowledgeBase | null) => void;
  refreshKey?: number;
  user: UserInfo;
  onLogout: () => void;
  canManage: boolean;
  /** 导航「问AI」→ 主区域切回问答 tab */
  onGoChat: () => void;
  chatActive: boolean;
  /** P0-4 第四轮（T4）：管理员「检索调优」导航 → 主区域切检索调优视图 */
  onGoFeedback?: () => void;
  feedbackActive?: boolean;
  /** P0-4 第四轮（T5）：打开文档 id 透传目录树（选中态高亮+自动展开） */
  activeDocId?: number;
  treeRefreshKey?: number;
  onDocChanged?: () => void;
  onOpenDoc: (doc: OpenableDoc) => void;
  /** P0-4 第三轮：目录树点击目录 → 主区域打开目录视图 tab */
  onOpenCategory?: (categoryId: number, name: string) => void;
}

/**
 * P0-4 乐享式左侧导航（第五轮 v1.4 修订）：
 * 库切换器（仅列知识库）→ 新建对话按钮（问AI 上方，对齐乐享）→ 导航（问AI / 知识地图(P1) / 主页(P1) / 检索调优(admin)）→
 * 历史对话列表（默认收起，标题箭头展开；kb=0 旧普通聊天会话不可见，迁移 P1）→
 * 目录树（新建/上传收拢到目录树「目录」行与节点「···」菜单内；打开文档选中态高亮）→ 底部用户卡。
 * 返工 R2/R3（v1.5 §12）：头部改乐享式库标识区（标识块+库名+副标题+「···」菜单：切换库/重命名/管理，
 * 替代 Select 下拉）；新建对话按钮主色实底；去硬分割线；用户卡固定左下角、树区内部滚动（无页面级滚动条）。
 * 个人知识库保护（T1）：不提供新建/删除知识库入口，仅保留重命名+管理
 * （识别锚点 name==='个人知识库'，迁移脚本 DEFAULT_TARGET_NAME；管理页删除按钮同步隐藏）。
 * 跨组件联动走轻量 CustomEvent 总线：
 * - p04:conv-new     侧栏 → 聊天窗：新建对话（清空消息开新会话，第五轮 T2）
 * - p04:conv-switch   侧栏 → 聊天窗：切换会话
 * - p04:conv-active   聊天窗 → 侧栏：当前活跃会话高亮
 * - p04:conv-list-changed 聊天窗 → 侧栏：会话列表变化（新建/首条消息落库）需刷新
 * - p04:conv-deleted  侧栏 → 聊天窗：删除的正是当前打开的会话，聊天窗清空
 */
export default function KnowledgeBaseSidebar({
  selectedId,
  onSelect,
  refreshKey,
  user,
  onLogout,
  canManage,
  onGoChat,
  chatActive,
  onGoFeedback,
  feedbackActive,
  activeDocId,
  treeRefreshKey,
  onDocChanged,
  onOpenDoc,
  onOpenCategory,
}: Props) {
  const navigate = useNavigate();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renamingKb, setRenamingKb] = useState<KnowledgeBase | null>(null);
  const [renameForm] = Form.useForm();

  // P0-4 v1.2：历史对话列表（常驻侧栏，随选中库拉取；普通聊天用 kb_id=0）
  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  // P0-4 第五轮（T3）：历史对话默认收起，标题箭头展开
  const [historyCollapsed, setHistoryCollapsed] = useState(true);

  const fetchList = async () => {
    setLoading(true);
    try {
      const { data } = await knowledgeBaseApi.list();
      setKnowledgeBases(data);
    } finally {
      setLoading(false);
    }
  };

  // P0-4 第四轮（T4）：历史对话仅列当前选中库（kb=0 旧普通聊天会话不再可见，迁移 P1）
  const fetchConversations = async () => {
    if (!selectedId) {
      setConversations([]);
      return;
    }
    try {
      const { data } = await chatApi.listConversations(selectedId);
      setConversations(data);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    fetchList();
  }, [refreshKey]);

  useEffect(() => {
    fetchConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // 监听聊天窗广播：活跃会话高亮 + 列表变化刷新
  useEffect(() => {
    const onActive = (e: Event) =>
      setActiveConvId((e as CustomEvent<number | null>).detail ?? null);
    const onListChanged = () => fetchConversations();
    window.addEventListener("p04:conv-active", onActive);
    window.addEventListener("p04:conv-list-changed", onListChanged);
    return () => {
      window.removeEventListener("p04:conv-active", onActive);
      window.removeEventListener("p04:conv-list-changed", onListChanged);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const current = knowledgeBases.find((kb) => kb.id === selectedId) ?? null;

  // P0-4 第五轮（T2）：新建对话入口（问AI 上方，对齐乐享）——通知聊天窗清空开新会话
  const handleNewConversation = () => {
    window.dispatchEvent(new CustomEvent("p04:conv-new"));
    onGoChat();
  };

  const handleRename = async () => {
    if (!renamingKb) return;
    const values = await renameForm.validateFields();
    await knowledgeBaseApi.update(renamingKb.id, { name: values.name });
    message.success("知识库已重命名");
    setRenameModalOpen(false);
    setRenamingKb(null);
    await fetchList();
  };

  const openRenameModal = (kb: KnowledgeBase) => {
    setRenamingKb(kb);
    renameForm.setFieldsValue({ name: kb.name });
    setRenameModalOpen(true);
  };

  // ---- 历史对话联动 ----
  const handleSwitchConv = (convId: number) => {
    window.dispatchEvent(new CustomEvent("p04:conv-switch", { detail: convId }));
    onGoChat();
  };

  const handleDeleteConv = async (convId: number) => {
    await chatApi.deleteConversation(convId);
    message.success("对话已删除");
    // 删除的可能正是聊天窗当前打开的会话 → 通知其清空
    window.dispatchEvent(new CustomEvent("p04:conv-deleted", { detail: convId }));
    fetchConversations();
  };

  return (
    <div className={styles.sidebar}>
      {/* 顶部：库标识区（返工 R2，对齐乐享：点击弹菜单=切换知识库（当前项高亮）/重命名/管理） */}
      <div className={styles.kbSwitcher}>
        <Dropdown
          trigger={["click"]}
          menu={{
            selectedKeys: selectedId ? [`kb-${selectedId}`] : [],
            items: [
              ...knowledgeBases.map((kb) => ({ key: `kb-${kb.id}`, label: kb.name })),
              { type: "divider" as const },
              { key: "rename", label: "重命名知识库", icon: <EditOutlined />, disabled: !current },
              { key: "manage", label: "管理", icon: <ToolOutlined />, disabled: !current },
            ],
            onClick: ({ key }) => {
              if (key.startsWith("kb-")) {
                onSelect(knowledgeBases.find((kb) => kb.id === Number(key.slice(3))) ?? null);
              }
              if (key === "manage" && current) navigate(`/spaces/${current.id}`);
              if (key === "rename" && current) openRenameModal(current);
            },
          }}
        >
          <div className={styles.kbHeader}>
            <span className={styles.kbBadge}>{current ? current.name.slice(0, 1) : "知"}</span>
            <div className={styles.kbMeta}>
              <span className={styles.kbName} title={current?.name}>
                {current?.name ?? "选择知识库"}
              </span>
              <span className={styles.kbSubtitle}>
                {current ? `知识库 · ${current.document_count} 篇文档` : "点击切换知识库"}
              </span>
            </div>
            <EllipsisOutlined className={styles.kbMore} />
          </div>
        </Dropdown>
      </div>

      {/* P0-4 第五轮（T2）：新建对话按钮（问AI 上方，对齐乐享）；返工 R3：主色实底企业级 */}
      <div className={styles.nav}>
        <Button
          block
          type="primary"
          icon={<PlusOutlined />}
          className={styles.newConvBtn}
          onClick={handleNewConversation}
        >
          新建对话
        </Button>
      </div>

      {/* 导航项 */}
      <div className={styles.nav}>
        <div
          className={`${styles.navItem} ${chatActive ? styles.navActive : ""}`}
          onClick={onGoChat}
        >
          <MessageOutlined className={styles.navIcon} /> 问AI
        </div>
        <Tooltip title="P1 敬请期待" placement="right">
          <div className={`${styles.navItem} ${styles.navDisabled}`}>
            <CompassOutlined className={styles.navIcon} /> 知识地图
          </div>
        </Tooltip>
        <Tooltip title="P1 敬请期待" placement="right">
          <div className={`${styles.navItem} ${styles.navDisabled}`}>
            <HomeOutlined className={styles.navIcon} /> 主页
          </div>
        </Tooltip>
        {/* P0-4 第四轮（T4）：检索调优（tabs 移除后的新入口，仅管理员可见） */}
        {user.is_admin && onGoFeedback && (
          <div
            className={`${styles.navItem} ${feedbackActive ? styles.navActive : ""}`}
            onClick={onGoFeedback}
          >
            <BarChartOutlined className={styles.navIcon} /> 检索调优
          </div>
        )}
      </div>

      {/* P0-4 v1.2：历史对话列表；第五轮 T3 默认收起，标题箭头展开 */}
      <div className={styles.historyBlock}>
        <div
          className={styles.historyTitle}
          onClick={() => setHistoryCollapsed((v) => !v)}
          role="button"
        >
          <RightOutlined
            className={`${styles.historyCaret} ${historyCollapsed ? "" : styles.historyCaretOpen}`}
          />
          <HistoryOutlined /> 历史对话
        </div>
        {!historyCollapsed &&
          (conversations.length === 0 ? (
            <Typography.Text type="secondary" className={styles.historyEmpty}>
              暂无历史对话
            </Typography.Text>
          ) : (
            conversations.map((conv) => (
            <div
              key={conv.id}
              className={`${styles.historyItem} ${
                conv.id === activeConvId ? styles.historyItemActive : ""
              }`}
              onClick={() => handleSwitchConv(conv.id)}
            >
              <MessageOutlined className={styles.historyIcon} />
              <span className={styles.historyName} title={conv.title}>
                {conv.title}
              </span>
              <Popconfirm
                title="删除此对话？"
                onConfirm={(e) => {
                  e?.stopPropagation();
                  handleDeleteConv(conv.id);
                }}
                onPopupClick={(e) => e.stopPropagation()}
              >
                <DeleteOutlined
                  className={styles.historyDelete}
                  onClick={(e) => e.stopPropagation()}
                />
              </Popconfirm>
            </div>
            ))
          )
        )}
      </div>

      {/* 目录树（打开文档选中态：activeDocId 透传）；返工 R1：树区 flex 伸展+内部滚动；R3：去硬分割线 */}
      <div className={styles.treeWrap}>
        {selectedId ? (
          <CategoryTree
            kbId={selectedId}
            refreshKey={treeRefreshKey}
            canManage={canManage}
            onOpenDoc={onOpenDoc}
            onOpenCategory={onOpenCategory}
            onDocChanged={onDocChanged}
            activeDocId={activeDocId}
          />
        ) : (
          <Typography.Text
            type="secondary"
            style={{ fontSize: 12, padding: "8px 12px", display: "block" }}
          >
            选择知识库后可在此管理目录与文档。
          </Typography.Text>
        )}
      </div>

      {/* 底部用户卡 */}
      <div className={styles.userCard}>
        <Avatar size={26} icon={<UserOutlined />} style={{ backgroundColor: "#1677ff", flexShrink: 0 }} />
        <span className={styles.userName} title={user.display_name}>
          {user.display_name}
        </span>
        <Dropdown
          trigger={["click"]}
          menu={{
            items: [
              {
                key: "role",
                label: `角色：${user.is_admin ? "管理员" : "成员"}`,
                disabled: true,
              },
              { type: "divider" },
              { key: "logout", label: "退出登录", icon: <LogoutOutlined />, onClick: onLogout },
            ],
          }}
        >
          <Button type="text" size="small" icon={<SettingOutlined />} />
        </Dropdown>
      </div>

      <Modal
        title="重命名知识库"
        open={renameModalOpen}
        onOk={handleRename}
        onCancel={() => {
          setRenameModalOpen(false);
          setRenamingKb(null);
        }}
        destroyOnClose
      >
        <Form form={renameForm} layout="vertical">
          <Form.Item
            name="name"
            label="新名称"
            rules={[{ required: true, message: "请输入知识库名称" }]}
          >
            <Input placeholder="输入新名称" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Select,
  Button,
  Input,
  Modal,
  Form,
  Typography,
  Dropdown,
  Avatar,
  Tooltip,
  Divider,
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
 * P0-4 乐享式左侧导航（第四轮 v1.3 修订）：
 * 库切换器（仅列知识库，「普通聊天」选项移除=问答模式清空信息源）→ 导航（问AI / 知识地图(P1) / 主页(P1) / 检索调优(admin)）→
 * 历史对话列表（常驻侧栏，随选中库拉取；kb=0 旧普通聊天会话不可见，迁移 P1）→
 * 目录树（新建/上传收拢到目录树「目录」行与节点「···」菜单内；打开文档选中态高亮）→ 底部用户卡。
 * 跨组件联动走轻量 CustomEvent 总线：
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
  const [modalOpen, setModalOpen] = useState(false);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renamingKb, setRenamingKb] = useState<KnowledgeBase | null>(null);
  const [form] = Form.useForm();
  const [renameForm] = Form.useForm();

  // P0-4 v1.2：历史对话列表（常驻侧栏，随选中库拉取；普通聊天用 kb_id=0）
  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);

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

  const handleCreate = async () => {
    const values = await form.validateFields();
    await knowledgeBaseApi.create(values);
    message.success("知识库创建成功");
    setModalOpen(false);
    form.resetFields();
    await fetchList();
  };

  const handleDelete = async (id: number) => {
    await knowledgeBaseApi.delete(id);
    message.success("知识库已删除");
    if (selectedId === id) onSelect(null);
    await fetchList();
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
      {/* 顶部：库切换器 + 新建 + 管理 */}
      <div className={styles.kbSwitcher}>
        {/* P0-4 第四轮（T4）：仅列知识库，左上角始终显示库名（普通聊天=问答模式清空信息源） */}
        <Select
          className={styles.kbSelect}
          size="small"
          value={selectedId}
          placeholder="选择知识库"
          loading={loading}
          onChange={(v) => onSelect(knowledgeBases.find((kb) => kb.id === v) ?? null)}
          options={knowledgeBases.map((kb) => ({ value: kb.id, label: kb.name }))}
        />
        <Tooltip title="新建知识库">
          <Button size="small" icon={<PlusOutlined />} onClick={() => setModalOpen(true)} />
        </Tooltip>
        {current && (
          <Dropdown
            trigger={["hover"]}
            menu={{
              items: [
                { key: "manage", label: "管理", icon: <ToolOutlined /> },
                { key: "rename", label: "重命名知识库", icon: <EditOutlined /> },
                {
                  key: "delete",
                  label: "删除知识库",
                  icon: <DeleteOutlined />,
                  danger: true,
                },
              ],
              onClick: ({ key }) => {
                if (key === "manage") navigate(`/spaces/${current.id}`);
                if (key === "rename") openRenameModal(current);
                if (key === "delete") {
                  Modal.confirm({
                    title: `删除知识库「${current.name}」？`,
                    content: "将同时删除库内文档与向量索引，不可恢复。",
                    okText: "删除",
                    okButtonProps: { danger: true },
                    onOk: () => handleDelete(current.id),
                  });
                }
              },
            }}
          >
            <Button size="small" icon={<SettingOutlined />} />
          </Dropdown>
        )}
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

      {/* P0-4 v1.2：历史对话列表（常驻侧栏；点击切换会话，hover 删除） */}
      <div className={styles.historyBlock}>
        <div className={styles.historyTitle}>
          <HistoryOutlined /> 历史对话
        </div>
        {conversations.length === 0 ? (
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
        )}
      </div>

      <Divider style={{ margin: "8px 0" }} />

      {/* 目录树（打开文档选中态：activeDocId 透传） */}
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
        <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: "#1677ff" }} />
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
        title="新建知识库"
        open={modalOpen}
        onOk={handleCreate}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入知识库名称" }]}
          >
            <Input placeholder="例如：产品手册" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="可选描述" rows={3} />
          </Form.Item>
        </Form>
      </Modal>

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

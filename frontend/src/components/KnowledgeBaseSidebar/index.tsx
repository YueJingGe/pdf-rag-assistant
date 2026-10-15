import React, { useEffect, useState } from "react";
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
  UploadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import CategoryTree, { type OpenableDoc } from "../CategoryTree";
import { knowledgeBaseApi, type KnowledgeBase, type UserInfo } from "../../services/api";
import styles from "./index.module.less";

const NONE_KB: KnowledgeBase = {
  id: 0,
  name: "普通聊天",
  description: "不选择知识库",
  permission: "private",
  document_count: 0,
  created_at: "",
  updated_at: "",
};

interface Props {
  selectedId: number | null;
  onSelect: (kb: KnowledgeBase | null) => void;
  refreshKey?: number;
  user: UserInfo;
  onLogout: () => void;
  canManage: boolean;
  /** 上传按钮 → App 切到文档管理 tab */
  onGoUpload: () => void;
  /** 导航「问AI」→ App 切回问答 tab */
  onGoChat: () => void;
  chatActive: boolean;
  treeRefreshKey?: number;
  onDocChanged?: () => void;
  onOpenDoc: (doc: OpenableDoc) => void;
  onOpenViewer: (filename: string) => void;
}

/**
 * P0-4 乐享式左侧导航：
 * 顶部库切换器（原 KB 列表收拢为 Select）+ 新建/管理 → 上传按钮 →
 * 导航项（问AI / 知识地图(P1 占位) / 主页(P1 占位)）→ 目录树 → 底部用户卡。
 * 知识库新建/重命名/删除逻辑保留（P0 前既有能力）。
 */
export default function KnowledgeBaseSidebar({
  selectedId,
  onSelect,
  refreshKey,
  user,
  onLogout,
  canManage,
  onGoUpload,
  onGoChat,
  chatActive,
  treeRefreshKey,
  onDocChanged,
  onOpenDoc,
  onOpenViewer,
}: Props) {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renamingKb, setRenamingKb] = useState<KnowledgeBase | null>(null);
  const [form] = Form.useForm();
  const [renameForm] = Form.useForm();

  const fetchList = async () => {
    setLoading(true);
    try {
      const { data } = await knowledgeBaseApi.list();
      setKnowledgeBases(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchList();
  }, [refreshKey]);

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

  return (
    <div className={styles.sidebar}>
      {/* 顶部：库切换器 + 新建 + 管理 */}
      <div className={styles.kbSwitcher}>
        <Select
          className={styles.kbSelect}
          size="small"
          value={selectedId ?? 0}
          loading={loading}
          onChange={(v) =>
            onSelect(v === 0 ? null : knowledgeBases.find((kb) => kb.id === v) ?? null)
          }
          options={[
            { value: 0, label: "普通聊天" },
            ...knowledgeBases.map((kb) => ({ value: kb.id, label: kb.name })),
          ]}
        />
        <Tooltip title="新建知识库">
          <Button size="small" icon={<PlusOutlined />} onClick={() => setModalOpen(true)} />
        </Tooltip>
        {current && (
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                { key: "rename", label: "重命名知识库", icon: <EditOutlined /> },
                {
                  key: "delete",
                  label: "删除知识库",
                  icon: <DeleteOutlined />,
                  danger: true,
                },
              ],
              onClick: ({ key }) => {
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

      {/* 操作：上传文档（需选中知识库） */}
      <div className={styles.actions}>
        <Button
          block
          size="small"
          type="primary"
          ghost
          icon={<UploadOutlined />}
          disabled={!selectedId}
          onClick={onGoUpload}
        >
          上传文档
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
      </div>

      <Divider style={{ margin: "8px 0" }} />

      {/* 目录树（普通聊天无目录） */}
      <div className={styles.treeWrap}>
        {selectedId ? (
          <CategoryTree
            kbId={selectedId}
            refreshKey={treeRefreshKey}
            canManage={canManage}
            onOpenDoc={onOpenDoc}
            onOpenViewer={onOpenViewer}
            onDocChanged={onDocChanged}
          />
        ) : (
          <Typography.Text
            type="secondary"
            style={{ fontSize: 12, padding: "8px 12px", display: "block" }}
          >
            普通聊天不使用知识库；选择知识库后可在此管理目录与文档。
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

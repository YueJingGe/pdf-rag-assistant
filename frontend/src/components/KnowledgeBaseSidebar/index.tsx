import React, { useEffect, useState } from "react";
import {
  List,
  Button,
  Input,
  Modal,
  Form,
  Typography,
  Tag,
  Space,
  Popconfirm,
  message,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  DatabaseOutlined,
  StopOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { knowledgeBaseApi, type KnowledgeBase } from "../../services/api";
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
}

export default function KnowledgeBaseSidebar({
  selectedId,
  onSelect,
  refreshKey,
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

  const handleCreate = async () => {
    const values = await form.validateFields();
    await knowledgeBaseApi.create(values);
    message.success("知识库创建成功");
    setModalOpen(false);
    form.resetFields();
    fetchList();
  };

  const handleDelete = async (id: number) => {
    await knowledgeBaseApi.delete(id);
    message.success("知识库已删除");
    fetchList();
  };

  const handleRename = async () => {
    if (!renamingKb) return;
    const values = await renameForm.validateFields();
    await knowledgeBaseApi.update(renamingKb.id, { name: values.name });
    message.success("知识库已重命名");
    setRenameModalOpen(false);
    setRenamingKb(null);
    fetchList();
  };

  const openRenameModal = (kb: KnowledgeBase) => {
    setRenamingKb(kb);
    renameForm.setFieldsValue({ name: kb.name });
    setRenameModalOpen(true);
  };

  const allItems = [NONE_KB, ...knowledgeBases];

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          知识库
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          size="small"
          onClick={() => setModalOpen(true)}
        >
          新建
        </Button>
      </div>

      <List
        loading={loading}
        dataSource={allItems}
        renderItem={(kb) => (
          <List.Item
            className={`${styles.item} ${
              (selectedId === null && kb.id === 0) || selectedId === kb.id
                ? styles.selected
                : ""
            }`}
            onClick={() => onSelect(kb.id === 0 ? null : kb)}
            actions={
              kb.id === 0
                ? []
                : [
                    <Button
                      key="edit"
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        openRenameModal(kb);
                      }}
                    />,
                    <Popconfirm
                      key="del"
                      title="确定删除该知识库？"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        handleDelete(kb.id);
                      }}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]
            }
          >
            <List.Item.Meta
              avatar={
                kb.id === 0 ? (
                  <StopOutlined style={{ fontSize: 20, color: "#999" }} />
                ) : (
                  <DatabaseOutlined
                    style={{ fontSize: 20, color: "#1677ff" }}
                  />
                )
              }
              title={kb.name}
              description={
                kb.id === 0 ? (
                  "不使用知识库"
                ) : (
                  <Space size={4}>
                    <Tag color="blue">{kb.document_count} 文档</Tag>
                    <Tag>{kb.permission === "private" ? "私有" : "公开"}</Tag>
                  </Space>
                )
              }
            />
          </List.Item>
        )}
      />

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

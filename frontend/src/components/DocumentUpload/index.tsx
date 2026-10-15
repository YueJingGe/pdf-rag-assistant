import React, { useEffect, useState, useRef } from "react";
import {
  Upload,
  Table,
  Button,
  Tag,
  message,
  Popconfirm,
  Progress,
  Empty,
  Space,
  Input,
  Modal,
  Form,
  TreeSelect,
} from "antd";
import { InboxOutlined, DeleteOutlined, EditOutlined } from "@ant-design/icons";
import type { Key } from "react";
import {
  documentApi,
  knowledgeBaseApi,
  type DocumentInfo,
  type CategoryInfo,
} from "../../services/api";
import { buildCategorySelectTree } from "../CategoryTree";
import styles from "./index.module.less";

const { Dragger } = Upload;

interface UploadingItem {
  filename: string;
  progress: number;
  status: "uploading" | "processing" | "done" | "error";
}

interface Props {
  knowledgeBaseId: number | null;
  onDocChange?: () => void;
}

export default function DocumentUpload({ knowledgeBaseId, onDocChange }: Props) {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingItem[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([]);
  const [batchDeleting, setBatchDeleting] = useState(false);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renamingDoc, setRenamingDoc] = useState<DocumentInfo | null>(null);
  const [renameForm] = Form.useForm();
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // P0-4：上传挂目录
  const [uploadCatId, setUploadCatId] = useState<number | null>(null);
  const [catCategories, setCatCategories] = useState<CategoryInfo[]>([]);

  const fetchDocuments = async () => {
    if (!knowledgeBaseId) return;
    const { data } = await documentApi.list(knowledgeBaseId);
    setDocuments(data);
  };

  // P0-4：目录选择数据（上传挂目录用）
  const loadCategories = async () => {
    if (!knowledgeBaseId) return;
    try {
      const { data } = await knowledgeBaseApi.getTree(knowledgeBaseId);
      setCatCategories(data.categories);
    } catch {
      setCatCategories([]);
    }
  };

  useEffect(() => {
    setDocuments([]);
    setUploadCatId(null);
    fetchDocuments();
    loadCategories();
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [knowledgeBaseId]);

  const startPolling = () => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      await fetchDocuments();
      setUploadingFiles((prev) => {
        const stillUploading = prev.filter(
          (f) => f.status === "uploading" || f.status === "processing"
        );
        if (stillUploading.length === 0 && pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        return prev;
      });
    }, 2000);
  };

  const handleUpload = async (file: File) => {
    if (!knowledgeBaseId) {
      message.warning("请先选择知识库");
      return false;
    }

    const uploadItem: UploadingItem = {
      filename: file.name,
      progress: 0,
      status: "uploading",
    };
    setUploadingFiles((prev) => [...prev, uploadItem]);

    try {
      setUploadingFiles((prev) =>
        prev.map((f) =>
          f.filename === file.name && f.status === "uploading"
            ? { ...f, progress: 30 }
            : f
        )
      );
      await documentApi.upload(knowledgeBaseId, file, uploadCatId);
      setUploadingFiles((prev) =>
        prev.map((f) =>
          f.filename === file.name && f.status === "uploading"
            ? { ...f, progress: 100, status: "done" }
            : f
        )
      );
      message.success(`${file.name} 上传成功`);
      fetchDocuments();
      onDocChange?.();
      startPolling();
      setTimeout(() => {
        setUploadingFiles((prev) =>
          prev.filter((f) => !(f.filename === file.name && f.status === "done"))
        );
      }, 2000);
    } catch {
      setUploadingFiles((prev) =>
        prev.map((f) =>
          f.filename === file.name && f.status === "uploading"
            ? { ...f, status: "error", progress: 100 }
            : f
        )
      );
      message.error(`${file.name} 上传失败`);
    }
    return false;
  };

  const handleDelete = async (docId: number) => {
    if (!knowledgeBaseId) return;
    await documentApi.delete(knowledgeBaseId, docId);
    message.success("文档已删除");
    setSelectedRowKeys((prev) => prev.filter((k) => k !== docId));
    fetchDocuments();
    onDocChange?.();
  };

  const handleBatchDelete = async () => {
    if (!knowledgeBaseId || selectedRowKeys.length === 0) return;
    setBatchDeleting(true);
    try {
      await documentApi.batchDelete(knowledgeBaseId, selectedRowKeys as number[]);
      message.success(`已删除 ${selectedRowKeys.length} 个文档`);
      setSelectedRowKeys([]);
      fetchDocuments();
      onDocChange?.();
    } catch {
      message.error("批量删除失败");
    } finally {
      setBatchDeleting(false);
    }
  };

  const openRenameModal = (doc: DocumentInfo) => {
    setRenamingDoc(doc);
    renameForm.setFieldsValue({ filename: doc.filename });
    setRenameModalOpen(true);
  };

  const handleRename = async () => {
    if (!knowledgeBaseId || !renamingDoc) return;
    const values = await renameForm.validateFields();
    await documentApi.rename(knowledgeBaseId, renamingDoc.id, values.filename);
    message.success("文档已重命名");
    setRenameModalOpen(false);
    setRenamingDoc(null);
    fetchDocuments();
  };

  const statusTag = (status: string) => {
    const map: Record<string, { color: string; text: string }> = {
      ready: { color: "green", text: "就绪" },
      processing: { color: "blue", text: "处理中" },
      error: { color: "red", text: "失败" },
    };
    const item = map[status] || { color: "default", text: status };
    return <Tag color={item.color}>{item.text}</Tag>;
  };

  if (!knowledgeBaseId) {
    return <Empty description="请先选择一个知识库" style={{ marginTop: 60 }} />;
  }

  const columns = [
    {
      title: "文档名",
      dataIndex: "filename",
      key: "filename",
      ellipsis: true,
    },
    {
      title: "来源",
      dataIndex: "source",
      key: "source",
      width: 90,
      render: (source: string) => (
        <Tag color={source === "online" ? "green" : "blue"}>
          {source === "online" ? "在线创作" : "上传"}
        </Tag>
      ),
    },
    {
      title: "大小",
      dataIndex: "file_size",
      key: "file_size",
      width: 200,
      render: (size: number) => `${(size / 1024).toFixed(1)} KB`,
    },
    {
      title: "文本块",
      dataIndex: "chunk_count",
      key: "chunk_count",
      width: 150,
      render: (count: number) => count || "-",
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 150,
      render: (status: string) => statusTag(status),
    },
    {
      title: "操作",
      key: "action",
      width: 150,
      render: (_: unknown, record: DocumentInfo) => (
        <Space size={0}>
          <Button type="text" size="small" icon={<EditOutlined />} onClick={() => openRenameModal(record)} />
          <Popconfirm
            title="确定删除？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      {/* P0-4：上传挂目录 */}
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 13, color: "#8c8c8c", flexShrink: 0 }}>上传到目录：</span>
        <TreeSelect
          style={{ flex: 1 }}
          size="small"
          treeData={buildCategorySelectTree(catCategories)}
          value={uploadCatId ?? undefined}
          onChange={(v) => setUploadCatId(v ?? null)}
          placeholder="未归类（根目录）"
          treeDefaultExpandAll
          allowClear
        />
      </div>
      <Dragger
        accept=".pdf,.docx,.doc,.txt,.md"
        showUploadList={false}
        multiple
        beforeUpload={handleUpload}
        disabled={uploadingFiles.some((f) => f.status === "uploading")}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p className="ant-upload-hint">支持 PDF、DOCX、TXT、Markdown 格式</p>
      </Dragger>

      {uploadingFiles.length > 0 && (
        <div style={{ marginTop: 12 }}>
          {uploadingFiles.map((item, index) => (
            <div key={index} style={{ marginBottom: 8 }}>
              <Space>
                <span style={{ fontSize: 13 }}>{item.filename}</span>
                <Tag color={item.status === "error" ? "red" : "blue"}>
                  {item.status === "uploading"
                    ? "上传中"
                    : item.status === "processing"
                    ? "处理中"
                    : item.status === "error"
                    ? "失败"
                    : "完成"}
                </Tag>
              </Space>
              <Progress
                percent={item.progress}
                size="small"
                status={
                  item.status === "error"
                    ? "exception"
                    : item.status === "done"
                    ? "success"
                    : "active"
                }
                showInfo={false}
              />
            </div>
          ))}
        </div>
      )}

      {selectedRowKeys.length > 0 && (
        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13 }}>已选择 {selectedRowKeys.length} 项</span>
          <Popconfirm title={`确定删除选中的 ${selectedRowKeys.length} 个文档？`} onConfirm={handleBatchDelete}>
            <Button type="primary" danger size="small" icon={<DeleteOutlined />} loading={batchDeleting}>
              批量删除
            </Button>
          </Popconfirm>
          <Button size="small" onClick={() => setSelectedRowKeys([])}>取消选择</Button>
        </div>
      )}

      <Table
        columns={columns}
        dataSource={documents}
        rowKey="id"
        size="small"
        pagination={false}
        style={{ marginTop: 16 }}
        locale={{ emptyText: "暂无文档" }}
        scroll={{ y: 300 }}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys),
        }}
      />

      <Modal
        title="重命名文档"
        open={renameModalOpen}
        onOk={handleRename}
        onCancel={() => { setRenameModalOpen(false); setRenamingDoc(null); }}
        destroyOnClose
      >
        <Form form={renameForm} layout="vertical">
          <Form.Item name="filename" label="文档名" rules={[{ required: true, message: '请输入文档名' }]}>
            <Input placeholder="输入新文档名" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

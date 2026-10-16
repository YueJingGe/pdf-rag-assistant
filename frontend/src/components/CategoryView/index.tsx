import React, { useEffect, useRef, useState } from "react";
import {
  Button,
  Dropdown,
  Empty,
  Form,
  Input,
  Modal,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  FolderOutlined,
  FileTextOutlined,
  FileMarkdownOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  UploadOutlined,
  FileAddOutlined,
  FolderAddOutlined,
  RightOutlined,
} from "@ant-design/icons";
import {
  categoryApi,
  documentApi,
  knowledgeBaseApi,
  type CategoryInfo,
  type TreeNodeDocument,
} from "../../services/api";
import type { OpenableDoc } from "../CategoryTree";
import UploadModal from "../UploadModal";
import styles from "./index.module.less";

interface Props {
  kbId: number;
  categoryId: number;
  /** 目录名（外部初始值；改名成功后经 onRenamed 同步外层 tab 标题） */
  name: string;
  canManage: boolean;
  /** 任何增删改后通知外层（刷新侧栏树/文档计数） */
  onChanged?: () => void;
  onOpenDoc: (doc: OpenableDoc) => void;
  /** 点击子目录 → 主区域打开该子目录视图 tab */
  onOpenCategory?: (categoryId: number, name: string) => void;
  /** inline 改名成功 → 外层同步 tab 标题 */
  onRenamed?: (categoryId: number, newName: string) => void;
  /** 目录已在侧栏被删除 → 外层关闭本 tab */
  onMissing?: () => void;
}

/**
 * P0-4 第三轮（T3）：目录视图 tab（乐享文件夹页）。
 * 头部：目录名（inline 改名）+「+ 新建」菜单（新建在线文档/新建文件夹）+「⬆ 上传」；
 * 内容：子目录行 + 文档行；空态「该文件夹暂无内容」。
 * 数据复用 getTree 全量接口前端过滤（无需新增后端端点，禁区零触碰）。
 */
export default function CategoryView({
  kbId,
  categoryId,
  name,
  canManage,
  onChanged,
  onOpenDoc,
  onOpenCategory,
  onRenamed,
  onMissing,
}: Props) {
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [documents, setDocuments] = useState<TreeNodeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [innerKey, setInnerKey] = useState(0);

  // inline 改名
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(name);

  // 新建弹窗（在线文档 / 子目录）+ 文档重命名弹窗
  const [newDocOpen, setNewDocOpen] = useState(false);
  const [newCatOpen, setNewCatOpen] = useState(false);
  const [renamingDoc, setRenamingDoc] = useState<TreeNodeDocument | null>(null);
  const [newDocForm] = Form.useForm();
  const [newCatForm] = Form.useForm();
  const [renameDocForm] = Form.useForm();

  // 上传自足（挂当前目录）
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);

  const fetchTree = async () => {
    setLoading(true);
    try {
      const { data } = await knowledgeBaseApi.getTree(kbId);
      setCategories(data.categories);
      setDocuments(data.documents);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTree();
    setRenaming(false);
    setRenameValue(name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, categoryId, innerKey]);

  // 目录已在侧栏被删除（刷新后不在全量列表中）→ 通知外层关闭本 tab
  useEffect(() => {
    if (!loading && !categories.some((c) => c.id === categoryId)) {
      onMissing?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, categories, categoryId]);

  const refresh = () => {
    setInnerKey((k) => k + 1);
    onChanged?.();
  };

  const childCategories = categories.filter((c) => c.parent_id === categoryId);
  const directDocs = documents.filter((d) => d.category_id === categoryId);
  const isEmpty = !loading && childCategories.length === 0 && directDocs.length === 0;

  // ---- inline 改名 ----
  const submitRename = async () => {
    const newName = renameValue.trim();
    if (!newName || newName === name) {
      setRenaming(false);
      return;
    }
    await categoryApi.rename(kbId, categoryId, newName);
    message.success("目录已重命名");
    setRenaming(false);
    onRenamed?.(categoryId, newName);
    refresh();
  };

  // ---- 新建 ----
  const handleCreateOnlineDoc = async () => {
    const values = await newDocForm.validateFields();
    const { data } = await documentApi.createOnline(kbId, {
      title: values.title,
      category_id: categoryId,
    });
    message.success("文档已创建");
    setNewDocOpen(false);
    newDocForm.resetFields();
    refresh();
    onOpenDoc({
      id: data.id,
      filename: data.filename,
      source: data.source,
      categoryName: name,
    });
  };

  const handleCreateSubCat = async () => {
    const values = await newCatForm.validateFields();
    await categoryApi.create(kbId, { name: values.name, parent_id: categoryId });
    message.success("文件夹已创建");
    setNewCatOpen(false);
    newCatForm.resetFields();
    refresh();
  };

  // ---- 删除 ----
  const deleteSubCat = (c: CategoryInfo) => {
    Modal.confirm({
      title: `删除文件夹「${c.name}」？`,
      content: "文件夹下的文档将移至「未归类」（挂根），不会删除任何文档。",
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        await categoryApi.remove(kbId, c.id);
        message.success("文件夹已删除");
        refresh();
      },
    });
  };

  const deleteDoc = (d: TreeNodeDocument) => {
    Modal.confirm({
      title: `删除文档「${d.filename}」？`,
      content: "将同时清理向量索引与物理文件，不可恢复。",
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        await documentApi.delete(kbId, d.id);
        message.success("文档已删除");
        refresh();
      },
    });
  };

  // ---- 重命名文档（Form Modal，与目录树同交互） ----
  const openRenameDocModal = (d: TreeNodeDocument) => {
    setRenamingDoc(d);
    renameDocForm.setFieldsValue({ name: d.filename });
  };

  const handleRenameDoc = async () => {
    if (!renamingDoc) return;
    const values = await renameDocForm.validateFields();
    await documentApi.rename(kbId, renamingDoc.id, values.name);
    message.success("文档已重命名");
    setRenamingDoc(null);
    refresh();
  };

  const docRowMenu = (d: TreeNodeDocument) => ({
    items: [
      { key: "rename", label: "重命名", icon: <EditOutlined /> },
      { type: "divider" as const },
      { key: "delete", label: "删除", icon: <DeleteOutlined />, danger: true },
    ],
    onClick: ({ key, domEvent }: { key: string; domEvent: { stopPropagation: () => void } }) => {
      domEvent.stopPropagation();
      if (key === "rename") openRenameDocModal(d);
      if (key === "delete") deleteDoc(d);
    },
  });

  const catRowMenu = (c: CategoryInfo) => ({
    items: [
      { key: "rename", label: "重命名", icon: <EditOutlined /> },
      { type: "divider" as const },
      { key: "delete", label: "删除（文档移至根）", icon: <DeleteOutlined />, danger: true },
    ],
    onClick: ({ key, domEvent }: { key: string; domEvent: { stopPropagation: () => void } }) => {
      domEvent.stopPropagation();
      if (key === "rename") {
        onOpenCategory?.(c.id, c.name);
      }
      if (key === "delete") deleteSubCat(c);
    },
  });

  const plusMenu = {
    items: [
      { key: "doc", label: "新建在线文档", icon: <FileAddOutlined /> },
      { key: "cat", label: "新建文件夹", icon: <FolderAddOutlined /> },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === "doc") setNewDocOpen(true);
      if (key === "cat") setNewCatOpen(true);
    },
  };

  const triggerUpload = () => fileInputRef.current?.click();

  const handleFileChosen = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // 允许重复选择同一文件
    if (files.length === 0) return;
    setUploadFiles(files);
    setUploadOpen(true);
  };

  return (
    <div className={styles.container}>
      {/* 头部：目录名（inline 改名）+ 新建/上传 */}
      <div className={styles.toolbar}>
        <FolderOutlined style={{ color: "#1677ff", fontSize: 16 }} />
        {renaming ? (
          <Input
            size="small"
            style={{ width: 220 }}
            value={renameValue}
            autoFocus
            onChange={(e) => setRenameValue(e.target.value)}
            onPressEnter={submitRename}
            onBlur={submitRename}
          />
        ) : (
          <span className={styles.titleGroup}>
            <Typography.Text strong ellipsis style={{ maxWidth: 280, fontSize: 15 }}>
              {name}
            </Typography.Text>
            {canManage && (
              <Tooltip title="重命名">
                <EditOutlined
                  className={styles.titleEdit}
                  onClick={() => {
                    setRenameValue(name);
                    setRenaming(true);
                  }}
                />
              </Tooltip>
            )}
          </span>
        )}
        {canManage && (
          <span className={styles.toolbarActions}>
            <Dropdown trigger={["click"]} menu={plusMenu}>
              <Button size="small" icon={<PlusOutlined />}>
                新建
              </Button>
            </Dropdown>
            <Button size="small" icon={<UploadOutlined />} onClick={triggerUpload}>
              上传
            </Button>
          </span>
        )}
      </div>

      {/* 内容：子目录 + 文档 行式列表 */}
      {isEmpty ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="该文件夹暂无内容"
          style={{ marginTop: 80 }}
        />
      ) : (
        <div className={styles.rows}>
          {childCategories.map((c) => (
            <div
              key={c.id}
              className={styles.row}
              onClick={() => onOpenCategory?.(c.id, c.name)}
            >
              <FolderOutlined style={{ color: "#1677ff" }} />
              <span className={styles.rowName} title={c.name}>
                {c.name}
              </span>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {documents.filter((d) => d.category_id === c.id).length} 个文档
              </Typography.Text>
              <RightOutlined style={{ color: "#bbb", fontSize: 12 }} />
              {canManage && (
                <Dropdown trigger={["click"]} menu={catRowMenu(c)}>
                  <span className={styles.rowMore} onClick={(e) => e.stopPropagation()}>
                    ···
                  </span>
                </Dropdown>
              )}
            </div>
          ))}
          {directDocs.map((d) => (
            <div
              key={d.id}
              className={styles.row}
              onClick={() =>
                // P0-4 第三轮（T7）：上传文档也开 doc tab（只读正文），不再走 Modal 查看器
                onOpenDoc({
                  id: d.id,
                  filename: d.filename,
                  source: d.source,
                  categoryName: name,
                })
              }
            >
              {d.source === "online" ? (
                <FileMarkdownOutlined style={{ color: "#52c41a" }} />
              ) : (
                <FileTextOutlined style={{ color: "#8c8c8c" }} />
              )}
              <span className={styles.rowName} title={d.filename}>
                {d.filename}
              </span>
              {d.status !== "ready" && (
                <Tag color={d.status === "error" ? "red" : "blue"}>
                  {d.status === "error" ? "失败" : "处理中"}
                </Tag>
              )}
              {canManage && (
                <Dropdown trigger={["click"]} menu={docRowMenu(d)}>
                  <span className={styles.rowMore} onClick={(e) => e.stopPropagation()}>
                    ···
                  </span>
                </Dropdown>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 上传自足（挂当前目录） */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.doc,.txt,.md"
        style={{ display: "none" }}
        onChange={handleFileChosen}
      />
      <UploadModal
        kbId={kbId}
        categoryId={categoryId}
        files={uploadFiles}
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          setUploadFiles([]);
        }}
        onUploaded={refresh}
      />

      {/* 重命名文档 */}
      <Modal
        title="重命名文档"
        open={renamingDoc !== null}
        onOk={handleRenameDoc}
        onCancel={() => setRenamingDoc(null)}
        destroyOnClose
      >
        <Form form={renameDocForm} layout="vertical">
          <Form.Item
            name="name"
            label="文档名"
            rules={[{ required: true, message: "请输入文档名" }]}
          >
            <Input placeholder="输入新文档名" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新建在线文档 / 新建文件夹 */}
      <Modal
        title="新建在线文档"
        open={newDocOpen}
        onOk={handleCreateOnlineDoc}
        onCancel={() => setNewDocOpen(false)}
        destroyOnClose
      >
        <Form form={newDocForm} layout="vertical">
          <Form.Item
            name="title"
            label="文档标题"
            rules={[{ required: true, message: "请输入文档标题" }]}
          >
            <Input placeholder="例如：React Hooks 笔记" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`新建文件夹（${name} 内）`}
        open={newCatOpen}
        onOk={handleCreateSubCat}
        onCancel={() => setNewCatOpen(false)}
        destroyOnClose
      >
        <Form form={newCatForm} layout="vertical">
          <Form.Item
            name="name"
            label="文件夹名"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="输入名称" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import {
  Tree,
  Dropdown,
  Modal,
  Form,
  Input,
  TreeSelect,
  Popconfirm,
  message,
  Empty,
  Spin,
} from "antd";
import {
  FolderOutlined,
  FileTextOutlined,
  FileMarkdownOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  DragOutlined,
  FileAddOutlined,
} from "@ant-design/icons";
import type { DataNode } from "antd/es/tree";
import {
  categoryApi,
  documentApi,
  knowledgeBaseApi,
  type CategoryInfo,
  type TreeNodeDocument,
} from "../../services/api";
import styles from "./index.module.less";

/** 可在文档工作台打开的文档（在线文档） */
export interface OpenableDoc {
  id: number;
  filename: string;
  source: string;
  categoryName?: string;
}

/** TreeSelect 节点结构 */
export interface CategorySelectNode {
  title: string;
  value: number;
  key: number;
  children: CategorySelectNode[];
}

/**
 * 纯目录选择树数据（不含文档节点），供「存为文档」「上传挂目录」的 TreeSelect 复用。
 * P0-4 目录树的简易版组树逻辑：按 parent_id 嵌套，孤儿目录兜底挂根。
 */
export function buildCategorySelectTree(
  categories: CategoryInfo[]
): CategorySelectNode[] {
  const nodes = new Map<number, CategorySelectNode>();
  categories.forEach((c) =>
    nodes.set(c.id, { title: c.name, value: c.id, key: c.id, children: [] })
  );
  const roots: CategorySelectNode[] = [];
  categories.forEach((c) => {
    const parent = c.parent_id != null ? nodes.get(c.parent_id) : undefined;
    if (parent) parent.children.push(nodes.get(c.id)!);
    else roots.push(nodes.get(c.id)!);
  });
  return roots;
}

interface Props {
  kbId: number;
  refreshKey?: number;
  canManage: boolean;
  /** 点击在线文档 → 打开工作台 tab */
  onOpenDoc: (doc: OpenableDoc) => void;
  /** 点击上传文档 → 复用 DocumentViewer 只读查看 */
  onOpenViewer: (filename: string) => void;
  onDocChanged?: () => void;
}

type ModalMode = "newDoc" | "newCat" | "renameCat" | "renameDoc" | "moveDoc";

interface MoveTarget {
  docId: number;
  name: string;
}

/**
 * P0-4 目录树组件：目录 + 文档混挂（未归类挂虚拟「未归类」组）。
 * 节点菜单：新建文档 / 新建子目录 / 重命名 / 移动到 / 删除（目录删除 = 文档移至根，不删文档）。
 */
export default function CategoryTree({
  kbId,
  refreshKey,
  canManage,
  onOpenDoc,
  onOpenViewer,
  onDocChanged,
}: Props) {
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [documents, setDocuments] = useState<TreeNodeDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);

  const [modalMode, setModalMode] = useState<ModalMode | null>(null);
  const [modalTitle, setModalTitle] = useState("");
  const [activeCategory, setActiveCategory] = useState<CategoryInfo | null>(null);
  const [activeDoc, setActiveDoc] = useState<TreeNodeDocument | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const fetchTree = async () => {
    setLoading(true);
    try {
      const { data } = await knowledgeBaseApi.getTree(kbId);
      setCategories(data.categories);
      setDocuments(data.documents);
      // 默认展开根级目录
      setExpandedKeys(
        data.categories.filter((c) => c.parent_id == null).map((c) => `cat-${c.id}`)
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTree();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, refreshKey]);

  const catName = (id: number | null) =>
    id == null ? "未归类" : categories.find((c) => c.id === id)?.name ?? "未归类";

  const refresh = () => {
    fetchTree();
    onDocChanged?.();
  };

  // ---- 组树：目录嵌套 + 未归类虚拟节点 + 文档挂载 ----
  const docNode = (d: TreeNodeDocument): DataNode => ({
    key: `doc-${d.id}`,
    icon:
      d.source === "online" ? (
        <FileMarkdownOutlined style={{ color: "#52c41a" }} />
      ) : (
        <FileTextOutlined style={{ color: "#8c8c8c" }} />
      ),
    title: (
      <span className={styles.nodeTitle}>
        <span
          className={styles.nodeLabel}
          onClick={() =>
            d.source === "online"
              ? onOpenDoc({ id: d.id, filename: d.filename, source: d.source, categoryName: catName(d.category_id) })
              : onOpenViewer(d.filename)
          }
          title={d.filename}
        >
          {d.filename}
          {d.status !== "ready" && (
            <span className={styles.nodeStatus}>{d.status === "error" ? "（失败）" : "（处理中）"}</span>
          )}
        </span>
        {canManage && (
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                { key: "move", label: "移动到", icon: <DragOutlined /> },
                { key: "rename", label: "重命名", icon: <EditOutlined /> },
                { type: "divider" },
                { key: "delete", label: "删除", icon: <DeleteOutlined />, danger: true },
              ],
              onClick: ({ key, domEvent }) => {
                domEvent.stopPropagation();
                if (key === "move") openMoveModal(d);
                if (key === "rename") openRenameDocModal(d);
                if (key === "delete") deleteDoc(d);
              },
            }}
          >
            <span className={styles.nodeMore} onClick={(e) => e.stopPropagation()}>···</span>
          </Dropdown>
        )}
      </span>
    ),
    isLeaf: true,
  });

  const treeData: DataNode[] = (() => {
    const catNodes = new Map<number, DataNode & { children: DataNode[] }>();
    categories.forEach((c) =>
      catNodes.set(c.id, {
        key: `cat-${c.id}`,
        icon: <FolderOutlined style={{ color: "#1677ff" }} />,
        title: (
          <span className={styles.nodeTitle}>
            <span className={styles.nodeLabel}>{c.name}</span>
            {canManage && (
              <Dropdown
                trigger={["click"]}
                menu={{
                  items: [
                    { key: "newDoc", label: "新建文档", icon: <FileAddOutlined /> },
                    { key: "newCat", label: "新建子目录", icon: <PlusOutlined /> },
                    { key: "rename", label: "重命名", icon: <EditOutlined /> },
                    { type: "divider" },
                    { key: "delete", label: "删除（文档移至根）", icon: <DeleteOutlined />, danger: true },
                  ],
                  onClick: ({ key, domEvent }) => {
                    domEvent.stopPropagation();
                    if (key === "newDoc") openNewDocModal(c);
                    if (key === "newCat") openNewCatModal(c);
                    if (key === "rename") openRenameCatModal(c);
                    if (key === "delete") deleteCategory(c);
                  },
                }}
              >
                <span className={styles.nodeMore} onClick={(e) => e.stopPropagation()}>···</span>
              </Dropdown>
            )}
          </span>
        ),
        children: [],
      })
    );
    const roots: DataNode[] = [];
    categories.forEach((c) => {
      if (c.parent_id != null && catNodes.has(c.parent_id)) {
        catNodes.get(c.parent_id)!.children.push(catNodes.get(c.id)!);
      } else {
        roots.push(catNodes.get(c.id)!);
      }
    });
    categories.forEach((c) => {
      const docs = documents.filter((d) => d.category_id === c.id).map(docNode);
      catNodes.get(c.id)!.children.push(...docs);
    });
    const uncategorized = documents.filter((d) => d.category_id == null);
    if (uncategorized.length > 0) {
      roots.push({
        key: "uncategorized",
        icon: <FolderOutlined style={{ color: "#faad14" }} />,
        title: <span className={styles.nodeLabel}>未归类</span>,
        selectable: false,
        children: uncategorized.map(docNode),
      });
    }
    return roots;
  })();

  // ---- 动作 ----
  const openNewDocModal = (c: CategoryInfo | null) => {
    setActiveCategory(c);
    setModalMode("newDoc");
    setModalTitle(`新建文档${c ? `（${c.name}）` : ""}`);
    form.resetFields();
  };

  const openNewCatModal = (c: CategoryInfo) => {
    setActiveCategory(c);
    setModalMode("newCat");
    setModalTitle(`新建子目录（${c.name}）`);
    form.resetFields();
  };

  const openRenameCatModal = (c: CategoryInfo) => {
    setActiveCategory(c);
    setModalMode("renameCat");
    setModalTitle("重命名目录");
    form.setFieldsValue({ name: c.name });
  };

  const openRenameDocModal = (d: TreeNodeDocument) => {
    setActiveDoc(d);
    setModalMode("renameDoc");
    setModalTitle("重命名文档");
    form.setFieldsValue({ name: d.filename });
  };

  const openMoveModal = (d: TreeNodeDocument) => {
    setActiveDoc(d);
    setModalMode("moveDoc");
    setModalTitle(`移动「${d.filename}」到`);
    form.setFieldsValue({ category: d.category_id ?? 0 });
  };

  const deleteCategory = (c: CategoryInfo) => {
    Modal.confirm({
      title: `删除目录「${c.name}」？`,
      content: "目录下的文档将移至「未归类」（挂根），不会删除任何文档。",
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        await categoryApi.remove(kbId, c.id);
        message.success("目录已删除");
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

  const handleModalOk = async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      if (modalMode === "newDoc") {
        const { data } = await documentApi.createOnline(kbId, {
          title: values.title,
          category_id: activeCategory?.id ?? null,
        });
        message.success("文档已创建");
        setModalMode(null);
        onOpenDoc({
          id: data.id,
          filename: data.filename,
          source: data.source,
          categoryName: catName(activeCategory?.id ?? null),
        });
      } else if (modalMode === "newCat") {
        await categoryApi.create(kbId, {
          name: values.name,
          parent_id: activeCategory?.id ?? null,
        });
        message.success("目录已创建");
        setModalMode(null);
      } else if (modalMode === "renameCat" && activeCategory) {
        await categoryApi.rename(kbId, activeCategory.id, values.name);
        message.success("目录已重命名");
        setModalMode(null);
      } else if (modalMode === "renameDoc" && activeDoc) {
        await documentApi.rename(kbId, activeDoc.id, values.name);
        message.success("文档已重命名");
        setModalMode(null);
      } else if (modalMode === "moveDoc" && activeDoc) {
        await categoryApi.moveDocuments(
          kbId,
          [activeDoc.id],
          values.category === 0 ? null : values.category
        );
        message.success("文档已移动");
        setModalMode(null);
      }
      refresh();
    } finally {
      setSubmitting(false);
    }
  };

  // 目录选择树数据（移动到用；0 = 根/未归类）
  const categoryTreeData = [
    { title: "未归类（根）", value: 0, key: 0, children: [] as unknown[] },
    ...categories.map((c) => ({ title: c.name, value: c.id, key: c.id, children: [] as unknown[] })),
  ];

  if (loading && categories.length === 0 && documents.length === 0) {
    return (
      <div className={styles.container}>
        <Spin size="small" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {treeData.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无目录与文档"
          style={{ marginTop: 24 }}
        />
      ) : (
        <Tree
          showIcon
          blockNode
          treeData={treeData}
          expandedKeys={expandedKeys}
          onExpand={(keys) => setExpandedKeys(keys)}
          selectable={false}
        />
      )}

      <Modal
        title={modalTitle}
        open={modalMode !== null}
        onOk={handleModalOk}
        onCancel={() => setModalMode(null)}
        confirmLoading={submitting}
        destroyOnClose
      >
        {(modalMode === "newDoc") && (
          <Form form={form} layout="vertical">
            <Form.Item
              name="title"
              label="文档标题"
              rules={[{ required: true, message: "请输入文档标题" }]}
            >
              <Input placeholder="例如：React Hooks 笔记" />
            </Form.Item>
          </Form>
        )}
        {(modalMode === "newCat" || modalMode === "renameCat" || modalMode === "renameDoc") && (
          <Form form={form} layout="vertical">
            <Form.Item
              name="name"
              label={modalMode === "renameDoc" ? "文档名" : "目录名"}
              rules={[{ required: true, message: "请输入名称" }]}
            >
              <Input placeholder="输入名称" />
            </Form.Item>
          </Form>
        )}
        {modalMode === "moveDoc" && (
          <Form form={form} layout="vertical">
            <Form.Item name="category" label="目标目录">
              <TreeSelect
                treeData={categoryTreeData as never}
                treeDefaultExpandAll
                placeholder="选择目标目录"
              />
            </Form.Item>
          </Form>
        )}
      </Modal>
    </div>
  );
}

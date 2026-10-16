import React, { useEffect, useRef, useState } from "react";
import {
  Tree,
  Dropdown,
  Modal,
  Form,
  Input,
  Checkbox,
  Button,
  Tooltip,
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
  FileAddOutlined,
  AppstoreOutlined,
  EllipsisOutlined,
  CloseOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import type { DataNode } from "antd/es/tree";
import {
  categoryApi,
  documentApi,
  knowledgeBaseApi,
  type CategoryInfo,
  type TreeNodeDocument,
} from "../../services/api";
import UploadModal from "../UploadModal";
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
  /** 点击文档 → 打开工作台 tab（在线可编辑/上传只读，P0-4 第三轮统一 doc tab） */
  onOpenDoc: (doc: OpenableDoc) => void;
  /** P0-4 第三轮：点击目录 → 主区域打开目录视图 tab */
  onOpenCategory?: (categoryId: number, name: string) => void;
  onDocChanged?: () => void;
  /** P0-4 第四轮（T5）：打开文档的树选中态（高亮+自动展开所在目录；/spaces 管理页不传即无选中态） */
  activeDocId?: number;
  /** 顶部「目录」标题行（主界面乐享式；/spaces 管理页自带标题，传 false 关闭） */
  showHeader?: boolean;
}

type ModalMode = "newDoc" | "newCat" | "renameCat" | "renameDoc";

/**
 * P0-4 目录树组件：目录 + 文档混挂（未归类挂虚拟「未归类」组）。
 * 第三轮乐享式交互：
 * - 「目录」标题行 hover 出「+」（新建菜单）/「···」（多选）
 * - 目录节点菜单：新建文档 / 新建子目录 / 重命名 / 删除（文档移根）；目录名可点击 → 目录视图
 * - 文档节点菜单：仅 重命名 / 删除（用户批注「保留重命名删除即可」）
 * - 多选模式：节点前 Checkbox（目录+文档），顶部操作条仅 批量删除（用户批注「只要删除即可」）
 * - 第四轮（T5）：打开文档 → 节点蓝底高亮 + 自动展开所在目录并滚动到可见（/spaces 不传 activeDocId 无选中态）
 */
export default function CategoryTree({
  kbId,
  refreshKey,
  canManage,
  onOpenDoc,
  onOpenCategory,
  onDocChanged,
  activeDocId,
  showHeader = true,
}: Props) {
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [documents, setDocuments] = useState<TreeNodeDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  // P0-4 第三轮：多选批量删除
  const [selectMode, setSelectMode] = useState(false);
  const [checkedDocs, setCheckedDocs] = useState<Set<number>>(new Set());
  const [checkedCats, setCheckedCats] = useState<Set<number>>(new Set());

  // P0-4 第四轮（T5）：滚动定位选中节点用
  const containerRef = useRef<HTMLDivElement>(null);
  // P0-4 v1.2：上传自足（「目录」行「+」菜单 → 上传文件；隐藏 input 选文件 → UploadModal 浮层，挂根目录）
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);

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

  // P0-4 第四轮（T5）：打开文档 → 自动展开其所在目录链（含「未归类」）并滚动到可见
  useEffect(() => {
    if (activeDocId == null) return;
    const doc = documents.find((d) => d.id === activeDocId);
    if (!doc) return;
    const chain: React.Key[] = [];
    let parentId: number | null = doc.category_id;
    const guard = new Set<number>();
    while (parentId != null && !guard.has(parentId)) {
      guard.add(parentId);
      chain.push(`cat-${parentId}`);
      parentId = categories.find((c) => c.id === parentId)?.parent_id ?? null;
    }
    if (doc.category_id == null) chain.push("uncategorized");
    setExpandedKeys((prev) => Array.from(new Set([...prev, ...chain])));
    const timer = setTimeout(() => {
      containerRef.current
        ?.querySelector(`[data-doc-id="${activeDocId}"]`)
        ?.scrollIntoView({ block: "nearest" });
    }, 50);
    return () => clearTimeout(timer);
  }, [activeDocId, documents, categories]);

  const catName = (id: number | null) =>
    id == null ? "未归类" : categories.find((c) => c.id === id)?.name ?? "未归类";

  const refresh = () => {
    fetchTree();
    onDocChanged?.();
  };

  // ---- 多选模式 ----
  const enterSelect = () => {
    setCheckedDocs(new Set());
    setCheckedCats(new Set());
    setSelectMode(true);
  };
  const exitSelect = () => {
    setSelectMode(false);
    setCheckedDocs(new Set());
    setCheckedCats(new Set());
  };
  const toggleDoc = (id: number) => {
    setCheckedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleCat = (id: number) => {
    setCheckedCats((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const checkedCount = checkedDocs.size + checkedCats.size;

  const batchDelete = () => {
    Modal.confirm({
      title: `删除选中的 ${checkedCount} 项？`,
      content: "文档将同时清理向量索引与物理文件，不可恢复；目录删除后其下文档移至根。",
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        if (checkedDocs.size > 0) {
          await documentApi.batchDelete(kbId, [...checkedDocs]);
        }
        for (const id of checkedCats) {
          await categoryApi.remove(kbId, id);
        }
        message.success(`已删除 ${checkedCount} 项`);
        exitSelect();
        refresh();
      },
    });
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
        {selectMode && canManage && (
          <Checkbox
            checked={checkedDocs.has(d.id)}
            onClick={(e) => e.stopPropagation()}
            onChange={() => toggleDoc(d.id)}
            style={{ marginRight: 4 }}
          />
        )}
        <span
          className={`${styles.nodeLabel} ${activeDocId === d.id ? styles.nodeLabelActive : ""}`}
          data-doc-id={d.id}
          onClick={() =>
            // P0-4 第三轮（T7）：上传文档也开 doc tab（只读正文），不再走 Modal 查看器
            onOpenDoc({
              id: d.id,
              filename: d.filename,
              source: d.source,
              categoryName: catName(d.category_id),
            })
          }
          title={d.filename}
        >
          {d.filename}
          {d.status !== "ready" && (
            <span className={styles.nodeStatus}>{d.status === "error" ? "（失败）" : "（处理中）"}</span>
          )}
        </span>
        {canManage && !selectMode && (
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                { key: "rename", label: "重命名", icon: <EditOutlined /> },
                { type: "divider" },
                { key: "delete", label: "删除", icon: <DeleteOutlined />, danger: true },
              ],
              onClick: ({ key, domEvent }) => {
                domEvent.stopPropagation();
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
            {selectMode && canManage && (
              <Checkbox
                checked={checkedCats.has(c.id)}
                onClick={(e) => e.stopPropagation()}
                onChange={() => toggleCat(c.id)}
                style={{ marginRight: 4 }}
              />
            )}
            <span
              className={styles.nodeLabel}
              onClick={() => onOpenCategory?.(c.id, c.name)}
              title={c.name}
            >
              {c.name}
            </span>
            {canManage && !selectMode && (
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

  const openNewCatModal = (c: CategoryInfo | null) => {
    setActiveCategory(c);
    setModalMode("newCat");
    setModalTitle(c ? `新建子目录（${c.name}）` : "新建文件夹");
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
      }
      refresh();
    } finally {
      setSubmitting(false);
    }
  };

  // 「目录」标题行「+」菜单（根级新建 / 上传文件，能力自足不依赖外部）
  const triggerUpload = () => fileInputRef.current?.click();

  const handleFileChosen = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // 允许重复选择同一文件
    if (files.length === 0) return;
    setUploadFiles(files);
    setUploadOpen(true);
  };

  const headerPlusMenu = {
    items: [
      { key: "newDoc", label: "新建在线文档", icon: <FileAddOutlined /> },
      { key: "newCat", label: "新建文件夹", icon: <PlusOutlined /> },
      { type: "divider" as const },
      { key: "upload", label: "上传文件", icon: <UploadOutlined /> },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === "newDoc") openNewDocModal(null);
      if (key === "newCat") openNewCatModal(null);
      if (key === "upload") triggerUpload();
    },
  };

  if (loading && categories.length === 0 && documents.length === 0) {
    return (
      <div className={styles.container}>
        <Spin size="small" />
      </div>
    );
  }

  return (
    <div className={styles.container} ref={containerRef}>
      {showHeader && (
        <div className={styles.treeHeader}>
          <span className={styles.treeHeaderTitle}>
            <AppstoreOutlined style={{ marginRight: 6 }} />
            目录
          </span>
          {canManage && (
            <span className={styles.headerActions}>
              <Dropdown trigger={["click"]} menu={headerPlusMenu}>
                <Tooltip title="新建">
                  <Button type="text" size="small" icon={<PlusOutlined />} />
                </Tooltip>
              </Dropdown>
              {!selectMode && (
                <Tooltip title="多选">
                  <Button type="text" size="small" icon={<EllipsisOutlined />} onClick={enterSelect} />
                </Tooltip>
              )}
            </span>
          )}
        </div>
      )}

      {/* 多选操作条（仅删除，用户批注「只要删除即可」） */}
      {selectMode && (
        <div className={styles.batchBar}>
          <span className={styles.batchCount}>已选 {checkedCount} 项</span>
          <Button size="small" danger disabled={checkedCount === 0} onClick={batchDelete}>
            删除
          </Button>
          <Button type="text" size="small" icon={<CloseOutlined />} onClick={exitSelect} />
        </div>
      )}

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

      {/* P0-4 v1.2：上传自足——隐藏文件选择 + UploadModal 浮层（挂根目录） */}
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
        categoryId={null}
        files={uploadFiles}
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          setUploadFiles([]);
        }}
        onUploaded={refresh}
      />

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
      </Modal>
    </div>
  );
}

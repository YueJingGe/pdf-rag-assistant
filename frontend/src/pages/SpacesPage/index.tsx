import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Layout,
  Menu,
  Button,
  Typography,
  Form,
  Input,
  Spin,
  Result,
  message,
  Popconfirm,
} from "antd";
import {
  ArrowLeftOutlined,
  SettingOutlined,
  FolderOpenOutlined,
  TeamOutlined,
  DeleteOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import CategoryTree from "../../components/CategoryTree";
import DocumentUpload from "../../components/DocumentUpload";
import {
  knowledgeBaseApi,
  PERSONAL_KB_NAME,
  type KnowledgeBase,
  type UserInfo,
} from "../../services/api";
import styles from "./index.module.less";

const { Sider, Content, Header } = Layout;

type MenuKey = "basic" | "docs";

interface Props {
  user: UserInfo;
  onLogout: () => void;
}

/**
 * /spaces/:kbId 知识库管理页（P0-4 第二轮，对齐乐享）：
 * 顶栏返回 + 左侧菜单（基本信息 / 目录与文档 / 成员与权限(占位) / 回收站(占位)）。
 * 文档点击统一 → 跳回主界面开 doc tab（第三轮 T7：上传文档也走 doc tab 只读，查看器仅在问答引用使用）。
 */
export default function SpacesPage({ user }: Props) {
  const { kbId } = useParams();
  const navigate = useNavigate();
  const kbIdNum = Number(kbId);
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [loading, setLoading] = useState(true);
  const [menuKey, setMenuKey] = useState<MenuKey>("basic");
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [treeRefreshKey, setTreeRefreshKey] = useState(0);

  const fetchKb = async () => {
    setLoading(true);
    try {
      const { data: kbs } = await knowledgeBaseApi.list();
      const found = kbs.find((k) => k.id === kbIdNum) ?? null;
      setKb(found);
      if (found) {
        form.setFieldsValue({ name: found.name, description: found.description });
      }
    } catch {
      setKb(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKb();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbIdNum]);

  const bumpTree = () => setTreeRefreshKey((k) => k + 1);

  const handleSaveBasic = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const { data } = await knowledgeBaseApi.update(kbIdNum, {
        name: values.name,
        description: values.description,
      });
      setKb(data);
      message.success("已保存");
    } catch (err: unknown) {
      const resp = (
        err as { response?: { status?: number; data?: { detail?: string } } }
      ).response;
      message.error(
        resp?.data?.detail ||
          (resp?.status === 403 ? "没有该知识库的管理权限" : "保存失败")
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteKb = async () => {
    if (!kb) return;
    await knowledgeBaseApi.delete(kb.id);
    message.success("知识库已删除");
    navigate("/");
  };

  if (loading) {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin />
      </div>
    );
  }

  if (!kb) {
    return (
      <Result
        status="404"
        title="知识库不存在"
        subTitle="可能已被删除或无权访问"
        extra={
          <Button type="primary" onClick={() => navigate("/")}>
            返回主界面
          </Button>
        }
      />
    );
  }

  return (
    <Layout style={{ height: "100vh", overflow: "hidden" }}>
      <Header className={styles.header}>
        <Button type="text" size="small" icon={<ArrowLeftOutlined />} onClick={() => navigate("/")}>
          返回
        </Button>
        <Typography.Text strong>知识库管理</Typography.Text>
        <Typography.Text type="secondary" ellipsis style={{ maxWidth: 300 }}>
          {kb.name}
        </Typography.Text>
      </Header>
      <Layout style={{ flex: 1, overflow: "hidden" }}>
        <Sider width={200} className={styles.sider}>
          <Menu
            mode="inline"
            selectedKeys={[menuKey]}
            onClick={({ key }) => setMenuKey(key as MenuKey)}
            style={{ border: "none" }}
            items={[
              { key: "basic", icon: <SettingOutlined />, label: "基本信息" },
              { key: "docs", icon: <FolderOpenOutlined />, label: "目录与文档" },
              { key: "members", icon: <TeamOutlined />, label: "成员与权限", disabled: true },
              { key: "recycle", icon: <DeleteOutlined />, label: "回收站", disabled: true },
            ]}
          />
          {/* P0-4 第五轮（T1）：个人知识库不可删除（识别锚点见 api.ts），隐藏删除按钮 */}
          {kb.name !== PERSONAL_KB_NAME && (
            <Popconfirm
              title="删除该知识库？"
              description="将同时删除库内文档与向量索引，不可恢复。"
              okText="删除"
              okButtonProps={{ danger: true }}
              onConfirm={handleDeleteKb}
            >
              <Button danger type="text" size="small" icon={<DeleteOutlined />} className={styles.deleteBtn}>
                删除知识库
              </Button>
            </Popconfirm>
          )}
        </Sider>
        <Content className={styles.content}>
          {menuKey === "basic" ? (
            <div className={styles.basicPanel}>
              <Typography.Title level={5} style={{ marginTop: 0 }}>
                基本信息
              </Typography.Title>
              <Form form={form} layout="vertical" style={{ maxWidth: 560 }}>
                <Form.Item
                  name="name"
                  label="知识库名称"
                  rules={[{ required: true, message: "请输入知识库名称" }]}
                >
                  <Input placeholder="知识库名称" />
                </Form.Item>
                <Form.Item name="description" label="知识库简介">
                  <Input.TextArea rows={4} placeholder="介绍一下这个知识库" showCount maxLength={200} />
                </Form.Item>
                <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSaveBasic}>
                  保存
                </Button>
              </Form>
            </div>
          ) : (
            <div className={styles.docsPanel}>
              <div className={styles.treeCol}>
                <Typography.Text
                  type="secondary"
                  style={{ fontSize: 12, padding: "4px 12px 8px", display: "block" }}
                >
                  目录结构（节点「···」菜单：新建文档 / 新建子目录 / 重命名 / 移动 / 删除）
                </Typography.Text>
                <CategoryTree
                  kbId={kb.id}
                  refreshKey={treeRefreshKey}
                  canManage
                  onOpenDoc={(doc) => navigate("/", { state: { openDoc: doc } })}
                  onDocChanged={bumpTree}
                />
              </div>
              <div className={styles.tableCol}>
                <DocumentUpload knowledgeBaseId={kb.id} onDocChange={bumpTree} />
              </div>
            </div>
          )}
        </Content>
      </Layout>
    </Layout>
  );
}

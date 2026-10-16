import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Layout, Tabs, Typography } from 'antd';
import {
  MessageOutlined, FileMarkdownOutlined, FolderOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import KnowledgeBaseSidebar from '../../components/KnowledgeBaseSidebar';
import ChatWindow from '../../components/ChatWindow';
import FeedbackDashboard from '../../components/FeedbackDashboard';
import DocumentViewer from '../../components/DocumentViewer';
import DocumentWorkbench from '../../components/DocumentWorkbench';
import CategoryView from '../../components/CategoryView';
import type { CitationClickInfo } from '../../components/CitationView';
import type { OpenableDoc } from '../../components/CategoryTree';
import { knowledgeBaseApi, type KnowledgeBase, type UserInfo } from '../../services/api';

const { Sider, Content, Header } = Layout;

// P0-4：文档工作台 tab key（key 与 docId 绑定，tab 可关闭）
const docTabKey = (docId: number) => `doc-${docId}`;
// P0-4 第三轮：目录视图 tab key
const catTabKey = (categoryId: number) => `dir-${categoryId}`;

interface Props {
  user: UserInfo;
  onLogout: () => void;
}

/**
 * 主界面（路由 "/"）：乐享式左导航 + editable-card Tabs（问AI/文档管理/检索调优/文档工作台）。
 * 登录门控由 App 层处理，本组件保证 user 非空。
 */
export default function MainPage({ user, onLogout }: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(() => {
    const saved = localStorage.getItem('selectedKB');
    return saved ? JSON.parse(saved) : null;
  });
  const [activeTab, setActiveTab] = useState('chat');
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [treeRefreshKey, setTreeRefreshKey] = useState(0);
  const [openDocs, setOpenDocs] = useState<OpenableDoc[]>([]); // P0-4：已打开的文档工作台 tabs
  // P0-4 第三轮：已打开的目录视图 tabs（点击目录树目录 → 打开目录视图，替代文档管理 tab）
  const [openCategories, setOpenCategories] = useState<{ id: number; name: string }[]>([]);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerCitation, setViewerCitation] = useState<CitationClickInfo>({ filename: '', page: 0, snippet: '' });

  const refreshSidebar = () => setSidebarRefreshKey((k) => k + 1);
  const bumpTree = () => setTreeRefreshKey((k) => k + 1);
  // 任何文档增删改 → 目录树与侧栏文档计数同步刷新
  const handleDocChanged = () => { bumpTree(); refreshSidebar(); };

  const handleCitationClick = (info: CitationClickInfo) => {
    setViewerCitation(info);
    setViewerOpen(true);
  };

  // Persist selectedKB to localStorage
  useEffect(() => {
    if (selectedKB) {
      localStorage.setItem('selectedKB', JSON.stringify(selectedKB));
    } else {
      localStorage.removeItem('selectedKB');
    }
  }, [selectedKB]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('selectedKB');
    onLogout();
  };

  // 登录后校验 localStorage 恢复的 selectedKB 是否在当前用户可见列表内
  // （防止用户 A 登录后看到用户 B 私有知识库名称的越权显示）
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const { data: kbs } = await knowledgeBaseApi.list();
        const saved = localStorage.getItem('selectedKB');
        const savedKB: KnowledgeBase | null = saved ? JSON.parse(saved) : null;
        if (savedKB?.id && kbs.some((kb) => kb.id === savedKB.id)) {
          return; // 恢复的知识库仍可见，保持不动
        }
        setSelectedKB(kbs[0] ?? null); // 不可见则回退到第一个可见 KB，无则普通聊天
      } catch {
        setSelectedKB(null);
      }
    })();
  }, [user]);

  const userRole = user?.is_admin ? 'owner' : 'member';
  const canManageDocs = userRole === 'owner' || userRole === 'member';

  const isPlainChat = !selectedKB;

  // P0-4：切换知识库 → 清空已打开的文档工作台/目录视图 tabs，回到问答页
  const handleSelectKB = (kb: KnowledgeBase | null) => {
    setSelectedKB(kb);
    setOpenDocs([]);
    setOpenCategories([]);
    setActiveTab('chat');
  };

  // 普通聊天模式没有文档管理/工作台，强制回到 chat tab
  useEffect(() => {
    if (isPlainChat && activeTab !== 'chat') {
      setActiveTab('chat');
    }
  }, [isPlainChat, activeTab]);

  // P0-4：打开文档工作台（同文档去重，仅激活）
  const openDoc = (doc: OpenableDoc) => {
    setOpenDocs((prev) => (prev.some((d) => d.id === doc.id) ? prev : [...prev, doc]));
    setActiveTab(docTabKey(doc.id));
  };

  // P0-4：关闭文档工作台 tab；若关的是当前 tab，切到最后一个未关闭的
  const closeDoc = (key: string) => {
    setOpenDocs((prev) => {
      const next = prev.filter((d) => docTabKey(d.id) !== key);
      if (activeTab === key) {
        setActiveTab(next.length > 0 ? docTabKey(next[next.length - 1].id) : 'chat');
      }
      return next;
    });
  };

  // P0-4 第三轮：目录视图 tab 打开/关闭/改名（同文档 tab 交互）
  const openCategory = (categoryId: number, name: string) => {
    setOpenCategories((prev) =>
      prev.some((c) => c.id === categoryId) ? prev : [...prev, { id: categoryId, name }]
    );
    setActiveTab(catTabKey(categoryId));
  };

  const closeCategory = (key: string) => {
    setOpenCategories((prev) => {
      const next = prev.filter((c) => catTabKey(c.id) !== key);
      if (activeTab === key) {
        setActiveTab(next.length > 0 ? catTabKey(next[next.length - 1].id) : 'chat');
      }
      return next;
    });
  };

  const renameCategoryTab = (categoryId: number, newName: string) => {
    setOpenCategories((prev) =>
      prev.map((c) => (c.id === categoryId ? { ...c, name: newName } : c))
    );
  };

  // P0-4 第二轮：管理页（/spaces）点击在线文档 → location.state 携带 openDoc 跳回主界面打开工作台
  useEffect(() => {
    const st = location.state as { openDoc?: OpenableDoc } | null;
    if (st?.openDoc) {
      openDoc(st.openDoc);
      navigate(location.pathname, { replace: true, state: null }); // 清 state 防刷新重复打开
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  const tabItems = [
    {
      key: 'chat',
      label: <span><MessageOutlined /> {isPlainChat ? '普通聊天' : '问AI'}</span>,
      children: (
        <div style={{ height: 'calc(100vh - 112px)', overflow: 'hidden' }}>
          <ChatWindow
            knowledgeBaseId={selectedKB?.id ?? null}
            knowledgeBaseName={selectedKB?.name ?? ''}
            userRole={userRole}
            onCitationClick={handleCitationClick}
            onDocSavedToKb={handleDocChanged}
          />
        </div>
      ),
    },
    ...(user?.is_admin && !isPlainChat ? [{
      key: 'feedback',
      label: <span><BarChartOutlined /> 检索调优</span>,
      children: (
        <div style={{ height: 'calc(100vh - 112px)', overflow: 'auto', padding: 16 }}>
          <FeedbackDashboard knowledgeBaseId={selectedKB?.id ?? null} />
        </div>
      ),
    }] : []),
    // P0-4 第三轮：动态目录视图 tabs（乐享文件夹页：inline 改名 + 新建/上传 + 子目录/文档列表）
    ...openCategories.map((cat) => ({
      key: catTabKey(cat.id),
      label: <span><FolderOutlined /> {cat.name}</span>,
      closable: true,
      children: (
        <div style={{ height: 'calc(100vh - 112px)', overflow: 'hidden' }}>
          <CategoryView
            kbId={selectedKB!.id}
            categoryId={cat.id}
            name={cat.name}
            canManage={canManageDocs}
            onChanged={handleDocChanged}
            onOpenDoc={openDoc}
            onOpenCategory={openCategory}
            onRenamed={renameCategoryTab}
            onMissing={() => closeCategory(catTabKey(cat.id))}
          />
        </div>
      ),
    })),
    // P0-4：动态文档工作台 tabs（在线文档可编辑，上传文档只读渲染）
    ...openDocs.map((doc) => ({
      key: docTabKey(doc.id),
      label: <span><FileMarkdownOutlined /> {doc.filename}</span>,
      closable: true,
      children: (
        <div style={{ height: 'calc(100vh - 112px)', overflow: 'hidden' }}>
          <DocumentWorkbench
            kbId={selectedKB!.id}
            docId={doc.id}
            filename={doc.filename}
            source={doc.source}
            categoryName={doc.categoryName}
            onSaved={handleDocChanged}
            onCitationClick={handleCitationClick}
          />
        </div>
      ),
    })),
  ];

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <Header style={{ background: '#fff', borderBottom: '1px solid #f0f0f0', padding: '0 24px', display: 'flex', alignItems: 'center', height: 56 }}>
        <span style={{ fontSize: 16, fontWeight: 600 }}>📚 PDF RAG 智能问答系统</span>
      </Header>
      <Layout style={{ flex: 1, overflow: 'hidden' }}>
        <Sider width={280} style={{ background: '#fff', borderRight: '1px solid #f0f0f0', overflow: 'auto' }}>
          <KnowledgeBaseSidebar
            selectedId={selectedKB?.id ?? null}
            onSelect={handleSelectKB}
            refreshKey={sidebarRefreshKey}
            user={user}
            onLogout={handleLogout}
            canManage={canManageDocs}
            onGoChat={() => setActiveTab('chat')}
            chatActive={activeTab === 'chat'}
            treeRefreshKey={treeRefreshKey}
            onDocChanged={handleDocChanged}
            onOpenDoc={openDoc}
            onOpenCategory={openCategory}
          />
        </Sider>
        <Content style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            type="editable-card"
            hideAdd
            onEdit={(targetKey, action) => {
              if (action === 'remove') {
                const key = String(targetKey);
                if (key.startsWith('dir-')) closeCategory(key);
                else closeDoc(key);
              }
            }}
            centered
            style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
            items={tabItems}
          />
        </Content>
      </Layout>
      <DocumentViewer
        open={viewerOpen}
        onClose={() => setViewerOpen(false)}
        knowledgeBaseId={selectedKB?.id ?? null}
        filename={viewerCitation.filename}
        snippet={viewerCitation.snippet}
        page={viewerCitation.page}
      />
    </Layout>
  );
}

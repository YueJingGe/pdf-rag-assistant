import React, { useState, useEffect } from 'react';
import { Layout, Tabs, Button, Typography, message } from 'antd';
import {
  MessageOutlined, FileOutlined, FileMarkdownOutlined,
  BarChartOutlined, LoginOutlined,
} from '@ant-design/icons';
import KnowledgeBaseSidebar from './components/KnowledgeBaseSidebar';
import DocumentUpload from './components/DocumentUpload';
import ChatWindow from './components/ChatWindow';
import LoginModal from './components/LoginModal';
import FeedbackDashboard from './components/FeedbackDashboard';
import DocumentViewer from './components/DocumentViewer';
import DocumentWorkbench from './components/DocumentWorkbench';
import type { CitationClickInfo } from './components/CitationView';
import type { OpenableDoc } from './components/CategoryTree';
import { authApi, knowledgeBaseApi, type KnowledgeBase, type UserInfo } from './services/api';

const { Sider, Content, Header } = Layout;

// P0-4：文档工作台 tab key（key 与 docId 绑定，tab 可关闭）
const docTabKey = (docId: number) => `doc-${docId}`;

export default function App() {
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(() => {
    const saved = localStorage.getItem('selectedKB');
    return saved ? JSON.parse(saved) : null;
  });
  const [activeTab, setActiveTab] = useState('chat');
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [treeRefreshKey, setTreeRefreshKey] = useState(0);
  const [openDocs, setOpenDocs] = useState<OpenableDoc[]>([]); // P0-4：已打开的文档工作台 tabs
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

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      authApi.getMe().then(({ data }) => setUser(data)).catch(() => {
        localStorage.removeItem('token');
      });
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('selectedKB');
    setUser(null);
    setSelectedKB(null);
    setOpenDocs([]);
    message.success('已退出登录');
  };

  // 登录后校验 localStorage 恢复的 selectedKB 是否在当前用户可见列表内
  // （防止用户 A 登录后看到用户 B 私有知识库名称的越权显示）
  const restoreVisibleKB = async () => {
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
  };

  const handleLoginSuccess = (userInfo: UserInfo, token: string) => {
    localStorage.setItem('token', token);
    setUser(userInfo);
    setLoginOpen(false);
    message.success(`欢迎回来，${userInfo.display_name}`);
    restoreVisibleKB();
  };

  // 监听 401 登录过期事件（axios 拦截器 / useSSE 广播），弹出登录框
  useEffect(() => {
    const handler = () => {
      setUser(null);
      setLoginOpen(true);
      message.warning('登录已过期，请重新登录');
    };
    window.addEventListener('auth:unauthorized', handler);
    return () => window.removeEventListener('auth:unauthorized', handler);
  }, []);

  const userRole = user?.is_admin ? 'owner' : 'member';
  const canManageDocs = userRole === 'owner' || userRole === 'member';

  const isPlainChat = !selectedKB;

  // P0-4：切换知识库 → 清空已打开的文档工作台 tabs，回到问答页
  const handleSelectKB = (kb: KnowledgeBase | null) => {
    setSelectedKB(kb);
    setOpenDocs([]);
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
    ...(canManageDocs && !isPlainChat ? [{
      key: 'docs',
      label: <span><FileOutlined /> 文档管理</span>,
      children: (
        <div style={{ height: 'calc(100vh - 112px)', overflow: 'hidden' }}>
          <DocumentUpload knowledgeBaseId={selectedKB?.id ?? null} onDocChange={handleDocChanged} />
        </div>
      ),
    }] : []),
    ...(user?.is_admin && !isPlainChat ? [{
      key: 'feedback',
      label: <span><BarChartOutlined /> 检索调优</span>,
      children: (
        <div style={{ height: 'calc(100vh - 112px)', overflow: 'auto', padding: 16 }}>
          <FeedbackDashboard knowledgeBaseId={selectedKB?.id ?? null} />
        </div>
      ),
    }] : []),
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
          />
        </div>
      ),
    })),
  ];

  // 未登录：不渲染业务组件，保证登录前不发起任何业务请求
  if (!user) {
    return (
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#f5f7fa' }}>
        <span style={{ fontSize: 40, marginBottom: 16 }}>📚</span>
        <Typography.Title level={3} style={{ marginBottom: 8 }}>PDF RAG 智能问答系统</Typography.Title>
        <Typography.Text type="secondary" style={{ marginBottom: 24 }}>
          多知识库 RAG 问答 · 混合检索 · 引用溯源
        </Typography.Text>
        <Button type="primary" icon={<LoginOutlined />} onClick={() => setLoginOpen(true)}>
          登录 / 注册
        </Button>
        <LoginModal open={loginOpen} onCancel={() => setLoginOpen(false)} onSuccess={handleLoginSuccess} />
      </div>
    );
  }

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
            onGoUpload={() => setActiveTab('docs')}
            onGoChat={() => setActiveTab('chat')}
            chatActive={activeTab === 'chat'}
            treeRefreshKey={treeRefreshKey}
            onDocChanged={handleDocChanged}
            onOpenDoc={openDoc}
            onOpenViewer={(filename) => {
              setViewerCitation({ filename, page: 0, snippet: '' });
              setViewerOpen(true);
            }}
          />
        </Sider>
        <Content style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            type="editable-card"
            hideAdd
            onEdit={(targetKey, action) => {
              if (action === 'remove') closeDoc(String(targetKey));
            }}
            centered
            style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
            items={tabItems}
          />
        </Content>
      </Layout>
      <LoginModal open={loginOpen} onCancel={() => setLoginOpen(false)} onSuccess={handleLoginSuccess} />
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

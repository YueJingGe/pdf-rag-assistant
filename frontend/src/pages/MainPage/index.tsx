import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Layout } from 'antd';
import KnowledgeBaseSidebar from '../../components/KnowledgeBaseSidebar';
import ChatWindow from '../../components/ChatWindow';
import FeedbackDashboard from '../../components/FeedbackDashboard';
import DocumentViewer from '../../components/DocumentViewer';
import DocumentWorkbench from '../../components/DocumentWorkbench';
import CategoryView from '../../components/CategoryView';
import type { CitationClickInfo } from '../../components/CitationView';
import type { OpenableDoc } from '../../components/CategoryTree';
import { knowledgeBaseApi, type KnowledgeBase, type UserInfo } from '../../services/api';

// P0-4 第五轮（T4）：移除全局 Header，对齐乐享（无顶部系统标题白条）；Sider/Content 铺满视口
const { Sider, Content } = Layout;

// P0-4 第四轮（T1）：主区域单视图（移除 tabs）——问AI / 检索调优(admin) / 目录视图 / 文档工作台
type MainView =
  | { type: 'chat' }
  | { type: 'feedback' }
  | { type: 'category'; id: number; name: string }
  | { type: 'doc'; doc: OpenableDoc };

interface Props {
  user: UserInfo;
  onLogout: () => void;
}

/**
 * 主界面（路由 "/"）：乐享式左导航 + 主区域单视图（第四轮 T1：移除顶部 tabs，对齐乐享；
 * 第五轮 T4：移除全局 Header）。
 * - 问AI 页：ChatWindow（空态=乐享欢迎页「今天从哪里开始?」）
 * - 目录视图：CategoryView（点目录进入，点文档切文档视图，头部关闭返回）
 * - 文档工作台：DocumentWorkbench（左正文 + 右问AI 面板，头部关闭返回）
 * - 不支持同时打开多个文档（点树即替换）
 * 登录门控由 App 层处理，本组件保证 user 非空。
 */
export default function MainPage({ user, onLogout }: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const [selectedKB, setSelectedKB] = useState<KnowledgeBase | null>(() => {
    const saved = localStorage.getItem('selectedKB');
    return saved ? JSON.parse(saved) : null;
  });
  // P0-4 第四轮（T1）：单视图状态（替代原 activeTab/openDocs/openCategories 多 tab 体系）
  const [view, setView] = useState<MainView>({ type: 'chat' });
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [treeRefreshKey, setTreeRefreshKey] = useState(0);
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
        setSelectedKB(kbs[0] ?? null); // 不可见则回退到第一个可见 KB
      } catch {
        setSelectedKB(null);
      }
    })();
  }, [user]);

  const userRole = user?.is_admin ? 'owner' : 'member';
  const canManageDocs = userRole === 'owner' || userRole === 'member';

  // P0-4 第四轮（T4）：库切换器仅列知识库（普通聊天 = 问答模式清空信息源）；切库一律回问AI 页
  const handleSelectKB = (kb: KnowledgeBase | null) => {
    setSelectedKB(kb);
    setView({ type: 'chat' });
  };

  // 打开文档（单视图：直接替换当前视图）
  const openDoc = (doc: OpenableDoc) => {
    setView({ type: 'doc', doc });
  };

  // 打开目录视图
  const openCategory = (categoryId: number, name: string) => {
    setView({ type: 'category', id: categoryId, name });
  };

  // 目录 inline 改名 → 同步当前视图标题
  const renameCategoryView = (categoryId: number, newName: string) => {
    setView((prev) =>
      prev.type === 'category' && prev.id === categoryId ? { ...prev, name: newName } : prev
    );
  };

  // 目录在侧栏被删除 / 用户关闭目录视图 → 回问AI 页
  const closeCategoryView = () => setView({ type: 'chat' });

  // P0-4 第二轮：管理页（/spaces）点击在线文档 → location.state 携带 openDoc 跳回主界面打开
  useEffect(() => {
    const st = location.state as { openDoc?: OpenableDoc } | null;
    if (st?.openDoc) {
      openDoc(st.openDoc);
      navigate(location.pathname, { replace: true, state: null }); // 清 state 防刷新重复打开
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  const goChat = () => setView({ type: 'chat' });

  return (
    <Layout style={{ height: '100vh', overflow: 'hidden' }}>
      <Layout style={{ flex: 1, overflow: 'hidden' }}>
        <Sider width={280} style={{ background: '#fff', borderRight: '1px solid #f0f0f0', overflow: 'auto' }}>
          <KnowledgeBaseSidebar
            selectedId={selectedKB?.id ?? null}
            onSelect={handleSelectKB}
            refreshKey={sidebarRefreshKey}
            user={user}
            onLogout={handleLogout}
            canManage={canManageDocs}
            onGoChat={goChat}
            chatActive={view.type === 'chat'}
            treeRefreshKey={treeRefreshKey}
            onDocChanged={handleDocChanged}
            onOpenDoc={openDoc}
            onOpenCategory={openCategory}
            onGoFeedback={user?.is_admin ? () => setView({ type: 'feedback' }) : undefined}
            feedbackActive={view.type === 'feedback'}
            activeDocId={view.type === 'doc' ? view.doc.id : undefined}
          />
        </Sider>
        <Content style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* P0-4 第四轮（T1）：单视图渲染（不再用 Tabs；同时只存在一个视图） */}
          {view.type === 'chat' && (
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <ChatWindow
                knowledgeBaseId={selectedKB?.id ?? null}
                knowledgeBaseName={selectedKB?.name ?? ''}
                userRole={userRole}
                onCitationClick={handleCitationClick}
                onDocSavedToKb={handleDocChanged}
              />
            </div>
          )}
          {view.type === 'feedback' && (
            <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 16 }}>
              <FeedbackDashboard knowledgeBaseId={selectedKB?.id ?? null} />
            </div>
          )}
          {view.type === 'category' && selectedKB && (
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <CategoryView
                kbId={selectedKB.id}
                categoryId={view.id}
                name={view.name}
                canManage={canManageDocs}
                onChanged={handleDocChanged}
                onOpenDoc={openDoc}
                onOpenCategory={openCategory}
                onRenamed={renameCategoryView}
                onMissing={closeCategoryView}
                onClose={goChat}
              />
            </div>
          )}
          {view.type === 'doc' && selectedKB && (
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <DocumentWorkbench
                key={`${selectedKB.id}-${view.doc.id}`}
                kbId={selectedKB.id}
                docId={view.doc.id}
                filename={view.doc.filename}
                source={view.doc.source}
                categoryName={view.doc.categoryName}
                onSaved={handleDocChanged}
                onCitationClick={handleCitationClick}
                onClose={goChat}
              />
            </div>
          )}
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

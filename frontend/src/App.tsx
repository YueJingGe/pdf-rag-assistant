import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Button, Typography, message } from 'antd';
import { LoginOutlined } from '@ant-design/icons';
import MainPage from './pages/MainPage';
import SpacesPage from './pages/SpacesPage';
import LoginModal from './components/LoginModal';
import { authApi, type UserInfo } from './services/api';

/**
 * 路由容器 + 登录门控（P0-4 第二轮引入 react-router-dom）：
 *   /              → 主界面（问AI / 目录树 / 文档工作台）
 *   /spaces/:kbId  → 知识库管理页（基本信息 / 目录与文档）
 * 未登录：只渲染登录引导页，业务组件与业务请求都不出现。
 */
export default function App() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);

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
    setUser(null);
    message.success('已退出登录');
  };

  const handleLoginSuccess = (userInfo: UserInfo, token: string) => {
    localStorage.setItem('token', token);
    setUser(userInfo);
    setLoginOpen(false);
    message.success(`欢迎回来，${userInfo.display_name}`);
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
    <>
      <Routes>
        <Route path="/" element={<MainPage user={user} onLogout={handleLogout} />} />
        <Route path="/spaces/:kbId" element={<SpacesPage user={user} onLogout={handleLogout} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <LoginModal open={loginOpen} onCancel={() => setLoginOpen(false)} onSuccess={handleLoginSuccess} />
    </>
  );
}

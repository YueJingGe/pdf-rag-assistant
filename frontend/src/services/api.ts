import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

// Inject auth token if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
  permission: string;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentInfo {
  id: number;
  knowledge_base_id: number;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  status: string;
  error_message: string;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  images?: string[];
  file_name?: string;
  citations?: Citation[];
  created_at: string;
}

export interface Citation {
  filename: string;
  page: number;
  snippet: string;
}

export interface ConversationInfo {
  id: number;
  knowledge_base_id: number;
  title: string;
}

export interface UserInfo {
  id: number;
  username: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
}

export interface RetrievalChunk {
  content: string;
  metadata: Record<string, unknown>;
}

export interface RetrievalDebug {
  chunks: RetrievalChunk[];
  retrieval_time_ms: number;
  strategy: string;
}

export interface FeedbackStats {
  total: number;
  relevant: number;
  irrelevant: number;
  relevance_rate: number;
}

export const authApi = {
  register: (data: { username: string; email: string; password: string; display_name?: string }) =>
    api.post('/auth/register', data),
  login: (username: string, password: string) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    return api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  getMe: () => api.get<UserInfo>('/auth/me'),
};

export const knowledgeBaseApi = {
  list: () => api.get<KnowledgeBase[]>('/knowledge_bases'),
  get: (id: number) => api.get<KnowledgeBase>(`/knowledge_bases/${id}`),
  create: (data: { name: string; description?: string }) =>
    api.post<KnowledgeBase>('/knowledge_bases', data),
  update: (id: number, data: { name?: string; description?: string }) =>
    api.put<KnowledgeBase>(`/knowledge_bases/${id}`, data),
  delete: (id: number) => api.delete(`/knowledge_bases/${id}`),
};

export interface DocumentContent {
  filename: string;
  content: string;
  page_count: number;
}

export const documentApi = {
  list: (kbId: number) =>
    api.get<DocumentInfo[]>(`/knowledge_bases/${kbId}/documents`),
  upload: (kbId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<DocumentInfo>(`/knowledge_bases/${kbId}/documents`, formData);
  },
  getContent: (kbId: number, docId: number) =>
    api.get<DocumentContent>(`/knowledge_bases/${kbId}/documents/${docId}/content`),
  getContentBySource: (kbId: number, sourceFilename: string) =>
    api.get<DocumentContent>(`/knowledge_bases/${kbId}/documents/by_source`, { params: { source_filename: sourceFilename } }),
  rename: (kbId: number, docId: number, filename: string) =>
    api.put<DocumentInfo>(`/knowledge_bases/${kbId}/documents/${docId}/rename`, { filename }),
  delete: (kbId: number, docId: number) =>
    api.delete(`/knowledge_bases/${kbId}/documents/${docId}`),
  batchDelete: (kbId: number, docIds: number[]) =>
    api.post(`/knowledge_bases/${kbId}/documents/batch_delete`, { doc_ids: docIds }),
};

export interface FileExtractResult {
  file_id: string;
  filename: string;
  content: string;
}

export const chatApi = {
  listConversations: (kbId: number) =>
    api.get<ConversationInfo[]>(`/chat/conversations/${kbId}`),
  getMessages: (conversationId: number) =>
    api.get<ChatMessage[]>(`/chat/messages/${conversationId}`),
  deleteConversation: (conversationId: number) =>
    api.delete(`/chat/conversations/${conversationId}`),
  uploadFile: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<FileExtractResult>('/chat/upload-file', formData);
  },
};

export const feedbackApi = {
  create: (data: {
    message_id: number;
    knowledge_base_id: number;
    question: string;
    chunk_content: string;
    chunk_metadata?: Record<string, unknown>;
    is_relevant: boolean;
  }) => api.post('/feedback', data),
  stats: (kbId: number) => api.get<FeedbackStats>(`/feedback/stats/${kbId}`),
  export: (kbId: number) => api.get(`/feedback/export/${kbId}`),
};

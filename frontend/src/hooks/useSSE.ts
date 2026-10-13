import { useCallback, useRef, useState } from 'react';
import type { Citation, RetrievalDebug } from '../services/api';

interface SSEState {
  loading: boolean;
  content: string;
  citations: Citation[];
  conversationId: number | null;
  retrievalDebug: RetrievalDebug | null;
  error: string | null;
}

interface SendOptions {
  knowledgeBaseId: number | null;
  question: string;
  conversationId?: number;
  useHyde?: boolean;
  images?: string[];  // base64 data URIs for multimodal chat
  fileContent?: string;  // extracted text from uploaded file
  fileName?: string;  // original filename
  webSearch?: boolean;  // enable web search for plain chat
}

export function useSSE() {
  const [state, setState] = useState<SSEState>({
    loading: false,
    content: '',
    citations: [],
    conversationId: null,
    retrievalDebug: null,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async (options: SendOptions) => {
    const { knowledgeBaseId, question, conversationId, useHyde = false, images, fileContent, fileName, webSearch } = options;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({
      loading: true, content: '', citations: [],
      conversationId: conversationId ?? null, retrievalDebug: null, error: null,
    });

    try {
      const token = localStorage.getItem('token');
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const body: Record<string, unknown> = {
        knowledge_base_id: knowledgeBaseId || null,
        question,
        conversation_id: conversationId ?? null,
        use_hyde: useHyde,
      };
      if (images && images.length > 0) {
        body.images = images;
      }
      if (fileContent) {
        body.file_content = fileContent;
        body.file_name = fileName;
      }
      if (webSearch) {
        body.web_search = true;
      }

      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      // SSE 走原生 fetch 不经过 axios 拦截器，401 需单独广播登录过期事件
      if (response.status === 401) {
        localStorage.removeItem('token');
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
        throw new Error('登录已过期，请重新登录');
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
            continue;
          }
          if (!line.startsWith('data:')) continue;

          const dataStr = line.slice(5).trim();
          if (!dataStr) continue;

          try {
            const data = JSON.parse(dataStr);

            switch (currentEvent) {
              case 'token':
                if (data.content) {
                  setState((prev) => ({ ...prev, content: prev.content + data.content }));
                }
                break;
              case 'citations':
                if (data.citations) {
                  setState((prev) => ({ ...prev, citations: data.citations }));
                }
                break;
              case 'conversation':
                if (data.conversation_id) {
                  setState((prev) => ({ ...prev, conversationId: data.conversation_id }));
                }
                break;
              case 'retrieval_debug':
                setState((prev) => ({ ...prev, retrievalDebug: data }));
                break;
              case 'done':
                setState((prev) => ({ ...prev, loading: false }));
                break;
              default:
                if (data.content && typeof data.content === 'string' && !data.citations) {
                  setState((prev) => ({ ...prev, content: prev.content + data.content }));
                }
                if (data.citations) {
                  setState((prev) => ({ ...prev, citations: data.citations }));
                }
                if (data.conversation_id) {
                  setState((prev) => ({ ...prev, conversationId: data.conversation_id }));
                }
            }
            currentEvent = '';
          } catch {
            // skip malformed JSON
          }
        }
      }

      setState((prev) => ({ ...prev, loading: false }));
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setState((prev) => ({
        ...prev,
        loading: false,
        error: err instanceof Error ? err.message : 'Unknown error',
      }));
    }
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({ ...prev, loading: false }));
  }, []);

  const setConversationId = useCallback((id: number | null) => {
    setState((prev) => ({ ...prev, conversationId: id }));
  }, []);

  return { ...state, send, abort, setConversationId };
}

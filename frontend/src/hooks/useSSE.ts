import { useCallback, useRef, useState } from 'react';
import type { AgentIntent, Citation, RetrievalDebug, ToolTraceItem } from '../services/api';

interface SSEState {
  loading: boolean;
  content: string;
  citations: Citation[];
  conversationId: number | null;
  retrievalDebug: RetrievalDebug | null;
  error: string | null;
  // P0-3a Agent 模式新增：意图分类结果与工具调用轨迹
  intent: AgentIntent | null;
  toolEvents: ToolTraceItem[];
}

interface SendOptions {
  knowledgeBaseId: number | null;
  // P0-4 第二轮：多库信息源（len>1 时后端走多库合并链；Agent 模式不传，仅作用主库）
  knowledgeBaseIds?: number[];
  // P0-4 第三轮（T7/T8）：文档级信息源（与 knowledgeBaseId 同传时后端切 doc_scoped 轻流式，不落会话）
  documentId?: number;
  // P0-4 第五轮（T6）：文档级多选（目录勾选展开的文档集合；与 knowledgeBaseIds 可并存=多范围合并链，落会话；Agent 模式不传）
  documentIds?: number[];
  question: string;
  conversationId?: number;
  useHyde?: boolean;
  images?: string[];  // base64 data URIs for multimodal chat
  fileContent?: string;  // extracted text from uploaded file
  fileName?: string;  // original filename
  webSearch?: boolean;  // enable web search for plain chat
  useAgent?: boolean;  // P0-3a：走 /api/chat/agent/stream（意图分类 + 工具调用）
}

export function useSSE() {
  const [state, setState] = useState<SSEState>({
    loading: false,
    content: '',
    citations: [],
    conversationId: null,
    retrievalDebug: null,
    error: null,
    intent: null,
    toolEvents: [],
  });
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(async (options: SendOptions) => {
    const { knowledgeBaseId, knowledgeBaseIds, documentId, documentIds, question, conversationId, useHyde = false, images, fileContent, fileName, webSearch, useAgent = false } = options;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({
      loading: true, content: '', citations: [],
      conversationId: conversationId ?? null, retrievalDebug: null, error: null,
      intent: null, toolEvents: [],
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
      if (!useAgent && knowledgeBaseIds && knowledgeBaseIds.length > 1) {
        body.knowledge_base_ids = knowledgeBaseIds;
      }
      if (documentId) {
        body.document_id = documentId;
      }
      if (!useAgent && documentIds && documentIds.length > 0) {
        body.document_ids = documentIds;
      }
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

      const response = await fetch(
        useAgent ? '/api/chat/agent/stream' : '/api/chat/stream',
        {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          signal: controller.signal,
        }
      );

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
              case 'intent':
                if (data.intent === 'rag' || data.intent === 'tool' || data.intent === 'plain') {
                  setState((prev) => ({ ...prev, intent: data.intent }));
                }
                break;
              case 'tool_call':
                if (data.name) {
                  setState((prev) => ({
                    ...prev,
                    toolEvents: [...prev.toolEvents, {
                      name: data.name,
                      argsSummary: data.args_summary || '',
                      status: 'running',
                      durationMs: null,
                      round: data.round ?? 0,
                    }],
                  }));
                }
                break;
              case 'tool_result':
                if (data.name) {
                  setState((prev) => {
                    // 回填最后一个同名 running 项（tool_call → tool_result 成对按序到达）
                    const events = [...prev.toolEvents];
                    for (let i = events.length - 1; i >= 0; i--) {
                      if (events[i].name === data.name && events[i].status === 'running') {
                        events[i] = {
                          ...events[i],
                          status: data.status ?? 'error',
                          durationMs: data.duration_ms ?? null,
                          resultSummary: data.result_summary || '',
                          round: data.round ?? events[i].round,
                        };
                        break;
                      }
                    }
                    return { ...prev, toolEvents: events };
                  });
                }
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

"""LCEL-based RAG chain for retrieval-augmented generation."""

from __future__ import annotations

import time
import numpy as np
from typing import AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage

from app.core.config import settings
from app.core.vector_store import vector_store_manager
from app.core.retrieval import hyde_retrieve
from app.core.embeddings import get_embedding_model
from app.utils.logging import get_langfuse_handler, logger


# ======================== Semantic Cache ========================
class SemanticCache:
    """In-memory semantic cache for RAG responses.

    Compares question embeddings using cosine similarity. If a new question
    is similar enough (>= threshold) to a cached one, returns the cached answer
    without calling the LLM.
    """

    def __init__(self, similarity_threshold: float = 0.93):
        self.threshold = similarity_threshold
        self._cache: dict[int, list[dict]] = {}  # kb_id -> [{embedding, answer, citations}]
        self._embedding_model = None

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            self._embedding_model = get_embedding_model()
        return self._embedding_model

    def _cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        a = np.array(vec_a)
        b = np.array(vec_b)
        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        return float(dot / norm) if norm > 0 else 0.0

    def get(self, knowledge_base_id: int, question: str) -> dict | None:
        """Check cache. Returns cached result or None."""
        entries = self._cache.get(knowledge_base_id, [])
        if not entries:
            return None

        question_embedding = self.embedding_model.embed_query(question)

        for entry in entries:
            similarity = self._cosine_similarity(question_embedding, entry["embedding"])
            if similarity >= self.threshold:
                logger.info(f"Cache HIT (similarity={similarity:.3f}) for: {question[:50]}")
                return {"answer": entry["answer"], "citations": entry["citations"]}

        return None

    def put(self, knowledge_base_id: int, question: str, answer: str, citations: list[dict]):
        """Store a response in cache."""
        question_embedding = self.embedding_model.embed_query(question)
        if knowledge_base_id not in self._cache:
            self._cache[knowledge_base_id] = []

        # Limit cache size per KB to 50 entries (LRU-like: drop oldest)
        if len(self._cache[knowledge_base_id]) >= 50:
            self._cache[knowledge_base_id].pop(0)

        self._cache[knowledge_base_id].append({
            "embedding": question_embedding,
            "answer": answer,
            "citations": citations,
        })

    def invalidate(self, knowledge_base_id: int):
        """Clear cache for a KB (e.g., after document changes)."""
        self._cache.pop(knowledge_base_id, None)


semantic_cache = SemanticCache()
# ===============================================================

# 保留最近 5 轮对话注入 LLM Prompt
MAX_HISTORY_ROUNDS = 3

# Prompt 规则第 7 条要求 LLM 理解对话上下文、避免重复回答

RAG_SYSTEM_PROMPT = """基于以下参考资料回答问题。

参考资料：
{context}

规则：
1. 仔细阅读所有片段，注意条件性描述（如"体重低于XX"）和LaTeX格式（$60\\mathrm{{kg}}$即60kg）
2. 严格基于参考资料回答，不编造信息
3. 用Markdown格式化：标题分隔主题、列表展示要点、**加粗**关键信息
4. 标注来源：[来源: 文件名, 第X页]
5. 仅当所有片段都无相关信息时才说"未找到"
6. 参考对话历史避免重复回答"""



RAG_PROMPT = ChatPromptTemplate.from_messages([
    ("system", RAG_SYSTEM_PROMPT),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{question}"),
])


def _get_llm(streaming: bool = False) -> ChatOpenAI:
    if not settings.deepseek_api_key:
        raise ValueError(
            "DEEPSEEK_API_KEY is not configured. "
            "Please set it in backend/.env file."
        )
    return ChatOpenAI(
        model=settings.deepseek_model,
        openai_api_key=settings.deepseek_api_key,
        openai_api_base=settings.deepseek_base_url,
        temperature=0.3,
        streaming=streaming,
    )


def _format_context(documents: list[Document]) -> str:
    parts = []
    for i, doc in enumerate(documents, 1):
        source = doc.metadata.get("source_filename", "未知文件")
        page = doc.metadata.get("page", 0)
        parts.append(f"【片段{i}】[来源: {source}, 第{page + 1}页]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def _extract_relevant_snippet(content: str, question: str, max_length: int = 300) -> str:
    """Extract the most relevant snippet from content based on the question keywords.

    Uses a sliding window approach: score each window by keyword overlap,
    return the highest-scoring window as the snippet.
    """
    import re

    if len(content) <= max_length:
        return content

    stop_words = {
        "的", "是", "在", "了", "和", "与", "或", "有", "中", "对", "为", "等",
        "哪", "什么", "如何", "怎么", "哪些", "哪种", "使用", "可以", "这个",
        "那个", "一个", "请", "吗", "呢", "吧", "啊",
    }
    keywords = [
        w for w in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', question)
        if w not in stop_words
    ]

    if not keywords:
        return content[:max_length]

    # Sliding window: find the window with the best keyword coverage
    step = 50
    best_score = -1
    best_start = 0

    for start in range(0, len(content) - max_length + 1, step):
        window = content[start:start + max_length]
        score = sum(len(kw) * window.count(kw) for kw in keywords)
        if score > best_score:
            best_score = score
            best_start = start

    # Try to start at a sentence boundary
    snippet_start = best_start
    if snippet_start > 0:
        boundary = content.rfind("。", max(0, snippet_start - 50), snippet_start + 30)
        if boundary != -1:
            snippet_start = boundary + 1

    snippet = content[snippet_start:snippet_start + max_length]

    # Trim to end at a sentence boundary if possible
    last_period = max(snippet.rfind("。"), snippet.rfind("；"), snippet.rfind("\n"))
    if last_period > max_length * 0.6:
        snippet = snippet[:last_period + 1]

    return snippet.strip()


def _build_citations(documents: list[Document], question: str = "") -> list[dict]:
    """Build citations from retrieved documents.

    For each unique source+page, pick the chunk whose content best matches the
    question (by keyword overlap) and extract the most relevant snippet from it.
    This ensures the citation shows the actual content that answers the question,
    not just the first chunk that happened to be retrieved.
    """
    import re

    # Group documents by source:page
    groups: dict[str, list[Document]] = {}
    for doc in documents:
        source = doc.metadata.get("source_filename", "未知文件")
        page = doc.metadata.get("page", 0)
        key = f"{source}:{page}"
        groups.setdefault(key, []).append(doc)

    # Extract question keywords for scoring
    stop_words = {
        "的", "是", "在", "了", "和", "与", "或", "有", "中", "对", "为", "等",
        "哪", "什么", "如何", "怎么", "哪些", "哪种", "使用", "可以", "这个",
    }
    keywords = [
        w for w in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', question)
        if w not in stop_words
    ] if question else []

    citations = []
    for key, docs in groups.items():
        source, page_str = key.rsplit(":", 1)
        page = int(page_str)

        # Pick the best chunk from this group based on keyword match
        best_doc = docs[0]
        if keywords and len(docs) > 1:
            best_score = -1
            for doc in docs:
                score = sum(len(kw) * doc.page_content.count(kw) for kw in keywords)
                if score > best_score:
                    best_score = score
                    best_doc = doc

        snippet = _extract_relevant_snippet(best_doc.page_content, question) if question else best_doc.page_content[:200]
        citations.append({
            "filename": source,
            "page": page + 1,
            "snippet": snippet,
        })

    return citations


def _trim_chat_history(chat_history: list[dict] | None) -> list[dict]:
    """Keep only the last MAX_HISTORY_ROUNDS rounds (pairs of user+assistant)."""
    if not chat_history:
        return []
    max_messages = MAX_HISTORY_ROUNDS * 2
    return chat_history[-max_messages:]


def _to_langchain_messages(chat_history: list[dict]):
    messages = []
    for msg in chat_history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    return messages


def retrieve_documents(knowledge_base_id: int, question: str) -> list[Document]:
    """Retrieve relevant documents from the knowledge base (vector search)."""
    store = vector_store_manager.get_store(knowledge_base_id)
    if store is None:
        return []
    return store.similarity_search(question, k=settings.retrieval_top_k)


def _deduplicate_documents(documents: list[Document]) -> list[Document]:
    """Remove duplicate documents based on page_content."""
    seen = set()
    unique = []
    for doc in documents:
        content_hash = hash(doc.page_content[:200])
        if content_hash not in seen:
            seen.add(content_hash)
            unique.append(doc)
    return unique


def hybrid_retrieve(knowledge_base_id: int, question: str) -> list[Document]:
    """Hybrid retrieval: combine vector search with BM25 keyword search.

    This addresses the limitation where embedding models fail to match
    LaTeX-formatted content (e.g., $60\\mathrm{kg}$) with natural language queries.
    """
    from app.core.retrieval import bm25_retrieve, hybrid_merge

    store = vector_store_manager.get_store(knowledge_base_id)
    if store is None:
        return []

    top_k = settings.retrieval_top_k

    # Vector retrieval
    vector_results = store.similarity_search(question, k=top_k)

    # BM25 retrieval over all documents in the index
    # Get all docs from the store for BM25
    try:
        all_docs_with_scores = store.similarity_search_with_score("", k=200)
        all_docs = [doc for doc, _ in all_docs_with_scores]
    except Exception:
        # Fallback: use docstore directly
        all_docs = list(store.docstore._dict.values()) if hasattr(store, 'docstore') else []

    if all_docs:
        bm25_results = bm25_retrieve(all_docs, question, top_k=top_k)
        merged = hybrid_merge(vector_results, bm25_results, top_k=top_k)
        return _deduplicate_documents(merged)

    return _deduplicate_documents(vector_results)


async def retrieve_with_strategy(
    knowledge_base_id: int,
    question: str,
    use_hyde: bool = False,
) -> list[Document]:
    """Retrieve documents using standard or HyDE strategy."""
    if use_hyde:
        return await hyde_retrieve(knowledge_base_id, question)
    return hybrid_retrieve(knowledge_base_id, question)


async def rag_query(
    knowledge_base_id: int,
    question: str,
    chat_history: list[dict] | None = None,
    use_hyde: bool = False,
) -> dict:
    """Non-streaming RAG query, returns full answer with citations."""
    trimmed_history = _trim_chat_history(chat_history)
    retrieved_docs = await retrieve_with_strategy(knowledge_base_id, question, use_hyde)
    context = _format_context(retrieved_docs)
    citations = _build_citations(retrieved_docs, question)

    messages = _to_langchain_messages(trimmed_history)

    llm = _get_llm(streaming=False)
    chain = RAG_PROMPT | llm

    kwargs: dict = {
        "context": context,
        "chat_history": messages,
        "question": question,
    }
    config: dict = {}
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]

    response = await chain.ainvoke(kwargs, config=config)

    return {
        "answer": response.content,
        "citations": citations,
        "retrieved_chunks": [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
            }
            for doc in retrieved_docs
        ],
    }


async def rag_stream(
    knowledge_base_id: int,
    question: str,
    chat_history: list[dict] | None = None,
    use_hyde: bool = False,
) -> AsyncIterator[dict]:
    """Streaming RAG query, yields token chunks and final citations."""
    # Check semantic cache first (only when no chat history context)
    trimmed_history = _trim_chat_history(chat_history)
    if not trimmed_history:
        cached = semantic_cache.get(knowledge_base_id, question)
        if cached:
            yield {"type": "retrieval_debug", "content": {
                "chunks": [], "retrieval_time_ms": 0, "strategy": "cache",
            }}
            yield {"type": "token", "content": cached["answer"]}
            yield {"type": "citations", "content": cached["citations"]}
            yield {"type": "done", "content": cached["answer"]}
            return

    start_time = time.time()

    retrieved_docs = await retrieve_with_strategy(knowledge_base_id, question, use_hyde)
    retrieval_time_ms = int((time.time() - start_time) * 1000)

    context = _format_context(retrieved_docs)
    citations = _build_citations(retrieved_docs, question)
    retrieved_chunks = [
        {"content": doc.page_content, "metadata": doc.metadata}
        for doc in retrieved_docs
    ]

    yield {"type": "retrieval_debug", "content": {
        "chunks": retrieved_chunks,
        "retrieval_time_ms": retrieval_time_ms,
        "strategy": "hyde" if use_hyde else "vector",
    }}

    messages = _to_langchain_messages(trimmed_history)

    llm = _get_llm(streaming=True)
    chain = RAG_PROMPT | llm

    kwargs: dict = {
        "context": context,
        "chat_history": messages,
        "question": question,
    }
    config: dict = {}
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        langfuse_handler.metadata = {
            "knowledge_base_id": knowledge_base_id,
            "use_hyde": use_hyde,
            "history_rounds": len(trimmed_history) // 2,
            "retrieval_time_ms": retrieval_time_ms,
        }

    full_answer = ""
    async for chunk in chain.astream(kwargs, config=config):
        token = chunk.content
        if token:
            full_answer += token
            yield {"type": "token", "content": token}

    total_time_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"RAG query completed: kb={knowledge_base_id}, hyde={use_hyde}, "
        f"retrieval={retrieval_time_ms}ms, total={total_time_ms}ms"
    )

    # Store in semantic cache (only for first question in a conversation)
    if not trimmed_history:
        semantic_cache.put(knowledge_base_id, question, full_answer, citations)

    yield {"type": "citations", "content": citations}
    yield {"type": "done", "content": full_answer}


# ======================== Plain Chat (GLM-4V-Flash - Free Multimodal from Zhipu AI) ========================

PLAIN_CHAT_SYSTEM_PROMPT_TEMPLATE = """你是一个智能AI助手，请用简洁、准确、友好的方式回答用户问题。
当前时间：{current_time}
使用Markdown格式化回复：标题分隔主题、列表展示要点、**加粗**关键信息。
如果用户发送了图片，请仔细观察图片内容并结合用户问题进行回答。
如果用户上传了文件，请仔细阅读文件内容并结合用户问题进行准确回答。
对于天气等实时信息，请告知用户你无法获取实时数据，建议查询天气应用。"""


def _get_chat_llm(streaming: bool = False) -> ChatOpenAI:
    """Get GLM-4V-Flash LLM instance for plain chat (free multimodal from Zhipu AI)."""
    if not settings.chat_api_key:
        # Fallback to DeepSeek if chat model is not configured
        logger.warning("CHAT_API_KEY not configured, falling back to DeepSeek for plain chat")
        return _get_llm(streaming=streaming)
    return ChatOpenAI(
        model=settings.chat_model,
        openai_api_key=settings.chat_api_key,
        openai_api_base=settings.chat_base_url,
        temperature=0.7,
        max_tokens=4096,
        streaming=streaming,
    )


async def plain_chat_stream(
    question: str,
    chat_history: list[dict] | None = None,
    images: list[str] | None = None,
    file_content: str | None = None,
) -> AsyncIterator[dict]:
    """Streaming plain chat using GLM-4V-Flash (free multimodal from Zhipu AI).

    Args:
        question: User's text question.
        chat_history: Previous conversation messages.
        images: List of image URLs or base64 data URIs.
        file_content: Extracted text from uploaded file (via Zhipu file-extract API).
    """
    from langchain_core.messages import SystemMessage

    trimmed_history = _trim_chat_history(chat_history)
    from datetime import datetime
    current_time = datetime.now().strftime("%Y年%m月%d日 %A %H:%M")
    system_prompt = PLAIN_CHAT_SYSTEM_PROMPT_TEMPLATE.format(current_time=current_time)
    messages = [SystemMessage(content=system_prompt)]
    messages.extend(_to_langchain_messages(trimmed_history))

    # Build the user question text, prepending file content if provided
    user_text = question
    if file_content:
        user_text = f"以下是用户上传的文件内容：\n\n{file_content}\n\n用户问题：{question}"

    # Build multimodal user message if images are provided
    if images:
        content_parts: list[dict] = []
        for image_url in images:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })
        content_parts.append({"type": "text", "text": user_text})
        messages.append(HumanMessage(content=content_parts))
    else:
        messages.append(HumanMessage(content=user_text))

    llm = _get_chat_llm(streaming=True)

    config: dict = {}
    langfuse_handler = get_langfuse_handler()
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]

    async for chunk in llm.astream(messages, config=config):
        token = chunk.content
        if token:
            yield {"type": "token", "content": token}

    yield {"type": "done", "content": ""}

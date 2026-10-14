"""检索服务：封装 RAG 链路的检索调用，供问答流程与未来的 Agent 工具使用。

本模块只做「转发 + 归属校验编排」，检索算法本体位于 core/（改动禁区，
见 docs/rules/50-rag-chain.md），不得在此重写。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import User, get_kb_or_raise
from app.core.rag_chain import retrieve_with_strategy


async def search(
    kb_id: int,
    query: str,
    top_k: int = 5,
    *,
    db: AsyncSession,
    user: User,
) -> list[dict]:
    """对指定知识库执行混合检索，返回结构化片段列表（不生成回答）。

    - 先做归属校验（viewer 级读权限），防越权检索私有库
    - 返回 [{content, source, page, score}, ...]，page 为 1 起始页码（与 citations 口径一致）
    - P0-3 Agent 工具将直接调用本函数（不经 HTTP 层），见 docs/requirements/P0-2-service-layer.md §6

    注意：检索召回数量由 settings.retrieval_top_k 决定（禁区文件内部逻辑），
    此处 top_k 仅对召回结果做截断，传入大于召回数的值时以实际召回为准。
    """
    await get_kb_or_raise(kb_id, user, "viewer", db)

    documents = await retrieve_with_strategy(kb_id, query, use_hyde=False)
    results: list[dict] = []
    for doc in documents[:top_k]:
        results.append(
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source_filename", "未知文件"),
                "page": doc.metadata.get("page", 0) + 1,
                "score": doc.metadata.get("score", 0.0),
            }
        )
    return results

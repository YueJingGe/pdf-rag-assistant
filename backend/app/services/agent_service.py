"""Agent service（P0-3a）：意图识别 + 工具注册表。

需求与边界见 docs/requirements/P0-3a-agent-tools.md：
- 头号安全约束（补充 A）：工具身份只从 contextvar 注入——工具函数与 LLM 可见参数
  schema 均禁止 user_id / db 参数；db + user 由路由层（HTTP 鉴权上下文已建立处）
  经 set_agent_context() 注入，这是 Agent 路径不绕过 P0-1 权限体系的唯一保险
- 分层纪律：不 import fastapi HTTP 符号；不 import 禁区私有模型工厂（rag_chain._get_llm
  等）；只抛 services.exceptions 领域异常
- 写操作工具一律不注册（终验 §12.14 白名单审计）
- run_agent_loop 循环与结构化可观测日志在第 2 轮实现（§11 任务分解）
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import operator
import time
from contextvars import ContextVar
from datetime import datetime
from typing import AsyncIterator, Callable, Literal, Optional
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.services import chat_service, feedback_service, kb_service, retrieval_service
from app.services.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.utils.logging import logger

# ---------------------------------------------------------------------------
# 上下文注入（补充 A 的唯一实现点）
# ---------------------------------------------------------------------------

_agent_db: ContextVar[Optional[AsyncSession]] = ContextVar("agent_db", default=None)
_agent_user: ContextVar[Optional[User]] = ContextVar("agent_user", default=None)


def set_agent_context(db: AsyncSession, user: User):
    """路由层进入 Agent 路径前调用；返回 (db_token, user_token) 供 finally 中 reset_agent_context。"""
    return _agent_db.set(db), _agent_user.set(user)


def reset_agent_context(tokens) -> None:
    db_token, user_token = tokens
    _agent_db.reset(db_token)
    _agent_user.reset(user_token)


def _require_agent_context():
    db, user = _agent_db.get(), _agent_user.get()
    if db is None or user is None:
        # 防误用：工具必须在 set_agent_context 之后调用（HTTP 路径由路由层保证）
        raise ValidationError(
            "Agent context not initialized: db/user 未注入，禁止在 set_agent_context() 之外调用工具"
        )
    return db, user


# ---------------------------------------------------------------------------
# 模型工厂（D1：可配置，留空回退 DeepSeek；不 import 禁区私有 _get_llm，短期重复即 3b 网关动机）
# ---------------------------------------------------------------------------


def _get_agent_llm(temperature: float = 0.0, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.agent_model_name or settings.deepseek_model,
        api_key=settings.agent_model_api_key or settings.deepseek_api_key,
        base_url=settings.agent_model_base_url or settings.deepseek_base_url,
        temperature=temperature,
        streaming=streaming,
    )


# ---------------------------------------------------------------------------
# 意图识别（§7：三分类 + few-shot 偏置 + 补充 B 降级策略）
# ---------------------------------------------------------------------------

INTENT_TIMEOUT_S = 3.0  # 补充 B：分类超时兜底，失败不影响主链路
INTENT_FALLBACK = "rag"  # 超时/格式异常/调用失败统一兜底（RAG 链路最成熟）

INTENT_SYSTEM_PROMPT = """你是意图分类器。把用户问题分为三类，只输出一个词：
- rag：知识库内容相关（查文档、总结、对比文档内容）
- tool：需要工具执行（数学计算、查时间、查订单等外部数据）
- plain：闲聊寒暄，与知识库和工具都无关

偏置规则：用户已选择知识库时，事实性问题优先判 rag；但问时间/算数/查订单，即使选了知识库也判 tool。
示例：
- "中国人民银行的职能是什么"（已选库）→ rag
- "总结这份文档的核心观点"（已选库）→ rag
- "现在几点了"（已选库）→ tool
- "3.75 乘以 12 等于多少"（未选库）→ tool
- "帮我查一下订单 SO-1001 的状态" → tool
- "你好呀，今天心情不错"（已选库）→ plain"""


async def classify_intent(
    db: AsyncSession, user: User, question: str, knowledge_base_id: Optional[int] = None
) -> Literal["rag", "tool", "plain"]:
    """意图三分类。db/user 当前仅用于可观测日志（用户维度统计），不参与查询。

    降级策略（补充 B）：超时 3s / 格式异常 / 调用失败 → 默认 rag；分类器独立于 Agent 循环。
    """
    start = time.perf_counter()
    llm = _get_agent_llm()
    kb_hint = f"（用户已选知识库 id={knowledge_base_id}）" if knowledge_base_id else "（用户未选知识库）"
    prompt = f"{INTENT_SYSTEM_PROMPT}\n\n当前问题：{question}{kb_hint}\n只输出 rag/tool/plain 之一："
    try:
        resp = await asyncio.wait_for(llm.ainvoke(prompt), timeout=INTENT_TIMEOUT_S)
        intent = str(resp.content).strip().lower()
        if intent not in ("rag", "tool", "plain"):
            intent = INTENT_FALLBACK  # 格式异常兜底
    except Exception:  # noqa: BLE001 超时/网络/解析失败统一兜底（补充 B：不影响主链路）
        intent = INTENT_FALLBACK
    logger.info(
        "[agent] intent classified: intent=%s kb_id=%s user_id=%s cost_ms=%d q=%s",
        intent, knowledge_base_id, user.id, int((time.perf_counter() - start) * 1000), question[:50],
    )
    return intent  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 外部工具实现（零依赖：ast 白名单求值 / zoneinfo / 内存 mock）
# ---------------------------------------------------------------------------

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_CMP_OPS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
            ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}


def _safe_eval(node: ast.AST):
    """ast 白名单求值：仅常量/四则/一元/单层比较；禁止名称调用、属性访问、下标（防注入）。"""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP_OPS:
        return _CMP_OPS[type(node.ops[0])](_safe_eval(node.left), _safe_eval(node.comparators[0]))
    raise ValidationError(f"calculator 仅支持四则/一元/比较表达式，拒绝节点：{type(node).__name__}")


_WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# Demo 模拟订单（D7：叙事用非核心；时间紧可整组砍掉）
_MOCK_ORDERS = {
    "SO-1001": {"status": "已发货", "carrier": "顺丰速运", "eta": "2026-10-16"},
    "SO-1002": {"status": "待支付", "carrier": None, "eta": None},
    "SO-1003": {"status": "已完成", "carrier": "中通快递", "eta": "2026-10-11"},
}


async def _tool_search(db: AsyncSession, user: User, *, kb_id: int, query: str, top_k: int = 5):
    return await retrieval_service.search(kb_id, query, top_k, db=db, user=user)


async def _tool_list_kbs(db: AsyncSession, user: User):
    return await kb_service.list_visible_kbs(db, user)


async def _tool_feedback_stats(db: AsyncSession, user: User, *, kb_id: int):
    return await feedback_service.get_feedback_stats(db, user, kb_id)


async def _tool_conversation_history(db: AsyncSession, user: User, *, conversation_id: int):
    return await chat_service.get_messages(db, conversation_id, user)


async def _tool_calculator(db: AsyncSession, user: User, *, expression: str):
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValidationError(f"非法数学表达式：{exc.msg}")
    return {"expression": expression, "result": _safe_eval(tree)}


async def _tool_current_time(db: AsyncSession, user: User, *, timezone: str = "Asia/Shanghai"):
    try:
        now = datetime.now(ZoneInfo(timezone))
    except Exception as exc:  # noqa: BLE001 未知时区名 / 系统缺 tzdata
        raise ValidationError(f"未知时区 {timezone}: {exc}")
    return {"datetime": now.strftime("%Y-%m-%d %H:%M:%S"), "weekday": _WEEKDAY_CN[now.weekday()], "timezone": timezone}


async def _tool_order_query(db: AsyncSession, user: User, *, order_id: str):
    oid = order_id.strip().upper()
    order = _MOCK_ORDERS.get(oid)
    if order is None:
        return {"order_id": order_id, "found": False, "message": "未找到订单（Demo 数据仅含 SO-1001~SO-1003）"}
    return {"order_id": oid, "found": True, **order}


# ---------------------------------------------------------------------------
# 工具包装与注册表（LLM 可见 schema 中禁止 db / user / user_id——头号安全约束）
# ---------------------------------------------------------------------------


class _EmptyArgs(BaseModel):
    """list_knowledge_bases 无业务参数。"""


class _SearchKBArgs(BaseModel):
    kb_id: int = Field(..., description="知识库 ID")
    query: str = Field(..., description="检索关键词或问题")
    top_k: int = Field(5, description="返回片段数上限", ge=1, le=20)


class _KBIdArgs(BaseModel):
    kb_id: int = Field(..., description="知识库 ID")


class _ConversationIdArgs(BaseModel):
    conversation_id: int = Field(..., description="会话 ID（本人会话）")


class _CalculatorArgs(BaseModel):
    expression: str = Field(..., description="数学表达式，如 (3+5)*12/2")


class _CurrentTimeArgs(BaseModel):
    timezone: str = Field("Asia/Shanghai", description="IANA 时区名，如 Asia/Shanghai / UTC")


class _OrderQueryArgs(BaseModel):
    order_id: str = Field(..., description="订单号，如 SO-1001")


def _wrap_tool(
    name: str,
    description: str,
    args_schema: type[BaseModel],
    run_fn: Callable,
) -> StructuredTool:
    """把 service/外部函数包装为 LangChain 工具。

    run_fn(db, user, **kwargs)：db/user 一律由 _require_agent_context 从 contextvar 提供，
    kwargs 只含 LLM 可见业务参数；返回值 JSON 序列化为字符串作为 ToolMessage 内容。
    """

    async def _run(**kwargs):
        db, user = _require_agent_context()
        result = await run_fn(db, user, **kwargs)
        return json.dumps(result, ensure_ascii=False, default=str)

    return StructuredTool(name=name, description=description, args_schema=args_schema, coroutine=_run)


# 写操作 service 函数（create_kb/update_kb/delete_kb/upload_document/delete_document/
# batch_delete_documents/rename_document/export_feedback）一律不得注册进本表（终验 §12.14）
AGENT_TOOLS: dict = {
    t.name: t
    for t in (
        _wrap_tool("search_knowledge_base", "在指定知识库中检索与查询最相关的文档片段", _SearchKBArgs, _tool_search),
        _wrap_tool("list_knowledge_bases", "列出当前用户可见的全部知识库（含 id/名称/文档数/权限）", _EmptyArgs, _tool_list_kbs),
        _wrap_tool("get_feedback_stats", "查询指定知识库的检索反馈质量统计（相关/不相关/相关率）", _KBIdArgs, _tool_feedback_stats),
        _wrap_tool("get_conversation_history", "读取本人某个会话的历史消息列表", _ConversationIdArgs, _tool_conversation_history),
        _wrap_tool("calculator", "计算数学表达式，支持 + - * / % ** // 与比较", _CalculatorArgs, _tool_calculator),
        _wrap_tool("current_time", "获取当前日期时间与星期", _CurrentTimeArgs, _tool_current_time),
        _wrap_tool("simulate_order_query", "查询订单状态（Demo 模拟数据，订单号 SO-1001~SO-1003）", _OrderQueryArgs, _tool_order_query),
    )
}


# ---------------------------------------------------------------------------
# Agent 循环（第 2 轮：补充 D 五种终止场景 + 双超时 + §9 可观测日志）
# ---------------------------------------------------------------------------

AGENT_SYSTEM_PROMPT = (
    "你是智能助手，可以调用工具回答用户问题。规则：\n"
    "1. 优先用最少的工具轮次完成任务，拿到足够信息后立即给出最终回答\n"
    "2. 工具执行失败时换参数或换工具；不要用完全相同的参数反复重试\n"
    "3. 用中文简洁回答"
)

MAX_TOOL_ROUNDS = 3      # D8：循环上限（§8 场景 ③）
TOOL_TIMEOUT_S = 10.0    # D8：单工具超时，每个工具独立计时（§8 场景 ⑤）
LLM_TIMEOUT_S = 15.0     # D10：LLM 单次决策超时，防 LLM 挂起卡死循环（提醒 2 双超时之二）
MAX_TOOL_CALLS_PER_ROUND = 10  # D16：单轮 tool_calls 数上限（§8 语义澄清：轮次上限 ≠ 调用次数上限，防 LLM 异常时爆炸）
FORCED_STOP_TEXT = "抱歉，无法完成该请求，请重新表述问题。"
_TOKEN_CHUNK_CHARS = 24  # D10：最终回答伪流式切块大小（决策已完整生成后切块下发，见 changelog 决策补充）


def _error_status(exc: Exception) -> str:
    """领域异常 → tool_result 状态归类（连续同类错误计数依据）。"""
    if isinstance(exc, PermissionDeniedError):
        return "denied"
    if isinstance(exc, NotFoundError):
        return "not_found"
    if isinstance(exc, ValidationError):
        return "validation"
    return "error"


def _log_tool_call(user_id: int, round_no: int, name: str, args: dict, status: str, duration_ms: int) -> None:
    """§9 可观测日志（单行 JSON：tool_name/params_hash/duration_ms/status/user_id/round）。"""
    params_hash = hashlib.md5(json.dumps(args, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:8]
    logger.info(
        '[agent_tool] {"tool_name":"%s","params_hash":"%s","duration_ms":%d,"status":"%s","user_id":%d,"round":%d}',
        name, params_hash, duration_ms, status, user_id, round_no,
    )


async def run_agent_loop(
    question: str, chat_history: Optional[list[dict]] = None
) -> AsyncIterator[tuple[str, dict]]:
    """工具意图的 Agent 循环（async generator，产出 (event_type, payload) 二元组，由路由层转 SSE）。

    终止场景（需求 §8）：①LLM 无 tool_calls 直接回答 ②工具→ToolMessage→再决策循环
    ③达 MAX_TOOL_ROUNDS 上限强制终止 ④连续 2 次同类错误强制终止（工具异常/超时/
    LLM 超时均计入）⑤单工具超时转述为观察结果由 LLM 决策下一步。
    身份从 contextvar 取（头号安全约束）；调用前路由层必须已 set_agent_context。
    """
    _db, user = _require_agent_context()
    llm = _get_agent_llm().bind_tools(list(AGENT_TOOLS.values()))
    messages: list = [SystemMessage(content=AGENT_SYSTEM_PROMPT)]
    for msg in (chat_history or [])[-6:]:  # 近 3 轮对话
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg.get("content", "")))
        else:
            messages.append(AIMessage(content=msg.get("content", "")))
    messages.append(HumanMessage(content=question))

    consecutive_same_errors = 0
    last_error_kind: Optional[str] = None

    for round_no in range(1, MAX_TOOL_ROUNDS + 1):
        # --- LLM 决策（15s 超时，超时计入连续错误计数） ---
        try:
            resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=LLM_TIMEOUT_S)
        except asyncio.TimeoutError:
            if last_error_kind == "llm_timeout":
                consecutive_same_errors += 1
            else:
                consecutive_same_errors, last_error_kind = 1, "llm_timeout"
            yield ("tool_result", {"name": "llm", "status": "timeout",
                                   "duration_ms": int(LLM_TIMEOUT_S * 1000), "result_summary": "LLM 响应超时"})
            if consecutive_same_errors >= 2:
                yield ("token", {"content": FORCED_STOP_TEXT})
                return
            continue

        tool_calls = resp.tool_calls or []
        if len(tool_calls) > MAX_TOOL_CALLS_PER_ROUND:
            # D16：单轮调用数超限——只执行前 10 个；被丢弃的 tool_call_id 仍须回填
            # ToolMessage（协议要求每个 tool_call 必须有响应，否则下轮请求报错）
            for dropped in tool_calls[MAX_TOOL_CALLS_PER_ROUND:]:
                messages.append(ToolMessage(
                    content=f"Error: 本轮工具调用数超上限({MAX_TOOL_CALLS_PER_ROUND})，此调用未执行",
                    tool_call_id=dropped["id"]))
            tool_calls = tool_calls[:MAX_TOOL_CALLS_PER_ROUND]
        if not tool_calls:
            # 场景 ①：最终回答（伪流式切块下发）
            text = str(resp.content or "")
            for i in range(0, len(text), _TOKEN_CHUNK_CHARS):
                yield ("token", {"content": text[i:i + _TOKEN_CHUNK_CHARS]})
            if not text:
                yield ("token", {"content": "（模型未返回内容，请重试）"})
            return

        # --- 执行本轮全部工具（一轮可含多个 tool_calls，逐个独立 10s 超时） ---
        messages.append(resp)  # AIMessage（含 tool_calls，与 ToolMessage 按 id 配对）
        for tc in tool_calls:
            name, args = tc["name"], dict(tc["args"] or {})
            yield ("tool_call", {"name": name, "args_summary": json.dumps(args, ensure_ascii=False)[:120], "round": round_no})
            start = time.perf_counter()
            tool = AGENT_TOOLS.get(name)
            if tool is None:
                observation, status = f"未知工具：{name}", "error"
            else:
                try:
                    observation = await asyncio.wait_for(tool.coroutine(**args), timeout=TOOL_TIMEOUT_S)
                    status = "success"
                except asyncio.TimeoutError:
                    observation, status = f"工具 {name} 执行超时（>{TOOL_TIMEOUT_S:g}s）", "timeout"
                except (NotFoundError, PermissionDeniedError, ValidationError, ConflictError) as exc:
                    observation, status = f"工具执行被拒绝：{exc}", _error_status(exc)
                except Exception as exc:  # noqa: BLE001 工具内部未知错误也转述给 LLM 决策
                    observation, status = f"工具执行出错：{exc}", "error"
            duration_ms = int((time.perf_counter() - start) * 1000)
            yield ("tool_result", {"name": name, "status": status,
                                   "duration_ms": duration_ms, "result_summary": str(observation)[:200],
                                   "round": round_no})
            _log_tool_call(user.id, round_no, name, args, status, duration_ms)
            messages.append(ToolMessage(content=str(observation)[:4000], tool_call_id=tc["id"]))
            if status == "success":
                consecutive_same_errors, last_error_kind = 0, None
            elif status == last_error_kind:
                consecutive_same_errors += 1
            else:
                consecutive_same_errors, last_error_kind = 1, status

        if consecutive_same_errors >= 2:
            # 场景 ④：连续 2 次同类错误强制终止
            yield ("token", {"content": FORCED_STOP_TEXT})
            return

    # 场景 ③：达到轮次上限仍未收敛
    yield ("token", {"content": FORCED_STOP_TEXT})

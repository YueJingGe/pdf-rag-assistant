"""LLM 网关：全项目唯一 ChatOpenAI 构造入口（P0-3b，需求文档 §5.1）。

settings 是唯一配置真相源；本模块只存"角色 → settings 字段名 + 采样参数"映射——
注册表不是配置源，是"角色 → 配置字段"的路由表。角色按能力档位命名（不按调用点命名），
5 角色覆盖 5 处调用点；591 内联（rag_chain.py:591-598）复用 chat_text 角色。

USE_LEGACY_LLM_FACTORY=true 时走 legacy 分支：网关内部逐字段复刻被替换的 5 处
旧工厂（rag_chain.py:114/458/591、retrieval.py:20、agent_service.py:77）行为，
等价性由需求 §7.5 开关两态回归保证（步 7 全量验证）。这不是 git revert 级回滚，
而是"网关内复刻旧路径"；彻底回滚 = revert 对应单 commit（§8）。

Python 3.9 兼容：函数签名注解禁用 `X | Y` 求值语法（统一 Optional）。
"""

from dataclasses import dataclass
from typing import Optional

from langchain_openai import ChatOpenAI

from app.core.config import settings


@dataclass(frozen=True)
class RoleSpec:
    """角色规格：只存 settings 字段名与采样参数（§5.1）。

    fallback_role + fallback_trigger="on_empty_api_key"：
        api_key 字段为空时整角色回退到 fallback_role（按目标角色 RoleSpec
        全套参数重新构造，连 temp/max_tokens 一起切，streaming 透传；
        精确复刻 rag_chain.py:460-462 的 `return _get_llm(streaming)` 语义）。
    per_field_fallback_prefix：
        逐字段回退——model/api_key/base_url 三字段逐个"本字段 or
        f"{prefix}{_SUFFIX[...]}"，保持可混搭语义（精确复刻
        agent_service.py:79-81 的三个 or）。
    raise_if_empty：
        构造前 api_key 为空是否 raise ValueError（复刻各旧工厂差异：
        rag_generate/hyde 的工厂写了检查，chat_text 的 591 内联没写——历史偶然，
        一并显式化避免"悄悄统一"）。
    """

    model_field: str
    api_key_field: str
    base_url_field: str
    temperature: float
    max_tokens: Optional[int]
    fallback_role: Optional[str] = None
    fallback_trigger: Optional[str] = None
    per_field_fallback_prefix: Optional[str] = None
    raise_if_empty: bool = False


# 逐字段回退时的字段名后缀（per_field_fallback_prefix + suffix → 回退字段名）
_SUFFIX = {"model_field": "_model", "api_key_field": "_api_key", "base_url_field": "_base_url"}

_ROLES = {
    # 角色             model 字段          key 字段            base_url 字段          temp  max_tokens  回退
    "rag_generate":    RoleSpec("deepseek_model", "deepseek_api_key", "deepseek_base_url", 0.3, None, raise_if_empty=True),
    "hyde":            RoleSpec("deepseek_model", "deepseek_api_key", "deepseek_base_url", 0.0, 256, raise_if_empty=True),
    "chat_multimodal": RoleSpec("chat_model", "chat_api_key", "chat_base_url", 0.7, 4096,
                                fallback_role="rag_generate", fallback_trigger="on_empty_api_key"),
    "chat_text":       RoleSpec("chat_text_model", "chat_api_key", "chat_base_url", 0.7, 4096),
    "agent":           RoleSpec("agent_model_name", "agent_model_api_key", "agent_model_base_url", 0.0, None,
                                per_field_fallback_prefix="deepseek"),
}


def _construct(spec: RoleSpec, model: str, api_key: str, base_url: str,
               streaming: bool, temperature: Optional[float] = None) -> ChatOpenAI:
    kwargs = {
        "model": model,
        "openai_api_key": api_key,
        "openai_api_base": base_url,
        "temperature": temperature if temperature is not None else spec.temperature,
        "streaming": streaming,
    }
    if spec.max_tokens is not None:
        kwargs["max_tokens"] = spec.max_tokens
    return ChatOpenAI(**kwargs)


def get_llm(role: str, streaming: bool = False, temperature: Optional[float] = None) -> ChatOpenAI:
    """唯一构造入口。USE_LEGACY_LLM_FACTORY=true 时走 legacy 分支（§5.3）。

    回退判定顺序（精确对应 §5.2）：
    1. spec.fallback_trigger == "on_empty_api_key" 且 getattr(settings, spec.api_key_field) 为空
       → 整角色切 spec.fallback_role（按目标角色 RoleSpec 全套参数重新构造，streaming 透传）
    2. spec.per_field_fallback_prefix 非空 → model/api_key/base_url 三字段逐个 or 回退
    3. 两者均空 → 无回退，按本角色字段直接构造（raise_if_empty 角色的 api_key 缺失报错
       语义与原工厂一致）

    temperature 仅 agent 角色的调用点会显式传入（原 _get_agent_llm 参数化语义）；
    其余角色传 None，取 RoleSpec 默认。回退时 temperature 不透传（旧语义回退后
    固定用目标角色默认参数）。
    """
    if settings.use_legacy_llm_factory:
        return _legacy_get_llm(role, streaming=streaming, temperature=temperature)

    if role not in _ROLES:
        raise KeyError(f"unknown llm role: {role!r} (available: {sorted(_ROLES)})")
    spec = _ROLES[role]

    # 1) 整角色回退（on_empty_api_key）
    if spec.fallback_trigger == "on_empty_api_key" and not getattr(settings, spec.api_key_field, None):
        return get_llm(spec.fallback_role, streaming=streaming)

    # 2) 逐字段回退（可混搭）
    if spec.per_field_fallback_prefix:
        prefix = spec.per_field_fallback_prefix

        def _or(field_name: str, suffix: str):
            value = getattr(settings, field_name)
            return value if value else getattr(settings, prefix + suffix)

        return _construct(
            spec,
            _or(spec.model_field, _SUFFIX["model_field"]),
            _or(spec.api_key_field, _SUFFIX["api_key_field"]),
            _or(spec.base_url_field, _SUFFIX["base_url_field"]),
            streaming,
            temperature,
        )

    # 3) 无回退
    api_key = getattr(settings, spec.api_key_field)
    if spec.raise_if_empty and not api_key:
        raise ValueError(
            f"{spec.api_key_field.upper()} is not configured. "
            "Please set it in backend/.env file."
        )
    return _construct(spec, getattr(settings, spec.model_field), api_key,
                      getattr(settings, spec.base_url_field), streaming, temperature)


def _legacy_get_llm(role: str, streaming: bool = False,
                    temperature: Optional[float] = None) -> ChatOpenAI:
    """legacy 分支：逐字段复刻被替换的 5 处旧工厂（字面级），来源行号见各分支注释。
    未来 roles 路径演进（如加重试/新参数）时此处冻结不动，保证回滚语义。

    复刻来源追溯（行号基准 = ddaf841，网关落盘时的 HEAD；hash 为 git blame 各行归属）：

    ================ ====================== ============================================
      角色             来源位置               复刻基线 commit
    ================ ====================== ============================================
      rag_generate     rag_chain.py:114-126   0e86d4f（2026-05-19 初始提交）
      chat_multimodal  rag_chain.py:458-470   f4ce9fe→9d84322→035fd31（05-19/05-20 演化）
      chat_text        rag_chain.py:591-598   9d84322（2026-05-20）
      hyde             retrieval.py:20-32     0e86d4f（2026-05-19 初始提交）
      agent            agent_service.py:77-84 6973111（2026-10-14 P0-3a 第 1 轮）
    ================ ====================== ============================================

    删除 legacy 分支前：先 git blame 复核上述位置原工厂未被后续 commit 改动语义，
    再以 §7.5 两态回归（真实 RAG 请求）兜底；构造参数等价性由
    smoke_test_llm_gateway.py 场景 5（legacy 12 项）保证。
    """
    if role == "rag_generate":
        # 复刻 rag_chain.py:114-126 _get_llm
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
    if role == "chat_multimodal":
        # 复刻 rag_chain.py:458-470 _get_chat_llm（含 460-462 整角色回退）
        if not settings.chat_api_key:
            return _legacy_get_llm("rag_generate", streaming=streaming)
        return ChatOpenAI(
            model=settings.chat_model,
            openai_api_key=settings.chat_api_key,
            openai_api_base=settings.chat_base_url,
            temperature=0.7,
            max_tokens=4096,
            streaming=streaming,
        )
    if role == "chat_text":
        # 复刻 rag_chain.py:591-598 内联（无 api_key 检查——原语义如此）
        return ChatOpenAI(
            model=settings.chat_text_model,
            openai_api_key=settings.chat_api_key,
            openai_api_base=settings.chat_base_url,
            temperature=0.7,
            max_tokens=4096,
            streaming=streaming,
        )
    if role == "hyde":
        # 复刻 retrieval.py:20-32 _get_llm
        if not settings.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not configured. "
                "Please set it in backend/.env file."
            )
        return ChatOpenAI(
            model=settings.deepseek_model,
            openai_api_key=settings.deepseek_api_key,
            openai_api_base=settings.deepseek_base_url,
            temperature=0.0,
            max_tokens=256,
        )
    if role == "agent":
        # 复刻 agent_service.py:77-84 _get_agent_llm（三字段逐个 or，可混搭）
        return ChatOpenAI(
            model=settings.agent_model_name or settings.deepseek_model,
            api_key=settings.agent_model_api_key or settings.deepseek_api_key,
            base_url=settings.agent_model_base_url or settings.deepseek_base_url,
            temperature=temperature if temperature is not None else 0.0,
            streaming=streaming,
        )
    raise KeyError(f"unknown llm role: {role!r}")

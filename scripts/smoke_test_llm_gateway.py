"""P0-3b 步 1 对拍：5 处旧工厂 vs llm_gateway.get_llm 参数零漂移。

纯构造对比，不调 LLM（ChatOpenAI 实例化不发网络请求）。覆盖：
- 5 角色常规构造（含 streaming 变体、agent temperature 覆盖）
- chat_multimodal 整角色回退（CHAT_API_KEY 置空 → 回退 rag_generate 全套参数）
- agent 逐字段 or 回退（三字段分别置空 / 全空，保持混搭语义）
- api_key 缺失报错语义（rag_generate/hyde 前置 raise；chat_text 591 无前置检查——
  空 key 时双方都会走进 ChatOpenAI 构造、由 openai SDK validate_environment 抛 OpenAIError）
- legacy 开关两态（use_legacy_llm_factory=True 下网关内部复刻 vs 旧工厂直调）

任一处不通过 → 修网关，不进入步 2（需求 §6 步 1 一次性窗口）。
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

from app.core.config import settings  # noqa: E402
from app.core.llm_gateway import get_llm  # noqa: E402

# 旧工厂直调（替换前基线；禁区文件只读 import，不改动）
from app.core.rag_chain import _get_chat_llm, _get_llm as _rag_get_llm  # noqa: E402
from app.core.retrieval import _get_llm as _hyde_get_llm  # noqa: E402
from app.services.agent_service import _get_agent_llm  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402

# ChatOpenAI 构造后参数统一存 pydantic 字段（api_key/base_url 是 alias），
# 统一读这六个属性即可屏蔽构造时参数名差异（openai_api_key= vs api_key=）
FIELDS = ("model_name", "temperature", "max_tokens", "streaming", "openai_api_key", "openai_api_base")

results = []


def snap(c: ChatOpenAI) -> dict:
    return {f: getattr(c, f) for f in FIELDS}


def check(name: str, old: ChatOpenAI, new: ChatOpenAI) -> None:
    o, n = snap(old), snap(new)
    diff = {f for f in FIELDS if o[f] != n[f]}
    ok = not diff
    results.append(ok)
    if ok:
        print(f"✅ {name}")
    else:
        detail = {f: (o[f], n[f]) for f in diff}
        print(f"❌ {name}  diff={detail}")


def check_ok(name: str, ok: bool, detail: str = "") -> None:
    results.append(ok)
    print(f"{'✅' if ok else '❌'} {name}" + (f"  {detail}" if detail else ""))


print("=== 场景 1：5 角色常规构造 ===")
check("rag_generate streaming=False", _rag_get_llm(), get_llm("rag_generate"))
check("rag_generate streaming=True", _rag_get_llm(streaming=True), get_llm("rag_generate", streaming=True))
check("chat_multimodal streaming=False", _get_chat_llm(), get_llm("chat_multimodal"))
check("chat_multimodal streaming=True", _get_chat_llm(streaming=True), get_llm("chat_multimodal", streaming=True))
# 591 内联（无工厂函数，按源码 rag_chain.py:591-598 字面构造作为"旧"）
old_591 = ChatOpenAI(
    model=settings.chat_text_model,
    openai_api_key=settings.chat_api_key,
    openai_api_base=settings.chat_base_url,
    temperature=0.7,
    max_tokens=4096,
    streaming=True,
)
check("chat_text 591字面 streaming=True", old_591, get_llm("chat_text", streaming=True))
check("hyde", _hyde_get_llm(), get_llm("hyde"))
check("agent 默认", _get_agent_llm(), get_llm("agent"))
check("agent temperature=0.7 streaming=True", _get_agent_llm(temperature=0.7, streaming=True), get_llm("agent", temperature=0.7, streaming=True))

print("\n=== 场景 2：chat_multimodal 整角色回退（CHAT_API_KEY 空 → rag_generate 全套参数）===")
_real_chat_key = settings.chat_api_key
settings.chat_api_key = ""
check("chat_multimodal 回退 streaming=False", _get_chat_llm(), get_llm("chat_multimodal"))
check("chat_multimodal 回退 streaming=True", _get_chat_llm(streaming=True), get_llm("chat_multimodal", streaming=True))
settings.chat_api_key = _real_chat_key

print("\n=== 场景 3：agent 逐字段 or 回退（混搭语义）===")
_agent_orig = (settings.agent_model_name, settings.agent_model_api_key, settings.agent_model_base_url)
settings.agent_model_name = ""
check("agent 仅 model 字段回退", _get_agent_llm(), get_llm("agent"))
settings.agent_model_name, settings.agent_model_api_key = _agent_orig[0], ""
check("agent 仅 api_key 字段回退", _get_agent_llm(), get_llm("agent"))
settings.agent_model_api_key, settings.agent_model_base_url = _agent_orig[1], ""
check("agent 仅 base_url 字段回退", _get_agent_llm(), get_llm("agent"))
settings.agent_model_base_url = _agent_orig[2]
settings.agent_model_name = settings.agent_model_api_key = settings.agent_model_base_url = ""
check("agent 三字段全回退 + temperature 覆盖", _get_agent_llm(temperature=0.5), get_llm("agent", temperature=0.5))
settings.agent_model_name, settings.agent_model_api_key, settings.agent_model_base_url = _agent_orig

print("\n=== 场景 4：api_key 缺失语义差异（精确复刻）===")
_real_deepseek_key = settings.deepseek_api_key
settings.deepseek_api_key = ""
old_raise = new_raise = None
try:
    _rag_get_llm()
except ValueError as exc:
    old_raise = str(exc)
try:
    get_llm("rag_generate")
except ValueError as exc:
    new_raise = str(exc)
check_ok("rag_generate api_key 空 → ValueError 且消息一致", old_raise is not None and new_raise == old_raise,
         f"old={old_raise!r}")
old_hyde = new_hyde = False
try:
    _hyde_get_llm()
except ValueError:
    old_hyde = True
try:
    get_llm("hyde")
except ValueError:
    new_hyde = True
check_ok("hyde api_key 空 → 双方都 raise", old_hyde and new_hyde)
settings.deepseek_api_key = _real_deepseek_key
_real_chat_key = settings.chat_api_key
settings.chat_api_key = ""
# 591 内联没有 api_key 前置检查（与 _get_llm/_get_chat_llm 的历史差异）：
# 空 key 时双方都会走到 ChatOpenAI 构造，由 openai SDK validate_environment 抛
# OpenAIError（首次对拍实测：构造不出实例，"照样构造"实为"构造层抛错"）。
# 故本用例对比双方抛错行为一致，而非实例参数。
old_err = new_err = None
try:
    ChatOpenAI(
        model=settings.chat_text_model,
        openai_api_key=settings.chat_api_key,
        openai_api_base=settings.chat_base_url,
        temperature=0.7,
        max_tokens=4096,
        streaming=True,
    )
except Exception as exc:
    old_err = type(exc).__name__
try:
    get_llm("chat_text", streaming=True)
except Exception as exc:
    new_err = type(exc).__name__
check_ok("chat_text api_key 空 → 双方构造层抛同类异常（591 原语义：无前置检查）",
         old_err is not None and new_err == old_err, f"exc={old_err!r}")
settings.chat_api_key = _real_chat_key

print("\n=== 场景 5：legacy 开关两态（use_legacy_llm_factory=True 内部复刻 vs 旧工厂直调）===")
settings.use_legacy_llm_factory = True
# 5.1 常规（5 角色 + streaming/temperature 变体）
check("legacy rag_generate", _rag_get_llm(), get_llm("rag_generate"))
check("legacy chat_multimodal", _get_chat_llm(), get_llm("chat_multimodal"))
check("legacy chat_multimodal streaming=True", _get_chat_llm(streaming=True), get_llm("chat_multimodal", streaming=True))
settings.chat_api_key = ""
# 5.2 整角色回退（chat_multimodal 是唯一 fallback_role 角色）
check("legacy chat_multimodal 回退", _get_chat_llm(streaming=True), get_llm("chat_multimodal", streaming=True))
settings.chat_api_key = _real_chat_key
check("legacy chat_text 591", old_591, get_llm("chat_text", streaming=True))
check("legacy hyde", _hyde_get_llm(), get_llm("hyde"))
check("legacy agent", _get_agent_llm(), get_llm("agent"))
check("legacy agent temperature=0.7 streaming=True", _get_agent_llm(temperature=0.7, streaming=True), get_llm("agent", temperature=0.7, streaming=True))
# 5.3 逐字段回退（agent 是唯一 per_field_fallback_prefix 角色，与场景 3 同 4 情形）
settings.agent_model_name = ""
check("legacy agent 仅 model 字段回退", _get_agent_llm(), get_llm("agent"))
settings.agent_model_name, settings.agent_model_api_key = _agent_orig[0], ""
check("legacy agent 仅 api_key 字段回退", _get_agent_llm(), get_llm("agent"))
settings.agent_model_api_key, settings.agent_model_base_url = _agent_orig[1], ""
check("legacy agent 仅 base_url 字段回退", _get_agent_llm(), get_llm("agent"))
settings.agent_model_base_url = _agent_orig[2]
settings.agent_model_name = settings.agent_model_api_key = settings.agent_model_base_url = ""
check("legacy agent 三字段全回退 + temperature 覆盖", _get_agent_llm(temperature=0.5), get_llm("agent", temperature=0.5))
settings.agent_model_name, settings.agent_model_api_key, settings.agent_model_base_url = _agent_orig
settings.use_legacy_llm_factory = False

n_fail = sum(1 for r in results if not r)
print(f"\n=== 对拍结果：{len(results) - n_fail}/{len(results)} 通过，{n_fail} 失败 ===")
if n_fail:
    print("任一处不通过 → 修网关，不进入步 2（需求 §6 步 1）")
sys.exit(1 if n_fail else 0)

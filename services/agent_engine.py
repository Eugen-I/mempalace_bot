"""services/agent_engine.py — агентный цикл (tool-calling) для qwen2.5 через Ollama.

run_agent() — основной вход: модель, способная вызывать инструменты, поочерёдно
выполняет tool_calls, получает результаты и собирает итоговый ответ.

Фаза 0: доступны только «системные» инструменты (agent_tools).
Фазы 1–2 расширят набор read-only инструментами MemPalace и Apple Notes.

Безопасность: инструменты ЗАПИСИ по умолчанию не доступны (include_write=False).
Цикл ограничен max_iterations (по умолчанию 5), каждый инструмент — таймаутом
tool_timeout (по умолчанию 60с).
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# Регистрация инструментов дворца, заметок и write-инструментов (side-effect imports).
from services import (  # noqa: F401
    agent_mcp_tools,
    agent_notes_tools,
    agent_notes_write_tools,
    agent_web_tools,
)
from services import agent_tools as atools
from services.ai_engine import (
    _OLLAMA_UNREACHABLE_MSG,
    _is_ollama_timeout,
    _is_ollama_unavailable,
    get_current_ai,
)
from services.ollama_process import ensure_ollama_running

try:
    from openai import OpenAI
except ImportError:
    OpenAI: Any = None  # type: ignore[no-redef]

logger = logging.getLogger("AgentEngine")

MAX_ITERATIONS = 5
TOOL_TIMEOUT = 60.0
MODEL_TIMEOUT = 120.0
OLLAMA_BASE_URL = "http://localhost:11434/v1"


class AgentEngineError(Exception):
    """Ошибка агентного режима (неподдерживаемый движок)."""


@dataclass
class AgentStep:
    """Один шаг цикла: вызовы инструментов и их результаты."""

    index: int
    calls: list = field(default_factory=list)  # [{"id", "name", "arguments"}]
    results: list = field(default_factory=list)  # [{"name", "ok", "output"}]


@dataclass
class AgentResult:
    """Итог работы агента."""

    final_answer: str
    steps: list = field(default_factory=list)
    iterations: int = 0
    finished_reason: str = "answer"  # answer | max_iterations | error
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True только для обычного завершения с ответом."""
        return self.finished_reason == "answer"

    @classmethod
    def failure(cls, error: str, *, finished_reason: str = "error") -> "AgentResult":
        """Безопасный результат для ошибок: final_answer всегда строка."""
        return cls(final_answer="", finished_reason=finished_reason, error=error)


def _qwen_tool_call(model: str, messages: list[dict], tools: list[dict]) -> dict:
    """Синхронный вызов Ollama c tools (запускается через asyncio.to_thread)."""
    ensure_ollama_running(model)
    if OpenAI is None:
        raise ImportError("Библиотека openai не установлена.")
    kwargs = {"base_url": OLLAMA_BASE_URL, "api_key": "ollama"}
    try:
        client = OpenAI(**kwargs, max_retries=0, timeout=MODEL_TIMEOUT)
    except TypeError:
        client = OpenAI(**kwargs)
    r = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools or None,
        tool_choice="auto",
        temperature=0.4,
        timeout=MODEL_TIMEOUT,
    )  # type: ignore[call-overload]
    choice = r.choices[0]
    message = choice.message
    tool_calls = []
    for tc in message.tool_calls or []:
        tool_calls.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": tc.function.arguments or "{}",
        })
    return {
        "content": message.content,
        "tool_calls": tool_calls,
        "finish_reason": choice.finish_reason,
    }


def _model_tool_call(engine: str, model: str, messages: list[dict], tools: list[dict]) -> dict:
    """Синхронный вызов модели c tools для qwen/ollama, openai, gemini."""
    engine = (engine or "").lower().strip()
    if engine in ("qwen", "ollama"):
        return _qwen_tool_call(model, messages, tools)

    if OpenAI is None:
        raise ImportError("Библиотека openai не установлена.")

    if engine == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set.")
        client = OpenAI(base_url="https://api.openai.com/v1", api_key=api_key)
        temperature = 0.4
    elif engine == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set.")
        client = OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=api_key,
        )
        temperature = 0.4
        # Google OpenAI-совместимый эндпоинт требует конкретных имён моделей
        if model in ("gemini-flash-latest", "gemini", ""):
            model = "gemini-2.5-flash"
        elif model in ("gemini-pro-latest", "gemini-pro"):
            model = "gemini-2.5-pro"
    else:
        raise AgentEngineError(f"Неподдерживаемый движок: '{engine}'.")

    r = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools or None,
        tool_choice="auto",
        temperature=temperature,
        timeout=MODEL_TIMEOUT,
    )  # type: ignore[call-overload]
    choice = r.choices[0]
    message = choice.message
    tool_calls = []
    for tc in message.tool_calls or []:
        tool_calls.append({
            "id": tc.id,
            "name": tc.function.name,
            "arguments": tc.function.arguments or "{}",
        })
    return {
        "content": message.content,
        "tool_calls": tool_calls,
        "finish_reason": choice.finish_reason,
    }


def _extract_tool_call_from_content(content: str, tool_map: dict) -> dict | None:
    """Извлекает «инструмент, написанный текстом» из ответа модели.

    qwen2.5 иногда возвращает JSON вызова инструмента не в структурированном
    tool_calls, а прямо в тексте content. Поддерживаем две формы:
      - {"name": "notes_search", "arguments": {...}}  («søker {…}»)
      - notes_search {"query": ...}                    («)&&(notes_search {…}»)
    Принимаем вызов только зарегистрированного инструмента; иначе None.
    """
    if not content:
        return None
    from services.json_parser import extract_json_from_text

    obj = extract_json_from_text(content)
    if isinstance(obj, dict):
        name = obj.get("name")
        arguments = obj.get("arguments")
        if (
            isinstance(name, str) and name in tool_map
            and isinstance(arguments, (dict, str))
        ):
            return {"id": "call_text", "name": name, "arguments": arguments}

    names = "|".join(map(re.escape, sorted(tool_map, key=len, reverse=True)))
    m = re.search(
        rf"(?:^|[\s()&;,+!]+)(?P<name>{names})\s*(?:\(\s*)?(?P<json>\{{)",
        content,
    )
    if not m:
        return None
    obj = extract_json_from_text(content[m.start("json"):])
    if not isinstance(obj, dict):
        return None
    return {"id": "call_text", "name": m.group("name"), "arguments": obj}


def _format_tool_status(name: str, args: dict, step: int, max_steps: int) -> str:
    """Формирует понятный статус выполнения инструмента для Telegram."""
    prefix = f"Шаг {step}/{max_steps}: "
    if name == "mp_search":
        q = args.get("query", "")
        return f"🔍 {prefix}Ищу во Дворце памяти: «{q[:40]}»…"
    if name == "web_search":
        q = args.get("query", "")
        return f"🌐 {prefix}Ищу в интернете: «{q[:40]}»…"
    if name == "notes_search":
        q = args.get("query", "")
        return f"📝 {prefix}Ищу в Apple Notes: «{q[:40]}»…"
    if name == "notes_read":
        return f"📄 {prefix}Читаю заметку Apple Notes…"
    if name in ("mempalace_list_wings", "mp_list_wings"):
        return f"🏛️ {prefix}Просматриваю крылья Дворца…"
    if name in ("mempalace_list_rooms", "mp_list_rooms"):
        w = args.get("wing", "")
        return f"🚪 {prefix}Просматриваю комнаты крыла «{w}»…"
    if name in ("mempalace_list_tunnels", "mp_list_tunnels"):
        return f"🔗 {prefix}Проверяю туннели Дворца…"
    if name in ("mempalace_list_drawers", "mp_list_drawers"):
        r = args.get("room", "")
        return f"🗄️ {prefix}Просматриваю ящики в комнате «{r}»…"
    if name == "mp_drawer_read":
        return f"📖 {prefix}Читаю ящик Дворца…"
    if name == "agent_now":
        return f"⏱️ {prefix}Уточняю текущую дату и время…"
    return f"🔧 {prefix}{name}…"


async def run_agent(
    system_prompt: str,
    user_prompt: str,
    engine: str | None = None,
    model: str | None = None,
    include_write: bool = False,
    allowed_categories: tuple | None = None,
    status_cb: Callable[[str], Awaitable[None]] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    tool_timeout: float = TOOL_TIMEOUT,
    confirm_write: Callable[[str, dict], Awaitable[bool]] | None = None,
    conversation_history: list[dict] | None = None,
) -> AgentResult:
    """Запускает агентный цикл и возвращает итоговый ответ.

    Параметры:
        system_prompt, user_prompt — системная инструкция и запрос пользователя.
        engine, model — движок и модель; если не заданы — из get_current_ai().
        include_write — разрешить инструменты записи (по умолчанию НЕТ).
        allowed_categories — ограничение категорий инструментов (allowlist).
        status_cb — async-колбэк для статусных сообщений («Шаг N/5: tool…»).
        confirm_write — async-колбэк (name, arguments) → bool. Вызывается ПЕРЕД
            выполнением каждого write-инструмента. Если возвращает False —
            инструмент НЕ выполняется, модели возвращается результат
            «Пользователь отклонил действие». Если confirm_write не передан,
            write-инструменты не доступны вообще (include_write игнорируется) —
            гарантия: запись без подтверждения невозможна.
    """
    if engine is None or model is None:
        engine, model = get_current_ai()
    engine = (engine or "").lower().strip()
    if engine not in ("qwen", "ollama", "openai", "gemini"):
        raise AgentEngineError(
            f"Неподдерживаемый движок агента: '{engine}'. "
            "Поддерживаются: qwen/ollama, openai, gemini. Смените модель в /settings.",
        )

    if confirm_write is None:
        include_write = False
    tools = atools.list_agent_tools(
        allowed_categories=allowed_categories, include_write=include_write,
    )
    tool_map = {t.name: t for t in tools}
    openai_tools = atools.to_openai_tools(tools)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]
    if conversation_history:
        messages.extend(
            m for m in conversation_history if m.get("role") != "system"
        )
    messages.append({"role": "user", "content": user_prompt})
    steps: list[AgentStep] = []

    if status_cb:
        display_m = "Gemini" if engine == "gemini" else model
        await status_cb(f"🤔 Анализирую задачу ({display_m})…")

    for i in range(1, max_iterations + 1):
        try:
            resp = await asyncio.to_thread(
                _model_tool_call, engine, model, messages, openai_tools,
            )
        except Exception as exc:
            if engine in ("qwen", "ollama") and _is_ollama_unavailable(exc):
                return AgentResult(
                    final_answer="",
                    steps=steps,
                    iterations=i - 1,
                    finished_reason="error",
                    error=(
                        f"{_OLLAMA_UNREACHABLE_MSG}. "
                        "Запустите Ollama или переключите модель в /settings."
                    ),
                )
            if engine in ("qwen", "ollama") and _is_ollama_timeout(exc):
                return AgentResult(
                    final_answer="",
                    steps=steps,
                    iterations=i - 1,
                    finished_reason="error",
                    error=(
                        f"⏱️ Локальная модель Ollama ({model}) не ответила вовремя (таймаут). "
                        "Рекомендуется уменьшить num_ctx в Ollama до 64K/128K "
                        "или переключить модель в /settings."
                    ),
                )
            logger.error("[AGENT] model call failed (%s): %s", engine, exc, exc_info=True)
            return AgentResult(
                final_answer="",
                steps=steps,
                iterations=i - 1,
                finished_reason="error",
                error=f"Ошибка вызова модели: {exc}",
            )

        calls = resp.get("tool_calls") or []
        content = (resp.get("content") or "").strip()
        if not calls:
            embedded = _extract_tool_call_from_content(content, tool_map)
            if embedded is not None:
                logger.info(
                    "[AGENT] модель написала вызов инструмента текстом: %s",
                    embedded["name"],
                )
                embedded["id"] = f"call_text_{i}"
                calls = [embedded]
            elif content:
                if status_cb:
                    await status_cb("🧠 Формирую итоговый ответ…")
                return AgentResult(
                    final_answer=content,
                    steps=steps,
                    iterations=i,
                    finished_reason="answer",
                )
            else:
                return AgentResult(
                    final_answer="",
                    steps=steps,
                    iterations=i,
                    finished_reason="error",
                    error="Модель вернула пустой ответ.",
                )

        step = AgentStep(index=i)
        for tc in calls:
            name = tc.get("name", "")
            args_raw = tc.get("arguments", "{}")
            try:
                arguments = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                arguments = {"_parse_error": args_raw}
            step.calls.append({
                "id": tc.get("id", f"call_{name}_{i}"),
                "name": name,
                "arguments": arguments,
            })

        for call in step.calls:
            name = call["name"]
            tool = tool_map.get(name)
            if tool is None:
                step.results.append({
                    "name": name, "ok": False,
                    "output": f"Инструмент '{name}' не существует.",
                })
                continue
            errors = atools.validate_arguments(tool, call["arguments"])
            if errors:
                step.results.append({
                    "name": name, "ok": False,
                    "output": "Ошибка аргументов: " + "; ".join(errors),
                })
                continue
            if tool.is_write and confirm_write is not None:
                approved = await confirm_write(name, call["arguments"])
                if not approved:
                    step.results.append({
                        "name": name, "ok": False,
                        "output": "Пользователь отклонил действие.",
                    })
                    continue
            if status_cb:
                await status_cb(
                    _format_tool_status(name, call["arguments"], i, max_iterations)
                )
            try:
                output = await asyncio.wait_for(
                    atools.execute_tool(tool, call["arguments"]),
                    timeout=tool_timeout,
                )
                step.results.append({"name": name, "ok": True, "output": output})
            except asyncio.TimeoutError:
                step.results.append({
                    "name": name, "ok": False,
                    "output": f"Превышен таймаут инструмента ({tool_timeout:g}с).",
                })
            except Exception as exc:
                logger.error("[AGENT] tool %s failed: %s", name, exc, exc_info=True)
                step.results.append({
                    "name": name, "ok": False,
                    "output": f"Ошибка инструмента: {exc}",
                })

        steps.append(step)
        for call, res in zip(step.calls, step.results):
            call_id = call["id"]
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                    },
                }],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": res["output"],
            })

    return AgentResult(
        final_answer="",
        steps=steps,
        iterations=max_iterations,
        finished_reason="max_iterations",
        error=(
            f"Достигнут лимит итераций агента ({max_iterations}). "
            "Уточните вопрос или разбейте задачу на части."
        ),
    )

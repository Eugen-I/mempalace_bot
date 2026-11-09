"""ai_engine.py
Унифицированный асинхронный вызов ИИ (Ollama, OpenAI, Gemini).
Поддерживает контекстно-зависимые промпты через get_smart_prompt.
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

# Настройка логгера для этого модуля
logger = logging.getLogger("AI_Engine")

try:
    from openai import OpenAI
except ImportError:
    OpenAI: Any = None  # type: ignore[no-redef]

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai: Any = None  # type: ignore[no-redef]

from config import CONFIG_AI_FILE, MODELS_CONFIG_PATH  # noqa: E402


@lru_cache(maxsize=1)
def _load_models_config() -> dict:
    """Загружает конфигурацию моделей из JSON файла."""
    if not os.path.exists(MODELS_CONFIG_PATH):
        logger.warning(f"Config file not found: {MODELS_CONFIG_PATH}. Using defaults.")
        return {"ollama": [], "openai": [], "gemini": []}
    try:
        with open(MODELS_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load models config: {e}")
        return {"ollama": [], "openai": [], "gemini": []}


def get_current_ai() -> tuple[str, str]:
    """Возвращает (engine, model_tag). Кэш сбрасывается при смене модели."""
    config = _load_models_config()
    current_tag = "gemini-flash-latest"

    if os.path.exists(CONFIG_AI_FILE):
        try:
            with open(CONFIG_AI_FILE) as f:
                content = f.read().strip()
                if content:
                    current_tag = content
        except Exception as e:
            logger.error(f"Error reading AI config file: {e}")

    # Поиск в конфиге
    for engine_type in ["ollama", "openai", "gemini"]:
        for m in config.get(engine_type, []):
            if m.get("tag") == current_tag:
                # Для Ollama используем совместимый с OpenAI клиент
                engine = "qwen" if engine_type == "ollama" else engine_type
                logger.info(f"Selected AI Engine: {engine}, Model: {m['tag']}")
                return engine, m["tag"]

    # Fallback
    logger.warning(
        f"Model tag '{current_tag}' not found in config. Falling back to gemini.",
    )
    return "gemini", current_tag


def invalidate_ai_cache():
    """Сбрасывает кэш конфигурации моделей."""
    _load_models_config.cache_clear()
    logger.info("AI Config cache invalidated.")


_OLLAMA_UNREACHABLE_MSG = "Не удалось подключиться к Ollama (localhost:11434)"

_OPENAI_STOP_TOKENS = [
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    "\nuser:",
    "\nUser:",
]

# Внешний таймаут async-адаптера. Он чуть больше сетевых таймаутов провайдеров,
# чтобы дать sync-вызову шанс завершиться самостоятельно.
DEFAULT_AI_TIMEOUT = 210.0


class AITimeoutError(TimeoutError):
    """Async-вызов AI не уложился в таймаут.

    Важно: отмена ``asyncio.to_thread`` не останавливает рабочий поток.
    Синхронный вызов может продолжить выполняться до завершения.
    """


def _is_ollama_unavailable(exc: Exception) -> bool:
    """True, если исключение связано с недоступностью локального Ollama."""
    if isinstance(exc, RuntimeError) and "Ollama" in str(exc):
        return True
    return type(exc).__name__ in {
        "APIConnectionError",
        "ConnectError",
        "ConnectTimeout",
    }


def _is_ollama_timeout(exc: Exception) -> bool:
    """True, если запрос к локальной модели Ollama превысил таймаут."""
    name = type(exc).__name__
    if name in {"APITimeoutError", "ReadTimeout", "TimeoutException"}:
        return True
    return "timed out" in str(exc).lower() or "readtimeout" in name.lower()


def _normalize_engine(engine: str) -> str:
    """Приводит имя движка к внутреннему виду (ollama → qwen)."""
    normalized = engine.lower().strip()
    return "qwen" if normalized == "ollama" else normalized


def _find_system_message(messages: list[dict]) -> dict | None:
    """Возвращает первое system-сообщение или None."""
    for message in messages:
        if message["role"] == "system":
            return message
    return None


def _system_instruction(messages: list[dict], fallback: str) -> str:
    """Берёт system-инструкцию из истории либо использует fallback."""
    system_message = _find_system_message(messages)
    if system_message is None:
        return fallback
    return system_message.get("content") or fallback


def _content_with_images(text: str, images: list[str]) -> list[dict]:
    """Собирает OpenAI-контент: текст + data-URL изображения."""
    content_parts: list[dict] = [{"type": "text", "text": text}]
    for image_b64 in images:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
        })
    return content_parts


def _prepare_chat_messages(
    messages: list[dict],
    system_prompt: str,
    images: list[str],
    *,
    use_message_system: bool,
    images_for_all_users: bool,
) -> list[dict]:
    """Нормализует историю для OpenAI-совместимых API.

    ``use_message_system`` — брать system из ``messages`` (sync) или объединять
    сгенерированный prompt с system-сообщениями из ``messages`` в одно ведущее
    system-сообщение (stream; в шаблонах Jinja Ollama/Qwen system-сообщение
    допустимо только на позиции 0).
    ``images_for_all_users`` — вкладывать изображения во все user-сообщения
    (stream) или только в первое (sync).
    """
    system_message = _find_system_message(messages) if use_message_system else None
    if system_message is not None:
        prepared = [system_message]
    else:
        extra_system: list[str] = []
        for msg in messages:
            if msg.get("role") == "system":
                content = (msg.get("content") or "").strip()
                if content and content != system_prompt:
                    if system_prompt and content.startswith(system_prompt):
                        content = content[len(system_prompt):].strip()
                    if content:
                        extra_system.append(content)
        combined = "\n\n".join(
            part for part in [system_prompt, *extra_system] if part
        )
        prepared = [{"role": "system", "content": combined or system_prompt}]

    if images:
        logger.info(f"[🖼️ MULTIMODAL] Received {len(images)} images.")
    else:
        logger.debug("[🖼️ MULTIMODAL] No images attached.")

    images_added = False
    for message in messages:
        if message.get("role") == "system":
            continue
        if (
            message["role"] == "user"
            and images
            and (images_for_all_users or not images_added)
        ):
            prepared.append({
                "role": "user",
                "content": _content_with_images(message.get("content", ""), images),
            })
            images_added = True
        else:
            prepared.append(message)
    return prepared


def _build_gemini_contents(
    messages: list[dict],
    images: list[str],
    *,
    include_images: bool,
    skip_system: bool,
) -> list:
    """Преобразует историю в Gemini Content; system-сообщения опциональны."""
    contents = []
    images_added = False
    for message in messages:
        if skip_system and message["role"] == "system":
            continue
        role = "user" if message["role"] == "user" else "model"
        parts = [genai_types.Part(text=message.get("content", ""))]
        if (
            include_images
            and message["role"] == "user"
            and images
            and not images_added
        ):
            for image_b64 in images:
                parts.append(
                    genai_types.Part.from_bytes(
                        data=base64.b64decode(image_b64),
                        mime_type="image/jpeg",
                    ),
                )
            images_added = True
        contents.append(genai_types.Content(role=role, parts=parts))
    return contents


def _extract_message_text(message: Any) -> str:
    """Достаёт текст из message-объекта OpenAI-совместимого ответа."""
    return getattr(message, "content", None) or ""


def _extract_openai_text(response: Any) -> str:
    """Достаёт текст первого choice; пустой список choices → ``""``."""
    choices = getattr(response, "choices", None)
    if not choices:
        return ""
    return _extract_message_text(choices[0].message)


def _extract_delta_text(chunk: Any) -> str:
    """Достаёт текстовый delta-чанк стрима; безопасен для пустых choices."""
    choices = getattr(chunk, "choices", None)
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return ""
    return getattr(delta, "content", None) or ""


def _extract_gemini_text(response: Any) -> str:
    """Достаёт текст Gemini-ответа; ``None`` превращается в ``""``."""
    text = getattr(response, "text", None) or ""
    try:
        candidates = getattr(response, "candidates", None)
        if candidates and len(candidates) > 0:
            c = candidates[0]
            finish_reason = getattr(c, "finish_reason", None)
            fr_str = str(finish_reason).upper()
            if "MAX_TOKENS" in fr_str:
                logger.warning("[GEMINI] Ответ был обрезан по MAX_TOKENS")
                notice = "\n\n⚠️ <i>(Ответ модели был обрезан из-за лимита токенов)</i>"
                is_json = text.lstrip().startswith(("{", "[", "```json", "```"))
                if not is_json and text and notice not in text:
                    text += notice
    except Exception as e:
        logger.debug("Failed checking finish_reason: %s", e)
    return text


def _strip_thinking_tags(text: str) -> str:
    """Удаляет теги размышлений DeepSeek и служебные токены."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return re.sub(
        r"<｜begin▁of▁sentence｜>.*?<｜end▁of▁sentence｜>",
        "",
        text,
        flags=re.DOTALL,
    )


def _build_system_prompt(context: str, user_query: str, has_images: bool) -> str:
    """Строит системный prompt или возвращает базовый fallback."""
    try:
        from services.prompts import get_smart_prompt

        return get_smart_prompt(
            context=context, query=user_query, has_images=has_images,
        )
    except ImportError:
        logger.error("Cannot import get_smart_prompt. Falling back to basic prompt.")
        return "Ты — полезный ассистент."


def _openai_client(engine: str, model: str) -> Any:
    """Создаёт OpenAI-совместимый клиент для qwen/openai."""
    if engine == "qwen":
        from services.ollama_process import ensure_ollama_running

        try:
            ensure_ollama_running(model)
        except RuntimeError as err:
            raise RuntimeError(f"{_OLLAMA_UNREACHABLE_MSG}. {err}") from err

        if OpenAI is None:
            raise ImportError("Библиотека openai не установлена.")

        logger.info(f"[OLLAMA] Sending request to {model}...")
        try:
            return OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
                max_retries=0,
                timeout=180.0,
            )
        except TypeError:
            return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    if engine == "openai":
        if OpenAI is None:
            raise ImportError("Библиотека openai не установлена.")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set.")
        return OpenAI(api_key=api_key)

    raise ValueError(f"Неизвестный движок: '{engine}'.")


def _gemini_client() -> Any:
    """Создаёт Gemini-клиент, проверяя зависимость и API-ключ."""
    if genai is None:
        raise ImportError("Библиотека google-genai не установлена.")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set.")
    return genai.Client(api_key=api_key)


def _openai_kwargs(
    model: str,
    messages: list[dict],
    *,
    default_temperature: float,
    sampling: dict | None,
    stream: bool,
) -> dict:
    """Собирает kwargs для chat.completions.create в sync/stream режимах."""
    sampling = sampling or {}
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": sampling.get("temperature", default_temperature),
        "max_tokens": 8192,
        "timeout": 180.0,
        "stop": list(_OPENAI_STOP_TOKENS),
    }
    kwargs.update({
        key: value for key, value in sampling.items() if key != "temperature"
    })
    if stream:
        kwargs["stream"] = True
    return kwargs


def _clean_qwen_sync_response(text: str, finish_reason: str | None) -> str:
    """Агрессивная очистка полного ответа qwen (только sync-режим)."""
    if not text:
        return "❌ Пустой ответ от Ollama."

    text = _strip_thinking_tags(text)

    for token in _OPENAI_STOP_TOKENS[:3]:
        if token in text:
            text = text.split(token)[0]

    text = re.split(
        r"\n(?:user|User|вы|Вы|Пользователь|Human|用户|助手):",
        text,
        flags=re.IGNORECASE,
    )[0]

    if re.search(r"[\u4e00-\u9fff]{5,}$", text):
        text = re.sub(r"[\u4e00-\u9fff]+$", "", text).strip()

    text = text.strip()
    if not text:
        if finish_reason == "length":
            return "❌ Ответ был обрезан из-за лимита токенов."
        return f"❌ Модель завершила генерацию без текста ({finish_reason})."
    return text


def _iter_ai_chunks(
    engine: str,
    model: str,
    messages: list[dict],
    system_prompt: str,
    images: list[str],
    *,
    sampling: dict | None = None,
    stream: bool,
) -> Iterator[str]:
    """Единый per-engine pipeline: отдаёт текст sync-ответа или stream-чанки.

    Sync-режим: один вызов провайдера, наружу отдаётся один текстовый чанк.
    Stream-режим: инкрементальные чанки провайдера. Различия сообщений,
    system и изображений инкапсулированы здесь и зависят только от ``stream``.
    """
    if engine in {"qwen", "openai"}:
        full_messages = _prepare_chat_messages(
            messages,
            system_prompt,
            images,
            use_message_system=not stream,
            images_for_all_users=stream,
        )
        client = _openai_client(engine, model)
        kwargs = _openai_kwargs(
            model,
            full_messages,
            default_temperature=0.6 if engine == "qwen" else 0.7,
            sampling=None if stream else sampling,
            stream=stream,
        )
        response = client.chat.completions.create(**kwargs)

        if stream:
            for chunk in response:
                text = _extract_delta_text(chunk)
                if text:
                    yield text
            return

        if engine == "qwen":
            choices = getattr(response, "choices", None)
            if not choices:
                yield "❌ Пустой ответ от Ollama."
                return
            choice = choices[0]
            yield _clean_qwen_sync_response(
                _extract_openai_text(response),
                choice.finish_reason,
            )
            return

        yield response.choices[0].message.content or ""
        return

    if engine == "gemini":
        if model in (
            "gemini-flash-latest", "gemini", "gemini-2.5-pro",
            "gemini-pro-latest", "gemini-pro", "",
        ):
            model = "gemini-2.5-flash"
        client = _gemini_client()
        contents = _build_gemini_contents(
            messages,
            images,
            include_images=not stream,
            skip_system=not stream,
        )
        sampling_dict = sampling or {}
        max_output_tokens = (
            sampling_dict.get("max_tokens")
            or sampling_dict.get("max_output_tokens")
            or 8192
        )
        temperature = sampling_dict.get("temperature", 0.7)
        config_kwargs: dict[str, Any] = {
            "system_instruction": (
                system_prompt if stream
                else _system_instruction(messages, system_prompt)
            ),
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if hasattr(genai_types, "ThinkingConfig") and "2.5" in model:
            config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)

        config = genai_types.GenerateContentConfig(**config_kwargs)

        if stream:
            response = client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
        text = _extract_gemini_text(response)
        yield text if text else "❌ Пустой ответ от Gemini."
        return

    if stream:
        # Историческое поведение: неизвестный движок в stream-режиме молча
        # завершает поток (legacy-адаптер не отдаёт чанков).
        return
    available = ["qwen", "openai", "gemini"]
    raise ValueError(f"Неизвестный движок: '{engine}'. Доступные: {available}")


def _sync_ai_call(
    engine: str,
    model: str,
    messages: list[dict],
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    **kwargs,
) -> str:
    """Синхронная обёртка для вызова в Thread (asyncio.to_thread).
    Использует get_smart_prompt для динамической генерации системной инструкции.

    Мультимодальный контракт: ``images`` — список base64-строк JPEG (без
    data-URL префикса). Для Gemini они передаются как inline image/jpeg,
    а system-сообщение — через ``system_instruction``.
    """
    engine = _normalize_engine(engine)
    start_time = time.time()
    logger.info(f"[SYNC_CALL] Starting call. Engine: {engine}, Model: {model}")

    existing_sys = _find_system_message(messages)
    if existing_sys and (existing_sys.get("content") or "").strip():
        system_prompt = existing_sys.get("content", "").strip()
    else:
        system_prompt = _build_system_prompt(context, user_query, has_images)

    try:
        return "".join(_iter_ai_chunks(
            engine,
            model,
            messages,
            system_prompt,
            kwargs.get("images", []),
            sampling=kwargs.get("sampling"),
            stream=False,
        ))
    except Exception as e:
        elapsed = time.time() - start_time
        if engine == "qwen" and _is_ollama_unavailable(e):
            error_msg = (
                f"🧠 {_OLLAMA_UNREACHABLE_MSG}. "
                "Запустите Ollama или переключите модель в /settings."
            )
        elif engine == "qwen" and _is_ollama_timeout(e):
            error_msg = (
                f"⏱️ Локальная модель Ollama ({model}) не ответила за {elapsed:.0f}с "
                "(таймаут). Рекомендуется уменьшить num_ctx в Ollama до 64K/128K "
                "или переключить модель в /settings."
            )
        else:
            error_msg = f"❌ Ошибка ИИ ({engine}) после {elapsed:.2f}s: {e!s}"
        logger.error(f"[AI_ERROR] {error_msg}", exc_info=True)
        return error_msg


def call_ai_sync(
    engine: str,
    model: str,
    messages: list[dict],
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    **kwargs,
) -> str:
    """Публичная sync-обёртка для запуска ``_sync_ai_call`` в отдельном потоке."""
    return _sync_ai_call(
        engine, model, messages, context, user_query, has_images, **kwargs,
    )


async def call_ai_async(
    engine: str | None,
    model: str | None,
    messages: list[dict],
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    *,
    timeout: float | None = None,
    **kwargs,
) -> str:
    """Выполняет синхронный AI-движок в отдельном потоке с таймаутом.

    Если ``engine``/``model`` не переданы, они берутся из ``get_current_ai()``.
    Это единственное место выбора движка/модели в адаптере — сам ``_sync_ai_call``
    получает уже разрешённые значения.

    ``asyncio.to_thread`` не прерывает рабочий поток при отмене: по таймауту
    выбрасывается ``AITimeoutError``, но sync-вызов может продолжать работать.
    Поэтому для долгих запросов таймаут обязателен.

    Ошибки синхронного вызова пробрасываются вызывающему без преобразования
    в пользовательскую строку — решение об обработке принимает handler.
    """
    resolved_engine = engine
    resolved_model = model
    if not resolved_engine or not resolved_model:
        current_engine, current_model = get_current_ai()
        resolved_engine = resolved_engine or current_engine
        resolved_model = resolved_model or current_model

    effective_timeout = DEFAULT_AI_TIMEOUT if timeout is None else timeout
    if effective_timeout <= 0:
        raise ValueError("AI timeout must be positive")

    call_kwargs = dict(kwargs)
    if context:
        call_kwargs["context"] = context
    if user_query:
        call_kwargs["user_query"] = user_query
    if has_images:
        call_kwargs["has_images"] = has_images

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _sync_ai_call,
                resolved_engine,
                resolved_model,
                messages,
                **call_kwargs,
            ),
            timeout=effective_timeout,
        )
    except TimeoutError as exc:
        raise AITimeoutError(
            f"AI call timed out after {effective_timeout:.2f}s "
            f"(engine={resolved_engine}, model={resolved_model}); "
            "worker thread may still be running",
        ) from exc


async def get_ai_response_async(
    engine: str,
    model: str,
    messages: list[dict],
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    **kwargs,
) -> str:
    """Асинхронный вызов ИИ без блокировки event loop."""
    loop = asyncio.get_event_loop()
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor() as pool:
        try:
            result = await loop.run_in_executor(
                pool,
                lambda: _sync_ai_call(
                    engine,
                    model,
                    messages,
                    context,
                    user_query=user_query,
                    has_images=has_images,
                    **kwargs,
                ),
            )
            return result
        except Exception as e:
            logger.error(f"[ASYNC_CALL] Executor failed: {e}", exc_info=True)
            return f"❌ Системная ошибка выполнения запроса: {e!s}"


@dataclass(frozen=True, slots=True)
class AIStreamEvent:
    """Структурированное событие стриминга AI.

    Текстовый чанк: ``ok=True`` и непустой ``text``.
    Ошибка: ``ok=False``, ``error_code`` и ``error_message``; ``text`` пустой.
    Ошибка приходит отдельным событием, поэтому её не нужно искать по префиксу.
    """

    ok: bool
    text: str = ""
    error_code: str | None = None
    error_message: str | None = None


async def stream_ai_events_async(
    engine: str,
    model: str,
    messages: list[dict],
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    **kwargs,
) -> AsyncIterator[AIStreamEvent]:
    """Асинхронный генератор структурированных событий стриминга.

    Успешный стрим отдаёт только события ``ok=True`` с текстовыми чанками.
    Ошибка до первого токена или в середине стрима приходит событием
    ``ok=False``; уже отданный текст остаётся в предыдущих событиях.
    Пустой успешный стрим превращается в событие ``error_code="empty_stream"``.
    """
    engine = _normalize_engine(engine)

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[AIStreamEvent | None] = asyncio.Queue()
    emitted_text = False

    existing_sys = _find_system_message(messages)
    if existing_sys and (existing_sys.get("content") or "").strip():
        system_prompt = existing_sys.get("content", "").strip()
    else:
        system_prompt = _build_system_prompt(context, user_query, has_images)

    def _emit_text(text: str) -> None:
        nonlocal emitted_text
        emitted_text = True
        loop.call_soon_threadsafe(
            queue.put_nowait, AIStreamEvent(ok=True, text=text),
        )

    def _run_stream():
        try:
            for chunk in _iter_ai_chunks(
                engine,
                model,
                messages,
                system_prompt,
                kwargs.get("images", []),
                sampling=None,
                stream=True,
            ):
                text = _strip_thinking_tags(chunk) if engine == "qwen" else chunk
                if text:
                    _emit_text(text)

        except Exception as e:
            if engine == "qwen" and _is_ollama_unavailable(e):
                error_code = "ollama_unavailable"
                error_message = (
                    f"{_OLLAMA_UNREACHABLE_MSG}. "
                    "Запустите Ollama или переключите модель в /settings."
                )
            else:
                error_code = "stream_error"
                error_message = str(e)
            logger.error(
                f"[STREAM_ERROR] {error_code}: {error_message}",
                exc_info=True,
            )
            loop.call_soon_threadsafe(
                queue.put_nowait,
                AIStreamEvent(
                    ok=False,
                    error_code=error_code,
                    error_message=error_message,
                ),
            )
        else:
            if not emitted_text:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    AIStreamEvent(
                        ok=False,
                        error_code="empty_stream",
                        error_message="Модель не вернула текст.",
                    ),
                )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    task = asyncio.create_task(asyncio.to_thread(_run_stream))

    while True:
        event = await queue.get()
        if event is None:
            break
        yield event

    await task


async def stream_ai_response_async(
    engine: str,
    model: str,
    messages: list[dict],
    context: str = "",
    user_query: str = "",
    has_images: bool = False,
    **kwargs,
) -> AsyncIterator[str]:
    """Устаревший строковый адаптер потока.

    .. deprecated:: S1.6
       Используйте :func:`stream_ai_events_async`: он различает текст и ошибки
       структурно. Этот адаптер оставлен для старых обработчиков, которые ещё
       ждут строковые чанки и проверяют префикс ``❌``.
    """
    async for event in stream_ai_events_async(
        engine,
        model,
        messages,
        context=context,
        user_query=user_query,
        has_images=has_images,
        **kwargs,
    ):
        if event.ok:
            if event.text:
                yield event.text
            continue
        # Сохраняем прежнее поведение: пустой поток не давал ни одного чанка.
        if event.error_code == "empty_stream":
            continue
        if event.error_code == "ollama_unavailable":
            yield f"\n🧠 {event.error_message or ''}"
        else:
            yield f"\n❌ Ошибка стриминга: {event.error_message or ''}"

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
from collections.abc import AsyncIterator
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
    # Нормализация названия движка
    engine = engine.lower().strip()
    if engine == "ollama":
        engine = "qwen"  # Для обратной совместимости с Ollama через OpenAI API

    start_time = time.time()
    logger.info(f"[SYNC_CALL] Starting call. Engine: {engine}, Model: {model}")

    # 1. Генерация УМНОГО ПРОМПТА
    try:
        from services.prompts import get_smart_prompt

        system_prompt = get_smart_prompt(
            context=context, query=user_query, has_images=has_images,
        )
    except ImportError:
        logger.error("Cannot import get_smart_prompt. Falling back to basic prompt.")
        system_prompt = "Ты — полезный ассистент."

    # 2. Формирование сообщений
    # Если в messages уже есть system prompt (например, FORMAT_PROMPT) — используем его
    # Иначе используем умный промпт с контекстом
    system_from_messages = [m for m in messages if m["role"] == "system"]
    if system_from_messages:
        full_messages = [system_from_messages[0]]
    else:
        full_messages = [{"role": "system", "content": system_prompt}]

    images_base64 = kwargs.get("images", [])
    images_added = False

    # Отладка изображений
    if images_base64:
        logger.info(f"[🖼️ MULTIMODAL] Received {len(images_base64)} images.")
    else:
        logger.debug("[🖼️ MULTIMODAL] No images attached.")

    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "user" and images_base64 and not images_added:
            # Формируем контент с картинками для OpenAI-compatible API
            content_parts = [{"type": "text", "text": m.get("content", "")}]
            for img_b64 in images_base64:
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                )
            full_messages.append({"role": "user", "content": content_parts})
            images_added = True
        else:
            full_messages.append(m)

    try:
        if engine == "qwen":  # Ollama через OpenAI совместимый API
            from services.ollama_process import ensure_ollama_running

            try:
                ensure_ollama_running(model)
            except RuntimeError as err:
                raise RuntimeError(
                    f"{_OLLAMA_UNREACHABLE_MSG}. {err}",
                ) from err

            if OpenAI is None:
                raise ImportError("Библиотека openai не установлена.")

            client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            logger.info(f"[OLLAMA] Sending request to {model}...")

            sampling = kwargs.get("sampling") or {}
            call_kwargs = {
                "model": model,
                "messages": full_messages,
                "temperature": sampling.get("temperature", 0.6),
                "max_tokens": 8192,
                "timeout": 200.0,
                "stop": [
                    "<|im_start|>",
                    "<|im_end|>",
                    "<|endoftext|>",
                    "\nuser:",
                    "\nUser:",
                ],
            }
            call_kwargs.update({
                k: v for k, v in sampling.items() if k != "temperature"
            })

            r = client.chat.completions.create(**call_kwargs)

            elapsed = time.time() - start_time

            choices = getattr(r, "choices", None)
            if not choices:
                return "❌ Пустой ответ от Ollama."

            choice = choices[0]
            response_text = choice.message.content or ""

            # ✅ АГРЕССИВНАЯ ОЧИСТКА ДЛЯ DEEPSEEK/R1
            if response_text:
                # 1. Удаляем теги мышления DeepSeek (если они просочились)
                # Удаляем всё внутри <think>...</think> или аналогичных конструкций
                response_text = re.sub(
                    r"<think>.*?</think>", "", response_text, flags=re.DOTALL,
                )
                response_text = re.sub(
                    r"<｜begin▁of▁sentence｜>.*?<｜end▁of▁sentence｜>",
                    "",
                    response_text,
                    flags=re.DOTALL,
                )

                # 2. Удаляем стандартные ChatML токены (для совместимости)
                for token in ["<|im_start|>", "<|im_end|>", "<|endoftext|>"]:
                    if token in response_text:
                        response_text = response_text.split(token)[0]

                # 3. Обрезаем имитацию реплики пользователя
                response_text = re.split(
                    r"\n(?:user|User|вы|Вы|Пользователь|Human|用户|助手):",
                    response_text,
                    flags=re.IGNORECASE,
                )[0]

                # 4. Удаляем оставшиеся китайские иероглифы, если они идут блоком в конце (артефакт утечки)  # noqa: E501
                # Это крайняя мера, если модель начала писать на китайском после русского текста
                if re.search(r"[\u4e00-\u9fff]{5,}$", response_text):
                    response_text = re.sub(
                        r"[\u4e00-\u9fff]+$", "", response_text,
                    ).strip()

                # 5. Финальная зачистка пробелов
                response_text = response_text.strip()

                if not response_text:
                    if choice.finish_reason == "length":
                        return "❌ Ответ был обрезан из-за лимита токенов."
                    return f"❌ Модель завершила генерацию без текста ({choice.finish_reason})."

                return response_text
            return "❌ Пустой ответ от Ollama."

        if engine == "openai":
            if OpenAI is None:
                raise ImportError("Библиотека openai не установлена.")

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set.")

            client = OpenAI(api_key=api_key)
            sampling = kwargs.get("sampling") or {}
            call_kwargs = {
                "model": model,
                "messages": full_messages,
                "temperature": sampling.get("temperature", 0.7),
                "max_tokens": 8192,
                "timeout": 200.0,
                "stop": [
                    "<|im_start|>",
                    "<|im_end|>",
                    "<|endoftext|>",
                    "\nuser:",
                    "\nUser:",
                ],
            }
            call_kwargs.update({
                k: v for k, v in sampling.items() if k != "temperature"
            })

            r = client.chat.completions.create(**call_kwargs)
            return r.choices[0].message.content or ""

        if engine == "gemini":
            if genai is None:
                raise ImportError("Библиотека google-genai не установлена.")

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set.")

            client = genai.Client(api_key=api_key)  # type: ignore[assignment]

            system_instruction = system_prompt
            if system_from_messages:
                system_instruction = (
                    system_from_messages[0].get("content") or system_prompt
                )

            # Преобразование сообщений в формат Gemini.
            # system-сообщения передаются через system_instruction, а не как role=model.
            hist = []
            gemini_images_added = False
            for m in messages:
                if m["role"] == "system":
                    continue
                role = "user" if m["role"] == "user" else "model"
                parts = [genai_types.Part(text=m.get("content", ""))]
                if (
                    m["role"] == "user"
                    and images_base64
                    and not gemini_images_added
                ):
                    for img_b64 in images_base64:
                        parts.append(
                            genai_types.Part.from_bytes(
                                data=base64.b64decode(img_b64),
                                mime_type="image/jpeg",
                            ),
                        )
                    gemini_images_added = True
                hist.append(genai_types.Content(role=role, parts=parts))

            r = client.models.generate_content(  # type: ignore[attr-defined]
                model=model,
                contents=hist,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )
            text = r.text
            if not text:
                return "❌ Пустой ответ от Gemini."
            return text

        available = ["qwen", "openai", "gemini"]
        raise ValueError(f"Неизвестный движок: '{engine}'. Доступные: {available}")

    except Exception as e:
        elapsed = time.time() - start_time
        if engine == "qwen" and _is_ollama_unavailable(e):
            error_msg = (
                f"🧠 {_OLLAMA_UNREACHABLE_MSG}. "
                "Запустите Ollama или переключите модель в /settings."
            )
        else:
            error_msg = f"❌ Ошибка ИИ ({engine}) после {elapsed:.2f}s: {e!s}"
        logger.error(f"[AI_ERROR] {error_msg}", exc_info=True)
        return error_msg


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
    engine = engine.lower().strip()
    if engine == "ollama":
        engine = "qwen"

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[AIStreamEvent | None] = asyncio.Queue()
    emitted_text = False

    try:
        from services.prompts import get_smart_prompt

        system_prompt = get_smart_prompt(
            context=context, query=user_query, has_images=has_images,
        )
    except ImportError:
        system_prompt = "Ты — полезный ассистент."

    full_messages = [{"role": "system", "content": system_prompt}]
    images_base64 = kwargs.get("images", [])

    for m in messages:
        if m["role"] == "user" and images_base64:
            content_parts = [{"type": "text", "text": m.get("content", "")}]
            for img_b64 in images_base64:
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                )
            user_content: dict[str, Any] = {"role": "user", "content": content_parts}
            full_messages.append(user_content)
        else:
            full_messages.append(m)

    def _clean_chunk(text: str) -> str:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(
            r"<｜begin▁of▁sentence｜>.*?<｜end▁of▁sentence｜>",
            "",
            text,
            flags=re.DOTALL,
        )
        return text

    def _emit_text(text: str) -> None:
        nonlocal emitted_text
        emitted_text = True
        loop.call_soon_threadsafe(
            queue.put_nowait, AIStreamEvent(ok=True, text=text),
        )

    def _run_stream():
        try:
            if engine == "qwen":
                from services.ollama_process import ensure_ollama_running

                try:
                    ensure_ollama_running(model)
                except RuntimeError as err:
                    raise RuntimeError(
                        f"{_OLLAMA_UNREACHABLE_MSG}. {err}",
                    ) from err

                if OpenAI is None:
                    raise ImportError("Библиотека openai не установлена.")
                client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
                stream = client.chat.completions.create(
                    model=model,
                    messages=full_messages,
                    temperature=0.6,
                    max_tokens=8192,
                    timeout=200.0,
                    stream=True,
                    stop=[
                        "<|im_start|>",
                        "<|im_end|>",
                        "<|endoftext|>",
                        "\nuser:",
                        "\nUser:",
                    ],
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        cleaned = _clean_chunk(delta.content)
                        if cleaned:
                            _emit_text(cleaned)

            elif engine == "openai":
                if OpenAI is None:
                    raise ImportError("Библиотека openai не установлена.")
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not set.")
                client = OpenAI(api_key=api_key)
                stream = client.chat.completions.create(
                    model=model,
                    messages=full_messages,
                    temperature=0.7,
                    max_tokens=8192,
                    timeout=200.0,
                    stream=True,
                    stop=[
                        "<|im_start|>",
                        "<|im_end|>",
                        "<|endoftext|>",
                        "\nuser:",
                        "\nUser:",
                    ],
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        _emit_text(delta.content)

            elif engine == "gemini":
                if genai is None:
                    raise ImportError("Библиотека google-genai не установлена.")
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("GEMINI_API_KEY not set.")
                client = genai.Client(api_key=api_key)
                hist = []
                for m in messages:
                    role = "user" if m["role"] == "user" else "model"
                    hist.append(
                        genai_types.Content(
                            role=role, parts=[genai_types.Part(text=m["content"])],
                        ),
                    )
                stream = client.models.generate_content_stream(
                    model=model,
                    contents=hist,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.7,
                        max_output_tokens=2048,
                    ),
                )
                for chunk in stream:
                    if chunk.text:
                        _emit_text(chunk.text)

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

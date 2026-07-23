"""
ai_engine.py
Унифицированный асинхронный вызов ИИ (Ollama, OpenAI, Gemini).
Поддерживает контекстно-зависимые промпты через get_smart_prompt.
"""
import os
import json
import asyncio
import logging
import time
from typing import List, Dict, Tuple
from functools import lru_cache

# Настройка логгера для этого модуля
logger = logging.getLogger("AI_Engine")

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None

from config import MODELS_CONFIG_PATH, CONFIG_AI_FILE

@lru_cache(maxsize=1)
def _load_models_config() -> dict:
    """Загружает конфигурацию моделей из JSON файла."""
    if not os.path.exists(MODELS_CONFIG_PATH):
        logger.warning(f"Config file not found: {MODELS_CONFIG_PATH}. Using defaults.")
        return {"ollama": [], "openai": [], "gemini": []}
    try:
        with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load models config: {e}")
        return {"ollama": [], "openai": [], "gemini": []}

def get_current_ai() -> Tuple[str, str]:
    """Возвращает (engine, model_tag). Кэш сбрасывается при смене модели."""
    config = _load_models_config()
    current_tag = "gemini-flash-latest"
    
    if os.path.exists(CONFIG_AI_FILE):
        try:
            with open(CONFIG_AI_FILE, "r") as f:
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
    logger.warning(f"Model tag '{current_tag}' not found in config. Falling back to gemini.")
    return "gemini", current_tag

def invalidate_ai_cache():
    """Сбрасывает кэш конфигурации моделей."""
    _load_models_config.cache_clear()
    logger.info("AI Config cache invalidated.")

def _sync_ai_call(
    engine: str, 
    model: str, 
    messages: List[Dict], 
    context: str = "", 
    user_query: str = "", 
    has_images: bool = False, 
    **kwargs
) -> str:
    """
    Синхронная обёртка для вызова в Thread (asyncio.to_thread).
    Использует get_smart_prompt для динамической генерации системной инструкции.
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
            context=context, 
            query=user_query, 
            has_images=has_images
        )
    except ImportError:
        logger.error("Cannot import get_smart_prompt. Falling back to basic prompt.")
        system_prompt = "Ты — полезный ассистент."

    # 2. Формирование сообщений
    full_messages = [{"role": "system", "content": system_prompt}]
    
    images_base64 = kwargs.get("images", [])
    images_added = False

    # Отладка изображений
    if images_base64:
        logger.info(f"[🖼️ MULTIMODAL] Received {len(images_base64)} images.")
    else:
        logger.debug("[🖼️ MULTIMODAL] No images attached.")

    for m in messages:
        if m["role"] == "user" and images_base64 and not images_added:
            # Формируем контент с картинками для OpenAI-compatible API
            content_parts = [{"type": "text", "text": m.get("content", "")}]
            for img_b64 in images_base64:
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                })
            full_messages.append({"role": "user", "content": content_parts})
            images_added = True
        else:
            full_messages.append(m)

    try:
        if engine == "qwen":  # Ollama через OpenAI совместимый API
            if not OpenAI: 
                raise ImportError("Библиотека openai не установлена.")
            
            client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            logger.info(f"[OLLAMA] Sending request to {model}...")
            
            r = client.chat.completions.create(
                model=model, 
                messages=full_messages, 
                temperature=0.6,  
                max_tokens=8192, 
                timeout=200.0,
                stop=["<|im_start|>", "<|im_end|>", "<|endoftext|>", "\nuser:", "\nUser:"]
            )
            
            elapsed = time.time() - start_time
            
            if hasattr(r, 'choices') and r.choices:
                choice = r.choices[0]
                response_text = choice.message.content
                
            
            # ✅ АГРЕССИВНАЯ ОЧИСТКА ДЛЯ DEEPSEEK/R1
            if response_text:
                # 1. Удаляем теги мышления DeepSeek (если они просочились)
                import re
                
                # Удаляем всё внутри <think>...</think> или аналогичных конструкций
                response_text = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL)
                response_text = re.sub(r'<｜begin▁of▁sentence｜>.*?<｜end▁of▁sentence｜>', '', response_text, flags=re.DOTALL)
                
                # 2. Удаляем стандартные ChatML токены (для совместимости)
                for token in ["<|im_start|>", "<|im_end|>", "<|endoftext|>"]:
                    if token in response_text:
                        response_text = response_text.split(token)[0]
                
                # 3. Обрезаем имитацию реплики пользователя
                response_text = re.split(
                    r'\n(?:user|User|вы|Вы|Пользователь|Human|用户|助手):', 
                    response_text, 
                    flags=re.IGNORECASE
                )[0]
                
                # 4. Удаляем оставшиеся китайские иероглифы, если они идут блоком в конце (артефакт утечки)
                # Это крайняя мера, если модель начала писать на китайском после русского текста
                if re.search(r'[\u4e00-\u9fff]{5,}$', response_text):
                    response_text = re.sub(r'[\u4e00-\u9fff]+$', '', response_text).strip()
                
                # 5. Финальная зачистка пробелов
                response_text = response_text.strip()

                if not response_text:
                    if choice.finish_reason == "length":
                        return "❌ Ответ был обрезан из-за лимита токенов."
                    return f"❌ Модель завершила генерацию без текста ({choice.finish_reason})."
                
                return response_text
            else:
                return "❌ Пустой ответ от Ollama."
    
        elif engine == "openai":
            if not OpenAI: 
                raise ImportError("Библиотека openai не установлена.")
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set.")
                
            client = OpenAI(api_key=api_key)
            r = client.chat.completions.create(
                model=model, 
                messages=full_messages, 
                temperature=0.7,
                max_tokens=8192,
                timeout=200.0,
                stop=["<|im_start|>", "<|im_end|>", "<|endoftext|>", "\nuser:", "\nUser:"]
            )
            return r.choices[0].message.content
    
        elif engine == "gemini":
            if not genai: 
                raise ImportError("Библиотека google-genai не установлена.")
            
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set.")

            client = genai.Client(api_key=api_key)
            
            # Преобразование сообщений в формат Gemini
            hist = []
            for m in messages:
                role = "user" if m["role"] == "user" else "model"
                parts = [genai_types.Part(text=m["content"])]
                hist.append(genai_types.Content(role=role, parts=parts))
            
            r = client.models.generate_content(
                model=model, 
                contents=hist,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt, 
                    temperature=0.7,
                    max_output_tokens=2048
                )
            )
            return r.text
    
        else:
            available = ["qwen", "openai", "gemini"]
            raise ValueError(f"Неизвестный движок: '{engine}'. Доступные: {available}")
        
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"❌ Ошибка ИИ ({engine}) после {elapsed:.2f}s: {str(e)}"
        logger.error(f"[AI_ERROR] {error_msg}", exc_info=True)
        return error_msg

async def get_ai_response_async(
    engine: str, 
    model: str, 
    messages: List[Dict], 
    context: str = "", 
    user_query: str = "", 
    has_images: bool = False, 
    **kwargs
) -> str:
    """Асинхронный вызов ИИ без блокировки event loop."""
    loop = asyncio.get_event_loop()
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor() as pool:
        try:
            result = await loop.run_in_executor(
                pool, 
                lambda: _sync_ai_call(
                    engine, model, messages, context, 
                    user_query=user_query, 
                    has_images=has_images, 
                    **kwargs
                )
            )
            return result
        except Exception as e:
            logger.error(f"[ASYNC_CALL] Executor failed: {e}", exc_info=True)
            return f"❌ Системная ошибка выполнения запроса: {str(e)}"
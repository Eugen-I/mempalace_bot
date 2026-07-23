"""
tts_processor.py
Подготовка текста для macOS say, обработка эмодзи, асинхронная генерация OGG.
ИСПРАВЛЕНО: Полное удаление бэкслешей и экранированных символов перед озвучкой.
"""
import os
import re
import asyncio
import tempfile
import json
from typing import List
from config import VOICE_OUTPUT_DIR, VOICE_REPLY_CONFIG

DEFAULT_SPEED = 175

# Эмоциональные эмодзи -> пауза + легкое изменение ритма
EMOTIONAL_EMOJI = re.compile(r'[😂🤣😭😡🥺🔥❤️👍👎🤔🎉🙏]')
TECHNICAL_EMOJI = re.compile(r'[📎⚙️📄✅❌🔍📝🤖💬📅🗑️🆕📂]')


def prepare_tts_text(text: str) -> str:
    """Очищает текст для озвучки. Игнорирует системные ошибки."""
    if not text:
        return ""
    # 🛑 Блокируем озвучку ошибок
    if text.strip().startswith("❌") or "Ошибка" in text or "NOT_FOUND" in text:
        return ""

    # 1. Удаляем технические эмодзи полностью
    text = TECHNICAL_EMOJI.sub('', text)
    # 2. Эмоциональные эмодзи -> пауза 400мс
    text = EMOTIONAL_EMOJI.sub(' [[slnc 400]] ', text)

    # 3. Чистим блоки кода и ссылки
    text = re.sub(r'```[\s\S]*?```', ' [[slnc 300]] блок кода пропущен [[slnc 300]] ', text)
    text = re.sub(r'`[^`]+`', ' фрагмент кода ', text)
    text = re.sub(r'https?://\S+', ' ссылка ', text)

    # 🔧 ЖЕСТКАЯ ОЧИСТКА ОТ БЭКСТЕШЕЙ И ЭКРАНИРОВАНИЯ
    # Удаляем экранированные символы (\n, \t, \*, \_, \\ и т.д.)
    text = re.sub(r'\\[ntr\'"\\*_~`#|<>]', ' ', text)
    # Удаляем любые оставшиеся одиночные бэкслеши
    text = text.replace('\\', ' ')
    # Удаляем оставшийся markdown-мусор
    text = re.sub(r'[#*_~|<>]', '', text)
    text = re.sub(r'\$', ' ', text)
    # 4. Абзацы -> паузы
    text = re.sub(r'\n\s*\n', ' [[slnc 500]] ', text)

    # 5. Финальная нормализация пробелов
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def split_tts_text(text: str, max_chars: int = 1800) -> List[str]:
    """Разбивает текст для say, не разрывая предложения."""
    if len(text) <= max_chars:
        return [text]
    parts, rem = [], text
    while rem:
        if len(rem) <= max_chars:
            parts.append(rem)
            break
        idx = max(rem.rfind('. ', 0, max_chars), rem.rfind('! ', 0, max_chars), rem.rfind('? ', 0, max_chars))
        if idx == -1:
            idx = max_chars
        parts.append(rem[:idx+1].strip())
        rem = rem[idx+1:].strip()
    return parts

def get_voice_settings(user_id: int) -> dict:
    if not os.path.exists(VOICE_REPLY_CONFIG):
        return {"mode": "text", "speed": DEFAULT_SPEED}
    with open(VOICE_REPLY_CONFIG, "r") as f:
        cfg = json.load(f)
    return cfg.get(str(user_id), {"mode": "text", "speed": DEFAULT_SPEED})

def set_voice_setting(user_id: int, key: str, value):
    cfg = {}
    if os.path.exists(VOICE_REPLY_CONFIG):
        with open(VOICE_REPLY_CONFIG, "r") as f:
            cfg = json.load(f)
    cfg.setdefault(str(user_id), {"mode": "text", "speed": DEFAULT_SPEED})[key] = value
    with tempfile.NamedTemporaryFile("w", delete=False, dir=os.path.dirname(VOICE_REPLY_CONFIG)) as tmp:
        json.dump(cfg, tmp, indent=2)
        os.replace(tmp.name, VOICE_REPLY_CONFIG)

async def generate_voice_async(user_id: int, text: str) -> List[str]:
    """Асинхронная генерация OGG через say + ffmpeg."""
    tts = prepare_tts_text(text)
    if not tts:
        return []
    chunks = split_tts_text(tts)
    paths = []
    speed = get_voice_settings(user_id).get("speed", DEFAULT_SPEED)
    for i, chunk in enumerate(chunks):
        uid = next(tempfile._get_candidate_names())
        aiff = os.path.join(VOICE_OUTPUT_DIR, f"v_{user_id}_{uid}_{i}.aiff")
        ogg = aiff.replace(".aiff", ".ogg")
        try:
            proc = await asyncio.create_subprocess_exec(
                "say", "-v", "Milena", "-r", str(speed), "-o", aiff, chunk,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                ffmpeg = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", aiff, "-c:a", "libopus", "-b:a", "64k", ogg,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await ffmpeg.communicate()
                if os.path.exists(ogg):
                    paths.append(ogg)
                if os.path.exists(aiff):
                    os.remove(aiff)
        except Exception as e:
            print(f"TTS Error: {e}")
    return paths
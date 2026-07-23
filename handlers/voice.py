"""
voice.py
Обработка голосовых сообщений: транскрипция faster-whisper, передача в главный обработчик.
ИСПРАВЛЕНО: Строгое соблюдение настроек режима ответа (Текст/Голос/Вместе).
"""
import os
import sys
import asyncio
import logging
from aiogram import F, Router, types
from aiogram.enums import ContentType
from faster_whisper import WhisperModel
import pydub
from config import TEMP_DIR, allowed_only
from services.text_formatter import safe_html_format
from services.tts_processor import get_voice_settings, generate_voice_async, prepare_tts_text, split_tts_text

router = Router()
logger = logging.getLogger("VoiceHandler")
_whisper = None

def get_whisper():
    global _whisper
    if not _whisper:
        # Для Apple Silicon (M1/M2/M3) стабильнее всего device="cpu" + compute_type="int8"
        _whisper = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper

def _process_audio_sync(ogg_path: str, wav_path: str) -> str:
    """Синхронная обработка аудио для запуска в отдельном потоке."""
    pydub.AudioSegment.from_ogg(ogg_path).export(wav_path, format="wav")
    segs, _ = get_whisper().transcribe(wav_path, language="ru", beam_size=5)
    return " ".join(s.text for s in segs).strip()

@router.message(F.voice)
@allowed_only
async def handle_voice(message: types.Message):
    status = await message.answer("🎧 Транскрибирую...")
    ogg = os.path.join(TEMP_DIR, f"v_{message.message_id}.ogg")
    wav = ogg.replace(".ogg", ".wav")
    
    try:
        file_info = await message.bot.get_file(message.voice.file_id)
        await message.bot.download_file(file_info.file_path, destination=ogg)

        # ✅ Запускаем CPU-задачи в фоновом потоке, не блокируя event loop бота
        text = await asyncio.to_thread(_process_audio_sync, ogg, wav)

        if not text:
            try: 
                await status.edit_text("❌ Речь не распознана.")
            except Exception: 
                pass
            return

        try:
            await status.edit_text(f"🗣️ <b>Распознано:</b>\n<i>{safe_html_format(text)}</i>", parse_mode="HTML")
        except Exception:
            pass

        # ✅ Получаем настройки голоса пользователя
        vs = get_voice_settings(message.from_user.id)
        voice_mode = vs["mode"] # 'text', 'voice', 'both'

        # ✅ Создаем копию сообщения с обновленным текстом и типом контента
        fake_message = message.model_copy(update={
             "text": text,
             "content_type": ContentType.TEXT
        })

        # ✅ Безопасный вызов главного обработчика
        main_mod = sys.modules.get("__main__") or sys.modules.get("main")
        if main_mod and hasattr(main_mod, "process_user_message"):
            # Важно: process_user_message теперь сам проверит настройки и отправит ответ правильно
            await main_mod.process_user_message(fake_message)
        else:
            logger.warning("⚠️ Главный обработчик не найден в sys.modules. Голос не передан в ИИ.")

    except Exception as e:
        logger.error(f"Voice processing error: {e}", exc_info=True)
        try: 
            await status.edit_text(f"❌ Ошибка обработки аудио: {e}")
        except Exception: 
            pass
    finally:
        # ✅ Гарантированная очистка временных файлов при любом исходе
        for f_path in (ogg, wav):
            try:
                if os.path.exists(f_path):
                    os.remove(f_path)
            except OSError:
                pass
        # Безопасное удаление статусного сообщения
        try: 
            await status.delete()
        except Exception: 
            pass
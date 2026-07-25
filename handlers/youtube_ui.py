import asyncio
import logging
import os

from aiogram import F, Router, types

from config import allowed_callback, allowed_only
from services.bot_setup import (
    yt_audio_cache as _yt_audio_cache,
    yt_quality_url as _yt_quality_url,
    yt_waiting_url as _yt_waiting_url,
)
from services.youtube import download_video, transcribe_audio

logger = logging.getLogger("YouTubeUI")
router = Router()
FILE_LIMIT = 50 * 1024 * 1024


async def _compress_video(path: str) -> str:
    import subprocess as _sp

    base, ext = os.path.splitext(path)
    compressed = f"{base}_compressed{ext}"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", path,
        "-c:v", "libx264", "-crf", "28",
        "-preset", "fast",
        "-c:a", "aac", "-b:a", "96k",
        compressed,
        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
    )
    await proc.wait()
    if os.path.exists(compressed):
        os.remove(path)
        return compressed
    return path


@router.message(F.text == "📹 Скачать видео")
@allowed_only
async def cmd_yt_video(message: types.Message):
    _yt_waiting_url[message.from_user.id] = "video"
    await message.answer("📹 Введите ссылку на YouTube видео:")


@router.message(F.text == "🎵 Скачать MP3")
@allowed_only
async def cmd_yt_audio(message: types.Message):
    _yt_waiting_url[message.from_user.id] = "audio"
    await message.answer("🎵 Введите ссылку на YouTube видео:")


@router.callback_query(F.data.startswith("yt_q:"))
@allowed_callback
async def cb_yt_quality(callback: types.CallbackQuery):
    quality = callback.data.split(":", 1)[1]
    uid = callback.from_user.id
    url = _yt_quality_url.pop(uid, "")
    if not url:
        return await callback.answer(
            "❌ Сессия истекла. Начните заново.", show_alert=True,
        )
    await callback.message.edit_text(f"⏬ Скачиваю {quality}p...")
    await callback.answer()
    try:
        path = await download_video(url, quality)
        size = os.path.getsize(path)
        if size > FILE_LIMIT:
            st = await callback.message.answer(
                f"📦 Видео {size // 1024 // 1024} MB, сжимаю..."
            )
            compressed = await _compress_video(path)
            size = os.path.getsize(compressed)
            if size > FILE_LIMIT:
                os.remove(compressed)
                return await st.edit_text(
                    f"❌ Видео слишком большое даже после сжатия "
                    f"({size // 1024 // 1024} MB). "
                    f"Лимит Telegram — 50 MB."
                )
            path = compressed
            await st.delete()
        await callback.message.answer_video(types.FSInputFile(path))
        os.remove(path)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {str(e)[:200]}")


@router.callback_query(F.data.startswith("yt_tr:"))
@allowed_callback
async def cb_yt_transcribe(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) < 3:
        return await callback.answer()
    sid, answer = parts[1], parts[2]
    audio_data = _yt_audio_cache.pop(sid, None)
    if not audio_data or not os.path.exists(audio_data["path"]):
        return await callback.answer("❌ Файл не найден.", show_alert=True)
    audio_path = audio_data["path"]
    audio_title = audio_data.get("title", "")
    if answer == "no":
        try:
            os.remove(audio_path)
        except Exception:
            pass
        await callback.message.edit_text("✅ Транскрипция отменена.")
        return await callback.answer()
    await callback.message.edit_text("📝 Транскрибирую аудио...")
    await callback.answer()
    try:
        txt_path = await transcribe_audio(audio_path, audio_title)
        with open(txt_path, encoding="utf-8") as f:
            text = f.read()
        await callback.message.answer(
            f"✅ Транскрипт сохранён в `{os.path.basename(txt_path)}`:\n\n{text[:3000]}",
            parse_mode="Markdown",
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка транскрибации: {str(e)[:200]}")
    finally:
        try:
            os.remove(audio_path)
        except Exception:
            pass

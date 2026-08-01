import asyncio
import logging
import os
import secrets

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DATA_DIR, allowed_callback, allowed_only
from services.bot_setup import (
    yt_audio_cache as _yt_audio_cache,
    yt_quality_url as _yt_quality_url,
    yt_waiting_url as _yt_waiting_url,
)
from services.youtube import download_video, transcribe_audio

logger = logging.getLogger("YouTubeUI")
router = Router()
FILE_LIMIT = 50 * 1024 * 1024

AUDIO_DIR = os.path.join(DATA_DIR, "audio_downloads")
os.makedirs(AUDIO_DIR, exist_ok=True)


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


# ─── Uploaded audio transcription ───


async def _handle_audio_file(message: types.Message, file_id: str, file_name: str):
    st = await message.answer("⏬ Скачиваю аудио...")
    try:
        f = await message.bot.get_file(file_id)
        ext = os.path.splitext(file_name)[1] or ".mp3"
        local = os.path.join(AUDIO_DIR, f"upload_{secrets.token_hex(4)}{ext}")
        await message.bot.download_file(f.file_path, destination=local)
        size = os.path.getsize(local)
        if size == 0:
            os.remove(local)
            return await st.edit_text("❌ Аудио пустое.")
        if size > FILE_LIMIT:
            os.remove(local)
            return await st.edit_text(
                f"❌ Аудио слишком большое ({size // 1024 // 1024} MB). "
                f"Лимит Telegram — 50 MB."
            )
        await st.delete()
        await message.answer_audio(types.FSInputFile(local))
        sid = secrets.token_hex(4)
        _yt_audio_cache[sid] = {"path": local, "title": os.path.splitext(file_name)[0]}
        logger.info(f"[AUDIO_UPLOAD] cached sid={sid} path={local}")
        kb = InlineKeyboardBuilder()
        kb.row(
            types.InlineKeyboardButton(text="✅ Да", callback_data=f"yt_tr:{sid}:yes"),
            types.InlineKeyboardButton(text="❌ Нет", callback_data=f"yt_tr:{sid}:no"),
        )
        await message.answer(
            "📝 Транскрибировать и сохранить в /transkript?",
            reply_markup=kb.as_markup(),
        )
    except Exception as e:
        await st.edit_text(f"❌ Ошибка: {str(e)[:200]}")


@router.message(F.audio)
@allowed_only
async def handle_uploaded_audio(message: types.Message):
    a = message.audio
    await _handle_audio_file(message, a.file_id, a.file_name or f"audio_{a.duration}s.mp3")


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
    logger.info(
        "[YT_TR] sid=%s answer=%s audio_data=%s cache_size=%d",
        sid, answer, audio_data, len(_yt_audio_cache),
    )
    if not audio_data:
        return await callback.answer(
            f"❌ Файл не найден в кэше (sid={sid}). Возможно, кэш переполнен или TTL истёк.",
            show_alert=True,
        )
    if not os.path.exists(audio_data["path"]):
        return await callback.answer(
            f"❌ Файл не найден на диске: {audio_data['path']}",
            show_alert=True,
        )
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

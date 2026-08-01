import asyncio
import logging
import os
import re
import subprocess
from datetime import datetime

import yt_dlp

logger = logging.getLogger("YouTubeService")
yt_logger = logging.getLogger("yt_dlp")
yt_logger.setLevel(logging.ERROR)


_YT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}

_YT_EXTRACTOR_ARGS = {
    "youtube": {
        "player_client": ["android", "web"],
        "skip": ["webpage"],
    },
}


def _sanitize_filename(title: str) -> str:
    clean = re.sub(r"[^\w\s\-]", "", title)[:40].strip()
    return clean.replace(" ", "_") or "video"


def _yt_path() -> str:
    from config import TEMP_DIR

    os.makedirs(TEMP_DIR, exist_ok=True)
    return TEMP_DIR


def _tr_path() -> str:
    from config import TRANSKRIPT_DIR

    os.makedirs(TRANSKRIPT_DIR, exist_ok=True)
    return TRANSKRIPT_DIR


async def download_video(url: str, quality: str = "720") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _run():
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = _sanitize_filename(info.get("title", "video"))
        outtmpl = os.path.join(_yt_path(), f"yt_{title}_{ts}.%(ext)s")
        fmt = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
        opts = {
            "format": fmt,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "logger": yt_logger,
            "http_headers": _YT_HEADERS,
            "extractor_args": _YT_EXTRACTOR_ARGS,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        base = os.path.join(_yt_path(), f"yt_{title}_{ts}")
        mp4 = base + ".mp4"
        if os.path.exists(mp4):
            return mp4
        for f in os.listdir(_yt_path()):
            if f.startswith(f"yt_{title}_{ts}"):
                return os.path.join(_yt_path(), f)
        return mp4

    return await asyncio.to_thread(_run)


async def download_audio(url: str) -> tuple[str, str]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _run():
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            raw_title = info.get("title", "audio")
            title = _sanitize_filename(raw_title)
        outtmpl = os.path.join(_yt_path(), f"yt_{title}_{ts}.%(ext)s")
        opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                },
            ],
            "quiet": True,
            "no_warnings": True,
            "logger": yt_logger,
            "http_headers": _YT_HEADERS,
            "extractor_args": _YT_EXTRACTOR_ARGS,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return os.path.join(_yt_path(), f"yt_{title}_{ts}.mp3"), raw_title

    return await asyncio.to_thread(_run)


def _format_transcription(segments) -> str:
    paragraphs = []
    current: list = []
    prev_end = 0.0
    GAP_THRESHOLD = 2.0

    for seg in segments:
        gap = seg.start - prev_end
        if gap > GAP_THRESHOLD and current:
            paragraphs.append(" ".join(current))
            current = []
        text = seg.text.strip()
        if text:
            if not text.endswith((".", "!", "?")):
                text += "."
            current.append(text)
        prev_end = seg.end

    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)


async def transcribe_audio(audio_path: str, title: str = "") -> str:
    from services.whisper_service import get_whisper

    my = datetime.now().strftime("%Y_%m")
    safe_title = (
        _sanitize_filename(title)
        if title
        else os.path.splitext(os.path.basename(audio_path))[0]
    )
    txt_path = os.path.join(_tr_path(), f"{safe_title}_{my}.txt")

    def _run():
        model = get_whisper("small")
        segments, _ = model.transcribe(audio_path, language="ru")
        return list(segments)

    seg_list = await asyncio.to_thread(_run)
    text = _format_transcription(seg_list)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    return txt_path


async def _compress_video(path: str) -> str:
    base, ext = os.path.splitext(path)
    compressed = f"{base}_compressed{ext}"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", path,
        "-c:v", "libx264", "-crf", "28",
        "-preset", "fast",
        "-c:a", "aac", "-b:a", "96k",
        compressed,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    await proc.wait()
    if os.path.exists(compressed):
        os.remove(path)
        return compressed
    return path

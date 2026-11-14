"""Defensive ZIP handling for Garmin exports.

Garmin exports are user-supplied archives.  We never trust member names,
symlinks, declared sizes, or compression ratios.  Extraction is confined to a
fresh temporary directory and every write is checked again.
"""

from __future__ import annotations

import os
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import GarminImportError

DEFAULT_MAX_FILES = 2_000
DEFAULT_MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
DEFAULT_MAX_MEMBER_UNCOMPRESSED = 128 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 200
DEFAULT_MAX_PATH_LENGTH = 240


@dataclass(frozen=True)
class ZipLimits:
    max_files: int = DEFAULT_MAX_FILES
    max_total_uncompressed: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED
    max_member_uncompressed: int = DEFAULT_MAX_MEMBER_UNCOMPRESSED
    max_compression_ratio: int = DEFAULT_MAX_COMPRESSION_RATIO
    max_path_length: int = DEFAULT_MAX_PATH_LENGTH


def _safe_name(name: str, limits: ZipLimits) -> str:
    if not name or "\x00" in name or "\\" in name:
        raise GarminImportError("unsafe ZIP member name")
    if len(name) > limits.max_path_length:
        raise GarminImportError("ZIP member path is too long")
    path = PurePosixPath(name)
    if path.is_absolute() or path.drive:
        raise GarminImportError("absolute ZIP member path")
    parts = path.parts
    if any(part in {"", ".", ".."} for part in parts):
        raise GarminImportError("path traversal in ZIP member")
    return path.as_posix()


def safe_members(
    archive: zipfile.ZipFile,
    *,
    limits: ZipLimits | None = None,
) -> list[zipfile.ZipInfo]:
    """Validate every member and return the safe list.

    Raises :class:`GarminImportError` on the first violation instead of
    extracting a partial archive.
    """
    limits = limits or ZipLimits()
    infos = archive.infolist()
    if len(infos) > limits.max_files:
        raise GarminImportError("too many files in ZIP")

    total = 0
    seen: set[str] = set()
    for info in infos:
        name = _safe_name(info.filename, limits)
        if name in seen:
            raise GarminImportError("duplicate ZIP member name")
        seen.add(name)

        if info.flag_bits & 0x1:
            raise GarminImportError("encrypted ZIP members are not supported")

        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise GarminImportError("symlinks in ZIP are not supported")

        if info.is_dir():
            continue
        if info.file_size > limits.max_member_uncompressed:
            raise GarminImportError("ZIP member is too large")
        total += info.file_size
        if total > limits.max_total_uncompressed:
            raise GarminImportError("ZIP uncompressed size is too large")
        if info.file_size > 1024 * 1024:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits.max_compression_ratio:
                raise GarminImportError("suspicious ZIP compression ratio")
    return infos


def _copy_limited(src, dst, *, max_bytes: int) -> int:
    written = 0
    while True:
        chunk = src.read(1024 * 1024)
        if not chunk:
            break
        written += len(chunk)
        if written > max_bytes:
            raise GarminImportError("ZIP member exceeded declared size")
        dst.write(chunk)
    return written


def extract(
    archive_path: str | Path,
    destination: str | Path,
    *,
    limits: ZipLimits | None = None,
) -> Path:
    """Safely extract an archive into ``destination`` and return it."""
    limits = limits or ZipLimits()
    dest = Path(destination).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)

    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = safe_members(archive, limits=limits)
            total = 0
            for info in infos:
                name = _safe_name(info.filename, limits)
                target = (dest / name).resolve()
                if dest not in target.parents and target != dest:
                    raise GarminImportError("ZIP member escapes destination")
                if target.is_symlink():
                    raise GarminImportError("refusing to write through a symlink")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                fd = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                with os.fdopen(fd, "wb") as out, archive.open(info) as src:
                    written = _copy_limited(
                        src,
                        out,
                        max_bytes=limits.max_member_uncompressed,
                    )
                total += written
                if total > limits.max_total_uncompressed:
                    raise GarminImportError("ZIP uncompressed size is too large")
    except zipfile.BadZipFile as exc:
        raise GarminImportError("invalid ZIP archive") from exc
    return dest


def fit_files(root: str | Path) -> list[Path]:
    """Return ``*.fit`` files under ``root`` in deterministic order."""
    return sorted(
        path for path in Path(root).rglob("*") if path.is_file() and path.suffix.lower() == ".fit"
    )


def remove_tree(path: str | Path) -> None:
    target = Path(path)
    if target.exists():
        shutil.rmtree(target)

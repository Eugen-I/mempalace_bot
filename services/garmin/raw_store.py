"""Immutable raw-file archive for Garmin exports.

Files are addressed by SHA-256.  The archive never overwrites an existing
object and never follows user-provided paths outside its root.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import GarminImportError

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class RawFileInfo:
    user_id: int
    sha256: str
    path: Path
    size_bytes: int
    source: str
    filename: str


def _safe_filename(filename: str) -> str:
    name = Path(filename or "upload.bin").name.strip()
    if not name or name in {".", ".."}:
        name = "upload.bin"
    # Keep only a short, harmless suffix; never use user directories.
    suffix = Path(name).suffix
    if not suffix or len(suffix) > 16 or any(c in suffix for c in "/\\"):
        suffix = ".bin"
    return suffix


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RawStore:
    """Content-addressed, per-user raw archive."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _object_path(self, user_id: int, sha256: str, filename: str) -> Path:
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise GarminImportError("invalid SHA-256")
        suffix = _safe_filename(filename)
        return self.root / str(int(user_id)) / sha256[:2] / f"{sha256}{suffix}"

    def _find_existing(self, user_id: int, sha256: str) -> Path | None:
        """Find any already-archived object with this hash.

        The suffix is metadata, not identity: the same bytes imported as
        ``day.fit`` and ``day.csv`` must resolve to one immutable object.
        """
        directory = self.root / str(int(user_id)) / sha256[:2]
        if not directory.is_dir():
            return None
        matches = sorted(directory.glob(f"{sha256}.*"))
        return matches[0] if matches else None

    def save_bytes(
        self,
        user_id: int,
        data: bytes,
        *,
        source: str,
        filename: str,
    ) -> RawFileInfo:
        if not isinstance(data, (bytes, bytearray)):
            raise GarminImportError("raw payload must be bytes")
        sha = _sha256_bytes(bytes(data))
        target = self._object_path(user_id, sha, filename)
        existing = self._find_existing(user_id, sha)
        if existing is not None:
            return RawFileInfo(
                user_id=user_id,
                sha256=sha,
                path=existing,
                size_bytes=existing.stat().st_size,
                source=source,
                filename=existing.name,
            )

        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".raw-",
            dir=str(target.parent),
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(bytes(data))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        return RawFileInfo(
            user_id=user_id,
            sha256=sha,
            path=target,
            size_bytes=len(data),
            source=source,
            filename=target.name,
        )

    def save_file(
        self,
        user_id: int,
        path: str | Path,
        *,
        source: str,
        filename: str | None = None,
    ) -> RawFileInfo:
        source_path = Path(path).expanduser()
        if not source_path.is_file():
            raise GarminImportError("source file does not exist")
        sha = _sha256_file(source_path)
        target = self._object_path(user_id, sha, filename or source_path.name)
        existing = self._find_existing(user_id, sha)
        if existing is not None:
            return RawFileInfo(
                user_id=user_id,
                sha256=sha,
                path=existing,
                size_bytes=existing.stat().st_size,
                source=source,
                filename=existing.name,
            )

        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".raw-",
            dir=str(target.parent),
        )
        try:
            with source_path.open("rb") as reader, os.fdopen(fd, "wb") as writer:
                for chunk in iter(lambda: reader.read(CHUNK_SIZE), b""):
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        return RawFileInfo(
            user_id=user_id,
            sha256=sha,
            path=target,
            size_bytes=target.stat().st_size,
            source=source,
            filename=target.name,
        )

    def open(self, info: RawFileInfo) -> Path:
        """Return the object path after a containment check."""
        resolved = info.path.resolve()
        if self.root not in resolved.parents:
            raise GarminImportError("raw path escapes archive root")
        if not resolved.is_file():
            raise GarminImportError("raw object is missing")
        return resolved

    def delete_user(self, user_id: int) -> None:
        target = self.root / str(int(user_id))
        if target.exists():
            shutil.rmtree(target)

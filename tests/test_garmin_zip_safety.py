"""Tests for defensive Garmin ZIP handling."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from services.garmin.errors import GarminImportError
from services.garmin.zip_safety import ZipLimits, extract, fit_files, safe_members


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_extracts_safe_archive(tmp_path: Path):
    archive = _zip(tmp_path / "safe.zip", {"Garmin 2026-01-01/a.fit": b"fit"})
    dest = extract(archive, tmp_path / "out")

    assert (dest / "Garmin 2026-01-01" / "a.fit").read_bytes() == b"fit"
    assert fit_files(dest) == [dest / "Garmin 2026-01-01" / "a.fit"]


def test_rejects_path_traversal(tmp_path: Path):
    archive = _zip(tmp_path / "bad.zip", {"../evil.fit": b"x"})
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(GarminImportError, match="traversal"):
            safe_members(zf)


def test_rejects_absolute_path(tmp_path: Path):
    archive = _zip(tmp_path / "bad.zip", {"/etc/evil.fit": b"x"})
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(GarminImportError, match="absolute"):
            safe_members(zf)


def test_rejects_duplicate_member(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.fit", b"x")
        zf.writestr("a.fit", b"y")
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(GarminImportError, match="duplicate"):
            safe_members(zf)


def test_rejects_symlink_member(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    info = zipfile.ZipInfo("link.fit")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, b"target")
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(GarminImportError, match="symlink"):
            safe_members(zf)


def test_rejects_too_many_files(tmp_path: Path):
    archive = _zip(tmp_path / "many.zip", {"a.fit": b"a", "b.fit": b"b"})
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(GarminImportError, match="too many"):
            safe_members(zf, limits=ZipLimits(max_files=1))


def test_rejects_oversized_member(tmp_path: Path):
    archive = _zip(tmp_path / "big.zip", {"a.fit": b"abc"})
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(GarminImportError, match="too large"):
            safe_members(zf, limits=ZipLimits(max_member_uncompressed=2))


def test_rejects_suspicious_ratio(tmp_path: Path):
    archive = _zip(tmp_path / "bomb.zip", {"a.fit": b"\0" * (2 * 1024 * 1024)})
    with zipfile.ZipFile(archive) as zf:
        with pytest.raises(GarminImportError, match="compression ratio"):
            safe_members(zf, limits=ZipLimits(max_compression_ratio=10))


def test_rejects_bad_zip(tmp_path: Path):
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not a zip")
    with pytest.raises(GarminImportError, match="invalid ZIP"):
        extract(path, tmp_path / "out")

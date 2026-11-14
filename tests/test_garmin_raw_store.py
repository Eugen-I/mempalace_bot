"""Tests for the immutable Garmin raw-file archive."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from services.garmin.errors import GarminImportError
from services.garmin.raw_store import RawFileInfo, RawStore


def test_save_bytes_is_content_addressed(tmp_path: Path):
    store = RawStore(tmp_path / "raw")
    info = store.save_bytes(1, b"hello", source="wellness", filename="day.fit")

    assert info.sha256
    assert info.path.is_file()
    assert info.path.read_bytes() == b"hello"
    assert info.path.name.endswith(".fit")
    assert os.stat(info.path).st_mode & 0o777 == 0o600


def test_same_content_is_deduplicated(tmp_path: Path):
    store = RawStore(tmp_path / "raw")
    first = store.save_bytes(1, b"same", source="a", filename="a.fit")
    second = store.save_bytes(1, b"same", source="b", filename="b.csv")

    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert second.size_bytes == 4


def test_save_file_deduplicates(tmp_path: Path):
    source = tmp_path / "input.fit"
    source.write_bytes(b"fit-bytes")
    store = RawStore(tmp_path / "raw")

    first = store.save_file(1, source, source="wellness")
    second = store.save_file(1, source, source="wellness")

    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert first.path.read_bytes() == b"fit-bytes"


def test_filename_traversal_is_neutralized(tmp_path: Path):
    store = RawStore(tmp_path / "raw")
    info = store.save_bytes(
        1,
        b"x",
        source="test",
        filename="../../../../etc/passwd.fit",
    )

    assert info.path.parent.parent.parent == store.root
    assert ".." not in info.path.parts
    assert info.path.is_file()


def test_open_rejects_outside_path(tmp_path: Path):
    store = RawStore(tmp_path / "raw")
    outside = tmp_path / "outside.fit"
    outside.write_bytes(b"x")
    info = RawFileInfo(
        user_id=1,
        sha256="0" * 64,
        path=outside,
        size_bytes=1,
        source="test",
        filename="outside.fit",
    )

    with pytest.raises(GarminImportError):
        store.open(info)


def test_delete_user_removes_only_that_user(tmp_path: Path):
    store = RawStore(tmp_path / "raw")
    store.save_bytes(1, b"a", source="test", filename="a.fit")
    store.save_bytes(2, b"b", source="test", filename="b.fit")

    store.delete_user(1)

    assert not (store.root / "1").exists()
    assert (store.root / "2").exists()

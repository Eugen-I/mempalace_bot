"""Тесты services/multimodal.py — кэш capabilities, base64, фото.

Покрытие: загрузка конфига моделей, encode/save/list/delete фото, границы.
"""
import base64
import json
import os

import pytest

import services.multimodal as multimodal


@pytest.fixture(autouse=True)
def _clean_cache():
    multimodal._model_caps_cache.clear()
    yield
    multimodal._model_caps_cache.clear()


@pytest.fixture
def models_config(tmp_path, monkeypatch):
    cfg = tmp_path / "models.json"
    cfg.write_text(
        json.dumps(
            {
                "ollama": [{"tag": "llava", "multimodal": True, "supports_audio": False}],
                "openai": [{"tag": "gpt-4o", "multimodal": True, "supports_audio": True}],
                "gemini": [{"tag": "flash", "multimodal": False, "supports_audio": False}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(multimodal, "MODELS_CONFIG_PATH", str(cfg))
    return cfg


# ─── load_model_capabilities ───


def test_load_capabilities_parses_config(models_config):
    caps = multimodal.load_model_capabilities()
    assert caps["llava"]["multimodal"] is True
    assert caps["gpt-4o"]["supports_audio"] is True
    assert caps["flash"]["multimodal"] is False


def test_load_capabilities_cached(models_config):
    multimodal.load_model_capabilities()
    assert multimodal._model_caps_cache
    caps1 = multimodal.load_model_capabilities()
    caps2 = multimodal.load_model_capabilities()
    assert caps1 is caps2


def test_load_capabilities_missing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "MODELS_CONFIG_PATH", str(tmp_path / "nope.json"))
    assert multimodal.load_model_capabilities() == {}


def test_load_capabilities_invalid_json(tmp_path, monkeypatch):
    cfg = tmp_path / "bad.json"
    cfg.write_text("{не json", encoding="utf-8")
    monkeypatch.setattr(multimodal, "MODELS_CONFIG_PATH", str(cfg))
    assert multimodal.load_model_capabilities() == {}


def test_load_capabilities_missing_multimodal_key(tmp_path, monkeypatch):
    cfg = tmp_path / "no_key.json"
    cfg.write_text(json.dumps({"ollama": [{"tag": "m1"}]}), encoding="utf-8")
    monkeypatch.setattr(multimodal, "MODELS_CONFIG_PATH", str(cfg))
    caps = multimodal.load_model_capabilities()
    assert caps["m1"]["multimodal"] is False
    assert caps["m1"]["supports_audio"] is False


# ─── check_capability ───


def test_check_capability_true(models_config):
    assert multimodal.check_capability("llava", "multimodal") is True


def test_check_capability_false(models_config):
    assert multimodal.check_capability("flash", "multimodal") is False


def test_check_capability_unknown_model(models_config):
    assert multimodal.check_capability("unknown", "multimodal") is False


def test_check_capability_unknown_feature(models_config):
    assert multimodal.check_capability("llava", "telepathy") is False


# ─── encode_image_to_base64 ───


def test_encode_image_to_base64_ok(tmp_path):
    img = tmp_path / "pic.jpg"
    img.write_bytes(b"\x00\x01\x02\xff")
    encoded = multimodal.encode_image_to_base64(str(img))
    assert encoded == base64.b64encode(b"\x00\x01\x02\xff").decode("utf-8")


def test_encode_image_to_base64_missing_file(tmp_path):
    assert multimodal.encode_image_to_base64(str(tmp_path / "nope.jpg")) == ""


def test_encode_image_to_base64_empty_file(tmp_path):
    img = tmp_path / "empty.jpg"
    img.write_bytes(b"")
    assert multimodal.encode_image_to_base64(str(img)) == ""


# ─── save_bot_photo ───


def test_save_bot_photo_copies_and_deletes_source(tmp_path, monkeypatch):
    photos_dir = tmp_path / "photos"
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(photos_dir))
    src = tmp_path / "tmp_photo.jpg"
    src.write_bytes(b"jpegdata")

    dest = multimodal.save_bot_photo(str(src), 12345)

    assert dest.startswith(str(photos_dir))
    assert os.path.exists(dest)
    assert not os.path.exists(src)
    assert dest.endswith(".jpg")
    assert "12345" in dest


def test_save_bot_photo_missing_source(tmp_path, monkeypatch):
    photos_dir = tmp_path / "photos"
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(photos_dir))
    assert multimodal.save_bot_photo(str(tmp_path / "nope.jpg"), 1) == ""


def test_save_bot_photo_source_already_gone(tmp_path, monkeypatch):
    photos_dir = tmp_path / "photos"
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(photos_dir))
    src = tmp_path / "tmp_photo.jpg"
    src.write_bytes(b"jpegdata")
    real_exists = os.path.exists
    monkeypatch.setattr(multimodal.os.path, "exists", lambda p: False)

    dest = multimodal.save_bot_photo(str(src), 5)

    assert dest.startswith(str(photos_dir))
    assert real_exists(dest)
    assert real_exists(src)


# ─── list_photos ───


def test_list_photos_listdir_error(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path))

    def boom(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(multimodal.os, "listdir", boom)
    assert multimodal.list_photos() == []


def test_list_photos_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path / "absent"))
    assert multimodal.list_photos() == []


def test_list_photos_filters_extensions(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path))
    (tmp_path / "a.jpg").write_bytes(b"1")
    (tmp_path / "b.PNG").write_bytes(b"2")
    (tmp_path / "c.txt").write_bytes(b"3")
    (tmp_path / "d.webp").write_bytes(b"4")

    result = multimodal.list_photos()
    assert sorted(result) == ["a.jpg", "b.PNG", "d.webp"]


def test_list_photos_limited_to_10(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path))
    for i in range(15):
        (tmp_path / f"f{i:02d}.jpg").write_bytes(b"x")
    assert len(multimodal.list_photos()) == 10


def test_list_photos_sorted_desc(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path))
    (tmp_path / "a.jpg").write_bytes(b"1")
    (tmp_path / "b.jpg").write_bytes(b"2")
    result = multimodal.list_photos()
    assert result == ["b.jpg", "a.jpg"]


# ─── delete_photo ───


def test_delete_photo_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path))
    (tmp_path / "del.jpg").write_bytes(b"x")
    assert multimodal.delete_photo("del.jpg") is True
    assert not (tmp_path / "del.jpg").exists()


def test_delete_photo_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path))
    assert multimodal.delete_photo("nope.jpg") is False


def test_delete_photo_remove_error(tmp_path, monkeypatch):
    monkeypatch.setattr(multimodal, "PHOTOS_DIR", str(tmp_path))
    (tmp_path / "del.jpg").write_bytes(b"x")

    def boom(*a, **k):
        raise OSError("busy")

    monkeypatch.setattr(multimodal.os, "remove", boom)
    assert multimodal.delete_photo("del.jpg") is False


def test_encode_image_to_base64_read_error(tmp_path, monkeypatch):
    src = tmp_path / "img.png"
    src.write_bytes(b"x")

    def boom(*a, **k):
        raise OSError("io error")

    monkeypatch.setattr("builtins.open", boom)
    assert multimodal.encode_image_to_base64(str(src)) == ""

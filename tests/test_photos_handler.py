"""Unit tests for handlers.photos."""

import os
from types import SimpleNamespace

import pytest

from handlers import photos as ph


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeFile:
    def __init__(self, file_id="p1"):
        self.file_id = file_id


class FakeDoc:
    def __init__(self, file_id="d1", mime="image/png"):
        self.file_id = file_id
        self.mime_type = mime


class FakeBot:
    def __init__(self):
        self.downloads = []
        self.file_path = "path/to/p1"

    async def get_file(self, file_id):
        return SimpleNamespace(file_path=self.file_path)

    async def download_file(self, file_path, destination=None):
        self.downloads.append((file_path, destination))


class FakeMessage:
    def __init__(self, uid=4242, photo=None, document=None):
        self.from_user = FakeUser(uid)
        self.photo = photo
        self.document = document
        self.message_id = 1
        self.bot = FakeBot()
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return SimpleNamespace(delete=self._noop_delete)

    async def _noop_delete(self):
        pass

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))


class FakeCb:
    def __init__(self, uid=4242, data="", chat_id=1):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid, photo=[FakeFile()])
        self.message.chat = SimpleNamespace(id=chat_id)
        self.answered = []
        self.edits = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.message.edits.append((text, parse_mode, reply_markup))


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    photos = tmp_path / "photos"
    notes = tmp_path / "notes"
    photos.mkdir()
    notes.mkdir()
    monkeypatch.setattr(ph, "PHOTOS_DIR", str(photos))
    monkeypatch.setattr(ph, "NOTES_DIR", str(notes))
    monkeypatch.setattr(ph, "_photo_delete_cache", ph.TTLCache(maxsize=500, ttl=300))
    return photos, notes


@pytest.mark.asyncio
async def test_handle_photo_requires_allowed_user(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=999, photo=[FakeFile()])
    await ph.handle_photo(msg)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_handle_photo_save_success(monkeypatch, tmp_path):
    photos, _ = _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=4242, photo=[FakeFile()])
    (photos / "bot_4242_20240101_000000.jpg").write_bytes(b"photo")

    def fake_save(src, uid):
        return str(photos / "bot_4242_20240101_000000.jpg")

    monkeypatch.setattr(ph, "save_bot_photo", fake_save)
    monkeypatch.setattr(ph, "list_photos", lambda: ["bot_1.jpg", "bot_2.jpg"])
    await ph.handle_photo(msg)
    assert "Фото сохранено" in msg.answers[0][0]
    assert "2 фото" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_handle_photo_document_image(monkeypatch, tmp_path):
    photos, _ = _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=4242, document=FakeDoc())

    def fake_save(src, uid):
        return str(photos / "b.jpg")

    monkeypatch.setattr(ph, "save_bot_photo", fake_save)
    monkeypatch.setattr(ph, "list_photos", lambda: [])
    await ph.handle_photo(msg)
    assert "Фото сохранено" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_handle_photo_document_not_image_ignored(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=4242, document=FakeDoc(mime="application/pdf"))
    await ph.handle_photo(msg)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_handle_photo_unexpected_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=4242, photo=[FakeFile()])

    def fake_save(src, uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(ph, "save_bot_photo", fake_save)
    await ph.handle_photo(msg)
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_success(monkeypatch, tmp_path):
    photos, _ = _enable(monkeypatch, tmp_path)
    (photos / "b1.jpg").write_bytes(b"x")
    cb = FakeCb(4242, data="photo_analyze_last")

    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg", "b2.jpg"])
    monkeypatch.setattr(ph, "get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr(ph, "check_capability", lambda model, feat: True)
    monkeypatch.setattr(ph, "encode_image_to_base64", lambda path: "b64data")
    monkeypatch.setattr(ph, "search_palace_context", _async_none)
    monkeypatch.setattr(ph, "get_smart_prompt", lambda **kw: "SYSTEM")
    monkeypatch.setattr(ph, "call_ai_sync", lambda *a, **kw: "очень полезный ответ про фото")
    monkeypatch.setattr(ph, "safe_html_format", lambda t: t)
    monkeypatch.setattr(ph, "split_message", lambda t: [t])

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ph.asyncio, "to_thread", fake_to_thread)
    await ph.cb_analyze_last_photo(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("Анализ" in b for b in bodies)
    assert any("очень полезный" in b for b in bodies)


async def _async_none(*a, **kw):
    return ""


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_no_photos(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="photo_analyze_last")
    monkeypatch.setattr(ph, "list_photos", lambda: [])
    await ph.cb_analyze_last_photo(cb)
    assert cb.answered == [(None, None)]
    assert "Нет фото" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_not_multimodal(monkeypatch, tmp_path):
    photos, _ = _enable(monkeypatch, tmp_path)
    (photos / "b1.jpg").write_bytes(b"x")
    cb = FakeCb(4242, data="photo_analyze_last")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg"])
    monkeypatch.setattr(ph, "get_current_ai", lambda: ("ollama", "qwen2"))
    monkeypatch.setattr(ph, "check_capability", lambda model, feat: False)
    await ph.cb_analyze_last_photo(cb)
    assert "не поддерживает фото" in cb.message.answers[-1][0]


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_no_base64(monkeypatch, tmp_path):
    photos, _ = _enable(monkeypatch, tmp_path)
    (photos / "b1.jpg").write_bytes(b"x")
    cb = FakeCb(4242, data="photo_analyze_last")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg"])
    monkeypatch.setattr(ph, "get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr(ph, "check_capability", lambda model, feat: True)
    monkeypatch.setattr(ph, "encode_image_to_base64", lambda path: "")
    await ph.cb_analyze_last_photo(cb)
    # format_user_error для ValueError возвращает "❌ Некорректные данные"
    assert any(
        "Некорректные данные" in (b[0] if isinstance(b, tuple) else b)
        for b in cb.message.answers
    )


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_analysis_error(monkeypatch, tmp_path):
    photos, _ = _enable(monkeypatch, tmp_path)
    (photos / "b1.jpg").write_bytes(b"x")
    cb = FakeCb(4242, data="photo_analyze_last")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg"])
    monkeypatch.setattr(ph, "get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr(ph, "check_capability", lambda model, feat: True)
    monkeypatch.setattr(ph, "encode_image_to_base64", lambda path: "b64")
    monkeypatch.setattr(ph, "search_palace_context", _async_none)
    monkeypatch.setattr(ph, "get_smart_prompt", lambda **kw: "S")

    def boom(*a, **kw):
        raise RuntimeError("model timeout")

    monkeypatch.setattr(ph, "call_ai_sync", boom)
    await ph.cb_analyze_last_photo(cb)
    assert any("❌ Ошибка" in (b[0] if isinstance(b, tuple) else b) for b in cb.message.answers)


# ---------- show_links ----------


@pytest.mark.asyncio
async def test_cb_show_links_success(monkeypatch, tmp_path):
    _, notes = _enable(monkeypatch, tmp_path)
    (notes / "note1.md").write_text(
        "тело\n## 🔗 Связанные записи\nсвязь А\nсвязь Б", encoding="utf-8",
    )
    cb = FakeCb(4242, data="show_links:note1.md")
    await ph.cb_show_links(cb)
    assert "Связанные записи" in cb.message.answers[0][0]
    assert "связь А" in cb.message.answers[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_show_links_missing_file(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="show_links:nope.md")
    await ph.cb_show_links(cb)
    assert "Файл не найден" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_show_links_no_links_section(monkeypatch, tmp_path):
    _, notes = _enable(monkeypatch, tmp_path)
    (notes / "note2.md").write_text("просто текст", encoding="utf-8")
    cb = FakeCb(4242, data="show_links:note2.md")
    await ph.cb_show_links(cb)
    assert "еще формируются" in cb.message.answers[0][0]


@pytest.mark.asyncio
async def test_cb_show_links_read_error(monkeypatch, tmp_path):
    _, notes = _enable(monkeypatch, tmp_path)
    (notes / "note3.md").write_text("текст", encoding="utf-8")
    cb = FakeCb(4242, data="show_links:note3.md")

    import builtins

    real_open = builtins.open

    def broken_open(path, *a, **kw):
        if path.endswith("note3.md"):
            raise OSError("io fail")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", broken_open)
    await ph.cb_show_links(cb)
    assert "Не удалось загрузить связи" in cb.message.answers[0][0]


# ---------- cb_delete_photo ----------


@pytest.mark.asyncio
async def test_cb_delete_photo_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="photo_delete_last")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg", "b2.jpg"])
    monkeypatch.setattr(ph, "delete_photo", lambda f: True)
    await ph.cb_delete_photo(cb)
    assert cb.answered == [("🗑 Удалено: b1.jpg", True)]


@pytest.mark.asyncio
async def test_cb_delete_photo_no_photos(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="photo_delete_last")
    monkeypatch.setattr(ph, "list_photos", lambda: [])
    await ph.cb_delete_photo(cb)
    assert cb.answered[-1] == ("❌ Не удалось удалить", True)


# ---------- cmd_photos ----------


@pytest.mark.asyncio
async def test_cmd_photos_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242)
    monkeypatch.setattr(ph, "list_photos", lambda: [])
    await ph.cmd_photos(msg)
    assert "пуста" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_cmd_photos_has_items(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(4242)
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg", "b2.jpg"])
    await ph.cmd_photos(msg)
    assert "Фото в базе (2)" in msg.answers[0][0]
    assert msg.answers[0][1] == "HTML"
    assert msg.answers[0][2] is not None


@pytest.mark.asyncio
async def test_cmd_photos_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(999)
    await ph.cmd_photos(msg)
    assert msg.answers == []


# ---------- cb_del_photo ----------


@pytest.mark.asyncio
async def test_handle_photo_download_no_file(monkeypatch, tmp_path):
    """Файл не появился после скачивания → FileNotFoundError (78)."""
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=4242, photo=[FakeFile()])

    real_exists = os.path.exists
    monkeypatch.setattr(
        ph.os.path, "exists",
        lambda p: False if isinstance(p, str) and p.endswith(".jpg") else real_exists(p),
    )

    def fake_save(src, uid):
        return "/x.jpg"

    monkeypatch.setattr(ph, "save_bot_photo", fake_save)
    await ph.handle_photo(msg)
    # format_user_error для FileNotFoundError возвращает "❌ Файл не найден"
    assert "Файл не найден" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_handle_photo_save_returns_empty(monkeypatch, tmp_path):
    """save_bot_photo вернул пусто → RuntimeError (83)."""
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=4242, photo=[FakeFile()])

    def fake_save(src, uid):
        return ""

    monkeypatch.setattr(ph, "save_bot_photo", fake_save)
    await ph.handle_photo(msg)
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_empty_parts_skipped(monkeypatch, tmp_path):
    """Пустые части ответа пропускаются (167->166)."""
    photos, _ = _enable(monkeypatch, tmp_path)
    (photos / "b1.jpg").write_bytes(b"x")
    cb = FakeCb(4242, data="photo_analyze_last")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg"])
    monkeypatch.setattr(ph, "get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr(ph, "check_capability", lambda model, feat: True)
    monkeypatch.setattr(ph, "encode_image_to_base64", lambda path: "b64")
    monkeypatch.setattr(ph, "search_palace_context", _async_none)
    monkeypatch.setattr(ph, "get_smart_prompt", lambda **kw: "S")
    monkeypatch.setattr(ph, "call_ai_sync", lambda *a, **kw: "ok")
    monkeypatch.setattr(ph, "safe_html_format", lambda t: t)
    monkeypatch.setattr(ph, "split_message", lambda t: ["part1", "", "part3"])

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ph.asyncio, "to_thread", fake_to_thread)
    await ph.cb_analyze_last_photo(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("part1" in b for b in bodies)
    assert any("part3" in b for b in bodies)


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_html_send_fails_fallback(monkeypatch, tmp_path):
    """HTML-отправка падает → повтор без parse_mode (170-172)."""
    photos, _ = _enable(monkeypatch, tmp_path)
    (photos / "b1.jpg").write_bytes(b"x")
    cb = FakeCb(4242, data="photo_analyze_last")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg"])
    monkeypatch.setattr(ph, "get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr(ph, "check_capability", lambda model, feat: True)
    monkeypatch.setattr(ph, "encode_image_to_base64", lambda path: "b64")
    monkeypatch.setattr(ph, "search_palace_context", _async_none)
    monkeypatch.setattr(ph, "get_smart_prompt", lambda **kw: "S")
    monkeypatch.setattr(ph, "call_ai_sync", lambda *a, **kw: "ok")
    monkeypatch.setattr(ph, "safe_html_format", lambda t: t)
    monkeypatch.setattr(ph, "split_message", lambda t: ["контент"])

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ph.asyncio, "to_thread", fake_to_thread)

    real_answer = cb.message.answer

    async def flaky_answer(text, parse_mode=None, reply_markup=None):
        if parse_mode == "HTML":
            raise RuntimeError("HTML not allowed")
        await real_answer(text, parse_mode=None)

    cb.message.answer = flaky_answer
    await ph.cb_analyze_last_photo(cb)
    bodies = [a[0] for a in cb.message.answers]
    assert any("контент" in b for b in bodies)


@pytest.mark.asyncio
async def test_cb_analyze_last_photo_status_delete_fails(monkeypatch, tmp_path):
    """status_msg.delete падает → игнорируется (180-181)."""
    photos, _ = _enable(monkeypatch, tmp_path)
    (photos / "b1.jpg").write_bytes(b"x")
    cb = FakeCb(4242, data="photo_analyze_last")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg"])
    monkeypatch.setattr(ph, "get_current_ai", lambda: ("ollama", "llava"))
    monkeypatch.setattr(ph, "check_capability", lambda model, feat: True)
    monkeypatch.setattr(ph, "encode_image_to_base64", lambda path: "b64")
    monkeypatch.setattr(ph, "search_palace_context", _async_none)
    monkeypatch.setattr(ph, "get_smart_prompt", lambda **kw: "S")
    monkeypatch.setattr(ph, "call_ai_sync", lambda *a, **kw: "ok")
    monkeypatch.setattr(ph, "safe_html_format", lambda t: t)
    monkeypatch.setattr(ph, "split_message", lambda t: ["x"])

    async def fake_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ph.asyncio, "to_thread", fake_to_thread)

    class BoomStatus:
        async def delete(self):
            raise RuntimeError("gone")

    real_answer = cb.message.answer

    async def st_answer(text, parse_mode=None, reply_markup=None):
        if "Анализирую" in text:
            return BoomStatus()
        return await real_answer(text, parse_mode, reply_markup)

    cb.message.answer = st_answer
    await ph.cb_analyze_last_photo(cb)
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_del_photo_bad_format(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="del_photo:only")
    await ph.cb_del_photo(cb)
    assert cb.answered == [("❌ Неверный формат запроса", True)]


@pytest.mark.asyncio
async def test_cb_del_photo_no_cache_entry(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(4242, data="del_photo:4242:zzzz")
    await ph.cb_del_photo(cb)
    assert cb.answered == [("❌ Сессия истекла. Откройте /photos заново", True)]


@pytest.mark.asyncio
async def test_cb_del_photo_file_already_deleted(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    ph._photo_delete_cache["4242:aaaa"] = "gone.jpg"
    cb = FakeCb(4242, data="del_photo:4242:aaaa")
    monkeypatch.setattr(ph, "list_photos", lambda: ["other.jpg"])
    await ph.cb_del_photo(cb)
    assert cb.answered == [("❌ Файл уже удален", True)]


@pytest.mark.asyncio
async def test_cb_del_photo_success_others_remain(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    ph._photo_delete_cache["4242:bbbb"] = "b1.jpg"
    cb = FakeCb(4242, data="del_photo:4242:bbbb")
    counter = {"n": 0}

    def fake_list():
        counter["n"] += 1
        if counter["n"] == 1:
            return ["b1.jpg", "b2.jpg"]
        return ["b2.jpg"]

    monkeypatch.setattr(ph, "list_photos", fake_list)
    monkeypatch.setattr(ph, "delete_photo", lambda f: True)
    await ph.cb_del_photo(cb)
    assert cb.answered == [("🗑 Удалено: b1.jpg", True)]
    assert "b2.jpg" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_del_photo_success_last_removed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    ph._photo_delete_cache["4242:cccc"] = "b1.jpg"
    cb = FakeCb(4242, data="del_photo:4242:cccc")
    counter = {"n": 0}

    def fake_list():
        counter["n"] += 1
        if counter["n"] == 1:
            return ["b1.jpg"]
        return []

    monkeypatch.setattr(ph, "list_photos", fake_list)
    monkeypatch.setattr(ph, "delete_photo", lambda f: True)
    await ph.cb_del_photo(cb)
    assert cb.message.edits[0][0] == "📁 Папка photos пуста."


@pytest.mark.asyncio
async def test_cb_del_photo_delete_fails(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    ph._photo_delete_cache["4242:dddd"] = "b1.jpg"
    cb = FakeCb(4242, data="del_photo:4242:dddd")
    monkeypatch.setattr(ph, "list_photos", lambda: ["b1.jpg"])
    monkeypatch.setattr(ph, "delete_photo", lambda f: False)
    await ph.cb_del_photo(cb)
    assert cb.answered == [("❌ Не удалось удалить: b1.jpg", True)]

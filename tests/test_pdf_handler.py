"""Unit tests for handlers.pdf."""

import json
import os
from types import SimpleNamespace

import pytest

from handlers import pdf as pdf_h


class FakeUser:
    def __init__(self, uid):
        self.id = uid


def _make_status_edit(status):
    async def edit(text, parse_mode=None, reply_markup=None):
        status.edits.append(text)

    return edit


class FakeMessage:
    def __init__(self, uid=4242, text="", document=None, bot=None):
        self.from_user = FakeUser(uid)
        self.text = text
        self.document = document
        self.bot = bot or SimpleNamespace()
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        status = SimpleNamespace(edits=[], deleted=False)
        status.edit_text = _make_status_edit(status)
        self.status = status
        return status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))

    async def answer_voice(self, voice):
        self.voice_sent = getattr(self, "voice_sent", []) + [voice]
        return None


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


class FakeTask:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


@pytest.fixture(autouse=True)
def _clean_buffer():
    pdf_h.pdf_buffer.clear()
    yield
    pdf_h.pdf_buffer.clear()


def _enable(monkeypatch, tmp_path):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(pdf_h, "TEMP_DIR", str(tmp_path / "temp"))
    os.makedirs(pdf_h.TEMP_DIR, exist_ok=True)
    monkeypatch.setattr(pdf_h, "PDF_ARCHIVE_DIR", str(tmp_path / "arch"))
    os.makedirs(pdf_h.PDF_ARCHIVE_DIR, exist_ok=True)
    monkeypatch.setattr(pdf_h, "LONG_RESPONSES_DIR", str(tmp_path / "long"))
    os.makedirs(pdf_h.LONG_RESPONSES_DIR, exist_ok=True)
    monkeypatch.setattr(
        "services.text_formatter.safe_html_format", lambda t: t,
    )
    monkeypatch.setattr(
        "services.text_formatter.split_message",
        lambda t, limit=4000: [t] if t else [],
    )
    monkeypatch.setattr(
        pdf_h, "get_voice_settings", lambda uid: {"mode": "text", "speed": 160},
    )
    return tmp_path


# ---------- create_prompt_kb ----------


def test_create_prompt_kb(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "load_prompts",
        lambda: {
            "sum": {"name": "📊 Суммаризация", "prompt": "Суммируй."},
            "qa": {"name": "❓ Q&A", "prompt": "Отвечай."},
        },
    )
    kb = pdf_h.create_prompt_kb()
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert texts == ["📊 Суммаризация", "❓ Q&A"]
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert datas == ["pdf_type:sum", "pdf_type:qa"]


# ---------- cmd_compare ----------


@pytest.mark.asyncio
async def test_cmd_compare(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await pdf_h.cmd_compare(msg)
    assert "Режим сравнения" in msg.answers[0][0]
    assert pdf_h.pdf_buffer[4242] == {"files": [], "mode": "compare", "timer": None}


@pytest.mark.asyncio
async def test_cmd_compare_not_allowed(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(uid=999)
    await pdf_h.cmd_compare(msg)
    assert msg.answers == []


# ---------- handle_pdf ----------


def _doc(name="doc.pdf", size=1024):
    return SimpleNamespace(file_name=name, file_id="fid1", file_size=size)


def _bot(monkeypatch):
    bot = SimpleNamespace()
    calls = []

    async def get_file(file_id):
        calls.append(("get_file", file_id))
        return SimpleNamespace(file_path=f"path/{file_id}")

    async def download_file(file_path, destination=None):
        calls.append(("download", file_path))
        with open(destination, "w", encoding="utf-8") as f:
            f.write("pdf-bytes")

    bot.get_file = get_file
    bot.download_file = download_file
    return bot, calls


@pytest.mark.asyncio
async def test_handle_pdf_not_pdf(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(document=_doc("readme.txt"))
    assert await pdf_h.handle_pdf(msg) is None
    assert msg.answers == []
    assert 4242 not in pdf_h.pdf_buffer


@pytest.mark.asyncio
async def test_handle_pdf_too_big(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage(document=_doc("big.pdf", 51 * 1024 * 1024))
    await pdf_h.handle_pdf(msg)
    assert "Лимит 50MB" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_handle_pdf_download_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    bot = SimpleNamespace()

    async def get_file(file_id):
        return SimpleNamespace(file_path="x.pdf")

    async def download_file(file_path, destination=None):
        raise OSError("сеть упала")

    bot.get_file = get_file
    bot.download_file = download_file
    msg = FakeMessage(document=_doc("doc.pdf"), bot=bot)
    await pdf_h.handle_pdf(msg)
    assert "Ошибка загрузки файла" in msg.status.edits[-1]


@pytest.mark.asyncio
async def test_handle_pdf_single_mode(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    saved = []
    monkeypatch.setattr(
        pdf_h, "save_pdf_original", lambda src, name: saved.append((src, name)),
    )
    bot, _ = _bot(monkeypatch)
    msg = FakeMessage(document=_doc("my doc.pdf"), bot=bot)
    await pdf_h.handle_pdf(msg)
    assert "PDF загружен и сохранён" in msg.status.edits[-1]
    assert msg.status.edits[-1] is not None
    assert pdf_h.pdf_buffer[4242]["mode"] == "single"
    assert len(pdf_h.pdf_buffer[4242]["files"]) == 1
    assert saved
    assert saved[0][1] == "my doc.pdf"


@pytest.mark.asyncio
async def test_handle_pdf_compare_waiting_second(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [], "mode": "compare", "timer": None}
    bot, _ = _bot(monkeypatch)
    msg = FakeMessage(document=_doc("a.pdf"), bot=bot)
    await pdf_h.handle_pdf(msg)
    assert "Ожидание второго PDF" in msg.status.edits[-1]
    assert len(pdf_h.pdf_buffer[4242]["files"]) == 1


@pytest.mark.asyncio
async def test_handle_pdf_compare_two_files(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    timer = FakeTask()
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a")], "mode": "compare", "timer": timer,
    }
    results = {"n": 0}

    async def fake_compare(uid, status):
        results["n"] += 1
        results["uid"] = uid

    monkeypatch.setattr(pdf_h, "run_comparison", fake_compare)
    bot, _ = _bot(monkeypatch)
    msg = FakeMessage(document=_doc("b.pdf"), bot=bot)
    await pdf_h.handle_pdf(msg)
    assert "Запускаю сравнение" in msg.status.edits[-1]
    assert results["n"] == 1
    assert timer.cancelled is True


@pytest.mark.asyncio
async def test_handle_pdf_compare_three_files_fallthrough(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a"), ("b.pdf", "/tmp/b")], "mode": "compare", "timer": None,
    }
    monkeypatch.setattr(pdf_h, "save_pdf_original", lambda src, name: None)
    bot, _ = _bot(monkeypatch)
    msg = FakeMessage(document=_doc("c.pdf"), bot=bot)
    await pdf_h.handle_pdf(msg)
    assert len(pdf_h.pdf_buffer[4242]["files"]) == 3
    assert "PDF загружен и сохранён" in msg.status.edits[-1]


@pytest.mark.asyncio
async def test_handle_pdf_compare_two_files_no_timer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a")], "mode": "compare", "timer": None,
    }
    results = {"n": 0}

    async def fake_compare(uid, status):
        results["n"] += 1

    monkeypatch.setattr(pdf_h, "run_comparison", fake_compare)
    bot, _ = _bot(monkeypatch)
    msg = FakeMessage(document=_doc("b.pdf"), bot=bot)
    await pdf_h.handle_pdf(msg)
    assert results["n"] == 1


# ---------- cb_show_prompts / cb_activate_compare ----------


@pytest.mark.asyncio
async def test_cb_show_prompts(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(pdf_h, "load_prompts", lambda: {})
    cb = FakeCb(data="show_pdf_prompts")
    await pdf_h.cb_show_prompts(cb)
    assert "Выберите тип анализа" in cb.message.edits[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_activate_compare(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    created = []

    def fake_create(coro):
        created.append(coro)
        coro.close()
        return FakeTask()

    monkeypatch.setattr(pdf_h.asyncio, "create_task", fake_create)
    cb = FakeCb(data="activate_compare")
    await pdf_h.cb_activate_compare(cb)
    assert pdf_h.pdf_buffer[4242]["mode"] == "compare"
    assert "Жду второй PDF" in cb.message.edits[0][0]
    assert len(created) == 1


@pytest.mark.asyncio
async def test_cb_activate_compare_cancels_old_timer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    old_timer = FakeTask()
    pdf_h.pdf_buffer[4242] = {
        "files": [], "mode": "single", "timer": old_timer,
    }
    created = []

    def fake_create(coro):
        created.append(coro)
        coro.close()
        return FakeTask()

    monkeypatch.setattr(pdf_h.asyncio, "create_task", fake_create)
    cb = FakeCb(data="activate_compare")
    await pdf_h.cb_activate_compare(cb)
    assert old_timer.cancelled is True
    assert len(created) == 1


@pytest.mark.asyncio
async def test_timeout_compare_task_loop(monkeypatch, tmp_path):
    """Таймер: sleep no-op, edit падает — обе warning ветки."""
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [("a.pdf", "/tmp/a")], "mode": "compare", "timer": None}
    created = []

    async def noop_sleep(sec):
        pass

    async def failing_edit(text, parse_mode=None, reply_markup=None):
        raise RuntimeError("edit fail")

    class FailMsg(FakeMessage):
        async def answer(self, text, parse_mode=None, reply_markup=None):
            self.answers.append((text, parse_mode, reply_markup))
            status = SimpleNamespace(edits=[], deleted=False)
            status.edit_text = failing_edit
            self.status = status
            return status

    monkeypatch.setattr(pdf_h.asyncio, "sleep", noop_sleep)
    monkeypatch.setattr(pdf_h, "create_prompt_kb", lambda: None)
    monkeypatch.setattr(
        pdf_h.asyncio, "create_task", lambda coro: created.append(coro) or FakeTask(),
    )
    cb = FakeCb(data="activate_compare", message=FailMsg())
    await pdf_h.cb_activate_compare(cb)
    assert len(created) == 1
    await created[0]
    assert pdf_h.pdf_buffer[4242]["mode"] == "single"


@pytest.mark.asyncio
async def test_timeout_compare_task_mode_changed(monkeypatch, tmp_path):
    """Во время таймера режим сменился — таск выходит рано."""
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [], "mode": "compare", "timer": None}
    created = []
    ran = []

    async def mode_change_sleep(sec):
        pdf_h.pdf_buffer[4242]["mode"] = "single"
        ran.append(1)

    monkeypatch.setattr(pdf_h.asyncio, "sleep", mode_change_sleep)
    monkeypatch.setattr(
        pdf_h.asyncio, "create_task", lambda coro: created.append(coro) or FakeTask(),
    )
    cb = FakeCb(data="activate_compare")
    await pdf_h.cb_activate_compare(cb)
    await created[0]
    assert ran == [1]


@pytest.mark.asyncio
async def test_timeout_compare_task_second_file_arrived(monkeypatch, tmp_path):
    """Во время таймера пришёл второй файл — таск выходит рано."""
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [("a.pdf", "/tmp/a")], "mode": "compare", "timer": None}
    created = []
    ran = []

    async def file_arrive_sleep(sec):
        pdf_h.pdf_buffer[4242]["files"].append(("b.pdf", "/tmp/b"))
        ran.append(1)

    monkeypatch.setattr(pdf_h.asyncio, "sleep", file_arrive_sleep)
    monkeypatch.setattr(
        pdf_h.asyncio, "create_task", lambda coro: created.append(coro) or FakeTask(),
    )
    cb = FakeCb(data="activate_compare")
    await pdf_h.cb_activate_compare(cb)
    await created[0]
    assert ran == [1]


@pytest.mark.asyncio
async def test_timeout_compare_task_cancelled(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [], "mode": "compare", "timer": None}
    created = []

    async def cancel_sleep(sec):
        raise asyncio.CancelledError()

    monkeypatch.setattr(pdf_h.asyncio, "sleep", cancel_sleep)
    monkeypatch.setattr(
        pdf_h.asyncio, "create_task", lambda coro: created.append(coro) or FakeTask(),
    )
    cb = FakeCb(data="activate_compare")
    await pdf_h.cb_activate_compare(cb)
    await created[0]
    assert created[0].__name__ == "timeout_compare"


import asyncio


@pytest.mark.asyncio
async def test_timeout_compare_task_no_files_no_reset(monkeypatch, tmp_path):
    """Таймер истёк, файлов нет — режим не сбрасывается (условие 179 false)."""
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [], "mode": "compare", "timer": None}
    created = []

    async def noop_sleep(sec):
        pass

    monkeypatch.setattr(pdf_h.asyncio, "sleep", noop_sleep)
    monkeypatch.setattr(
        pdf_h.asyncio, "create_task", lambda coro: created.append(coro) or FakeTask(),
    )
    cb = FakeCb(data="activate_compare")
    await pdf_h.cb_activate_compare(cb)
    await created[0]
    assert pdf_h.pdf_buffer[4242]["mode"] == "compare"


# ---------- cb_pdf_type ----------


@pytest.mark.asyncio
async def test_cb_pdf_type_no_data(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data=None)
    await pdf_h.cb_pdf_type(cb)
    assert cb.answered == [("❌ Неверный запрос", True)]


@pytest.mark.asyncio
async def test_cb_pdf_type_empty_buffer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="pdf_type:sum")
    await pdf_h.cb_pdf_type(cb)
    assert cb.answered == [("Буфер пуст", None)]


@pytest.mark.asyncio
async def test_cb_pdf_type_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [("a.pdf", "/tmp/a")], "mode": "single", "timer": None}
    calls = []

    async def fake_run(uid, ptype, msg):
        calls.append((uid, ptype))

    monkeypatch.setattr(pdf_h, "run_analysis", fake_run)
    cb = FakeCb(data="pdf_type:sum")
    await pdf_h.cb_pdf_type(cb)
    assert "Извлекаю текст" in cb.message.edits[0][0]
    assert calls == [(4242, "sum")]


# ---------- send_long_response_parts ----------


@pytest.mark.asyncio
async def test_send_long_response_parts_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message", lambda t, limit=4000: [],
    )
    msg = FakeMessage()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "text")
    assert msg.answers == []
    assert msg.edits == []


@pytest.mark.asyncio
async def test_send_long_response_parts_text_mode(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message",
        lambda t, limit=4000: ["часть1", "часть2", "часть3"],
    )
    msg = FakeMessage()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "text")
    assert len(msg.answers) == 3
    assert msg.answers[0][2] is not None
    texts0 = [b.text for row in msg.answers[0][2].inline_keyboard for b in row]
    texts2 = [b.text for row in msg.answers[2][2].inline_keyboard for b in row]
    assert "➡️ Читать дальше (2/3)" in texts0
    assert texts2 == []
    saved = json.loads((tmp / "long" / "base.json").read_text(encoding="utf-8"))
    assert saved == ["часть1", "часть2", "часть3"]


@pytest.mark.asyncio
async def test_send_long_response_parts_voice_mode(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message", lambda t, limit=4000: ["часть1", "часть2"],
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "озвучка")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: ["озвучка-1", "озвучка-2"],
    )
    monkeypatch.setattr(
        pdf_h, "generate_voice_async", _async_result(["/tmp/one.ogg"]),
    )
    msg = FakeMessage()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "voice")
    assert msg.answers[0][0] == "🎤 Генерирую полный голосовой ответ..."
    assert len(msg.voice_sent) == 2


@pytest.mark.asyncio
async def test_send_long_response_parts_both_mode_voice_error(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message", lambda t, limit=4000: ["часть1"],
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "озвучка")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: ["озвучка-1"],
    )

    async def bad_voice(uid, chunk):
        raise RuntimeError("tts упал")

    monkeypatch.setattr(pdf_h, "generate_voice_async", bad_voice)
    msg = FakeMessage()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "both")
    assert msg.answers[0][0] == "часть1"
    assert not hasattr(msg, "voice_sent")


@pytest.mark.asyncio
async def test_send_long_response_parts_voice_send_fails(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message", lambda t, limit=4000: ["часть1"],
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "озвучка")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: ["озвучка-1"],
    )
    monkeypatch.setattr(
        pdf_h, "generate_voice_async", _async_result(["/tmp/x.ogg"]),
    )

    class FailMsg(FakeMessage):
        async def answer_voice(self, voice):
            raise RuntimeError("send fail")

    msg = FailMsg()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "voice")
    assert not os.path.exists("/tmp/x.ogg")


@pytest.mark.asyncio
async def test_send_long_response_parts_voice_no_tts_text(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message", lambda t, limit=4000: ["часть1"],
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: [],
    )
    msg = FakeMessage()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "voice")
    assert msg.answers == []


@pytest.mark.asyncio
async def test_send_long_response_parts_voice_no_chunks(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message", lambda t, limit=4000: ["часть1"],
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "озвучка")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: [],
    )
    msg = FakeMessage()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "voice")
    assert msg.answers == []


@pytest.mark.asyncio
async def test_send_long_response_parts_voice_mode_error_no_text(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "split_message", lambda t, limit=4000: ["часть1"],
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "озвучка")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: ["озвучка-1"],
    )

    async def bad_voice(uid, chunk):
        raise RuntimeError("tts упал")

    monkeypatch.setattr(pdf_h, "generate_voice_async", bad_voice)
    msg = FakeMessage()
    await pdf_h.send_long_response_parts(msg, "текст", "base", "voice")
    bodies = [a[0] for a in msg.answers]
    assert any("Не удалось сгенерировать голос" in b for b in bodies)


# ---------- cb_read_next ----------


@pytest.mark.asyncio
async def test_cb_read_next_no_data(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data=None)
    await pdf_h.cb_read_next(cb)
    assert cb.answered == [("❌ Неверный запрос", True)]


@pytest.mark.asyncio
async def test_cb_read_next_missing_file(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data="read_next:base:1")
    await pdf_h.cb_read_next(cb)
    assert cb.answered == [("❌ Файл ответа не найден", True)]


@pytest.mark.asyncio
async def test_cb_read_next_last_part(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    (tmp / "long" / "base.json").write_text(
        json.dumps(["a", "b"]), encoding="utf-8",
    )
    cb = FakeCb(data="read_next:base:2")
    await pdf_h.cb_read_next(cb)
    assert cb.answered == [("Это последняя часть.", True)]


@pytest.mark.asyncio
async def test_cb_read_next_success_text_mode(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    (tmp / "long" / "base.json").write_text(
        json.dumps(["a", "b", "c"]), encoding="utf-8",
    )
    cb = FakeCb(data="read_next:base:1")
    await pdf_h.cb_read_next(cb)
    assert cb.message.answers[0][0] == "b"
    texts = [b.text for row in cb.message.answers[0][2].inline_keyboard for b in row]
    assert "➡️ Далее (3/3)" in texts
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_read_next_success_last_with_end_button(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    (tmp / "long" / "base.json").write_text(
        json.dumps(["a", "b"]), encoding="utf-8",
    )
    cb = FakeCb(data="read_next:base:1")
    await pdf_h.cb_read_next(cb)
    texts = [b.text for row in cb.message.answers[0][2].inline_keyboard for b in row]
    assert "✅ Конец" in texts


@pytest.mark.asyncio
async def test_cb_read_next_success_voice_mode(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(pdf_h, "get_voice_settings", lambda uid: {"mode": "both", "speed": 160})
    (tmp / "long" / "base.json").write_text(
        json.dumps(["a", "b"]), encoding="utf-8",
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "озвучка")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: ["озвучка-1"],
    )
    monkeypatch.setattr(
        pdf_h, "generate_voice_async", _async_result(["/tmp/v.ogg"]),
    )
    cb = FakeCb(data="read_next:base:0")
    await pdf_h.cb_read_next(cb)
    assert len(cb.message.voice_sent) == 1


@pytest.mark.asyncio
async def test_cb_read_next_voice_error(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(pdf_h, "get_voice_settings", lambda uid: {"mode": "voice", "speed": 160})
    (tmp / "long" / "base.json").write_text(
        json.dumps(["a", "b"]), encoding="utf-8",
    )

    async def bad_voice(uid, chunk):
        raise RuntimeError("tts упал")

    monkeypatch.setattr(pdf_h, "generate_voice_async", bad_voice)
    cb = FakeCb(data="read_next:base:0")
    await pdf_h.cb_read_next(cb)
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_read_next_voice_send_fails(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(pdf_h, "get_voice_settings", lambda uid: {"mode": "both", "speed": 160})
    (tmp / "long" / "base.json").write_text(
        json.dumps(["a", "b"]), encoding="utf-8",
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "озвучка")
    monkeypatch.setattr(
        pdf_h, "split_tts_text", lambda t, max_chars=1800: ["озвучка-1"],
    )
    monkeypatch.setattr(
        pdf_h, "generate_voice_async", _async_result(["/tmp/v.ogg"]),
    )

    class FailMsg(FakeMessage):
        async def answer_voice(self, voice):
            raise RuntimeError("send fail")

    cb = FakeCb(data="read_next:base:0", message=FailMsg())
    await pdf_h.cb_read_next(cb)
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_read_next_voice_no_tts_text(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(pdf_h, "get_voice_settings", lambda uid: {"mode": "voice", "speed": 160})
    (tmp / "long" / "base.json").write_text(
        json.dumps(["a", "b"]), encoding="utf-8",
    )
    monkeypatch.setattr(pdf_h, "prepare_tts_text", lambda t: "")
    cb = FakeCb(data="read_next:base:0")
    await pdf_h.cb_read_next(cb)
    assert cb.answered == [(None, None)]


# ---------- cmd_pdfs ----------


@pytest.mark.asyncio
async def test_cmd_pdfs_empty(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(pdf_h, "list_archived_pdfs", lambda: [])
    msg = FakeMessage()
    await pdf_h.cmd_pdfs(msg)
    assert "В архиве нет PDF" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_cmd_pdfs_with_entries(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "list_archived_pdfs",
        lambda: [
            {"id": "i1", "original_name": "one.pdf"},
            {"id": "i2", "original_name": "x" * 50 + ".pdf"},
        ],
    )
    msg = FakeMessage()
    await pdf_h.cmd_pdfs(msg)
    assert "PDF в архиве (2)" in msg.answers[0][0]
    texts = [b.text for row in msg.answers[0][2].inline_keyboard for b in row]
    assert texts[0] == "📄 one.pdf"
    assert len(texts[1]) <= 45


# ---------- cb_select_archived_pdf ----------


@pytest.mark.asyncio
async def test_cb_select_archived_pdf_no_data(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    cb = FakeCb(data=None)
    await pdf_h.cb_select_archived_pdf(cb)
    assert cb.answered == [("❌ Неверный запрос", True)]


@pytest.mark.asyncio
async def test_cb_select_archived_pdf_not_found(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(pdf_h, "list_archived_pdfs", lambda: [])
    cb = FakeCb(data="pdf_archive:nope")
    await pdf_h.cb_select_archived_pdf(cb)
    assert cb.answered == [("❌ Файл не найден", True)]


@pytest.mark.asyncio
async def test_cb_select_archived_pdf_missing_on_disk(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pdf_h, "list_archived_pdfs",
        lambda: [{"id": "i1", "original_name": "a.pdf", "path": "/no/such/file.pdf"}],
    )
    cb = FakeCb(data="pdf_archive:i1")
    await pdf_h.cb_select_archived_pdf(cb)
    assert cb.answered == [("❌ Файл не найден", True)]


@pytest.mark.asyncio
async def test_cb_select_archived_pdf_success(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    real_path = tmp / "arch" / "saved.pdf"
    real_path.write_bytes(b"pdf")
    monkeypatch.setattr(
        pdf_h, "list_archived_pdfs",
        lambda: [{"id": "i1", "original_name": "a.pdf", "path": str(real_path)}],
    )
    monkeypatch.setattr(pdf_h, "load_prompts", lambda: {})
    cb = FakeCb(data="pdf_archive:i1")
    await pdf_h.cb_select_archived_pdf(cb)
    assert "Выбери тип анализа" in cb.message.edits[0][0]
    assert pdf_h.pdf_buffer[4242]["mode"] == "single"
    assert pdf_h.pdf_buffer[4242]["files"] == [("a.pdf", str(real_path))]
    assert cb.answered == [(None, None)]


# ---------- run_analysis ----------


@pytest.mark.asyncio
async def test_run_analysis_empty_buffer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await pdf_h.run_analysis(4242, "sum", msg)
    assert msg.edits[-1][0] == "❌ Буфер PDF пуст."


@pytest.mark.asyncio
async def test_run_analysis_extract_fails(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [("a.pdf", "/tmp/a")], "mode": "single", "timer": None}

    async def bad_extract(path):
        raise RuntimeError("broken pdf")

    monkeypatch.setattr(pdf_h, "extract_pdf_async", bad_extract)
    msg = FakeMessage()
    await pdf_h.run_analysis(4242, "sum", msg)
    assert msg.edits[-1][0] == "❌ Не удалось извлечь текст."


@pytest.mark.asyncio
async def test_run_analysis_empty_text(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {"files": [("a.pdf", "/tmp/a")], "mode": "single", "timer": None}
    monkeypatch.setattr(pdf_h, "extract_pdf_async", _async_result(("", "pypdf")))
    msg = FakeMessage()
    await pdf_h.run_analysis(4242, "sum", msg)
    assert msg.edits[-1][0] == "❌ Не удалось извлечь текст."


@pytest.mark.asyncio
async def test_run_analysis_success(monkeypatch, tmp_path):
    tmp = _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a.pdf")], "mode": "single", "timer": None,
    }
    monkeypatch.setattr(
        pdf_h, "extract_pdf_async", _async_result(("текст документа", "pypdf")),
    )
    monkeypatch.setattr(pdf_h, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(pdf_h, "load_prompts", lambda: {"sum": {"prompt": "Суммируй."}})
    monkeypatch.setattr(
        pdf_h, "analyze_large_document",
        _async_result("итоговый анализ"),
    )
    msg = FakeMessage()
    await pdf_h.run_analysis(4242, "sum", msg)
    assert not os.path.exists("/tmp/a.pdf")
    arch_files = os.listdir(tmp / "arch")
    assert any("pdf_" in f and f.endswith(".txt") for f in arch_files)
    assert "итоговый анализ" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_run_analysis_error_answer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a.pdf")], "mode": "single", "timer": None,
    }
    monkeypatch.setattr(
        pdf_h, "extract_pdf_async", _async_result(("текст документа", "pypdf")),
    )
    monkeypatch.setattr(pdf_h, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(pdf_h, "load_prompts", lambda: {})
    monkeypatch.setattr(
        pdf_h, "analyze_large_document",
        _async_result("❌ Слишком длинный документ"),
    )
    msg = FakeMessage()
    await pdf_h.run_analysis(4242, "sum", msg)
    assert any("❌ Слишком длинный документ" in a[0] for a in msg.answers)


@pytest.mark.asyncio
async def test_run_analysis_empty_final_answer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a.pdf")], "mode": "single", "timer": None,
    }
    monkeypatch.setattr(
        pdf_h, "extract_pdf_async", _async_result(("текст документа", "pypdf")),
    )
    monkeypatch.setattr(pdf_h, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(pdf_h, "load_prompts", lambda: {})
    monkeypatch.setattr(
        pdf_h, "analyze_large_document", _async_result(""),
    )
    msg = FakeMessage()
    await pdf_h.run_analysis(4242, "sum", msg)
    assert msg.answers == []


@pytest.mark.asyncio
async def test_run_analysis_error_answer_fails_to_send(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a.pdf")], "mode": "single", "timer": None,
    }
    monkeypatch.setattr(
        pdf_h, "extract_pdf_async", _async_result(("текст документа", "pypdf")),
    )
    monkeypatch.setattr(pdf_h, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(pdf_h, "load_prompts", lambda: {})
    monkeypatch.setattr(
        pdf_h, "analyze_large_document",
        _async_result("❌ Слишком длинный документ"),
    )

    class FailMsg(FakeMessage):
        async def answer(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("send fail")

    msg = FailMsg()
    await pdf_h.run_analysis(4242, "sum", msg)


# ---------- run_comparison ----------


@pytest.mark.asyncio
async def test_run_comparison_empty_buffer(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    msg = FakeMessage()
    await pdf_h.run_comparison(4242, msg)
    assert msg.edits[-1][0] == "❌ Ошибка буфера сравнения."


@pytest.mark.asyncio
async def test_run_comparison_success(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    pdf_h.pdf_buffer[4242] = {
        "files": [("a.pdf", "/tmp/a"), ("b.pdf", "/tmp/b")], "mode": "compare", "timer": None,
    }
    monkeypatch.setattr(
        pdf_h, "extract_pdf_async",
        _async_result(("текст-anything", "pypdf")),
    )
    monkeypatch.setattr(pdf_h, "build_comparison_prompt", lambda a, b: f"сравни {a} и {b}")
    monkeypatch.setattr(pdf_h, "get_current_ai", lambda: ("ollama", "llama3"))
    monkeypatch.setattr(
        pdf_h, "get_ai_response_async",
        _async_result("сравнение готово"),
    )
    msg = FakeMessage()
    await pdf_h.run_comparison(4242, msg)
    assert "llama3" in msg.edits[-1][0]
    assert "сравнение готово" in msg.answers[0][0]


def _async_result(value):
    async def _inner(*a, **kw):
        return value

    return _inner

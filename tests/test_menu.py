"""Unit tests for services.menu (safe return to main menu)."""

import sys

import pytest

import services.menu as menu


class FakeTarget:
    def __init__(self):
        self.answers = []
        self.edits = []

    async def answer(self, text):
        self.answers.append(text)

    async def edit_text(self, text):
        self.edits.append(text)


class FakeCmdStart:
    def __init__(self):
        self.calls = 0
        self.answers = []

    async def __call__(self, target):
        self.calls += 1
        self.answers.append("menu opened")


# ---------- через __main__ ----------


@pytest.mark.asyncio
async def test_go_main_menu_via_main_module(monkeypatch):
    target = FakeTarget()
    fake = FakeCmdStart()
    mod = type(sys)("__main__")
    mod.cmd_start = fake
    monkeypatch.setitem(sys.modules, "__main__", mod)
    await menu.go_main_menu(target)
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_go_main_menu_via_main_name(monkeypatch):
    target = FakeTarget()
    fake = FakeCmdStart()
    mod = type(sys)("main")
    mod.cmd_start = fake
    monkeypatch.setitem(sys.modules, "main", mod)
    await menu.go_main_menu(target)
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_go_main_menu_none_target():
    assert await menu.go_main_menu(None) is None


@pytest.mark.asyncio
async def test_go_main_menu_fallback_success(monkeypatch):
    """main недоступен в sys.modules, но импорт из файла работает → cmd_start вызван."""
    import builtins

    class FakeCmd:
        async def __call__(self, target):
            self.calls = getattr(self, "calls", 0) + 1

    fake = FakeCmd()
    target = FakeTarget()
    fake_mod = type(sys)("main")
    fake_mod.cmd_start = fake

    monkeypatch.delitem(sys.modules, "main", raising=False)
    monkeypatch.delitem(sys.modules, "__main__", raising=False)
    orig_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "main" and fromlist and "cmd_start" in fromlist:
            return fake_mod
        return orig_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    await menu.go_main_menu(target)
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_go_main_menu_fallback_import(monkeypatch):
    target = FakeTarget()
    empty_mod = type(sys)("main")  # нет cmd_start
    monkeypatch.delitem(sys.modules, "main", raising=False)
    monkeypatch.setitem(sys.modules, "main", empty_mod)

    async def fake_answer(text):
        target.answers.append(text)

    monkeypatch.setattr(target, "answer", fake_answer)

    class FakeLogger:
        def error(self, msg, exc_info=False):
            pass

    monkeypatch.setattr(menu, "logger", FakeLogger())
    await menu.go_main_menu(target)
    assert target.answers
    assert "Не удалось" in target.answers[0]


@pytest.mark.asyncio
async def test_go_main_menu_cmd_start_fails(monkeypatch):
    """cmd_start бросил исключение → уведомляем об ошибке."""
    target = FakeTarget()
    mod = type(sys)("fake_main")

    async def boom(self):
        raise RuntimeError("exploded")

    mod.cmd_start = boom
    monkeypatch.setitem(sys.modules, "main", mod)

    class FakeLogger:
        def error(self, msg, exc_info=False):
            pass

    monkeypatch.setattr(menu, "logger", FakeLogger())
    await menu.go_main_menu(target)
    assert target.answers
    assert "Не удалось" in target.answers[0]


@pytest.mark.asyncio
async def test_go_main_menu_answer_also_fails(monkeypatch):
    """И уведомление падает — глотается."""
    target = FakeTarget()
    mod = type(sys)("fake_main")

    async def boom(self):
        raise RuntimeError("exploded")

    mod.cmd_start = boom
    monkeypatch.setitem(sys.modules, "main", mod)

    async def bad_answer(text):
        raise RuntimeError("answer dead")

    monkeypatch.setattr(target, "answer", bad_answer)

    class FakeLogger:
        def error(self, msg, exc_info=False):
            pass

    monkeypatch.setattr(menu, "logger", FakeLogger())
    await menu.go_main_menu(target)
    assert target.answers == []

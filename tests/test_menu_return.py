"""Тесты Шага 3 ТЗ: безопасный возврат в главное меню (баг №5 — «🏠 В меню»).

Баг: personal_note искал cmd_start через sys.modules.get("__main__") без
fallback на `from main import cmd_start` — когда модуль отсутствовал,
кнопка «В меню» молча ничего не делала.
"""
import importlib
import sys
import types

import pytest

import handlers.personal_note as pn
from services import menu


class FakeTarget:
    def __init__(self):
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


@pytest.fixture(autouse=True)
def _save_main(monkeypatch):
    """Изолируем sys.modules от изменений. Реальный __main__ прячем."""
    stored_main_module = None
    for name in ("__main__", "main"):
        stored = sys.modules.pop(name, None)
        if name == "__main__":
            stored_main_module = stored
    yield
    for name, stored in {"__main__": stored_main_module, "main": stored}.items():
        if stored is not None:
            sys.modules[name] = stored
        elif name in sys.modules:
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _patch_pn_go_main_menu(monkeypatch):
    """В личных заметках go_main_menu не должен реально лезть в main."""
    async def noop(_target):
        return None

    monkeypatch.setattr(pn, "go_main_menu", noop)


@pytest.fixture(autouse=True)
def _allow_ids(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {424242, 1})


def _install_main_with_cmd_start(monkeypatch, recorded):
    mod = importlib.types.SimpleNamespace()
    mod.cmd_start = recorded
    monkeypatch.setitem(sys.modules, "main", mod)


@pytest.mark.asyncio
async def test_uses_cmd_start_from_dunder_main(monkeypatch):
    calls = []
    fake = types.ModuleType("__main__")
    fake.cmd_start = lambda t: calls.append(t)
    monkeypatch.setitem(sys.modules, "__main__", fake)
    target = FakeTarget()
    await menu.go_main_menu(target)
    assert calls == [target]


@pytest.mark.asyncio
async def test_main_module_fallback(monkeypatch):
    """Нет __main__.cmd_start — берём cmd_start из модуля main."""
    calls = []
    fake = types.ModuleType("main")
    fake.cmd_start = lambda t: calls.append(t)
    monkeypatch.setitem(sys.modules, "main", fake)
    target = FakeTarget()
    await menu.go_main_menu(target)
    assert calls == [target]


@pytest.mark.asyncio
async def test_direct_import_fallback(monkeypatch):
    """Ни __main__ ни main нет — прямой import main.cmd_start."""
    target = FakeTarget()
    calls = []
    fake = types.ModuleType("main")
    fake.cmd_start = lambda t: calls.append(t)
    # чтобы from main import cmd_start сработал, кладём fake в sys.modules
    monkeypatch.setitem(sys.modules, "main", fake)
    # убираем cmd_start из __main__, чтобы путь через __main__ не сработал
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))
    await menu.go_main_menu(target)
    assert calls == [target]


@pytest.mark.asyncio
async def test_main_module_has_no_cmd_start_error_message(monkeypatch):
    """Негатив: в main нет cmd_start — пользователь видит сообщение об ошибке."""
    target = FakeTarget()
    fake_main = types.ModuleType("main")
    assert not hasattr(fake_main, "cmd_start")
    monkeypatch.setitem(sys.modules, "main", fake_main)
    # __main__ без cmd_start
    empty = types.ModuleType("__main__")
    monkeypatch.setitem(sys.modules, "__main__", empty)
    await menu.go_main_menu(target)
    assert target.answers and "Не удалось открыть меню" in target.answers[0]


@pytest.mark.asyncio
async def test_cmd_start_raises_shows_fallback_message(monkeypatch):
    """Негатив: cmd_start падает с исключением — не льём ошибку пользователю."""
    target = FakeTarget()

    def boom(t):
        raise RuntimeError("crash")

    fake = types.ModuleType("__main__")
    fake.cmd_start = boom
    monkeypatch.setitem(sys.modules, "__main__", fake)
    await menu.go_main_menu(target)
    assert target.answers and "Не удалось открыть меню" in target.answers[0]


@pytest.mark.asyncio
async def test_none_target_silent():
    """Edge: target=None — тихий выход без исключений."""
    await menu.go_main_menu(None)


@pytest.mark.asyncio
async def test_answer_failure_swallowed(monkeypatch):
    """Edge: ответ пользователю падает — не пробрасываем исключение."""
    class BadTarget:
        async def answer(self, text, **kwargs):
            raise RuntimeError("no network")

    fake = types.ModuleType("main")
    monkeypatch.setitem(sys.modules, "main", fake)
    empty_main = types.ModuleType("__main__")
    monkeypatch.setitem(sys.modules, "__main__", empty_main)
    await menu.go_main_menu(BadTarget())


@pytest.mark.asyncio
async def test_cb_pn_list_back_cleans_state(monkeypatch):
    """Интеграция: кнопка «В меню» чистит состояние списка и активный drawer."""
    class User:
        id = 424242

    class Callback:
        from_user = User()
        message = None
        answered = False

        async def answer(self, *a, **k):
            self.answered = True

    # фолбэк в модуле всё равно должен ходить в menu.go_main_menu,
    # поэтому укажем собственный noop на handler уровне и проверим вызов
    calls = []

    async def fake_go(t):
        calls.append(t)

    monkeypatch.setattr(pn, "go_main_menu", fake_go)
    pn._list_state[424242] = {"wing": "личные_мысли"}
    pn._active_drawer[424242] = "drawer_x"
    await pn.cb_pn_list_back(Callback())
    assert pn._list_state.pop(424242, None) is None
    assert pn._active_drawer.pop(424242, None) is None
    assert calls

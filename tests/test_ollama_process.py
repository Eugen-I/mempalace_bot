import subprocess
import time

import pytest

import services.ollama_process as ollama_process


@pytest.fixture(autouse=True)
def _clear_spawned_registry():
    ollama_process._SPAWNED.clear()
    yield
    ollama_process._SPAWNED.clear()


class DummyProc:
    def __init__(self, poll_result=None) -> None:
        self.poll_result = poll_result
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self):
        return self.poll_result

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_calls += 1
        return 0


class _Result:
    def __init__(self, code, stdout=""):
        self.returncode = code
        self.stdout = stdout


# ---------- is_server_available ----------


def test_server_available_ok(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: _Result(0),
    )
    assert m.is_server_available() is True


def test_server_available_nonzero(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: _Result(1),
    )
    assert m.is_server_available() is False


def test_server_available_timeout(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("ollama", 5)),
    )
    assert m.is_server_available() is False


def test_server_available_not_found(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert m.is_server_available() is False


def test_server_available_oserror(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(OSError("denied")),
    )
    assert m.is_server_available() is False


# ---------- is_model_available ----------


def test_model_available_by_base_name(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: _Result(0, "qwen2.5:7b 4.1 GB"),
    )
    assert m.is_model_available() is True


def test_model_available_by_full_name(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="custom:latest")
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: _Result(0, "custom:latest"),
    )
    assert m.is_model_available() is True


def test_model_available_not_found(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="phi3")
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: _Result(0, "qwen2.5:7b"),
    )
    assert m.is_model_available() is False


def test_model_available_nonzero(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="phi3")
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: _Result(1),
    )
    assert m.is_model_available() is False


def test_model_available_error(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="phi3")
    monkeypatch.setattr(
        ollama_process.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(OSError("denied")),
    )
    assert m.is_model_available() is False


# ---------- wait_for_server ----------


def test_wait_for_server_returns_true(monkeypatch):
    m = ollama_process.OllamaProcessManager(startup_timeout=2)
    monkeypatch.setattr(m, "is_server_available", lambda: True)
    monkeypatch.setattr(ollama_process.time, "sleep", lambda s: None)
    assert m.wait_for_server(timeout=1) is True


def test_wait_for_server_timeout(monkeypatch):
    m = ollama_process.OllamaProcessManager(startup_timeout=2)
    monkeypatch.setattr(m, "is_server_available", lambda: False)
    monkeypatch.setattr(ollama_process.time, "sleep", lambda s: None)
    # deadline = time.time() + timeout; цикл сразу выходит если time.time() уже >=
    patched_time = {"now": 0.0}

    class FakeTime:
        @staticmethod
        def time():
            return patched_time["now"]

        @staticmethod
        def sleep(s):
            patched_time["now"] += s

    monkeypatch.setattr(ollama_process, "time", FakeTime)
    assert m.wait_for_server(timeout=1) is False


def test_wait_for_server_uses_default_timeout(monkeypatch):
    m = ollama_process.OllamaProcessManager(startup_timeout=3)
    monkeypatch.setattr(m, "is_server_available", lambda: False)

    state = {"now": 0.0}

    class FakeTime:
        @staticmethod
        def time():
            return state["now"]

        @staticmethod
        def sleep(s):
            state["now"] += s

    monkeypatch.setattr(ollama_process, "time", FakeTime)
    assert m.wait_for_server() is False
    # было 6 проверок (deadline 3, шаг 0.5): 3/0.5 = 6 сбоев + финальный
    assert state["now"] >= 3.0


# ---------- ensure_running ----------


def test_start_skips_when_server_is_already_available(monkeypatch):
    manager = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    monkeypatch.setattr(manager, "is_server_available", lambda: True)

    started = []

    def fake_popen(*args, **kwargs):
        started.append((args, kwargs))
        return DummyProc()

    monkeypatch.setattr(ollama_process.subprocess, "Popen", fake_popen)

    assert manager.ensure_running() is None
    assert started == []


def test_start_launches_server_and_pulls_model(monkeypatch):
    manager = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    monkeypatch.setattr(manager, "is_server_available", lambda: False)
    monkeypatch.setattr(manager, "wait_for_server", lambda timeout=30: None)
    monkeypatch.setattr(manager, "is_model_available", lambda: False)

    calls = []
    proc = DummyProc()

    def fake_popen(*args, **kwargs):
        calls.append(("popen", args, kwargs))
        return proc

    def fake_run(cmd, **kwargs):
        calls.append(("run", cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ollama_process.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ollama_process.subprocess, "run", fake_run)

    assert manager.ensure_running() is proc
    assert calls[0][0] == "popen"
    assert calls[1][0] == "run"
    assert calls[1][1][0] == "ollama"
    assert calls[1][1][1] == "pull"


def test_stop_terminates_running_process():
    manager = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    proc = DummyProc()
    manager._proc = proc

    manager.stop()

    assert proc.terminated is True


def test_ensure_running_returns_existing_proc(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    proc = DummyProc(poll_result=None)
    m._proc = proc
    assert m.ensure_running() is proc


def test_ensure_running_no_cli(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    monkeypatch.setattr(m, "is_server_available", lambda: False)
    monkeypatch.setattr(ollama_process.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Ollama CLI not found"):
        m.ensure_running()


def test_ensure_running_timeout_stops(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    monkeypatch.setattr(m, "is_server_available", lambda: False)
    monkeypatch.setattr(ollama_process.shutil, "which", lambda name: "/usr/bin/ollama")
    stopped = []

    def fake_wait(timeout=None):
        return False

    monkeypatch.setattr(m, "wait_for_server", fake_wait)
    monkeypatch.setattr(m, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(
        ollama_process.subprocess,
        "Popen",
        lambda *a, **k: DummyProc(poll_result=None),
    )

    with pytest.raises(RuntimeError, match="did not start in time"):
        m.ensure_running()
    assert stopped == [True]


# ---------- реестр запущенных + stop_all ----------


def test_ensure_running_tracks_when_spawned(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    monkeypatch.setattr(m, "is_server_available", lambda: False)
    monkeypatch.setattr(m, "wait_for_server", lambda timeout=30: None)
    monkeypatch.setattr(m, "is_model_available", lambda: True)
    monkeypatch.setattr(
        ollama_process.subprocess,
        "Popen",
        lambda *a, **k: DummyProc(poll_result=None),
    )
    m.ensure_running()
    assert m in ollama_process._SPAWNED


def test_ensure_running_not_tracked_when_server_available(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    monkeypatch.setattr(m, "is_server_available", lambda: True)
    monkeypatch.setattr(ollama_process.subprocess, "Popen", lambda *a, **k: DummyProc())
    m.ensure_running()
    assert m not in ollama_process._SPAWNED


def test_stop_all_terminates_all_spawned():
    m1 = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    m2 = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    p1 = DummyProc(poll_result=None)
    p2 = DummyProc(poll_result=None)
    m1._proc = p1
    m2._proc = p2
    ollama_process._track(m1)
    ollama_process._track(m2)

    ollama_process.stop_all()

    assert p1.terminated is True
    assert p2.terminated is True
    assert ollama_process._SPAWNED == []


def test_stop_all_is_idempotent():
    m = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    p = DummyProc(poll_result=None)
    m._proc = p
    ollama_process._track(m)

    ollama_process.stop_all()
    ollama_process.stop_all()

    assert p.terminated is True
    assert ollama_process._SPAWNED == []


def test_ensure_running_avoids_pull_if_model_exists(monkeypatch):
    m = ollama_process.OllamaProcessManager(model="qwen2.5:7b")
    calls = []

    def fake_available():
        return False

    def fake_wait(timeout=None):
        return True

    def fake_model_available():
        return True

    monkeypatch.setattr(m, "is_server_available", fake_available)
    monkeypatch.setattr(m, "wait_for_server", fake_wait)
    monkeypatch.setattr(m, "is_model_available", fake_model_available)
    monkeypatch.setattr(
        ollama_process.subprocess,
        "Popen",
        lambda *a, **k: (calls.append(("popen", a)), DummyProc())[1],
    )

    def fake_run(cmd, **kwargs):
        calls.append(("run", cmd))
        return _Result(0)

    monkeypatch.setattr(ollama_process.subprocess, "run", fake_run)
    assert m.ensure_running() is not None
    assert [c[0] for c in calls] == ["popen"]


# ---------- stop ----------


def test_stop_no_proc_noop():
    m = ollama_process.OllamaProcessManager()
    m.stop()
    assert m._proc is None


def test_stop_skips_finished_proc():
    m = ollama_process.OllamaProcessManager()
    proc = DummyProc(poll_result=0)
    m._proc = proc
    m.stop()
    assert not proc.terminated


def test_stop_terminate_fails_then_kill(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    proc = DummyProc(poll_result=None)

    def boom_terminate():
        raise OSError("no such proc")

    proc.terminate = boom_terminate
    monkeypatch.setattr(proc, "kill", lambda: setattr(proc, "killed", True))
    m._proc = proc
    m.stop()
    assert proc.killed is True


def test_stop_kill_also_fails(monkeypatch):
    m = ollama_process.OllamaProcessManager()
    proc = DummyProc(poll_result=None)

    def boom_terminate():
        raise OSError("no such proc")

    def boom_kill():
        raise OSError("no such proc")

    proc.terminate = boom_terminate
    proc.kill = boom_kill
    m._proc = proc
    m.stop()  # не должно падать


# ---------- ensure_ollama_running ----------


def test_ensure_ollama_running_returns_manager(monkeypatch):
    started = []

    def fake_ensure(self):
        started.append(self.model)

    monkeypatch.setattr(ollama_process.OllamaProcessManager, "ensure_running", fake_ensure)
    m = ollama_process.ensure_ollama_running(model="phi3:mini")
    assert isinstance(m, ollama_process.OllamaProcessManager)
    assert started == ["phi3:mini"]
    assert m._proc is None


def test_default_model_is_qwen():
    m = ollama_process.OllamaProcessManager()
    assert m.model == "qwen2.5:7b"
    assert m.host == "http://127.0.0.1:11434"
    assert m.startup_timeout == 30

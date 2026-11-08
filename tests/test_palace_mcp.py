"""Unit tests for services.palace_mcp.

Covers PalaceMCPClient lifecycle: start/handshake, send/notify, reader loop,
RPC (seq, timeout, cleanup), call_tool, stop, and the get_mcp singleton.
"""

import asyncio
import json
import logging

import pytest

from config import DATA_DIR
from services.palace_mcp import PalaceMCPClient, get_mcp, reset_mcp


class FakeStdin:
    def __init__(self):
        self.writes = []

    def write(self, data: bytes):
        self.writes.append(data)

    async def drain(self):
        return None


class FakeProc:
    def __init__(self, stdout=None, stderr=None, returncode=None):
        self.stdin = FakeStdin()
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.waited = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    async def wait(self):
        self.waited = True
        return 0


@pytest.mark.asyncio
async def test_start_creates_process_and_handshake(monkeypatch):
    client = PalaceMCPClient()
    proc = FakeProc()
    calls = {}

    async def fake_exec(*args, **kwargs):
        calls["args"] = args
        calls["env"] = kwargs.get("env", {})
        return proc

    async def fake_rpc(method, params=None, timeout=30.0):
        return {"result": {"protocolVersion": "2024-11-05"}}

    async def fake_notify(method):
        calls["notify"] = method

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_notify", fake_notify)
    await client.start()
    assert client._proc is proc
    assert calls["args"][1] == "-m"
    assert calls["args"][2] == "mempalace.mcp_server"
    assert calls["env"]["VIRTUAL_ENV"].endswith("venv")
    assert calls["env"]["PYTHONPATH"].startswith(DATA_DIR)
    assert calls["notify"] == "notifications/initialized"
    assert client._ready.is_set()
    await client.stop()


@pytest.mark.asyncio
async def test_start_skips_if_already_running(monkeypatch):
    client = PalaceMCPClient()
    client._proc = object()
    called = []

    async def boom(*args, **kwargs):
        called.append(True)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)
    await client.start()
    assert called == []
    client._proc = None


@pytest.mark.asyncio
async def test_start_handshake_failure(monkeypatch):
    client = PalaceMCPClient()
    proc = FakeProc(
        stdout=asyncio.StreamReader(),
        stderr=asyncio.StreamReader(),
    )

    async def fake_exec(*args, **kwargs):
        return proc

    async def fake_rpc(method, params=None, timeout=30.0):
        return {"error": {"code": -32601}}

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client, "_rpc", fake_rpc)
    with pytest.raises(RuntimeError, match="MCP handshake failed"):
        await client.start()
    assert proc.terminated
    assert proc.waited
    assert client._proc is None
    assert client._reader_task is None
    assert client._stderr_task is None
    assert not client._ready.is_set()
    assert client._pending == {}


@pytest.mark.asyncio
async def test_start_handshake_timeout_cleans_up(monkeypatch):
    client = PalaceMCPClient()
    proc = FakeProc(
        stdout=asyncio.StreamReader(),
        stderr=asyncio.StreamReader(),
    )

    async def fake_exec(*args, **kwargs):
        return proc

    async def fake_rpc(method, params=None, timeout=30.0):
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client, "_rpc", fake_rpc)
    with pytest.raises(RuntimeError, match="handshake timed out"):
        await client.start()
    assert proc.terminated
    assert proc.waited
    assert client._proc is None
    assert client._reader_task is None
    assert client._stderr_task is None
    assert not client._ready.is_set()


@pytest.mark.asyncio
async def test_start_can_restart_after_handshake_failure(monkeypatch):
    client = PalaceMCPClient()
    created = []
    rpc_calls = 0

    async def fake_exec(*args, **kwargs):
        proc = FakeProc()
        created.append(proc)
        return proc

    async def fake_rpc(method, params=None, timeout=30.0):
        nonlocal rpc_calls
        rpc_calls += 1
        if rpc_calls == 1:
            return {"error": {"code": -32601}}
        return {"result": {"protocolVersion": "2024-11-05"}}

    async def fake_notify(method):
        return None

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_notify", fake_notify)
    with pytest.raises(RuntimeError, match="MCP handshake failed"):
        await client.start()
    assert client._proc is None

    await client.start()
    assert len(created) == 2
    assert client._proc is created[1]
    assert client._ready.is_set()
    await client.stop()


@pytest.mark.asyncio
async def test_start_replaces_dead_process(monkeypatch):
    client = PalaceMCPClient()
    old_proc = FakeProc(returncode=1)
    new_proc = FakeProc()
    client._proc = old_proc

    async def fake_exec(*args, **kwargs):
        return new_proc

    async def fake_rpc(method, params=None, timeout=30.0):
        return {"result": {"protocolVersion": "2024-11-05"}}

    async def fake_notify(method):
        return None

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_notify", fake_notify)
    await client.start()
    assert old_proc.terminated
    assert old_proc.waited
    assert client._proc is new_proc
    assert client._ready.is_set()
    await client.stop()


@pytest.mark.asyncio
async def test_start_drains_noisy_stderr(monkeypatch, caplog):
    client = PalaceMCPClient()
    stderr = asyncio.StreamReader()
    stderr.feed_data(b"warning one\nwarning two\n")
    stderr.feed_eof()
    proc = FakeProc(stderr=stderr)

    async def fake_exec(*args, **kwargs):
        return proc

    async def fake_rpc(method, params=None, timeout=30.0):
        return {"result": {"protocolVersion": "2024-11-05"}}

    async def fake_notify(method):
        return None

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_notify", fake_notify)
    caplog.set_level(logging.WARNING, logger="PalaceMCP")
    await client.start()
    assert client._stderr_task is not None
    await asyncio.wait_for(client._stderr_task, timeout=1.0)
    assert "warning one" in caplog.text
    assert "warning two" in caplog.text
    await client.stop()


@pytest.mark.asyncio
async def test_start_silent_stderr_does_not_block(monkeypatch):
    client = PalaceMCPClient()
    stderr = asyncio.StreamReader()
    stderr.feed_eof()
    proc = FakeProc(stderr=stderr)

    async def fake_exec(*args, **kwargs):
        return proc

    async def fake_rpc(method, params=None, timeout=30.0):
        return {"result": {"protocolVersion": "2024-11-05"}}

    async def fake_notify(method):
        return None

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_notify", fake_notify)
    await client.start()
    assert client._stderr_task is not None
    await asyncio.wait_for(client._stderr_task, timeout=1.0)
    await client.stop()


@pytest.mark.asyncio
async def test_read_stderr_without_pipe_returns():
    client = PalaceMCPClient()
    client._proc = FakeProc()
    await client._read_stderr()


@pytest.mark.asyncio
async def test_read_stderr_handles_text_and_read_error(caplog):
    class TextThenError:
        def __init__(self):
            self.calls = 0

        async def readline(self):
            self.calls += 1
            if self.calls == 1:
                return "plain text\n"
            raise OSError("stderr dead")

    client = PalaceMCPClient()
    client._proc = FakeProc(stderr=TextThenError())
    caplog.set_level(logging.WARNING, logger="PalaceMCP")
    await client._read_stderr()
    assert "plain text" in caplog.text
    assert "stderr reader error" in caplog.text


@pytest.mark.asyncio
async def test_send_not_running_raises():
    client = PalaceMCPClient()
    with pytest.raises(RuntimeError, match="not running"):
        await client._send({"jsonrpc": "2.0", "id": 1})


@pytest.mark.asyncio
async def test_send_writes_json_line():
    client = PalaceMCPClient()
    proc = FakeProc()
    client._proc = proc
    await client._send({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert proc.stdin.writes == [b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}\n']


@pytest.mark.asyncio
async def test_notify_sends_method_only():
    client = PalaceMCPClient()
    proc = FakeProc()
    client._proc = proc
    await client._notify("notifications/initialized")
    assert proc.stdin.writes == [b'{"jsonrpc": "2.0", "method": "notifications/initialized"}\n']


def test_reader_sets_result_on_pending():
    client = PalaceMCPClient()

    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"jsonrpc":"2.0","id":7,"result":{}}\n')
        reader.feed_eof()
        client._proc = FakeProc(stdout=reader)
        fut = asyncio.get_event_loop().create_future()
        client._pending[7] = fut
        task = asyncio.create_task(client._reader())
        await fut
        task.cancel()
        return fut.result()

    assert asyncio.run(run()) == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_reader_handles_large_payload_exceeding_default_64kb():
    client = PalaceMCPClient()

    async def run():
        # Payload well over 64 KB (150 KB) to ensure chunk limit overrun is avoided
        large_text = "x" * (150 * 1024)
        raw = json.dumps({"jsonrpc": "2.0", "id": 42, "result": {"data": large_text}})
        reader = asyncio.StreamReader(limit=client._BUFFER_LIMIT)
        reader.feed_data(raw.encode() + b"\n")
        reader.feed_eof()
        client._proc = FakeProc(stdout=reader)
        fut = asyncio.get_event_loop().create_future()
        client._pending[42] = fut
        await client._reader()
        assert fut.done()
        assert len(fut.result()["result"]["data"]) == 150 * 1024
        return True

    assert asyncio.run(run())


def test_reader_ignores_invalid_json():
    client = PalaceMCPClient()

    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(b"not json\n")
        reader.feed_data(b'{"jsonrpc":"2.0","id":3,"result":{"ok":1}}\n')
        reader.feed_eof()
        client._proc = FakeProc(stdout=reader)
        fut = asyncio.get_event_loop().create_future()
        client._pending[3] = fut
        await client._reader()
        assert fut.done()
        assert fut.result() == {"jsonrpc": "2.0", "id": 3, "result": {"ok": 1}}
        return True

    assert asyncio.run(run())


def test_reader_ignores_response_without_pending():
    client = PalaceMCPClient()

    async def run():
        reader = asyncio.StreamReader()
        reader.feed_data(b'{"jsonrpc":"2.0","id":99,"result":{}}\n')
        reader.feed_data(b'{"jsonrpc":"2.0","result":{}}\n')
        reader.feed_eof()
        client._proc = FakeProc(stdout=reader)
        await client._reader()
        assert client._pending == {}
        return True

    assert asyncio.run(run())


def test_reader_swallows_readline_exception(caplog):
    client = PalaceMCPClient()

    async def run():
        class BoomStdout:
            async def readline(self):
                raise OSError("stream dead")

        client._proc = FakeProc(stdout=BoomStdout())
        fut = asyncio.get_event_loop().create_future()
        client._pending[5] = fut
        await client._reader()
        assert fut.done()
        with pytest.raises(RuntimeError, match="connection lost"):
            fut.result()
        return True

    assert asyncio.run(run())


def test_reader_connection_lost_fails_pending():
    client = PalaceMCPClient()

    async def run():
        reader = asyncio.StreamReader()
        reader.feed_eof()
        client._proc = FakeProc(stdout=reader)
        fut = asyncio.get_event_loop().create_future()
        client._pending[1] = fut
        await client._reader()
        assert fut.done()
        with pytest.raises(RuntimeError, match="connection lost"):
            fut.result()
        assert client._pending == {}
        assert not client._ready.is_set()
        return True

    assert asyncio.run(run())


@pytest.mark.asyncio
async def test_rpc_sends_sequence_and_returns(monkeypatch):
    client = PalaceMCPClient()
    sent = []

    async def fake_send(msg):
        sent.append(msg)

    async def resolve():
        await asyncio.sleep(0.02)
        if sent:
            fut = client._pending[sent[-1]["id"]]
            if not fut.done():
                fut.set_result({"jsonrpc": "2.0", "id": sent[-1]["id"], "result": {}})

    monkeypatch.setattr(client, "_send", fake_send)
    task = asyncio.create_task(resolve())
    resp = await client._rpc("tools/call", {"name": "x"}, timeout=2.0)
    await task
    assert resp == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert client._seq == 1
    assert client._pending == {}
    assert sent[0]["id"] == 1
    assert sent[0]["params"] == {"name": "x"}


@pytest.mark.asyncio
async def test_rpc_timeout_raises_and_cleans_up(monkeypatch):
    client = PalaceMCPClient()
    sent = []

    async def fake_send(msg):
        sent.append(msg)

    monkeypatch.setattr(client, "_send", fake_send)
    with pytest.raises(asyncio.TimeoutError):
        await client._rpc("slow", timeout=0.01)
    assert client._pending == {}


@pytest.mark.asyncio
async def test_ensure_alive_ok_when_proc_running(monkeypatch):
    client = PalaceMCPClient()
    client._proc = FakeProc(returncode=None)
    client._ready.set()
    stopped = []

    async def fake_stop():
        stopped.append(True)

    async def fake_start():
        stopped.append("start")

    monkeypatch.setattr(client, "stop", fake_stop)
    monkeypatch.setattr(client, "start", fake_start)
    await client._ensure_alive()
    assert stopped == []


@pytest.mark.asyncio
async def test_ensure_alive_restarts_dead_proc(monkeypatch):
    client = PalaceMCPClient()
    client._proc = FakeProc(returncode=1)
    order = []

    async def fake_stop():
        order.append("stop")

    async def fake_start():
        order.append("start")

    monkeypatch.setattr(client, "stop", fake_stop)
    monkeypatch.setattr(client, "start", fake_start)
    await client._ensure_alive()
    assert order == ["stop", "start"]


@pytest.mark.asyncio
async def test_ensure_alive_waits_for_ready(monkeypatch):
    client = PalaceMCPClient()
    client._proc = FakeProc(returncode=None)
    client._ready.clear()

    async def set_ready():
        await asyncio.sleep(0.05)
        client._ready.set()

    task = asyncio.create_task(set_ready())
    await client._ensure_alive()
    await task


@pytest.mark.asyncio
async def test_ensure_alive_ready_timeout_cleans_up():
    client = PalaceMCPClient()
    proc = FakeProc(returncode=None)
    client._proc = proc
    client._ready.clear()
    client._READY_TIMEOUT = 0.01
    with pytest.raises(RuntimeError, match="did not become ready"):
        await client._ensure_alive()
    assert proc.terminated
    assert proc.waited
    assert client._proc is None
    assert not client._ready.is_set()


@pytest.mark.asyncio
async def test_call_tool_success(monkeypatch):
    client = PalaceMCPClient()
    rpc_calls = []

    async def fake_rpc(method, params=None, timeout=30.0):
        rpc_calls.append((method, params))
        return {
            "result": {
                "content": [
                    {"type": "text", "text": "первая строка"},
                    {"type": "text", "text": "вторая строка"},
                    {"type": "image", "text": "не текст"},
                ],
            },
        }

    async def fake_alive():
        return None

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_ensure_alive", fake_alive)
    out = await client.call_tool("search", {"q": "наполеон"})
    assert out == "первая строка\nвторая строка"
    assert rpc_calls[0][0] == "tools/call"
    assert rpc_calls[0][1] == {"name": "search", "arguments": {"q": "наполеон"}}


@pytest.mark.asyncio
async def test_call_tool_without_arguments(monkeypatch):
    client = PalaceMCPClient()

    async def fake_rpc(method, params=None, timeout=30.0):
        assert params == {"name": "health", "arguments": {}}
        return {"result": {"content": []}}

    async def fake_alive():
        return None

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_ensure_alive", fake_alive)
    assert await client.call_tool("health") == ""


@pytest.mark.asyncio
async def test_call_tool_error_raises(monkeypatch):
    client = PalaceMCPClient()

    async def fake_rpc(method, params=None, timeout=30.0):
        return {"error": {"code": -32602, "message": "bad args"}}

    async def fake_alive():
        return None

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "_ensure_alive", fake_alive)
    with pytest.raises(RuntimeError, match="MCP error"):
        await client.call_tool("search")


@pytest.mark.asyncio
async def test_stop_terminates_and_cancels_tasks(monkeypatch):
    client = PalaceMCPClient()
    proc = FakeProc()

    async def fake_wait():
        proc.waited = True
        return 0

    monkeypatch.setattr(proc, "wait", fake_wait)
    client._proc = proc
    reader_task = asyncio.create_task(asyncio.sleep(60))
    stderr_task = asyncio.create_task(asyncio.sleep(60))
    client._reader_task = reader_task
    client._stderr_task = stderr_task
    client._ready.set()
    await client.stop()
    await asyncio.sleep(0)
    assert proc.terminated
    assert proc.waited
    assert client._proc is None
    assert client._reader_task is None
    assert client._stderr_task is None
    assert not client._ready.is_set()
    assert reader_task.cancelled()
    assert stderr_task.cancelled()


@pytest.mark.asyncio
async def test_stop_kills_process_if_terminate_times_out():
    class HangingProc(FakeProc):
        def __init__(self):
            super().__init__()
            self.kill_event = asyncio.Event()

        def kill(self):
            self.killed = True
            self.kill_event.set()

        async def wait(self):
            self.waited = True
            if not self.killed:
                await self.kill_event.wait()
            return 0

    client = PalaceMCPClient()
    client._STOP_TIMEOUT = 0.01
    proc = HangingProc()
    client._proc = proc
    await client.stop()
    assert proc.terminated
    assert proc.killed
    assert proc.waited
    assert client._proc is None


@pytest.mark.asyncio
async def test_stop_fails_pending_futures():
    client = PalaceMCPClient()
    fut = asyncio.get_event_loop().create_future()
    client._pending[1] = fut
    await client.stop()
    assert fut.done()
    with pytest.raises(RuntimeError, match="connection lost"):
        fut.result()


@pytest.mark.asyncio
async def test_stop_no_proc_is_noop():
    client = PalaceMCPClient()
    await client.stop()
    assert client._proc is None


@pytest.mark.asyncio
async def test_stop_swallows_wait_exception(monkeypatch):
    client = PalaceMCPClient()
    proc = FakeProc()

    async def boom_wait():
        raise OSError("wait failed")

    monkeypatch.setattr(proc, "wait", boom_wait)
    client._proc = proc
    await client.stop()
    assert proc.terminated
    assert client._proc is None


@pytest.mark.asyncio
async def test_reader_cancellation_is_propagated():
    class BlockingStdout:
        async def readline(self):
            await asyncio.Event().wait()

    client = PalaceMCPClient()
    client._proc = FakeProc(stdout=BlockingStdout())
    client._ready.set()
    task = asyncio.create_task(client._reader())
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not client._ready.is_set()


@pytest.mark.asyncio
async def test_stderr_reader_cancellation_is_propagated():
    class BlockingStderr:
        async def readline(self):
            await asyncio.Event().wait()

    client = PalaceMCPClient()
    client._proc = FakeProc(stderr=BlockingStderr())
    task = asyncio.create_task(client._read_stderr())
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_reader_without_process_fails_pending():
    client = PalaceMCPClient()
    fut = asyncio.get_event_loop().create_future()
    client._pending[1] = fut
    client._ready.set()

    await client._reader()

    assert fut.done()
    with pytest.raises(RuntimeError, match="connection lost"):
        fut.result()
    assert not client._ready.is_set()


@pytest.mark.asyncio
async def test_read_stderr_skips_blank_lines():
    class BlankThenEOF:
        def __init__(self):
            self.calls = 0

        async def readline(self):
            self.calls += 1
            if self.calls == 1:
                return "\n"
            return b""

    stream = BlankThenEOF()
    client = PalaceMCPClient()
    client._proc = FakeProc(stderr=stream)

    await client._read_stderr()

    assert stream.calls == 2


@pytest.mark.asyncio
async def test_stop_returns_when_terminate_process_is_gone():
    class GoneProc(FakeProc):
        def terminate(self):
            raise ProcessLookupError

    proc = GoneProc()
    client = PalaceMCPClient()
    client._proc = proc

    await client.stop()

    assert not proc.killed
    assert not proc.waited


@pytest.mark.asyncio
async def test_stop_logs_unexpected_terminate_error(caplog):
    class BrokenTerminateProc(FakeProc):
        def terminate(self):
            raise OSError("terminate failed")

    proc = BrokenTerminateProc()
    client = PalaceMCPClient()
    client._proc = proc
    caplog.set_level(logging.WARNING, logger="PalaceMCP")

    await client.stop()

    assert proc.waited
    assert "Не удалось завершить MCP-процесс" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ProcessLookupError, AttributeError, OSError])
async def test_stop_handles_kill_errors(caplog, error):
    class KillErrorProc(FakeProc):
        def __init__(self):
            super().__init__()
            self.wait_calls = 0

        async def wait(self):
            self.wait_calls += 1
            if self.wait_calls == 1:
                await asyncio.sleep(60)
            return 0

        def kill(self):
            raise error("kill failed")

    proc = KillErrorProc()
    client = PalaceMCPClient()
    client._STOP_TIMEOUT = 0.01
    client._proc = proc
    caplog.set_level(logging.WARNING, logger="PalaceMCP")

    await client.stop()

    assert proc.terminated
    assert proc.wait_calls == 1
    if error is OSError:
        assert "Не удалось убить MCP-процесс" in caplog.text
    else:
        assert "Не удалось убить MCP-процесс" not in caplog.text


@pytest.mark.asyncio
async def test_stop_logs_final_wait_error(caplog):
    class FinalWaitErrorProc(FakeProc):
        def __init__(self):
            super().__init__()
            self.wait_calls = 0

        async def wait(self):
            self.wait_calls += 1
            if self.wait_calls == 1:
                await asyncio.sleep(60)
            raise OSError("final wait failed")

        def kill(self):
            self.killed = True

    proc = FinalWaitErrorProc()
    client = PalaceMCPClient()
    client._STOP_TIMEOUT = 0.01
    client._proc = proc
    caplog.set_level(logging.WARNING, logger="PalaceMCP")

    await client.stop()

    assert proc.killed
    assert proc.wait_calls == 2
    assert "не подтвердил завершение" in caplog.text


@pytest.mark.asyncio
async def test_get_mcp_singleton_and_reset():
    reset_mcp()
    a = get_mcp()
    b = get_mcp()
    assert a is b
    assert isinstance(a, PalaceMCPClient)
    reset_mcp()
    c = get_mcp()
    assert c is not a


def test_client_initial_state():
    client = PalaceMCPClient()
    assert client._proc is None
    assert client._seq == 0
    assert client._pending == {}
    assert not client._ready.is_set()
    assert client._reader_task is None
    assert client._stderr_task is None

import asyncio
import json
import logging
import os
import sys

from config import DATA_DIR

logger = logging.getLogger("PalaceMCP")


class PalaceMCPClient:
    _HANDSHAKE_TIMEOUT = 30.0
    _READY_TIMEOUT = 10.0
    _STOP_TIMEOUT = 5.0
    _BUFFER_LIMIT = 32 * 1024 * 1024  # 32 MiB buffer for large JSON-RPC lines

    def __init__(self):
        self._proc = None
        self._seq = 0
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._pending = {}
        self._reader_task = None
        self._stderr_task = None

    async def start(self):
        if self._proc is not None:
            if getattr(self._proc, "returncode", None) is None:
                return
            await self.stop()
        venv_dir = os.path.join(DATA_DIR, "venv")
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = venv_dir
        env["PATH"] = os.path.join(venv_dir, "bin") + os.pathsep + env.get("PATH", "")
        env["PYTHONPATH"] = DATA_DIR + os.pathsep + env.get("PYTHONPATH", "")

        self._proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "mempalace.mcp_server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self._BUFFER_LIMIT,
            env=env,
        )

        # stderr нельзя оставлять непрочитанным: при переполнении pipe
        # сервер блокируется на записи и handshake зависает.
        if getattr(self._proc, "stdout", None) is not None:
            self._reader_task = asyncio.create_task(self._reader())
        if getattr(self._proc, "stderr", None) is not None:
            self._stderr_task = asyncio.create_task(self._read_stderr())

        try:
            init_resp = await self._rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mempalace-bot", "version": "1.0"},
                },
                timeout=self._HANDSHAKE_TIMEOUT,
            )
            if "result" not in init_resp:
                raise RuntimeError(f"MCP handshake failed: {init_resp}")

            await asyncio.wait_for(
                self._notify("notifications/initialized"),
                timeout=self._HANDSHAKE_TIMEOUT,
            )
        except asyncio.TimeoutError as exc:
            await self.stop()
            raise RuntimeError(
                f"MCP handshake timed out after {self._HANDSHAKE_TIMEOUT:g}s",
            ) from exc
        except BaseException:
            await self.stop()
            raise

        self._ready.set()
        logger.info("MCP client ready")

    async def _send(self, msg: dict):
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("MCP server not running")
        data = (json.dumps(msg) + "\n").encode()
        self._proc.stdin.write(data)
        await self._proc.stdin.drain()

    async def _notify(self, method: str):
        await self._send({"jsonrpc": "2.0", "method": method})

    async def _reader(self):
        try:
            while self._proc and self._proc.stdout:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                try:
                    resp = json.loads(line)
                    req_id = resp.get("id")
                    if req_id is not None and req_id in self._pending:
                        self._pending[req_id].set_result(resp)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid MCP JSON: {line[:200]}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"MCP reader error: {e}")
        finally:
            self._ready.clear()
            self._fail_pending("MCP connection lost")

    async def _read_stderr(self):
        """Постоянно вычитывает stderr, чтобы не переполнить pipe."""
        proc = self._proc
        stderr = getattr(proc, "stderr", None)
        if stderr is None:
            return
        try:
            while True:
                line = await stderr.readline()
                if not line:
                    break
                if isinstance(line, bytes):
                    text = line.decode("utf-8", errors="replace")
                else:
                    text = str(line)
                text = text.rstrip()
                if text:
                    logger.warning("MCP stderr: %s", text[:500])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"MCP stderr reader error: {e}")

    def _fail_pending(self, message: str):
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(RuntimeError(message))
        self._pending.clear()

    async def _rpc(
        self, method: str, params: dict | None = None, timeout: float = 30.0,
    ) -> dict:
        async with self._lock:
            self._seq += 1
            seq = self._seq
            msg = {"jsonrpc": "2.0", "id": seq, "method": method}
            if params is not None:
                msg["params"] = params
            future = asyncio.get_event_loop().create_future()
            self._pending[seq] = future
            await self._send(msg)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            async with self._lock:
                self._pending.pop(seq, None)

    async def _ensure_alive(self):
        if self._proc is None or getattr(self._proc, "returncode", None) is not None:
            logger.warning("MCP process dead, restarting...")
            await self.stop()
            await self.start()
            return
        if not self._ready.is_set():
            try:
                await asyncio.wait_for(
                    self._ready.wait(), timeout=self._READY_TIMEOUT,
                )
            except asyncio.TimeoutError as exc:
                await self.stop()
                raise RuntimeError(
                    "MCP server did not become ready within "
                    f"{self._READY_TIMEOUT:g}s",
                ) from exc

    async def call_tool(self, name: str, arguments: dict | None = None) -> str:
        await self._ensure_alive()
        resp = await self._rpc(
            "tools/call", {"name": name, "arguments": arguments or {}},
        )
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        content = resp.get("result", {}).get("content", [])
        texts = [c["text"] for c in content if c.get("type") == "text"]
        return "\n".join(texts)

    async def _terminate(self, proc):
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        except Exception as e:
            logger.warning(f"Не удалось завершить MCP-процесс: {e}")

        try:
            await asyncio.wait_for(proc.wait(), timeout=self._STOP_TIMEOUT)
            return
        except asyncio.TimeoutError:
            logger.warning(
                "MCP-процесс не завершился за %.1fs, отправляю kill",
                self._STOP_TIMEOUT,
            )
        except Exception as e:
            logger.warning(f"Ошибка ожидания MCP-процесса: {e}")
            return

        try:
            proc.kill()
        except ProcessLookupError:
            return
        except AttributeError:
            return
        except Exception as e:
            logger.warning(f"Не удалось убить MCP-процесс: {e}")
            return

        try:
            await asyncio.wait_for(proc.wait(), timeout=self._STOP_TIMEOUT)
        except Exception as e:
            logger.warning(f"MCP-процесс не подтвердил завершение: {e}")

    async def stop(self):
        proc = self._proc
        self._proc = None
        self._ready.clear()

        if proc is not None:
            await self._terminate(proc)

        tasks = [
            task for task in (self._reader_task, self._stderr_task)
            if task is not None
        ]
        self._reader_task = None
        self._stderr_task = None
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._fail_pending("MCP connection lost")
        logger.info("MCP client stopped")


# Singleton
_mcp_client = None


def get_mcp() -> PalaceMCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = PalaceMCPClient()
    return _mcp_client


def reset_mcp():
    global _mcp_client
    _mcp_client = None

import asyncio
import json
import logging
import os
import sys

from config import DATA_DIR

logger = logging.getLogger("PalaceMCP")


class PalaceMCPClient:
    def __init__(self):
        self._proc = None
        self._seq = 0
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._pending = {}
        self._reader_task = None

    async def start(self):
        if self._proc:
            return
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
            env=env,
        )

        self._reader_task = asyncio.create_task(self._reader())

        init_resp = await self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mempalace-bot", "version": "1.0"},
            },
        )
        if "result" not in init_resp:
            raise RuntimeError(f"MCP handshake failed: {init_resp}")

        await self._notify("notifications/initialized")
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
        except Exception as e:
            logger.error(f"MCP reader error: {e}")
        finally:
            self._ready.clear()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("MCP connection lost"))
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
        if self._proc is None or self._proc.returncode is not None:
            logger.warning("MCP process dead, restarting...")
            await self.stop()
            await self.start()
            return
        if not self._ready.is_set():
            await self._ready.wait()

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

    async def stop(self):
        if self._proc:
            try:
                self._proc.terminate()
                await self._proc.wait()
            except Exception:
                pass
            self._proc = None
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        self._ready.clear()
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

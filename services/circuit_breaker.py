"""
circuit_breaker.py
Защита от каскадных отказов при обращениях к внешним сервисам.
Поддерживает MCP-сервер и subprocess-вызовы palace.
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Awaitable, Any

logger = logging.getLogger("CircuitBreaker")

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_retries = half_open_max_retries

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0

    async def call(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s"
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)"
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)"
                )
                self.state = CircuitState.OPEN

            raise

    def reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

class CircuitBreakerOpenError(Exception):
    pass

# Глобальные экземпляры для MCP и palace-команд
_mcp_cb: CircuitBreaker | None = None
_palace_cb: CircuitBreaker | None = None

def get_mcp_circuit_breaker() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb

def get_palace_circuit_breaker() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker("Palace", failure_threshold=2, recovery_timeout=60.0)
    return _palace_cb

import time

import pytest

from services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


async def _success():
    return "ok"


async def _failure():
    raise ValueError("fail")


class TestCircuitBreaker:
    async def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    async def test_successful_call_returns_result(self):
        cb = CircuitBreaker("test")
        result = await cb.call(_success)
        assert result == "ok"

    async def test_open_after_failures(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.CLOSED
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN

    async def test_open_raises_immediately(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(_success)

    async def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        time.sleep(0.01)
        result = await cb.call(_success)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    async def test_half_open_failure_goes_open(self):
        cb = CircuitBreaker(
            "test", failure_threshold=1, recovery_timeout=0, half_open_max_retries=1,
        )
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        time.sleep(0.01)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN

    async def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        result = await cb.call(_success)
        assert result == "ok"

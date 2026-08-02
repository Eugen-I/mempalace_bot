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

    async def test_open_circuit_reaches_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.01)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        result = await cb.call(_success)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED
        assert cb.half_open_retries == 0

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


class TestCircuitBreakerMutants:
    async def test_defaults(self):
        cb = CircuitBreaker("test")
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 30.0
        assert cb.half_open_max_retries == 2
        assert cb.last_failure_time == 0.0
        assert cb.half_open_retries == 0

    async def test_open_error_message_exact(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=1)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await cb.call(_success)
        assert "Circuit 'test' is OPEN. Retry in 1s" in str(exc_info.value)

    async def test_open_to_half_open_logs_exact_message(self, caplog):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        time.sleep(0.01)
        with caplog.at_level("INFO", logger="CircuitBreaker"):
            caplog.clear()
            await cb.call(_success)
        assert caplog.records[0].getMessage() == "[test] OPEN → HALF_OPEN (timeout elapsed)"
        assert caplog.records[1].getMessage() == "[test] HALF_OPEN → CLOSED (success)"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    async def test_closed_to_open_warning_message(self, caplog):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)
        with caplog.at_level("WARNING", logger="CircuitBreaker"):
            with pytest.raises(ValueError):
                await cb.call(_failure)
            with pytest.raises(ValueError):
                await cb.call(_failure)
        assert caplog.records[-1].getMessage() == "[test] CLOSED → OPEN (2/2 failures)"

    async def test_half_open_to_open_warning_message(self, caplog):
        cb = CircuitBreaker(
            "test", failure_threshold=1, recovery_timeout=0, half_open_max_retries=1,
        )
        with pytest.raises(ValueError):
            await cb.call(_failure)
        time.sleep(0.01)
        with caplog.at_level("WARNING", logger="CircuitBreaker"):
            with pytest.raises(ValueError):
                await cb.call(_failure)
        assert caplog.records[-1].getMessage() == "[test] HALF_OPEN → OPEN (1/1 retries failed)"

    async def test_half_open_failure_stays_half_open_until_retries_exhausted(self):
        cb = CircuitBreaker(
            "test", failure_threshold=1, recovery_timeout=0, half_open_max_retries=2,
        )
        with pytest.raises(ValueError):
            await cb.call(_failure)
        time.sleep(0.01)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.half_open_retries == 1
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        assert cb.half_open_retries == 2

    async def test_args_and_kwargs_passed_to_fn(self):
        cb = CircuitBreaker("test")
        captured = {}

        async def spy(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return "ok"

        await cb.call(spy, 1, 2, key="val")
        assert captured == {"args": (1, 2), "kwargs": {"key": "val"}}

    async def test_reset_resets_half_open_retries(self):
        cb = CircuitBreaker(
            "test", failure_threshold=1, recovery_timeout=0, half_open_max_retries=5,
        )
        with pytest.raises(ValueError):
            await cb.call(_failure)
        time.sleep(0.01)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.half_open_retries == 1
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.half_open_retries == 0
        assert cb.last_failure_time == 0.0

    async def test_reset_logs_exact_message(self, caplog):
        cb = CircuitBreaker("test")
        with caplog.at_level("INFO", logger="CircuitBreaker"):
            cb.reset()
        assert caplog.records[-1].getMessage() == "[test] Reset to CLOSED"

    async def test_open_retry_in_message_exact(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60)
        with pytest.raises(ValueError):
            await cb.call(_failure)
        assert cb.state == CircuitState.OPEN
        cb.last_failure_time = time.time() - 10
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await cb.call(_success)
        assert "Retry in 50s" in str(exc_info.value)

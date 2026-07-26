"""circuit_breaker.py
Защита от каскадных отказов при обращениях к внешним сервисам.
Поддерживает MCP-сервер и subprocess-вызовы palace.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

logger = logging.getLogger("CircuitBreaker")


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
mutants_xǁCircuitBreakerǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁCircuitBreakerǁcall__mutmut: MutantDict = {}  # type: ignore
mutants_xǁCircuitBreakerǁreset__mutmut: MutantDict = {}  # type: ignore


class CircuitBreaker:
    @_mutmut_mutated(mutants_xǁCircuitBreakerǁ__init____mutmut)
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
    def xǁCircuitBreakerǁ__init____mutmut_orig(
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
    def xǁCircuitBreakerǁ__init____mutmut_1(
        self,
        name: str,
        failure_threshold: int = 4,
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
    def xǁCircuitBreakerǁ__init____mutmut_2(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 31.0,
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
    def xǁCircuitBreakerǁ__init____mutmut_3(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 3,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_retries = half_open_max_retries

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_4(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 2,
    ):
        self.name = None
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_retries = half_open_max_retries

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_5(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 2,
    ):
        self.name = name
        self.failure_threshold = None
        self.recovery_timeout = recovery_timeout
        self.half_open_max_retries = half_open_max_retries

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_6(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = None
        self.half_open_max_retries = half_open_max_retries

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_7(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        half_open_max_retries: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_retries = None

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_8(
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

        self.state = None
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_9(
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
        self.failure_count = None
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_10(
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
        self.failure_count = 1
        self.last_failure_time = 0.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_11(
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
        self.last_failure_time = None
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_12(
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
        self.last_failure_time = 1.0
        self.half_open_retries = 0
    def xǁCircuitBreakerǁ__init____mutmut_13(
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
        self.half_open_retries = None
    def xǁCircuitBreakerǁ__init____mutmut_14(
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
        self.half_open_retries = 1

    @_mutmut_mutated(mutants_xǁCircuitBreakerǁcall__mutmut)
    async def call(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_orig(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_1(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state != CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_2(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() + self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_3(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_4(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(None)
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_5(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = None
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_6(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = None
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_7(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 1
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_8(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    None,  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_9(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout + (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_10(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() + self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_11(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = None

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_12(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(**kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_13(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, )

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_14(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state != CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_15(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(None)
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_16(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = None
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_17(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = None
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_18(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 1
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_19(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = None

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_20(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 1

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_21(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count = 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_22(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count -= 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_23(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 2
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_24(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = None

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_25(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state != CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_26(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries = 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_27(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries -= 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_28(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 2
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_29(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries > self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_30(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        None,
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_31(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = None
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_32(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count > self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_33(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    None,
                )
                self.state = CircuitState.OPEN

            raise

    async def xǁCircuitBreakerǁcall__mutmut_34(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"[{self.name}] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                self.half_open_retries = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Retry in {self.recovery_timeout - (time.time() - self.last_failure_time):.0f}s",  # noqa: E501
                )

        try:
            result = await fn(*args, **kwargs)

            if self.state == CircuitState.HALF_OPEN:
                logger.info(f"[{self.name}] HALF_OPEN → CLOSED (success)")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_retries = 0

            return result

        except Exception:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_retries += 1
                if self.half_open_retries >= self.half_open_max_retries:
                    logger.warning(
                        f"[{self.name}] HALF_OPEN → OPEN "
                        f"({self.half_open_retries}/{self.half_open_max_retries} retries failed)",
                    )
                    self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    f"[{self.name}] CLOSED → OPEN "
                    f"({self.failure_count}/{self.failure_threshold} failures)",
                )
                self.state = None

            raise

    @_mutmut_mutated(mutants_xǁCircuitBreakerǁreset__mutmut)
    def reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_orig(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_1(self):
        self.state = None
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_2(self):
        self.state = CircuitState.CLOSED
        self.failure_count = None
        self.last_failure_time = 0.0
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_3(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 1
        self.last_failure_time = 0.0
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_4(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_5(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 1.0
        self.half_open_retries = 0
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_6(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = None
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_7(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 1
        logger.info(f"[{self.name}] Reset to CLOSED")

    def xǁCircuitBreakerǁreset__mutmut_8(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.half_open_retries = 0
        logger.info(None)

mutants_xǁCircuitBreakerǁ__init____mutmut['_mutmut_orig'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_1'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_2'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_3'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_4'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_4 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_5'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_5 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_6'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_6 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_7'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_7 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_8'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_8 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_9'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_9 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_10'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_10 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_11'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_11 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_12'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_12 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_13'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_13 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁ__init____mutmut['xǁCircuitBreakerǁ__init____mutmut_14'] = CircuitBreaker.xǁCircuitBreakerǁ__init____mutmut_14 # type: ignore # mutmut generated

mutants_xǁCircuitBreakerǁcall__mutmut['_mutmut_orig'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_orig # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_1'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_1 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_2'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_2 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_3'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_3 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_4'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_4 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_5'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_5 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_6'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_6 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_7'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_7 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_8'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_8 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_9'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_9 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_10'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_10 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_11'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_11 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_12'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_12 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_13'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_13 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_14'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_14 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_15'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_15 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_16'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_16 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_17'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_17 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_18'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_18 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_19'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_19 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_20'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_20 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_21'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_21 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_22'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_22 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_23'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_23 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_24'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_24 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_25'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_25 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_26'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_26 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_27'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_27 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_28'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_28 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_29'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_29 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_30'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_30 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_31'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_31 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_32'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_32 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_33'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_33 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁcall__mutmut['xǁCircuitBreakerǁcall__mutmut_34'] = CircuitBreaker.xǁCircuitBreakerǁcall__mutmut_34 # type: ignore # mutmut generated

mutants_xǁCircuitBreakerǁreset__mutmut['_mutmut_orig'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_orig # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_1'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_1 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_2'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_2 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_3'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_3 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_4'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_4 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_5'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_5 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_6'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_6 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_7'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_7 # type: ignore # mutmut generated
mutants_xǁCircuitBreakerǁreset__mutmut['xǁCircuitBreakerǁreset__mutmut_8'] = CircuitBreaker.xǁCircuitBreakerǁreset__mutmut_8 # type: ignore # mutmut generated


class CircuitBreakerOpenError(Exception):
    pass


# Глобальные экземпляры для MCP и palace-команд
_mcp_cb: CircuitBreaker | None = None
_palace_cb: CircuitBreaker | None = None
mutants_x_get_mcp_circuit_breaker__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_mcp_circuit_breaker__mutmut)
def get_mcp_circuit_breaker() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_orig() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_1() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is not None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_2() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = None
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_3() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker(None, failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_4() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=None, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_5() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=3, recovery_timeout=None)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_6() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_7() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_8() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=3, )
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_9() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("XXMCPXX", failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_10() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("mcp", failure_threshold=3, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_11() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=4, recovery_timeout=30.0)
    return _mcp_cb


def x_get_mcp_circuit_breaker__mutmut_12() -> CircuitBreaker:
    global _mcp_cb
    if _mcp_cb is None:
        _mcp_cb = CircuitBreaker("MCP", failure_threshold=3, recovery_timeout=31.0)
    return _mcp_cb

mutants_x_get_mcp_circuit_breaker__mutmut['_mutmut_orig'] = x_get_mcp_circuit_breaker__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_1'] = x_get_mcp_circuit_breaker__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_2'] = x_get_mcp_circuit_breaker__mutmut_2 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_3'] = x_get_mcp_circuit_breaker__mutmut_3 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_4'] = x_get_mcp_circuit_breaker__mutmut_4 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_5'] = x_get_mcp_circuit_breaker__mutmut_5 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_6'] = x_get_mcp_circuit_breaker__mutmut_6 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_7'] = x_get_mcp_circuit_breaker__mutmut_7 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_8'] = x_get_mcp_circuit_breaker__mutmut_8 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_9'] = x_get_mcp_circuit_breaker__mutmut_9 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_10'] = x_get_mcp_circuit_breaker__mutmut_10 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_11'] = x_get_mcp_circuit_breaker__mutmut_11 # type: ignore # mutmut generated
mutants_x_get_mcp_circuit_breaker__mutmut['x_get_mcp_circuit_breaker__mutmut_12'] = x_get_mcp_circuit_breaker__mutmut_12 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_palace_circuit_breaker__mutmut)
def get_palace_circuit_breaker() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_orig() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_1() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is not None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_2() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = None
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_3() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            None, failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_4() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=None, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_5() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=2, recovery_timeout=None,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_6() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_7() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_8() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=2, )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_9() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "XXPalaceXX", failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_10() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "palace", failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_11() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "PALACE", failure_threshold=2, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_12() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=3, recovery_timeout=60.0,
        )
    return _palace_cb


def x_get_palace_circuit_breaker__mutmut_13() -> CircuitBreaker:
    global _palace_cb
    if _palace_cb is None:
        _palace_cb = CircuitBreaker(
            "Palace", failure_threshold=2, recovery_timeout=61.0,
        )
    return _palace_cb

mutants_x_get_palace_circuit_breaker__mutmut['_mutmut_orig'] = x_get_palace_circuit_breaker__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_1'] = x_get_palace_circuit_breaker__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_2'] = x_get_palace_circuit_breaker__mutmut_2 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_3'] = x_get_palace_circuit_breaker__mutmut_3 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_4'] = x_get_palace_circuit_breaker__mutmut_4 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_5'] = x_get_palace_circuit_breaker__mutmut_5 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_6'] = x_get_palace_circuit_breaker__mutmut_6 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_7'] = x_get_palace_circuit_breaker__mutmut_7 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_8'] = x_get_palace_circuit_breaker__mutmut_8 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_9'] = x_get_palace_circuit_breaker__mutmut_9 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_10'] = x_get_palace_circuit_breaker__mutmut_10 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_11'] = x_get_palace_circuit_breaker__mutmut_11 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_12'] = x_get_palace_circuit_breaker__mutmut_12 # type: ignore # mutmut generated
mutants_x_get_palace_circuit_breaker__mutmut['x_get_palace_circuit_breaker__mutmut_13'] = x_get_palace_circuit_breaker__mutmut_13 # type: ignore # mutmut generated

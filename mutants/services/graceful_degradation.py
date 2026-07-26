"""graceful_degradation.py
Постепенная деградация функциональности при отказе компонентов.
4 уровня: Full → Medium → Basic → Emergency.
"""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("GracefulDegradation")


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


class DegradationLevel(Enum):
    FULL = "full"  # AI + Palace + Memory + Code
    MEDIUM = "medium"  # AI + Memory (Palace off)
    BASIC = "basic"  # AI only
    EMERGENCY = "emergency"  # Заглушка


@dataclass
class ComponentHealth:
    palace_mcp: bool = True
    palace_search: bool = True
    memory_store: bool = True
    whisper: bool = True
    last_check: float = 0
mutants_xǁDegradationManagerǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁDegradationManagerǁrecord_failure__mutmut: MutantDict = {}  # type: ignore
mutants_xǁDegradationManagerǁrecord_success__mutmut: MutantDict = {}  # type: ignore
mutants_xǁDegradationManagerǁ_recalculate__mutmut: MutantDict = {}  # type: ignore
mutants_xǁDegradationManagerǁshould_use_palace__mutmut: MutantDict = {}  # type: ignore
mutants_xǁDegradationManagerǁshould_use_memory__mutmut: MutantDict = {}  # type: ignore
mutants_xǁDegradationManagerǁget_status_text__mutmut: MutantDict = {}  # type: ignore
mutants_xǁDegradationManagerǁget_available_features__mutmut: MutantDict = {}  # type: ignore


class DegradationManager:
    @_mutmut_mutated(mutants_xǁDegradationManagerǁ__init____mutmut)
    def __init__(self):
        self.level = DegradationLevel.FULL
        self.health = ComponentHealth()
        self._degraded_reason = ""
    def xǁDegradationManagerǁ__init____mutmut_orig(self):
        self.level = DegradationLevel.FULL
        self.health = ComponentHealth()
        self._degraded_reason = ""
    def xǁDegradationManagerǁ__init____mutmut_1(self):
        self.level = None
        self.health = ComponentHealth()
        self._degraded_reason = ""
    def xǁDegradationManagerǁ__init____mutmut_2(self):
        self.level = DegradationLevel.FULL
        self.health = None
        self._degraded_reason = ""
    def xǁDegradationManagerǁ__init____mutmut_3(self):
        self.level = DegradationLevel.FULL
        self.health = ComponentHealth()
        self._degraded_reason = None
    def xǁDegradationManagerǁ__init____mutmut_4(self):
        self.level = DegradationLevel.FULL
        self.health = ComponentHealth()
        self._degraded_reason = "XXXX"

    @_mutmut_mutated(mutants_xǁDegradationManagerǁrecord_failure__mutmut)
    def record_failure(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_orig(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_1(self, component: str):
        if component != "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_2(self, component: str):
        if component == "XXpalace_mcpXX":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_3(self, component: str):
        if component == "PALACE_MCP":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_4(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = None
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_5(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_6(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component != "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_7(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "XXpalace_searchXX":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_8(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "PALACE_SEARCH":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_9(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = None
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_10(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_11(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component != "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_12(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "XXmemoryXX":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_13(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "MEMORY":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_14(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = None
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_15(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_16(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component != "whisper":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_17(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "XXwhisperXX":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_18(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "WHISPER":
            self.health.whisper = False
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_19(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = None
        self._recalculate()

    def xǁDegradationManagerǁrecord_failure__mutmut_20(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    @_mutmut_mutated(mutants_xǁDegradationManagerǁrecord_success__mutmut)
    def record_success(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_orig(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_1(self, component: str):
        if component != "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_2(self, component: str):
        if component == "XXpalace_mcpXX":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_3(self, component: str):
        if component == "PALACE_MCP":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_4(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = None
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_5(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = False
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_6(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component != "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_7(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "XXpalace_searchXX":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_8(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "PALACE_SEARCH":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_9(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = None
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_10(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = False
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_11(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component != "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_12(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "XXmemoryXX":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_13(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "MEMORY":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_14(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = None
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_15(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = False
        elif component == "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_16(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component != "whisper":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_17(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "XXwhisperXX":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_18(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "WHISPER":
            self.health.whisper = True
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_19(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = None
        self._recalculate()

    def xǁDegradationManagerǁrecord_success__mutmut_20(self, component: str):
        if component == "palace_mcp":
            self.health.palace_mcp = True
        elif component == "palace_search":
            self.health.palace_search = True
        elif component == "memory":
            self.health.memory_store = True
        elif component == "whisper":
            self.health.whisper = False
        self._recalculate()

    @_mutmut_mutated(mutants_xǁDegradationManagerǁ_recalculate__mutmut)
    def _recalculate(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_orig(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_1(self):
        old = None
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_2(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search or self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_3(self):
        old = self.level
        if (
            self.health.palace_mcp or self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_4(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = None
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_5(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp and self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_6(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store and self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_7(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = None
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_8(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = None

        if self.level != old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_9(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level == old:
            logger.warning(
                f"Degradation level changed: {old.value} → {self.level.value}",
            )

    def xǁDegradationManagerǁ_recalculate__mutmut_10(self):
        old = self.level
        if (
            self.health.palace_mcp
            and self.health.palace_search
            and self.health.memory_store
        ):
            self.level = DegradationLevel.FULL
        elif (
            self.health.memory_store
            or self.health.palace_mcp
            or self.health.palace_search
        ):
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(
                None,
            )

    @_mutmut_mutated(mutants_xǁDegradationManagerǁshould_use_palace__mutmut)
    def should_use_palace(self) -> bool:
        return self.level in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    def xǁDegradationManagerǁshould_use_palace__mutmut_orig(self) -> bool:
        return self.level in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    def xǁDegradationManagerǁshould_use_palace__mutmut_1(self) -> bool:
        return self.level not in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    @_mutmut_mutated(mutants_xǁDegradationManagerǁshould_use_memory__mutmut)
    def should_use_memory(self) -> bool:
        return self.level in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    def xǁDegradationManagerǁshould_use_memory__mutmut_orig(self) -> bool:
        return self.level in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    def xǁDegradationManagerǁshould_use_memory__mutmut_1(self) -> bool:
        return self.level not in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    def should_use_whisper(self) -> bool:
        return self.health.whisper

    @_mutmut_mutated(mutants_xǁDegradationManagerǁget_status_text__mutmut)
    def get_status_text(self) -> str:
        icons = {
            DegradationLevel.FULL: "🟢",
            DegradationLevel.MEDIUM: "🟡",
            DegradationLevel.BASIC: "🟠",
            DegradationLevel.EMERGENCY: "🔴",
        }
        return f"{icons[self.level]} {self.level.value}"

    def xǁDegradationManagerǁget_status_text__mutmut_orig(self) -> str:
        icons = {
            DegradationLevel.FULL: "🟢",
            DegradationLevel.MEDIUM: "🟡",
            DegradationLevel.BASIC: "🟠",
            DegradationLevel.EMERGENCY: "🔴",
        }
        return f"{icons[self.level]} {self.level.value}"

    def xǁDegradationManagerǁget_status_text__mutmut_1(self) -> str:
        icons = None
        return f"{icons[self.level]} {self.level.value}"

    def xǁDegradationManagerǁget_status_text__mutmut_2(self) -> str:
        icons = {
            DegradationLevel.FULL: "XX🟢XX",
            DegradationLevel.MEDIUM: "🟡",
            DegradationLevel.BASIC: "🟠",
            DegradationLevel.EMERGENCY: "🔴",
        }
        return f"{icons[self.level]} {self.level.value}"

    def xǁDegradationManagerǁget_status_text__mutmut_3(self) -> str:
        icons = {
            DegradationLevel.FULL: "🟢",
            DegradationLevel.MEDIUM: "XX🟡XX",
            DegradationLevel.BASIC: "🟠",
            DegradationLevel.EMERGENCY: "🔴",
        }
        return f"{icons[self.level]} {self.level.value}"

    def xǁDegradationManagerǁget_status_text__mutmut_4(self) -> str:
        icons = {
            DegradationLevel.FULL: "🟢",
            DegradationLevel.MEDIUM: "🟡",
            DegradationLevel.BASIC: "XX🟠XX",
            DegradationLevel.EMERGENCY: "🔴",
        }
        return f"{icons[self.level]} {self.level.value}"

    def xǁDegradationManagerǁget_status_text__mutmut_5(self) -> str:
        icons = {
            DegradationLevel.FULL: "🟢",
            DegradationLevel.MEDIUM: "🟡",
            DegradationLevel.BASIC: "🟠",
            DegradationLevel.EMERGENCY: "XX🔴XX",
        }
        return f"{icons[self.level]} {self.level.value}"

    @_mutmut_mutated(mutants_xǁDegradationManagerǁget_available_features__mutmut)
    def get_available_features(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_orig(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_1(self) -> list[str]:
        if self.level != DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_2(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "XXAIXX",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_3(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "ai",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_4(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "XXPalace SearchXX",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_5(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "palace search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_6(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "PALACE SEARCH",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_7(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "XXKnowledge GraphXX",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_8(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "knowledge graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_9(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "KNOWLEDGE GRAPH",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_10(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "XXMemoryXX",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_11(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_12(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "MEMORY",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_13(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "XXCode ModeXX",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_14(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "code mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_15(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "CODE MODE",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_16(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "XXVoiceXX",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_17(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_18(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "VOICE",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_19(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level != DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_20(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["XXAIXX", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_21(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["ai", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_22(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "XXMemoryXX", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_23(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_24(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "MEMORY", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_25(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "XXCode ModeXX", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_26(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "code mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_27(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "CODE MODE", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_28(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "XXVoiceXX"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_29(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_30(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "VOICE"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_31(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level != DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_32(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["XXAIXX", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_33(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["ai", "Voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_34(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "XXVoice (если доступен)XX"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_35(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "voice (если доступен)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_36(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "VOICE (ЕСЛИ ДОСТУПЕН)"]
        return ["Emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_37(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["XXEmergency responses onlyXX"]

    def xǁDegradationManagerǁget_available_features__mutmut_38(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["emergency responses only"]

    def xǁDegradationManagerǁget_available_features__mutmut_39(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return [
                "AI",
                "Palace Search",
                "Knowledge Graph",
                "Memory",
                "Code Mode",
                "Voice",
            ]
        if self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        if self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        return ["EMERGENCY RESPONSES ONLY"]

mutants_xǁDegradationManagerǁ__init____mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ__init____mutmut['xǁDegradationManagerǁ__init____mutmut_1'] = DegradationManager.xǁDegradationManagerǁ__init____mutmut_1 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ__init____mutmut['xǁDegradationManagerǁ__init____mutmut_2'] = DegradationManager.xǁDegradationManagerǁ__init____mutmut_2 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ__init____mutmut['xǁDegradationManagerǁ__init____mutmut_3'] = DegradationManager.xǁDegradationManagerǁ__init____mutmut_3 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ__init____mutmut['xǁDegradationManagerǁ__init____mutmut_4'] = DegradationManager.xǁDegradationManagerǁ__init____mutmut_4 # type: ignore # mutmut generated

mutants_xǁDegradationManagerǁrecord_failure__mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_1'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_1 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_2'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_2 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_3'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_3 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_4'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_4 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_5'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_5 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_6'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_6 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_7'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_7 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_8'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_8 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_9'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_9 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_10'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_10 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_11'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_11 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_12'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_12 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_13'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_13 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_14'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_14 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_15'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_15 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_16'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_16 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_17'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_17 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_18'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_18 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_19'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_19 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_failure__mutmut['xǁDegradationManagerǁrecord_failure__mutmut_20'] = DegradationManager.xǁDegradationManagerǁrecord_failure__mutmut_20 # type: ignore # mutmut generated

mutants_xǁDegradationManagerǁrecord_success__mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_1'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_1 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_2'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_2 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_3'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_3 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_4'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_4 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_5'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_5 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_6'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_6 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_7'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_7 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_8'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_8 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_9'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_9 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_10'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_10 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_11'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_11 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_12'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_12 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_13'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_13 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_14'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_14 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_15'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_15 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_16'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_16 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_17'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_17 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_18'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_18 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_19'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_19 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁrecord_success__mutmut['xǁDegradationManagerǁrecord_success__mutmut_20'] = DegradationManager.xǁDegradationManagerǁrecord_success__mutmut_20 # type: ignore # mutmut generated

mutants_xǁDegradationManagerǁ_recalculate__mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_1'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_1 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_2'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_2 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_3'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_3 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_4'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_4 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_5'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_5 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_6'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_6 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_7'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_7 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_8'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_8 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_9'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_9 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁ_recalculate__mutmut['xǁDegradationManagerǁ_recalculate__mutmut_10'] = DegradationManager.xǁDegradationManagerǁ_recalculate__mutmut_10 # type: ignore # mutmut generated

mutants_xǁDegradationManagerǁshould_use_palace__mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁshould_use_palace__mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁshould_use_palace__mutmut['xǁDegradationManagerǁshould_use_palace__mutmut_1'] = DegradationManager.xǁDegradationManagerǁshould_use_palace__mutmut_1 # type: ignore # mutmut generated

mutants_xǁDegradationManagerǁshould_use_memory__mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁshould_use_memory__mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁshould_use_memory__mutmut['xǁDegradationManagerǁshould_use_memory__mutmut_1'] = DegradationManager.xǁDegradationManagerǁshould_use_memory__mutmut_1 # type: ignore # mutmut generated

mutants_xǁDegradationManagerǁget_status_text__mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁget_status_text__mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_status_text__mutmut['xǁDegradationManagerǁget_status_text__mutmut_1'] = DegradationManager.xǁDegradationManagerǁget_status_text__mutmut_1 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_status_text__mutmut['xǁDegradationManagerǁget_status_text__mutmut_2'] = DegradationManager.xǁDegradationManagerǁget_status_text__mutmut_2 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_status_text__mutmut['xǁDegradationManagerǁget_status_text__mutmut_3'] = DegradationManager.xǁDegradationManagerǁget_status_text__mutmut_3 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_status_text__mutmut['xǁDegradationManagerǁget_status_text__mutmut_4'] = DegradationManager.xǁDegradationManagerǁget_status_text__mutmut_4 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_status_text__mutmut['xǁDegradationManagerǁget_status_text__mutmut_5'] = DegradationManager.xǁDegradationManagerǁget_status_text__mutmut_5 # type: ignore # mutmut generated

mutants_xǁDegradationManagerǁget_available_features__mutmut['_mutmut_orig'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_orig # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_1'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_1 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_2'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_2 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_3'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_3 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_4'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_4 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_5'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_5 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_6'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_6 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_7'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_7 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_8'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_8 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_9'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_9 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_10'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_10 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_11'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_11 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_12'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_12 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_13'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_13 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_14'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_14 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_15'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_15 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_16'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_16 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_17'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_17 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_18'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_18 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_19'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_19 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_20'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_20 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_21'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_21 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_22'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_22 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_23'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_23 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_24'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_24 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_25'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_25 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_26'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_26 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_27'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_27 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_28'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_28 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_29'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_29 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_30'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_30 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_31'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_31 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_32'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_32 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_33'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_33 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_34'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_34 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_35'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_35 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_36'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_36 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_37'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_37 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_38'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_38 # type: ignore # mutmut generated
mutants_xǁDegradationManagerǁget_available_features__mutmut['xǁDegradationManagerǁget_available_features__mutmut_39'] = DegradationManager.xǁDegradationManagerǁget_available_features__mutmut_39 # type: ignore # mutmut generated


_mgr: DegradationManager | None = None
mutants_x_get_degradation_manager__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_degradation_manager__mutmut)
def get_degradation_manager() -> DegradationManager:
    global _mgr
    if _mgr is None:
        _mgr = DegradationManager()
    return _mgr


def x_get_degradation_manager__mutmut_orig() -> DegradationManager:
    global _mgr
    if _mgr is None:
        _mgr = DegradationManager()
    return _mgr


def x_get_degradation_manager__mutmut_1() -> DegradationManager:
    global _mgr
    if _mgr is not None:
        _mgr = DegradationManager()
    return _mgr


def x_get_degradation_manager__mutmut_2() -> DegradationManager:
    global _mgr
    if _mgr is None:
        _mgr = None
    return _mgr

mutants_x_get_degradation_manager__mutmut['_mutmut_orig'] = x_get_degradation_manager__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_degradation_manager__mutmut['x_get_degradation_manager__mutmut_1'] = x_get_degradation_manager__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_degradation_manager__mutmut['x_get_degradation_manager__mutmut_2'] = x_get_degradation_manager__mutmut_2 # type: ignore # mutmut generated
mutants_x_report_failure__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_report_failure__mutmut)
def report_failure(component: str):
    get_degradation_manager().record_failure(component)


def x_report_failure__mutmut_orig(component: str):
    get_degradation_manager().record_failure(component)


def x_report_failure__mutmut_1(component: str):
    get_degradation_manager().record_failure(None)

mutants_x_report_failure__mutmut['_mutmut_orig'] = x_report_failure__mutmut_orig # type: ignore # mutmut generated
mutants_x_report_failure__mutmut['x_report_failure__mutmut_1'] = x_report_failure__mutmut_1 # type: ignore # mutmut generated
mutants_x_report_success__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_report_success__mutmut)
def report_success(component: str):
    get_degradation_manager().record_success(component)


def x_report_success__mutmut_orig(component: str):
    get_degradation_manager().record_success(component)


def x_report_success__mutmut_1(component: str):
    get_degradation_manager().record_success(None)

mutants_x_report_success__mutmut['_mutmut_orig'] = x_report_success__mutmut_orig # type: ignore # mutmut generated
mutants_x_report_success__mutmut['x_report_success__mutmut_1'] = x_report_success__mutmut_1 # type: ignore # mutmut generated

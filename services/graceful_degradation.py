"""
graceful_degradation.py
Постепенная деградация функциональности при отказе компонентов.
4 уровня: Full → Medium → Basic → Emergency.
"""
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("GracefulDegradation")

class DegradationLevel(Enum):
    FULL = "full"           # AI + Palace + Memory + Code
    MEDIUM = "medium"       # AI + Memory (Palace off)
    BASIC = "basic"         # AI only
    EMERGENCY = "emergency" # Заглушка

@dataclass
class ComponentHealth:
    palace_mcp: bool = True
    palace_search: bool = True
    memory_store: bool = True
    whisper: bool = True
    last_check: float = 0

class DegradationManager:
    def __init__(self):
        self.level = DegradationLevel.FULL
        self.health = ComponentHealth()
        self._degraded_reason = ""

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

    def _recalculate(self):
        old = self.level
        if self.health.palace_mcp and self.health.palace_search and self.health.memory_store:
            self.level = DegradationLevel.FULL
        elif self.health.memory_store:
            self.level = DegradationLevel.MEDIUM
        elif self.health.palace_mcp or self.health.palace_search:
            self.level = DegradationLevel.MEDIUM
        else:
            self.level = DegradationLevel.BASIC

        if self.level != old:
            logger.warning(f"Degradation level changed: {old.value} → {self.level.value}")

    def should_use_palace(self) -> bool:
        return self.level in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    def should_use_memory(self) -> bool:
        return self.level in (DegradationLevel.FULL, DegradationLevel.MEDIUM)

    def should_use_whisper(self) -> bool:
        return self.health.whisper

    def get_status_text(self) -> str:
        icons = {
            DegradationLevel.FULL: "🟢",
            DegradationLevel.MEDIUM: "🟡",
            DegradationLevel.BASIC: "🟠",
            DegradationLevel.EMERGENCY: "🔴",
        }
        return f"{icons[self.level]} {self.level.value}"

    def get_available_features(self) -> list[str]:
        if self.level == DegradationLevel.FULL:
            return ["AI", "Palace Search", "Knowledge Graph", "Memory", "Code Mode", "Voice"]
        elif self.level == DegradationLevel.MEDIUM:
            return ["AI", "Memory", "Code Mode", "Voice"]
        elif self.level == DegradationLevel.BASIC:
            return ["AI", "Voice (если доступен)"]
        else:
            return ["Emergency responses only"]

_mgr: Optional[DegradationManager] = None

def get_degradation_manager() -> DegradationManager:
    global _mgr
    if _mgr is None:
        _mgr = DegradationManager()
    return _mgr

def report_failure(component: str):
    get_degradation_manager().record_failure(component)

def report_success(component: str):
    get_degradation_manager().record_success(component)
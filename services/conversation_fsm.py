"""conversation_fsm.py — Finite State Machine for conversation state management."""
import time
import logging
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    IDLE = auto()
    MCP_INPUT = auto()
    SEARCH_WING = auto()
    PERSONAL_NOTE = auto()
    QUOTE_WAITING = auto()


class ConversationFSM:
    __slots__ = ("_entries", "_ttl")

    def __init__(self, ttl: int = 86400):
        self._entries: dict[int, tuple[ConversationState, dict[str, Any], float]] = {}
        self._ttl = ttl

    def _prune(self, uid: int):
        entry = self._entries.get(uid)
        if entry and time.monotonic() > entry[2]:
            del self._entries[uid]

    def _refresh(self, uid: int):
        entry = self._entries.get(uid)
        if entry:
            self._entries[uid] = (entry[0], entry[1], time.monotonic() + self._ttl)

    def get_state(self, uid: int) -> ConversationState:
        self._prune(uid)
        entry = self._entries.get(uid)
        if not entry:
            return ConversationState.IDLE
        self._refresh(uid)
        return entry[0]

    def get_data(self, uid: int) -> dict[str, Any]:
        self._prune(uid)
        entry = self._entries.get(uid)
        if not entry:
            return {}
        self._refresh(uid)
        return entry[1]

    def set_state(self, uid: int, state: ConversationState, data: dict[str, Any] | None = None):
        self._entries[uid] = (state, data or {}, time.monotonic() + self._ttl)

    def update_data(self, uid: int, **kwargs):
        self._prune(uid)
        entry = self._entries.get(uid)
        if entry:
            entry[1].update(kwargs)
            self._entries[uid] = (entry[0], entry[1], time.monotonic() + self._ttl)
        else:
            self._entries[uid] = (ConversationState.IDLE, kwargs, time.monotonic() + self._ttl)

    def pop_data(self, uid: int, key: str, default: Any = None) -> Any:
        self._prune(uid)
        entry = self._entries.get(uid)
        if entry:
            self._refresh(uid)
            return entry[1].pop(key, default)
        return default

    def clear(self, uid: int):
        self._entries.pop(uid, None)

    def setdefault(self, uid: int, key: str, value: Any) -> Any:
        self._prune(uid)
        entry = self._entries.get(uid)
        if entry:
            self._refresh(uid)
            return entry[1].setdefault(key, value)
        self._entries[uid] = (ConversationState.IDLE, {key: value}, time.monotonic() + self._ttl)
        return value

    def __contains__(self, uid: int) -> bool:
        self._prune(uid)
        return uid in self._entries

    @property
    def active_count(self) -> int:
        now = time.monotonic()
        return sum(1 for uid, (_, _, exp) in self._entries.items() if now <= exp)

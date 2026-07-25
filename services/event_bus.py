"""event_bus.py
Асинхронная шина событий — ядро слабой связности.
Позволяет подписываться на события и реагировать без прямой зависимости.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any

logger = logging.getLogger("EventBus")


class Event(Enum):
    USER_MESSAGE_RECEIVED = "user_message_received"
    AI_RESPONSE_START = "ai_response_start"
    AI_RESPONSE_CHUNK = "ai_response_chunk"
    AI_RESPONSE_COMPLETE = "ai_response_complete"
    AI_RESPONSE_SENT = "ai_response_sent"
    NOTE_SAVED = "note_saved"
    CHAT_CREATED = "chat_created"
    CHAT_SYNCED = "chat_synced"
    FACTS_EXTRACTED = "facts_extracted"


Handler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self):
        self._subscribers: dict[Event, list[Handler]] = {}

    def subscribe(self, event: Event, handler: Handler):
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(handler)
        logger.debug(f"Handler {handler.__name__} subscribed to {event.value}")

    def unsubscribe(self, event: Event, handler: Handler):
        if event in self._subscribers:
            self._subscribers[event] = [
                h for h in self._subscribers[event] if h != handler
            ]

    async def publish(self, event: Event, **kwargs):
        handlers = self._subscribers.get(event, [])
        if not handlers:
            return
        logger.debug(f"Publishing {event.value} to {len(handlers)} handlers")
        for handler in handlers:
            try:
                await handler(**kwargs)
            except Exception as e:
                logger.error(
                    f"Handler {handler.__name__} failed for {event.value}: {e}",
                    exc_info=True,
                )

    def publish_background(self, event: Event, **kwargs):
        asyncio.create_task(self.publish(event, **kwargs))


_bus: EventBus | None = None


def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus():
    global _bus
    _bus = None

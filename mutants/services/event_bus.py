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


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict


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
mutants_xǁEventBusǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁEventBusǁsubscribe__mutmut: MutantDict = {}  # type: ignore
mutants_xǁEventBusǁunsubscribe__mutmut: MutantDict = {}  # type: ignore
mutants_xǁEventBusǁpublish__mutmut: MutantDict = {}  # type: ignore
mutants_xǁEventBusǁpublish_background__mutmut: MutantDict = {}  # type: ignore


class EventBus:
    @_mutmut_mutated(mutants_xǁEventBusǁ__init____mutmut)
    def __init__(self):
        self._subscribers: dict[Event, list[Handler]] = {}
    def xǁEventBusǁ__init____mutmut_orig(self):
        self._subscribers: dict[Event, list[Handler]] = {}
    def xǁEventBusǁ__init____mutmut_1(self):
        self._subscribers: dict[Event, list[Handler]] = None

    @_mutmut_mutated(mutants_xǁEventBusǁsubscribe__mutmut)
    def subscribe(self, event: Event, handler: Handler):
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(handler)
        logger.debug(f"Handler {handler.__name__} subscribed to {event.value}")

    def xǁEventBusǁsubscribe__mutmut_orig(self, event: Event, handler: Handler):
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(handler)
        logger.debug(f"Handler {handler.__name__} subscribed to {event.value}")

    def xǁEventBusǁsubscribe__mutmut_1(self, event: Event, handler: Handler):
        if event in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(handler)
        logger.debug(f"Handler {handler.__name__} subscribed to {event.value}")

    def xǁEventBusǁsubscribe__mutmut_2(self, event: Event, handler: Handler):
        if event not in self._subscribers:
            self._subscribers[event] = None
        self._subscribers[event].append(handler)
        logger.debug(f"Handler {handler.__name__} subscribed to {event.value}")

    def xǁEventBusǁsubscribe__mutmut_3(self, event: Event, handler: Handler):
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(None)
        logger.debug(f"Handler {handler.__name__} subscribed to {event.value}")

    def xǁEventBusǁsubscribe__mutmut_4(self, event: Event, handler: Handler):
        if event not in self._subscribers:
            self._subscribers[event] = []
        self._subscribers[event].append(handler)
        logger.debug(None)

    @_mutmut_mutated(mutants_xǁEventBusǁunsubscribe__mutmut)
    def unsubscribe(self, event: Event, handler: Handler):
        if event in self._subscribers:
            self._subscribers[event] = [
                h for h in self._subscribers[event] if h != handler
            ]

    def xǁEventBusǁunsubscribe__mutmut_orig(self, event: Event, handler: Handler):
        if event in self._subscribers:
            self._subscribers[event] = [
                h for h in self._subscribers[event] if h != handler
            ]

    def xǁEventBusǁunsubscribe__mutmut_1(self, event: Event, handler: Handler):
        if event not in self._subscribers:
            self._subscribers[event] = [
                h for h in self._subscribers[event] if h != handler
            ]

    def xǁEventBusǁunsubscribe__mutmut_2(self, event: Event, handler: Handler):
        if event in self._subscribers:
            self._subscribers[event] = None

    def xǁEventBusǁunsubscribe__mutmut_3(self, event: Event, handler: Handler):
        if event in self._subscribers:
            self._subscribers[event] = [
                h for h in self._subscribers[event] if h == handler
            ]

    @_mutmut_mutated(mutants_xǁEventBusǁpublish__mutmut)
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

    async def xǁEventBusǁpublish__mutmut_orig(self, event: Event, **kwargs):
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

    async def xǁEventBusǁpublish__mutmut_1(self, event: Event, **kwargs):
        handlers = None
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

    async def xǁEventBusǁpublish__mutmut_2(self, event: Event, **kwargs):
        handlers = self._subscribers.get(None, [])
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

    async def xǁEventBusǁpublish__mutmut_3(self, event: Event, **kwargs):
        handlers = self._subscribers.get(event, None)
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

    async def xǁEventBusǁpublish__mutmut_4(self, event: Event, **kwargs):
        handlers = self._subscribers.get([])
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

    async def xǁEventBusǁpublish__mutmut_5(self, event: Event, **kwargs):
        handlers = self._subscribers.get(event, )
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

    async def xǁEventBusǁpublish__mutmut_6(self, event: Event, **kwargs):
        handlers = self._subscribers.get(event, [])
        if handlers:
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

    async def xǁEventBusǁpublish__mutmut_7(self, event: Event, **kwargs):
        handlers = self._subscribers.get(event, [])
        if not handlers:
            return
        logger.debug(None)
        for handler in handlers:
            try:
                await handler(**kwargs)
            except Exception as e:
                logger.error(
                    f"Handler {handler.__name__} failed for {event.value}: {e}",
                    exc_info=True,
                )

    async def xǁEventBusǁpublish__mutmut_8(self, event: Event, **kwargs):
        handlers = self._subscribers.get(event, [])
        if not handlers:
            return
        logger.debug(f"Publishing {event.value} to {len(handlers)} handlers")
        for handler in handlers:
            try:
                await handler(**kwargs)
            except Exception as e:
                logger.error(
                    None,
                    exc_info=True,
                )

    async def xǁEventBusǁpublish__mutmut_9(self, event: Event, **kwargs):
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
                    exc_info=None,
                )

    async def xǁEventBusǁpublish__mutmut_10(self, event: Event, **kwargs):
        handlers = self._subscribers.get(event, [])
        if not handlers:
            return
        logger.debug(f"Publishing {event.value} to {len(handlers)} handlers")
        for handler in handlers:
            try:
                await handler(**kwargs)
            except Exception as e:
                logger.error(
                    exc_info=True,
                )

    async def xǁEventBusǁpublish__mutmut_11(self, event: Event, **kwargs):
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
                    )

    async def xǁEventBusǁpublish__mutmut_12(self, event: Event, **kwargs):
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
                    exc_info=False,
                )

    @_mutmut_mutated(mutants_xǁEventBusǁpublish_background__mutmut)
    def publish_background(self, event: Event, **kwargs):
        asyncio.create_task(self.publish(event, **kwargs))

    def xǁEventBusǁpublish_background__mutmut_orig(self, event: Event, **kwargs):
        asyncio.create_task(self.publish(event, **kwargs))

    def xǁEventBusǁpublish_background__mutmut_1(self, event: Event, **kwargs):
        asyncio.create_task(None)

    def xǁEventBusǁpublish_background__mutmut_2(self, event: Event, **kwargs):
        asyncio.create_task(self.publish(None, **kwargs))

    def xǁEventBusǁpublish_background__mutmut_3(self, event: Event, **kwargs):
        asyncio.create_task(self.publish(**kwargs))

    def xǁEventBusǁpublish_background__mutmut_4(self, event: Event, **kwargs):
        asyncio.create_task(self.publish(event, ))

mutants_xǁEventBusǁ__init____mutmut['_mutmut_orig'] = EventBus.xǁEventBusǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁEventBusǁ__init____mutmut['xǁEventBusǁ__init____mutmut_1'] = EventBus.xǁEventBusǁ__init____mutmut_1 # type: ignore # mutmut generated

mutants_xǁEventBusǁsubscribe__mutmut['_mutmut_orig'] = EventBus.xǁEventBusǁsubscribe__mutmut_orig # type: ignore # mutmut generated
mutants_xǁEventBusǁsubscribe__mutmut['xǁEventBusǁsubscribe__mutmut_1'] = EventBus.xǁEventBusǁsubscribe__mutmut_1 # type: ignore # mutmut generated
mutants_xǁEventBusǁsubscribe__mutmut['xǁEventBusǁsubscribe__mutmut_2'] = EventBus.xǁEventBusǁsubscribe__mutmut_2 # type: ignore # mutmut generated
mutants_xǁEventBusǁsubscribe__mutmut['xǁEventBusǁsubscribe__mutmut_3'] = EventBus.xǁEventBusǁsubscribe__mutmut_3 # type: ignore # mutmut generated
mutants_xǁEventBusǁsubscribe__mutmut['xǁEventBusǁsubscribe__mutmut_4'] = EventBus.xǁEventBusǁsubscribe__mutmut_4 # type: ignore # mutmut generated

mutants_xǁEventBusǁunsubscribe__mutmut['_mutmut_orig'] = EventBus.xǁEventBusǁunsubscribe__mutmut_orig # type: ignore # mutmut generated
mutants_xǁEventBusǁunsubscribe__mutmut['xǁEventBusǁunsubscribe__mutmut_1'] = EventBus.xǁEventBusǁunsubscribe__mutmut_1 # type: ignore # mutmut generated
mutants_xǁEventBusǁunsubscribe__mutmut['xǁEventBusǁunsubscribe__mutmut_2'] = EventBus.xǁEventBusǁunsubscribe__mutmut_2 # type: ignore # mutmut generated
mutants_xǁEventBusǁunsubscribe__mutmut['xǁEventBusǁunsubscribe__mutmut_3'] = EventBus.xǁEventBusǁunsubscribe__mutmut_3 # type: ignore # mutmut generated

mutants_xǁEventBusǁpublish__mutmut['_mutmut_orig'] = EventBus.xǁEventBusǁpublish__mutmut_orig # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_1'] = EventBus.xǁEventBusǁpublish__mutmut_1 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_2'] = EventBus.xǁEventBusǁpublish__mutmut_2 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_3'] = EventBus.xǁEventBusǁpublish__mutmut_3 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_4'] = EventBus.xǁEventBusǁpublish__mutmut_4 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_5'] = EventBus.xǁEventBusǁpublish__mutmut_5 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_6'] = EventBus.xǁEventBusǁpublish__mutmut_6 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_7'] = EventBus.xǁEventBusǁpublish__mutmut_7 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_8'] = EventBus.xǁEventBusǁpublish__mutmut_8 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_9'] = EventBus.xǁEventBusǁpublish__mutmut_9 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_10'] = EventBus.xǁEventBusǁpublish__mutmut_10 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_11'] = EventBus.xǁEventBusǁpublish__mutmut_11 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish__mutmut['xǁEventBusǁpublish__mutmut_12'] = EventBus.xǁEventBusǁpublish__mutmut_12 # type: ignore # mutmut generated

mutants_xǁEventBusǁpublish_background__mutmut['_mutmut_orig'] = EventBus.xǁEventBusǁpublish_background__mutmut_orig # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish_background__mutmut['xǁEventBusǁpublish_background__mutmut_1'] = EventBus.xǁEventBusǁpublish_background__mutmut_1 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish_background__mutmut['xǁEventBusǁpublish_background__mutmut_2'] = EventBus.xǁEventBusǁpublish_background__mutmut_2 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish_background__mutmut['xǁEventBusǁpublish_background__mutmut_3'] = EventBus.xǁEventBusǁpublish_background__mutmut_3 # type: ignore # mutmut generated
mutants_xǁEventBusǁpublish_background__mutmut['xǁEventBusǁpublish_background__mutmut_4'] = EventBus.xǁEventBusǁpublish_background__mutmut_4 # type: ignore # mutmut generated


_bus: EventBus | None = None
mutants_x_get_bus__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_get_bus__mutmut)
def get_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def x_get_bus__mutmut_orig() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def x_get_bus__mutmut_1() -> EventBus:
    global _bus
    if _bus is not None:
        _bus = EventBus()
    return _bus


def x_get_bus__mutmut_2() -> EventBus:
    global _bus
    if _bus is None:
        _bus = None
    return _bus

mutants_x_get_bus__mutmut['_mutmut_orig'] = x_get_bus__mutmut_orig # type: ignore # mutmut generated
mutants_x_get_bus__mutmut['x_get_bus__mutmut_1'] = x_get_bus__mutmut_1 # type: ignore # mutmut generated
mutants_x_get_bus__mutmut['x_get_bus__mutmut_2'] = x_get_bus__mutmut_2 # type: ignore # mutmut generated
mutants_x_reset_bus__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_reset_bus__mutmut)
def reset_bus():
    global _bus
    _bus = None


def x_reset_bus__mutmut_orig():
    global _bus
    _bus = None


def x_reset_bus__mutmut_1():
    global _bus
    _bus = ""

mutants_x_reset_bus__mutmut['_mutmut_orig'] = x_reset_bus__mutmut_orig # type: ignore # mutmut generated
mutants_x_reset_bus__mutmut['x_reset_bus__mutmut_1'] = x_reset_bus__mutmut_1 # type: ignore # mutmut generated

import asyncio

from services.event_bus import Event, EventBus


class TestEventBus:
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        async def handler(msg: str):
            received.append(msg)

        bus.subscribe(Event.AI_RESPONSE_COMPLETE, handler)
        await bus.publish(Event.AI_RESPONSE_COMPLETE, msg="hello")
        assert received == ["hello"]

    async def test_multiple_handlers(self):
        bus = EventBus()
        results = []

        async def h1():
            results.append("h1")

        async def h2():
            results.append("h2")

        bus.subscribe(Event.NOTE_SAVED, h1)
        bus.subscribe(Event.NOTE_SAVED, h2)
        await bus.publish(Event.NOTE_SAVED)
        assert results == ["h1", "h2"]

    async def test_handler_error_isolation(self):
        bus = EventBus()
        results = []

        async def failing_handler():
            raise RuntimeError("oops")

        async def good_handler():
            results.append("ok")

        bus.subscribe(Event.CHAT_CREATED, failing_handler)
        bus.subscribe(Event.CHAT_CREATED, good_handler)
        await bus.publish(Event.CHAT_CREATED)
        assert results == ["ok"]

    async def test_unsubscribe(self):
        bus = EventBus()
        results = []

        async def handler():
            results.append("called")

        bus.subscribe(Event.AI_RESPONSE_START, handler)
        bus.unsubscribe(Event.AI_RESPONSE_START, handler)
        await bus.publish(Event.AI_RESPONSE_START)
        assert results == []

    async def test_no_subscribers_does_not_raise(self):
        bus = EventBus()
        await bus.publish(Event.AI_RESPONSE_START)

    async def test_publish_with_kwargs(self):
        bus = EventBus()
        received = {}

        async def handler(**kwargs):
            received.update(kwargs)

        bus.subscribe(Event.FACTS_EXTRACTED, handler)
        await bus.publish(Event.FACTS_EXTRACTED, fact="test", count=3)
        assert received == {"fact": "test", "count": 3}

    async def test_publish_background_schedules_handler(self):
        bus = EventBus()
        received = []

        async def handler(msg: str):
            received.append(msg)

        bus.subscribe(Event.AI_RESPONSE_SENT, handler)
        bus.publish_background(Event.AI_RESPONSE_SENT, msg="later")
        await asyncio.sleep(0)
        assert received == ["later"]


class TestEventBusMutants:
    async def test_unsubscribe_keeps_other_handlers(self):
        bus = EventBus()
        results = []

        async def h1():
            results.append("h1")

        async def h2():
            results.append("h2")

        bus.subscribe(Event.AI_RESPONSE_START, h1)
        bus.subscribe(Event.AI_RESPONSE_START, h2)
        bus.unsubscribe(Event.AI_RESPONSE_START, h1)
        await bus.publish(Event.AI_RESPONSE_START)
        assert results == ["h2"]

    async def test_handler_error_logs_exact_message(self, caplog):
        bus = EventBus()

        async def failing_handler():
            raise RuntimeError("oops")

        bus.subscribe(Event.CHAT_CREATED, failing_handler)
        with caplog.at_level("ERROR", logger="EventBus"):
            await bus.publish(Event.CHAT_CREATED)
        assert (
            caplog.records[-1].getMessage()
            == "Handler failing_handler failed for chat_created: oops"
        )
        assert caplog.records[-1].exc_info

    async def test_publish_debug_log_exact(self, caplog):
        bus = EventBus()
        received = []

        async def handler(msg: str):
            received.append(msg)

        bus.subscribe(Event.AI_RESPONSE_START, handler)
        with caplog.at_level("DEBUG", logger="EventBus"):
            await bus.publish(Event.AI_RESPONSE_START, msg="x")
        assert received == ["x"]
        assert caplog.records[-1].getMessage() == "Publishing ai_response_start to 1 handlers"

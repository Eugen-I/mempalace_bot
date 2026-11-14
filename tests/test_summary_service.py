"""Unit tests for services.summary_service — shared summary generation."""

import pytest

from services import summary_service
from services.prompts import get_summary_prompt


def _capture(monkeypatch, result):
    calls = []

    async def fake_ai(engine, model, messages):
        calls.append({"engine": engine, "model": model, "messages": messages})
        return result

    monkeypatch.setattr(summary_service, "call_ai_async", fake_ai)
    return calls


@pytest.mark.asyncio
async def test_chat_mode_prompt_and_truncation(monkeypatch):
    messages = [
        {"role": "user" if i % 2 else "assistant", "content": f"m{i}"}
        for i in range(25)
    ]
    calls = _capture(monkeypatch, "слово " * 60)

    result = await summary_service.generate_summary(
        summary_service.SummaryMode.CHAT,
        engine="ollama",
        model="llama3",
        messages=messages,
        existing_summary="предыдущее саммари",
    )

    expected_dialog = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages[-20:]
    )
    expected_prompt = get_summary_prompt(
        dialog_slice=expected_dialog,
        context_prefix=(
            "ПРЕДЫДУЩЕЕ САММАРИ:\nпредыдущее саммари\n\n"
            "ТЕКУЩИЙ ДИАЛОГ:\n"
        ),
    )
    assert calls == [{
        "engine": "ollama",
        "model": "llama3",
        "messages": [{"role": "system", "content": expected_prompt}],
    }]
    assert result.endswith("...")
    assert len(result.split()) == 50


@pytest.mark.asyncio
async def test_chat_mode_empty_chat_skips_ai(monkeypatch):
    async def must_not_call(*args, **kwargs):
        raise AssertionError("AI must not be called")

    monkeypatch.setattr(summary_service, "call_ai_async", must_not_call)

    result = await summary_service.generate_summary(
        summary_service.SummaryMode.CHAT,
        engine="ollama",
        model="llama3",
        messages=[],
    )
    assert result == "Чат пуст."


@pytest.mark.asyncio
async def test_periodic_chat_mode_prompt_limit_and_raw_output(monkeypatch):
    messages = [
        {"role": "user", "content": f"m{i}"}
        for i in range(25)
    ]
    calls = _capture(monkeypatch, "  короткое саммари  ")

    result = await summary_service.generate_summary(
        summary_service.SummaryMode.CHAT_PERIODIC,
        engine="ollama",
        model="llama3",
        messages=messages,
        existing_summary="должно игнорироваться",
    )

    expected_dialog = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages[-15:]
    )
    expected_prompt = get_summary_prompt(
        dialog_slice=expected_dialog, context_prefix="",
    )
    assert calls[0]["messages"] == [{"role": "user", "content": expected_prompt}]
    assert result == "  короткое саммари  "


@pytest.mark.asyncio
async def test_periodic_chat_mode_truncates_to_40_words(monkeypatch):
    _capture(monkeypatch, "слово " * 50)

    result = await summary_service.generate_summary(
        summary_service.SummaryMode.CHAT_PERIODIC,
        engine="ollama",
        model="llama3",
        messages=[{"role": "user", "content": "x"}],
    )
    assert result.endswith("...")
    assert len(result.split()) == 40


@pytest.mark.asyncio
async def test_insight_mode_prompt_and_raw_output(monkeypatch):
    calls = _capture(monkeypatch, "длинный итог " * 30)

    result = await summary_service.generate_summary(
        summary_service.SummaryMode.INSIGHT,
        engine="ollama",
        model="llama3",
        text="текст ответа",
    )

    assert calls[0]["messages"] == [
        {"role": "user", "content": "Суммаризируй: текст ответа"},
    ]
    assert result == "длинный итог " * 30


@pytest.mark.asyncio
async def test_room_mode_prompt_and_raw_output(monkeypatch):
    calls = _capture(monkeypatch, "саммари комнаты")

    result = await summary_service.generate_summary(
        summary_service.SummaryMode.ROOM,
        engine="ollama",
        model="qwen",
        text="заметка 1\n\nзаметка 2",
        wing="w",
        room="r",
    )

    expected_prompt = (
        "Ниже — все записи из комнаты w/r.\n"
        "Сделай две вещи:\n"
        "1) Для каждой записи напиши краткую саммари (2–3 предложения).\n"
        "2) После этого составь ОБЩУЮ структурированную саммари по всей комнате — "
        "сгруппируй темы, выдели главное, свяжи между собой.\n\n"
        "Записи комнаты:\nзаметка 1\n\nзаметка 2"
    )
    assert calls[0]["messages"] == [
        {
            "role": "system",
            "content": (
                "Ты — аналитик. Составляешь саммари по заметкам. "
                "Отвечай на русском языке."
            ),
        },
        {"role": "user", "content": expected_prompt},
    ]
    assert result == "саммари комнаты"


@pytest.mark.asyncio
async def test_ai_error_propagates_to_caller(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("ai down")

    monkeypatch.setattr(summary_service, "call_ai_async", boom)

    with pytest.raises(RuntimeError, match="ai down"):
        await summary_service.generate_summary(
            summary_service.SummaryMode.INSIGHT,
            engine="ollama",
            model="llama3",
            text="x",
        )


@pytest.mark.asyncio
async def test_unknown_mode_raises_before_ai_call(monkeypatch):
    async def must_not_call(*args, **kwargs):
        raise AssertionError("AI must not be called")

    monkeypatch.setattr(summary_service, "call_ai_async", must_not_call)

    with pytest.raises(ValueError, match="Неизвестный режим"):
        await summary_service.generate_summary(
            "unknown",
            engine="ollama",
            model="llama3",
        )

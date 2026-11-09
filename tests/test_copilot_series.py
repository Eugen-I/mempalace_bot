"""tests/test_copilot_series.py — Unit-тесты для кураторской серии и раскадровки.

Проверяет:
- Модели данных SeriesShot и PhotoSeries (to_dict/from_dict);
- Генерацию триптиха (3 кадра) и пентаптиха (5 кадров);
- Драматургический ритм и чередование планов;
- Кураторскую экспликацию и промпты Midjourney;
- Отказоустойчивый fallback при сбоях LLM;
- Форматирование карточек для Telegram (HTML, без <!-- -->);
- Экспорт в Apple Notes в формате Markdown [Серия к съемке];
- Обработчики Telegram callback (просмотр серии, смена формата, перелистывание кадров, экспорт).
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.copilot_series import (
    ACT_ROLES_PENTA,
    ACT_ROLES_TRIPTYCH,
    PhotoSeries,
    SeriesShot,
    build_series_storyboard,
    build_series_storyboard_async,
    export_series_to_apple_notes,
    format_series_for_notes,
    format_series_overview_card,
    format_series_shot_card,
)
from services.copilot_session import CopilotSession, CopilotSessionManager


@pytest.fixture
def sample_session() -> CopilotSession:
    """Фикстура сессии копайлота с утвержденным проектом."""
    tmp_path = Path(tempfile.mkdtemp()) / "test_series_sessions.json"
    manager = CopilotSessionManager(file_path=tmp_path, ttl=3600)
    session = manager.create_or_replace_session(user_id=123456, topic="Тени в ночном городе")
    session.stage = "completed"
    session.selected_styles = ["Экспрессионизм", "Сюрреализм"]
    session.manifesto = "Манифест: исследование границ между Персоной и Тенью через жесткий свет."
    session.tech_preferences = {
        "support": "Съемка с рук (микро-ICM)",
        "lens": "Гелиос 44-2 58mm f/2",
        "filter_accessory": "Black Pro-Mist 1/4",
        "lighting": "Контровой натриевый свет",
    }
    session.candidate_projects = [
        {
            "id": 1,
            "title": "Шепот Тени",
            "vector": "Интимный / Камерный",
            "visual_hook": "Одинокая фигура у мокрой кирпичной арки.",
            "lighting_scene": "Один узкий контровой натриевый фонарь.",
            "camera_setup": "1/15 с, f/2, ISO 200, Classic Chrome",
            "shooting_action": "Микро-тремор с рук в момент экспозиции.",
        }
    ]
    session.selected_project_idx = 0
    return session


def test_series_shot_dataclass():
    """Проверка сериализации и десериализации SeriesShot."""
    shot = SeriesShot(
        frame_index=1,
        act_role="Акт I: Вход",
        shot_type="Общий план",
        title="Вход в сумрак",
        visual_description="Пустынная улица",
        lighting_setup="Контровой свет",
        optics_action="Гелиос f/4",
        fuji_recipe_note="Classic Chrome DR400",
        midjourney_prompt="cinematic wide shot --ar 16:9",
    )
    d = shot.to_dict()
    assert d["frame_index"] == 1
    assert d["act_role"] == "Акт I: Вход"

    restored = SeriesShot.from_dict(d)
    assert restored.title == "Вход в сумрак"
    assert restored.shot_type == "Общий план"


def test_photo_series_dataclass():
    """Проверка сериализации и десериализации PhotoSeries."""
    series = PhotoSeries(
        project_title="Шепот Тени",
        series_format="triptych",
        manifesto_core="Манифест",
        curatorial_statement="Кураторский текст",
        shots=[
            SeriesShot(
                frame_index=1,
                act_role="Акт I",
                shot_type="Общий план",
                title="Кадр 1",
                visual_description="...",
                lighting_setup="...",
                optics_action="...",
                fuji_recipe_note="...",
                midjourney_prompt="...",
            )
        ],
        fuji_recipe_summary="Classic Chrome",
    )
    d = series.to_dict()
    assert d["project_title"] == "Шепот Тени"
    assert len(d["shots"]) == 1

    restored = PhotoSeries.from_dict(d)
    assert restored.project_title == "Шепот Тени"
    assert restored.series_format == "triptych"
    assert len(restored.shots) == 1
    assert restored.shots[0].frame_index == 1


def test_build_fallback_series_triptych(sample_session: CopilotSession):
    """Проверка построения триптиха (3 кадра): роли, крупности, оптика."""
    series = build_series_storyboard(sample_session, series_format="triptych")
    assert series.series_format == "triptych"
    assert len(series.shots) == 3
    assert series.project_title == "Шепот Тени"
    assert "Шепот Тени" in series.curatorial_statement
    assert "Гелиос 44-2" in series.curatorial_statement

    # Проверка драматургии актов
    for i, (expected_role, expected_type) in enumerate(ACT_ROLES_TRIPTYCH, start=1):
        shot = series.shots[i - 1]
        assert shot.frame_index == i
        assert shot.act_role == expected_role
        assert shot.shot_type == expected_type
        assert len(shot.midjourney_prompt) > 20
        assert "--ar 16:9 --style raw --v 6.1" in shot.midjourney_prompt


def test_build_fallback_series_penta(sample_session: CopilotSession):
    """Проверка построения пентаптиха (5 кадров): чередование крупностей."""
    series = build_series_storyboard(sample_session, series_format="penta")
    assert series.series_format == "penta"
    assert len(series.shots) == 5

    shot_types = [s.shot_type for s in series.shots]
    # Убеждаемся, что нет двух одинаковых крупностей подряд
    for i in range(len(shot_types) - 1):
        assert shot_types[i] != shot_types[i + 1]

    for i, (expected_role, expected_type) in enumerate(ACT_ROLES_PENTA, start=1):
        shot = series.shots[i - 1]
        assert shot.frame_index == i
        assert shot.act_role == expected_role
        assert shot.shot_type == expected_type


@pytest.mark.asyncio
async def test_build_series_storyboard_async_llm_success(sample_session: CopilotSession):
    """Проверка генерации серии через LLM при валидном JSON-ответе."""
    mock_llm_payload = {
        "curatorial_statement": "Искусствоведческий текст об исследовании Тени в темноте.",
        "fuji_recipe_summary": "Acros+R, DR400, Tone H-1/S+3",
        "shots": [
            {
                "frame_index": 1,
                "act_role": "Акт I: Пространство",
                "shot_type": "Общий план",
                "title": "Холодная улица",
                "visual_description": "Геометрия пустой площади",
                "lighting_setup": "Контровой натрий",
                "optics_action": "Гелиос f/4",
                "fuji_recipe_note": "Acros+R",
                "midjourney_prompt": "moody wide shot --ar 16:9 --v 6.1",
            },
            {
                "frame_index": 2,
                "act_role": "Акт II: Столкновение",
                "shot_type": "Кульминационный средний план",
                "title": "Разлом личности",
                "visual_description": "Фигура и двойник",
                "lighting_setup": "Резкие тени",
                "optics_action": "Гелиос f/2 + призма",
                "fuji_recipe_note": "Acros+R",
                "midjourney_prompt": "hero chiaroscuro shot --ar 16:9 --v 6.1",
            },
            {
                "frame_index": 3,
                "act_role": "Акт III: Развязка",
                "shot_type": "Деталь",
                "title": "След на стене",
                "visual_description": "Текстура кирпича",
                "lighting_setup": "Угасающий свет",
                "optics_action": "Гелиос f/2",
                "fuji_recipe_note": "Acros+R",
                "midjourney_prompt": "detail texture shot --ar 16:9 --v 6.1",
            },
        ],
    }

    raw_response = f"```json\n{json.dumps(mock_llm_payload, ensure_ascii=False)}\n```"

    with patch("services.ai_engine.get_current_ai", return_value=("gemini", "gemini-2.5-flash")), \
         patch("services.ai_engine.get_ai_response_async", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = raw_response

        series = await build_series_storyboard_async(sample_session, series_format="triptych")
        assert series.series_format == "triptych"
        assert len(series.shots) == 3
        assert series.shots[0].title == "Холодная улица"
        assert series.curatorial_statement == (
            "Искусствоведческий текст об исследовании Тени в темноте."
        )


@pytest.mark.asyncio
async def test_build_series_storyboard_async_llm_failure_fallback(
    sample_session: CopilotSession,
):
    """Проверка автоматического перехода на fallback при сбое LLM."""
    with patch("services.ai_engine.get_current_ai", return_value=("gemini", "gemini-2.5-flash")), \
         patch("services.ai_engine.get_ai_response_async", new_callable=AsyncMock) as mock_ai:
        mock_ai.side_effect = RuntimeError("API 429 quota exhausted")

        series = await build_series_storyboard_async(sample_session, series_format="triptych")
        assert series.series_format == "triptych"
        assert len(series.shots) == 3
        assert "Шепот Тени" in series.project_title
        assert len(series.curatorial_statement) > 50


def test_format_series_overview_card(sample_session: CopilotSession):
    """Проверка форматирования сводной карточки Telegram (HTML, без <!-- -->)."""
    series = build_series_storyboard(sample_session, series_format="triptych")
    card = format_series_overview_card(series)

    assert "<!--" not in card
    assert "-->" not in card
    assert "<b>Кураторская фотосерия: «Шепот Тени»</b>" in card
    assert "<blockquote>" in card
    assert "</blockquote>" in card
    assert "Триптих (3 кадра)" in card
    assert "Кадр 1" in card
    assert "Кадр 2" in card
    assert "Кадр 3" in card


def test_format_series_shot_card(sample_session: CopilotSession):
    """Проверка форматирования карточки одного кадра."""
    series = build_series_storyboard(sample_session, series_format="triptych")
    shot_card = format_series_shot_card(series, shot_idx=0)

    assert "<!--" not in shot_card
    assert "Кадр 1 из 3" in shot_card
    assert "<code>" in shot_card
    assert "</code>" in shot_card
    assert "--ar 16:9" in shot_card

    # Проверка некорректного индекса
    invalid_card = format_series_shot_card(series, shot_idx=99)
    assert "Кадр серии не найден" in invalid_card


def test_format_series_for_notes(sample_session: CopilotSession):
    """Проверка экспорта в Markdown для Apple Notes."""
    series = build_series_storyboard(sample_session, series_format="triptych")
    title, body = format_series_for_notes(series)

    assert title == "[Серия к съемке] Шепот Тени"
    assert "# Кураторская фотосерия: «Шепот Тени»" in body
    assert "## 📜 Кураторская экспликация (Curatorial Statement)" in body
    assert "### Кадр 1:" in body
    assert "### Кадр 2:" in body
    assert "### Кадр 3:" in body
    assert "```text" in body


def test_export_series_to_apple_notes_success(sample_session: CopilotSession):
    """Проверка успешного экспорта в Apple Notes."""
    series = build_series_storyboard(sample_session, series_format="triptych")

    with patch("services.apple_notes.ensure_folder") as mock_ensure, \
         patch("services.apple_notes.create_note", return_value="note-999") as mock_create:
        ok, note_id = export_series_to_apple_notes(series, folder="Фотопроекты")
        assert ok is True
        assert note_id == "note-999"
        mock_ensure.assert_called_once_with("Фотопроекты")
        mock_create.assert_called_once()


def test_export_series_to_apple_notes_failure(sample_session: CopilotSession):
    """Проверка изоляции ошибок при недоступности Apple Notes."""
    series = build_series_storyboard(sample_session, series_format="triptych")

    with patch("services.apple_notes.ensure_folder", side_effect=OSError("AppleScript timeout")):
        ok, err_msg = export_series_to_apple_notes(series, folder="Фотопроекты")
        assert ok is False
        assert "AppleScript timeout" in err_msg


@pytest.mark.asyncio
async def test_cb_copilot_view_series(sample_session: CopilotSession):
    """Проверка Telegram-обработчика cp_view_series."""
    from handlers.copilot import cb_copilot_view_series

    cb = MagicMock()
    cb.from_user.id = sample_session.user_id
    cb.data = "cp_view_series"
    cb.message = AsyncMock()
    cb.answer = AsyncMock()

    with patch("handlers.copilot.get_copilot_manager") as mock_mgr_getter:
        mgr = MagicMock()
        mgr.get_session.return_value = sample_session
        mock_mgr_getter.return_value = mgr

        await cb_copilot_view_series(cb)

        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        args, kwargs = cb.message.edit_text.call_args
        assert "Кураторская фотосерия: «Шепот Тени»" in args[0]
        assert kwargs["parse_mode"] == "HTML"
        assert sample_session.series_data is not None


@pytest.mark.asyncio
async def test_cb_copilot_series_format(sample_session: CopilotSession):
    """Проверка переключения формата серии (triptych -> penta)."""
    from handlers.copilot import cb_copilot_series_format

    cb = MagicMock()
    cb.from_user.id = sample_session.user_id
    cb.data = "cp_series_format:penta"
    cb.message = AsyncMock()
    cb.answer = AsyncMock()

    with patch("handlers.copilot.get_copilot_manager") as mock_mgr_getter:
        mgr = MagicMock()
        mgr.get_session.return_value = sample_session
        mock_mgr_getter.return_value = mgr

        await cb_copilot_series_format(cb)

        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        args, kwargs = cb.message.edit_text.call_args
        assert "Пентаптих (5 кадров)" in args[0]
        assert sample_session.series_data["series_format"] == "penta"
        assert len(sample_session.series_data["shots"]) == 5


@pytest.mark.asyncio
async def test_cb_copilot_series_shot(sample_session: CopilotSession):
    """Проверка детального просмотра кадра (cp_series_shot:1)."""
    from handlers.copilot import cb_copilot_series_shot

    cb = MagicMock()
    cb.from_user.id = sample_session.user_id
    cb.data = "cp_series_shot:1"
    cb.message = AsyncMock()
    cb.answer = AsyncMock()

    with patch("handlers.copilot.get_copilot_manager") as mock_mgr_getter:
        mgr = MagicMock()
        mgr.get_session.return_value = sample_session
        mock_mgr_getter.return_value = mgr

        await cb_copilot_series_shot(cb)

        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        args, kwargs = cb.message.edit_text.call_args
        assert "Кадр 2 из" in args[0]
        assert "Промпт для Midjourney" in args[0]


@pytest.mark.asyncio
async def test_cb_copilot_series_export_notes(sample_session: CopilotSession):
    """Проверка callback экспорта серии в Apple Notes."""
    from handlers.copilot import cb_copilot_series_export_notes

    cb = MagicMock()
    cb.from_user.id = sample_session.user_id
    cb.data = "cp_series_export_notes"
    cb.message = AsyncMock()
    cb.answer = AsyncMock()

    with patch("handlers.copilot.get_copilot_manager") as mock_mgr_getter, \
         patch("handlers.copilot.export_series_to_apple_notes", return_value=(True, "note-777")):
        mgr = MagicMock()
        mgr.get_session.return_value = sample_session
        mock_mgr_getter.return_value = mgr

        await cb_copilot_series_export_notes(cb)

        cb.answer.assert_called_once()
        alert_text = cb.answer.call_args[0][0]
        assert "экспортирована в Apple Notes" in alert_text
        assert cb.answer.call_args[1].get("show_alert") is True

"""Unit-тесты для Шага 12: Полевой ассистент, Midjourney-эскизы и Apple Notes."""

from unittest.mock import patch
import pytest

from handlers import copilot as hc
import services.copilot_engine as engine
from services.copilot_session import CopilotSessionManager


class FakeUser:
    def __init__(self, uid=9999):
        self.id = uid


class FakeStatus:
    def __init__(self):
        self.edits = []
        self.last_kw = {}

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_kw = {"parse_mode": parse_mode, "reply_markup": reply_markup}


class FakeMessage:
    def __init__(self, uid=9999, text=""):
        self.from_user = FakeUser(uid)
        self.chat = type("C", (), {"id": 1})()
        self.text = text
        self.answers = []
        self.edits = []
        self.last_reply_markup = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        status = FakeStatus()
        return status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup


class FakeCb:
    def __init__(self, uid=9999, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=False):
        self.answered.append((text, show_alert))


@pytest.fixture
def temp_manager(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "ALLOWED_IDS", {9999})
    mgr = CopilotSessionManager(file_path=tmp_path / "copilot_test.json")
    monkeypatch.setattr(hc, "get_copilot_manager", lambda: mgr)
    monkeypatch.setattr(engine, "get_copilot_manager", lambda: mgr)
    return mgr


@pytest.fixture
def completed_session(temp_manager):
    session = temp_manager.create_or_replace_session(9999, "Архитипы Юнга в городе")
    session.stage = "completed"
    session.selected_styles = ["Сюрреализм", "Экспрессионизм"]
    session.manifesto = "Манифест: исследование Тени через оптические искажения и резкие тени."
    session.summary = "Психологический нерв — столкновение Персоны и Тени в бетонном колодце."
    session.tech_preferences = {
        "support": "Съемка с рук (микро-ICM)",
        "lens": "Гелиос 44-2 58mm f/2",
        "filter_accessory": "Black Pro-Mist 1/4",
        "lighting": "Контровой свет",
        "handwriting_notes": "Любит мягкий вихревой боке и глубокие тени",
    }
    session.candidate_projects = [
        {
            "id": 1,
            "title": "Шепот Тени",
            "vector": "Интимный / Камерный",
            "visual_hook": "Одинокая фигура в черном пальто у мокрой бетонной стены.",
            "lighting_scene": "Один узкий луч контрового натриевого фонаря.",
            "camera_setup": "1/15 с, f/2, ISO 200, Velvia, Тоновая кривая: -1/+1",
            "shooting_action": "Микро-тремор с рук в момент спуска затвора.",
            "gear_summary": "Fujifilm X-T4, Гелиос 44-2, Black Pro-Mist 1/4",
            "shooting_steps": [
                "Найти узкий проулок с контровым натриевым фонарем",
                "Выставить Focus Peaking на силуэт",
                "Сделать кадр с микро-сдвигом камеры вниз",
            ],
        },
        {
            "id": 2,
            "title": "Геометрия Персоны",
            "vector": "Монументальный / Геометрический",
            "visual_hook": "Стеклянный фасад небоскреба с отражением искаженного силуэта.",
            "lighting_scene": "Резкие диагональные тени от офисных жалюзи.",
            "camera_setup": "1/125 с, f/5.6, ISO 160, Classic Chrome",
            "shooting_action": "Штатив, строгая центральная симметрия.",
            "gear_summary": "Fujifilm X-T4, Fujinon XF 18-55mm",
            "shooting_steps": ["Установить штатив", "Выверить уровень по горизонту"],
        },
    ]
    session.selected_project_idx = 0
    temp_manager.save_session(session)
    return session


def test_generate_field_assistant_checklist(completed_session):
    """Проверка формирования карманного чек-листа для выезда на локацию."""
    checklist = engine.generate_field_assistant_checklist(completed_session)

    assert "🎒 <b>Полевой ассистент съемки: «Шепот Тени»</b>" in checklist
    assert "Архитипы Юнга в городе" in checklist
    assert "Сюрреализм, Экспрессионизм" in checklist
    assert "Интимный / Камерный" in checklist
    assert "Одинокая фигура в черном пальто" in checklist

    # Чек-лист снаряжения
    assert "Fujifilm X-T4" in checklist
    assert "Гелиос 44-2 58mm f/2" in checklist
    assert "Black Pro-Mist 1/4" in checklist
    assert "NP-W235" in checklist
    assert "UHS-II" in checklist
    assert "Съемка с рук" in checklist

    # Настройки и шаги
    assert "1/15 с, f/2, ISO 200" in checklist
    assert "Микро-тремор с рук" in checklist
    assert "1. Найти узкий проулок" in checklist


def test_field_assistant_tripod_branch(completed_session):
    """Проверка чек-листа при штативном сетапе."""
    completed_session.selected_project_idx = 1
    completed_session.tech_preferences["support"] = "Штатив (геометрическая статика)"

    checklist = engine.generate_field_assistant_checklist(completed_session)
    assert "Геометрия Персоны" in checklist
    assert "Штатив и устойчивая площадка" in checklist


def test_build_raw_midjourney_prompt(completed_session):
    """Проверка сборки чистого промпта для Midjourney / Flux."""
    prompt = engine.build_raw_midjourney_prompt(completed_session)

    assert "surrealism aesthetic" in prompt
    assert "German expressionist cinema aesthetic" in prompt
    assert "cinematic shot of Одинокая фигура в черном пальто" in prompt
    assert "Helios 44-2 58mm f/2 lens" in prompt
    assert "Black Pro-Mist diffusion filter" in prompt
    assert "Fujifilm X-T4 film simulation Velvia" in prompt
    assert "--ar 16:9 --v 6.1 --style raw" in prompt


def test_generate_midjourney_prompt_card(completed_session):
    """Проверка форматирования Telegram-карточки с кликабельным кодом."""
    card = engine.generate_midjourney_prompt(completed_session)

    assert "🎨 <b>Эскизный промпт для нейросетей" in card
    assert "«Шепот Тени»" in card
    assert "<code>" in card and "</code>" in card
    assert "surrealism aesthetic" in card
    assert "💡" in card


def test_format_copilot_project_for_notes(completed_session):
    """Проверка форматирования Markdown для заметки Apple Notes."""
    title, body = engine.format_copilot_project_for_notes(completed_session)

    assert title == "[К съемке] Шепот Тени"
    assert "# [К съемке] Шепот Тени" in body
    assert "- **Тема:** Архитипы Юнга в городе" in body
    assert "Сюрреализм, Экспрессионизм" in body
    assert "## 📜 Художественный манифест" in body
    assert "## 🖼 Визуальный образ кадра" in body
    assert "## 💡 Схема освещения" in body
    assert "## 📷 Параметры съёмки (Fujifilm X-T4)" in body
    assert "## 👐 Физика съёмки (действие фотографа)" in body
    assert "## 📋 Пошаговый план на локации" in body
    assert "## ✅ Чек-лист перед выходом" in body
    assert "## 🎨 Эскизный промпт (Midjourney v6.1 / Flux)" in body
    assert "## 💬 Резюме смыслового поиска автора" in body


def test_export_copilot_project_to_apple_notes(completed_session):
    """Проверка выгрузки проекта в Apple Notes с моками API."""
    with patch("services.apple_notes.ensure_folder", return_value=True) as mock_folder:
        with patch(
            "services.apple_notes.create_note", return_value="x-coredata://note-copilot-77",
        ) as mock_create:
            note_id = engine.export_copilot_project_to_apple_notes(
                completed_session, folder="Фотопроекты",
            )

    assert note_id == "x-coredata://note-copilot-77"
    mock_folder.assert_called_once_with("Фотопроекты")
    mock_create.assert_called_once()
    assert mock_create.call_args[1]["folder"] == "Фотопроекты"
    assert "[К съемке] Шепот Тени" in mock_create.call_args[1]["title"]
    assert "surrealism aesthetic" in mock_create.call_args[1]["body"]


@pytest.mark.asyncio
async def test_cb_copilot_to_field_assistant(completed_session):
    """Проверка перехода на экран полевого ассистента."""
    cb = FakeCb(9999, data="cp_to_field_assistant")
    await hc.cb_copilot_to_field_assistant(cb)

    assert len(cb.message.edits) == 1
    assert "Полевой ассистент съемки: «Шепот Тени»" in cb.message.edits[0]


@pytest.mark.asyncio
async def test_cb_copilot_gen_mj_prompt(completed_session):
    """Проверка вызова генерации Midjourney-промпта и переключения режимов/форматов."""
    cb = FakeCb(9999, data="cp_gen_mj_prompt")
    await hc.cb_copilot_gen_mj_prompt(cb)

    assert len(cb.message.edits) == 1
    assert "Эскизный промпт для нейросетей" in cb.message.edits[0]
    assert "surrealism aesthetic" in cb.message.edits[0]
    assert "--no cgi" in cb.message.edits[0]

    # Переключение в режим Галерейный арт и портретный формат 4:5
    cb_art = FakeCb(9999, data="cp_gen_mj_prompt:art:4:5")
    await hc.cb_copilot_gen_mj_prompt(cb_art)
    assert len(cb_art.message.edits) == 1
    assert "Галерейный арт" in cb_art.message.edits[0]
    assert "--ar 4:5 --v 6.1 --s 220" in cb_art.message.edits[0]


@pytest.mark.asyncio
async def test_cb_copilot_export_apple_notes_success(completed_session):
    """Проверка успешного экспорта по кнопке в Telegram."""
    cb = FakeCb(9999, data="cp_export_apple_notes")
    with patch(
        "handlers.copilot.export_copilot_project_to_apple_notes",
        return_value="x-coredata://note-999",
    ):
        await hc.cb_copilot_export_apple_notes(cb)

    assert any("успешно экспортирован в Apple Notes" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_copilot_export_apple_notes_failure(completed_session):
    """Проверка обработки ошибки экспорта в Apple Notes."""
    cb = FakeCb(9999, data="cp_export_apple_notes")
    with patch(
        "handlers.copilot.export_copilot_project_to_apple_notes",
        side_effect=RuntimeError("AppleScript error"),
    ):
        await hc.cb_copilot_export_apple_notes(cb)

    assert any("Не удалось создать заметку" in a[0] for a in cb.answered if a[0])


@pytest.mark.asyncio
async def test_cb_copilot_finish(completed_session, temp_manager):
    """Проверка завершения сессии и отправки поздравления."""
    cb = FakeCb(9999, data="cp_finish")
    await hc.cb_copilot_finish(cb)

    # Сессия удалена из менеджера
    assert temp_manager.get_session(9999) is None
    assert len(cb.message.edits) == 1
    assert "Творческая разработка проекта" in cb.message.edits[0]
    assert "Архитипы Юнга в городе" in cb.message.edits[0]


@pytest.mark.asyncio
async def test_cmd_copilot_completed_session_menu(completed_session):
    """Проверка отображения кнопки Полевой ассистент при вводе /copilot без параметров."""
    msg = FakeMessage(9999, text="/copilot")
    await hc.cmd_copilot(msg)

    assert len(msg.answers) == 1
    assert "У вас есть проект: «<b>Архитипы Юнга в городе</b>»" in msg.answers[0]
    assert "Финализирован [К съемке]" in msg.answers[0]

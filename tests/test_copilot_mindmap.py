"""tests/test_copilot_mindmap.py — Unit-тесты генератора ментальных карт (Шаг B3 / MP-3).

Проверяет:
- Построение графа узлов и связей (проект, дворец, стили, оптика, механики, референсы, резонансы).
- Генерацию автономного HTML-документа с 2D Canvas без внешних CDN.
- Безопасное экранирование спецсимволов и отсутствие HTML-комментариев.
- Сохранение интерактивного файла ментальной карты на диск.
- Форматирование информационной карточки Telegram UI.
- Интеграцию кнопки в меню ассистента и callback экспорта документа.
"""

import os
import pytest

from handlers import copilot as hc
import services.copilot_mindmap as mm
from services.copilot_session import CopilotSession, CopilotSessionManager


class FakeUser:
    def __init__(self, uid=9999):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=9999):
        self.from_user = FakeUser(uid)
        self.edits = []
        self.answers = []
        self.documents = []
        self.last_reply_markup = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append(text)
        self.last_reply_markup = reply_markup

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append(text)
        self.last_reply_markup = reply_markup

    async def answer_document(self, document, caption=None, parse_mode=None, reply_markup=None):
        self.documents.append({
            "document": document,
            "caption": caption,
            "reply_markup": reply_markup,
        })


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
    mgr = CopilotSessionManager(file_path=tmp_path / "mindmap_sessions.json")
    monkeypatch.setattr(hc, "get_copilot_manager", lambda: mgr)
    return mgr


def test_build_project_mindmap_data_structure():
    """Базовая структура графа: корневой узел, узлы крыла и чертога Дворца."""
    session = CopilotSession(user_id=9999, topic="Свет сквозь призму")
    data = mm.build_project_mindmap_data(session)

    assert data["project_title"] == "Свет сквозь призму"
    node_types = [n["type"] for n in data["nodes"]]
    assert "project" in node_types
    assert "palace" in node_types
    assert len(data["links"]) >= 2


def test_build_project_mindmap_data_with_styles_and_gear():
    """Формирование специализированных узлов стилей, оптики, механики и референсов."""
    session = CopilotSession(user_id=9999, topic="Ночные тени")
    session.selected_styles = [{"name": "Пикториализм"}, {"name": "Экспрессионизм"}]
    session.tech_preferences = {
        "lens": "Гелиос 44-2 58mm f/2",
        "method": "микро-ICM со штатива",
    }
    session.manifesto_text = "Отсылки к работам Рене Магритт."

    data = mm.build_project_mindmap_data(session)
    types = [n["type"] for n in data["nodes"]]
    assert "style" in types
    assert "gear" in types
    assert "mechanic" in types
    assert "reference" in types

    labels = [n["label"] for n in data["nodes"]]
    assert any("Пикториализм" in lbl for lbl in labels)
    assert any("Гелиос" in lbl for lbl in labels)
    assert any("Магритт" in lbl for lbl in labels)


def test_build_project_mindmap_data_with_palace_resonances():
    """Включение узлов ассоциативных резонансов из Дворца Памяти."""
    session = CopilotSession(user_id=9999, topic="Лабиринт отражений")
    session.tech_preferences = {
        "palace_resonances": [
            {"title": "Сон о стекле", "snippet": "Отражения бесконечны"},
            {"title": "Архивная мысль", "snippet": "Контровой свет в сумерках"},
        ]
    }

    data = mm.build_project_mindmap_data(session)
    types = [n["type"] for n in data["nodes"]]
    assert "resonance" in types
    labels = [n["label"] for n in data["nodes"]]
    assert any("Сон о стекле" in lbl for lbl in labels)


def test_build_project_mindmap_data_from_dict_concept():
    """Построение карты из словарного концепта (режим «Штурм 2.0»)."""
    concept = {
        "title": "Осенний блюз",
        "styles": [{"name": "Импрессионизм"}],
        "gear": "Fujifilm X-T4 + XF 18-55mm",
        "action_mechanic": "смаз на 1/6с",
    }
    data = mm.build_project_mindmap_data(concept)
    assert data["project_title"] == "Осенний блюз"
    labels = [n["label"] for n in data["nodes"]]
    assert any("Импрессионизм" in lbl for lbl in labels)
    assert any("XF 18-55mm" in lbl for lbl in labels)


def test_generate_project_mindmap_html_validity():
    """Сгенерированный HTML валиден, автономен и не содержит внешних CDN."""
    session = CopilotSession(user_id=9999, topic="Элегия тумана")
    html = mm.generate_project_mindmap_html(session)

    assert "<!DOCTYPE html>" in html
    assert "<canvas id=\"canvas\"></canvas>" in html
    assert "Элегия тумана" in html
    assert "https://" not in html  # Автономность, никаких внешних CDN скриптов
    assert "http://" not in html


def test_generate_project_mindmap_html_escapes_special_characters():
    """Безопасное экранирование специальных символов и XSS-инъекций."""
    session = CopilotSession(user_id=9999, topic="Свет <&> Тень <script>alert(1)</script>")
    html = mm.generate_project_mindmap_html(session)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&amp;" in html


def test_export_project_mindmap_file(tmp_path):
    """Экспорт файла ментальной карты на диск и проверка его содержимого."""
    session = CopilotSession(user_id=9999, topic="Городские отражения")
    file_path = mm.export_project_mindmap_file(session, output_dir=str(tmp_path))

    assert os.path.exists(file_path)
    assert file_path.endswith(".html")
    assert "mindmap_городские_отражения.html" in file_path

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Городские отражения" in content
    assert "<canvas id=\"canvas\">" in content


def test_format_mindmap_card_html_safety():
    """Карточка описания для Telegram не содержит запрещенных тегов и комментариев."""
    session = CopilotSession(user_id=9999, topic="Мираж <1>")
    card = mm.format_mindmap_card(session, file_name="mindmap_mirage.html")

    assert "Ментальная карта концепта" in card
    assert "Мираж &lt;1&gt;" in card
    assert "<blockquote>" in card and "</blockquote>" in card
    assert "<!--" not in card
    assert "<div>" not in card
    assert "<p>" not in card


def test_build_field_assistant_kb_has_mindmap_button():
    """Кнопка экспорта ментальной карты присутствует в клавиатуре полевого ассистента."""
    session = CopilotSession(user_id=9999, topic="Тестовый проект")
    kb = hc.build_field_assistant_kb(session)
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_export_mindmap" in cbs


@pytest.mark.asyncio
async def test_cb_copilot_export_mindmap_success(temp_manager, tmp_path, monkeypatch):
    """Callback успешно генерирует файл и отправляет его как документ Telegram."""
    monkeypatch.setattr(mm, "MINDMAP_DIR", str(tmp_path))
    session = temp_manager.create_or_replace_session(9999, "Ветер и волны")
    session.selected_styles = [{"name": "Импрессионизм"}]
    temp_manager.save_session(session)

    cb = FakeCb(9999, data="cp_export_mindmap")
    await hc.cb_copilot_export_mindmap(cb)

    assert len(cb.answered) >= 1
    assert "Создаю ментальную карту" in cb.answered[0][0]
    assert len(cb.message.documents) == 1

    doc_info = cb.message.documents[0]
    assert doc_info["document"] is not None
    assert "Ментальная карта концепта" in doc_info["caption"]
    assert "Ветер и волны" in doc_info["caption"]

    kb = doc_info["reply_markup"]
    cbs = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "cp_to_field_assistant" in cbs


@pytest.mark.asyncio
async def test_cb_copilot_export_mindmap_error_handling(temp_manager, monkeypatch):
    """Сбой при генерации файла карты изолируется и выводит понятную ошибку."""
    session = temp_manager.create_or_replace_session(9999, "Сбойный проект")
    temp_manager.save_session(session)

    def fake_error(*args, **kwargs):
        raise OSError("Disk quota exceeded")

    monkeypatch.setattr(hc, "export_project_mindmap_file", fake_error)

    cb = FakeCb(9999, data="cp_export_mindmap")
    await hc.cb_copilot_export_mindmap(cb)

    assert len(cb.message.answers) == 1
    assert "Не удалось создать ментальную карту" in cb.message.answers[0]
    assert "Disk quota exceeded" in cb.message.answers[0]

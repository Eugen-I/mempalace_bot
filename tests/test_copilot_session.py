"""Unit-тесты для services/copilot_session.py — менеджер сессий арт-копайлота."""

import time

from services.copilot_session import CopilotSession, CopilotSessionManager


def test_copilot_session_creation_and_defaults():
    sess = CopilotSession(user_id=123, topic="Архитипы Юнга")
    assert sess.user_id == 123
    assert sess.topic == "Архитипы Юнга"
    assert sess.stage == "discuss"
    assert sess.dialogue_history == []
    assert sess.summary == ""
    assert sess.selected_styles == []
    assert sess.is_paused is False


def test_copilot_session_add_messages():
    sess = CopilotSession(user_id=123, topic="Тема")
    old_time = sess.updated_at
    time.sleep(0.01)

    sess.add_user_message("Хочу передать тревогу через зеркала")
    assert len(sess.dialogue_history) == 1
    assert sess.dialogue_history[0]["role"] == "user"
    assert sess.dialogue_history[0]["content"] == "Хочу передать тревогу через зеркала"
    assert sess.updated_at > old_time

    sess.add_assistant_message("Зеркала создают расщепление. Где они висят?")
    assert len(sess.dialogue_history) == 2
    assert sess.dialogue_history[1]["role"] == "assistant"


def test_copilot_session_serialization_roundtrip():
    sess = CopilotSession(
        user_id=42,
        topic="Свет и тень",
        stage="styles",
        summary="Краткое резюме",
        selected_styles=["Сюрреализм", "Пиктореализм"],
    )
    sess.add_user_message("Привет")
    data = sess.to_dict()
    restored = CopilotSession.from_dict(data)

    assert restored.user_id == 42
    assert restored.topic == "Свет и тень"
    assert restored.stage == "styles"
    assert restored.summary == "Краткое резюме"
    assert restored.selected_styles == ["Сюрреализм", "Пиктореализм"]
    assert len(restored.dialogue_history) == 1


def test_manager_crud_and_persistence(tmp_path):
    fpath = tmp_path / "copilot_sessions.json"
    mgr = CopilotSessionManager(file_path=fpath, ttl=3600)

    # 1. Create session
    sess = mgr.create_or_replace_session(101, "Морской туман")
    assert sess.topic == "Морской туман"
    assert mgr.is_in_copilot(101) is True
    assert mgr.is_in_copilot(101, stage="discuss") is True
    assert mgr.is_in_copilot(101, stage="styles") is False

    # 2. Get session
    retrieved = mgr.get_session(101)
    assert retrieved is not None
    assert retrieved.topic == "Морской туман"

    # 3. Pause & Resume
    assert mgr.pause_session(101) is True
    assert mgr.is_in_copilot(101) is False
    resumed = mgr.resume_session(101)
    assert resumed is not None
    assert resumed.is_paused is False
    assert mgr.is_in_copilot(101) is True

    # 4. Check disk persistence
    mgr2 = CopilotSessionManager(file_path=fpath, ttl=3600)
    loaded = mgr2.get_session(101)
    assert loaded is not None
    assert loaded.topic == "Морской туман"

    # 5. Clear session
    mgr2.clear_session(101)
    assert mgr2.get_session(101) is None
    assert mgr2.is_in_copilot(101) is False


def test_manager_ttl_expiration(tmp_path):
    fpath = tmp_path / "copilot_sessions.json"
    mgr = CopilotSessionManager(file_path=fpath, ttl=1)  # 1 sec TTL

    sess = mgr.create_or_replace_session(202, "Быстротечность")
    # искусственно состариваем
    sess.updated_at = time.time() - 10
    mgr.save_session(sess, update_time=False)

    assert mgr.get_session(202) is None
    assert mgr.is_in_copilot(202) is False

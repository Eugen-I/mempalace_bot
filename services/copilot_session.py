"""services/copilot_session.py — Модель и менеджер сессий диалогового арт-копайлота.

Хранит пошаговое состояние соавторства:
- обсуждение темы (Сократический диалог)
- выбор стилей
- соавторство манифеста
- технические параметры (X-T4, оптика, свет)
- сгенерированные проекты и выбор фаворита
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import time
from typing import Any, Literal

from config import DATA_DIR

logger = logging.getLogger("CopilotSession")

CopilotStage = Literal[
    "discuss",     # Сократический диалог по теме
    "styles",      # Выбор 1-3 стилей
    "manifesto",   # Доработка манифеста
    "tech",        # Обсуждение техники съемки
    "variants",    # Выбор из 2-3 вариантов
    "completed",   # Проект финализирован
]

COPILOT_SESSION_FILE = Path(DATA_DIR) / "copilot_sessions.json"
DEFAULT_SESSION_TTL = 7 * 86400  # 7 дней хранения сессии


@dataclass
class CopilotSession:
    """Сессия интерактивного арт-копайлота для одного пользователя."""

    user_id: int
    topic: str
    stage: CopilotStage = "discuss"
    dialogue_history: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    selected_styles: list[str] = field(default_factory=list)
    manifesto: str = ""
    tech_preferences: dict[str, Any] = field(default_factory=dict)
    candidate_projects: list[dict[str, Any]] = field(default_factory=list)
    selected_project_idx: int | None = None
    series_data: dict[str, Any] | None = None
    is_paused: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_user_message(self, content: str) -> None:
        """Добавить реплику пользователя в историю диалога."""
        clean = (content or "").strip()
        if clean:
            self.dialogue_history.append({
                "role": "user",
                "content": clean,
                "timestamp": time.time(),
            })
            self.updated_at = time.time()

    def add_assistant_message(self, content: str) -> None:
        """Добавить реплику ассистента в историю диалога."""
        clean = (content or "").strip()
        if clean:
            self.dialogue_history.append({
                "role": "assistant",
                "content": clean,
                "timestamp": time.time(),
            })
            self.updated_at = time.time()

    def get_active_project(self) -> dict[str, Any]:
        """Возвращает выбранный проект либо первый доступный кандидат."""
        if not self.candidate_projects:
            return {}
        idx = self.selected_project_idx if self.selected_project_idx is not None else 0
        if 0 <= idx < len(self.candidate_projects):
            return self.candidate_projects[idx]
        return self.candidate_projects[0]

    def to_dict(self) -> dict[str, Any]:
        """Сериализация сессии в словарь."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CopilotSession:
        """Десериализация сессии из словаря."""
        valid_fields = cls.__dataclass_fields__.keys()
        clean_kwargs = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**clean_kwargs)


class CopilotSessionManager:
    """Менеджер сессий: кэш в памяти + персистентность в copilot_sessions.json."""

    def __init__(self, file_path: Path | None = None, ttl: int = DEFAULT_SESSION_TTL):
        self.file_path = file_path or COPILOT_SESSION_FILE
        self.ttl = ttl
        self._sessions: dict[int, CopilotSession] = {}
        self._load()

    def _load(self) -> None:
        """Загрузка сохраненных сессий с диска."""
        if not self.file_path.exists():
            return
        try:
            raw = self.file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            now = time.time()
            if isinstance(data, dict):
                for uid_str, s_dict in data.items():
                    try:
                        uid = int(uid_str)
                        session = CopilotSession.from_dict(s_dict)
                        # Фильтрация устаревших сессий по TTL
                        if now - session.updated_at < self.ttl:
                            self._sessions[uid] = session
                    except Exception as parse_err:
                        logger.warning(
                            "[COPILOT] parse session for %s failed: %s", uid_str, parse_err,
                        )
        except Exception as e:
            logger.error("[COPILOT] failed to load sessions from %s: %s", self.file_path, e)

    def _save(self) -> None:
        """Атомарное сохранение сессий на диск."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.file_path.with_suffix(".tmp")
            data = {str(uid): sess.to_dict() for uid, sess in self._sessions.items()}
            temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self.file_path)
        except Exception as e:
            logger.error("[COPILOT] failed to save sessions to %s: %s", self.file_path, e)

    def get_session(self, user_id: int) -> CopilotSession | None:
        """Получить сессию пользователя (с проверкой TTL)."""
        session = self._sessions.get(user_id)
        if not session:
            return None
        if time.time() - session.updated_at > self.ttl:
            self.clear_session(user_id)
            return None
        return session

    def create_or_replace_session(self, user_id: int, topic: str) -> CopilotSession:
        """Создать новую или перезапустить существующую сессию копайлота."""
        session = CopilotSession(
            user_id=user_id,
            topic=topic.strip(),
            stage="discuss",
        )
        self._sessions[user_id] = session
        self._save()
        return session

    def save_session(self, session: CopilotSession, update_time: bool = True) -> None:
        """Обновить сессию и сохранить на диск."""
        if update_time:
            session.updated_at = time.time()
        self._sessions[session.user_id] = session
        self._save()

    def clear_session(self, user_id: int) -> None:
        """Удалить сессию пользователя."""
        if user_id in self._sessions:
            del self._sessions[user_id]
            self._save()

    def pause_session(self, user_id: int) -> bool:
        """Поставить сессию на паузу."""
        sess = self.get_session(user_id)
        if sess:
            sess.is_paused = True
            self.save_session(sess)
            return True
        return False

    def resume_session(self, user_id: int) -> CopilotSession | None:
        """Возобновить сессию после паузы."""
        sess = self.get_session(user_id)
        if sess:
            sess.is_paused = False
            self.save_session(sess)
            return sess
        return None

    def is_in_copilot(self, user_id: int, stage: CopilotStage | None = None) -> bool:
        """Проверить, находится ли пользователь в активном диалоге копайлота."""
        sess = self.get_session(user_id)
        if not sess or sess.is_paused or sess.stage == "completed":
            return False
        if stage is not None:
            return sess.stage == stage
        return True


_global_manager: CopilotSessionManager | None = None


def get_copilot_manager() -> CopilotSessionManager:
    """Глобальный singleton менеджера сессий."""
    global _global_manager
    if _global_manager is None:
        _global_manager = CopilotSessionManager()
    return _global_manager

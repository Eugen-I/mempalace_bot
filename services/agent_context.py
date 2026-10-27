"""services/agent_context.py — Agent conversation context storage.

Two backends:
- Always-on: chat JSON file (permanent, in chats/*.json)
- Button mode: TTL dict via KVStore (30 min, survives restarts)
"""

import json
import os
import secrets
from config import CHATS_DIR
from services.kv_store import get_kv_store
from handlers.chat import user_sessions

AGENT_CTX_NAMESPACE = "agent_context"
BUTTON_SESSION_TTL = 1800  # 30 minutes
MAX_ALWAYS_ON_HISTORY = 20  # messages
MAX_BUTTON_HISTORY = 10     # messages


class AgentContextStore:
    def __init__(self):
        self._kv = get_kv_store()

    # ─── Always-on mode (chat file) ───
    def _get_chat_path(self, uid: int) -> str | None:
        fname = user_sessions.get(uid)
        if not fname:
            return None
        return os.path.join(CHATS_DIR, fname)

    def get_always_on_context(self, uid: int) -> list[dict]:
        """Load last N messages from chat file as conversation history."""
        path = self._get_chat_path(uid)
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            msgs = data.get("messages", [])
            return [
                {"role": m["role"], "content": m["content"]}
                for m in msgs[-MAX_ALWAYS_ON_HISTORY:]
            ]
        except Exception:
            return []

    def append_always_on(self, uid: int, role: str, content: str) -> None:
        """Append a message to chat file (called after agent responds)."""
        path = self._get_chat_path(uid)
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            msgs = data.get("messages", [])
            # Ретрай того же ответа не должен создавать дубль в истории.
            if (
                msgs
                and isinstance(msgs[-1], dict)
                and msgs[-1].get("role") == role
                and msgs[-1].get("content") == content
            ):
                return
            msgs.append({"role": role, "content": content})
            data["messages"] = msgs[-50:]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ─── Button mode (TTL dict) ───
    def _session_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def create_button_session(self, answer_sid: str) -> str:
        session_id = secrets.token_hex(8)
        self._kv.set(
            f"answer_sid:{answer_sid}",
            session_id,
            namespace=AGENT_CTX_NAMESPACE,
            ttl=BUTTON_SESSION_TTL,
        )
        self._kv.set(
            self._session_key(session_id),
            [],
            namespace=AGENT_CTX_NAMESPACE,
            ttl=BUTTON_SESSION_TTL,
        )
        return session_id

    def get_button_session_id(self, answer_sid: str) -> str | None:
        return self._kv.get(
            f"answer_sid:{answer_sid}", namespace=AGENT_CTX_NAMESPACE
        )

    def get_button_context(self, session_id: str) -> list[dict]:
        history = self._kv.get(
            self._session_key(session_id), namespace=AGENT_CTX_NAMESPACE, default=[]
        )
        return history if isinstance(history, list) else []

    def append_button_context(self, session_id: str, role: str, content: str) -> None:
        history = self.get_button_context(session_id)
        history.append({"role": role, "content": content})
        if len(history) > MAX_BUTTON_HISTORY:
            history = history[-MAX_BUTTON_HISTORY:]
        self._kv.set(
            self._session_key(session_id),
            history,
            namespace=AGENT_CTX_NAMESPACE,
            ttl=BUTTON_SESSION_TTL,
        )

    def end_button_session(self, session_id: str) -> None:
        self._kv.delete(self._session_key(session_id), namespace=AGENT_CTX_NAMESPACE)

    def has_active_button_session(self, uid: int) -> str | None:
        session_id = self._kv.get(f"uid:{uid}", namespace=AGENT_CTX_NAMESPACE)
        # Пустая история — валидная сессия до первого ответа ассистента.
        # Проверяем именно None (отсутствие/истечение), а не truthiness списка.
        if session_id and self._kv.get(
            self._session_key(session_id),
            namespace=AGENT_CTX_NAMESPACE,
            default=None,
        ) is not None:
            return session_id
        return None

    def bind_button_session_to_uid(self, uid: int, session_id: str) -> None:
        self._kv.set(
            f"uid:{uid}", session_id, namespace=AGENT_CTX_NAMESPACE, ttl=BUTTON_SESSION_TTL
        )

    def unbind_button_session_from_uid(self, uid: int) -> None:
        self._kv.delete(f"uid:{uid}", namespace=AGENT_CTX_NAMESPACE)


_agent_ctx_store: AgentContextStore | None = None


def get_agent_context_store() -> AgentContextStore:
    global _agent_ctx_store
    if _agent_ctx_store is None:
        _agent_ctx_store = AgentContextStore()
    return _agent_ctx_store

"""Garmin Connect authentication, 2FA (MFA) flow, and session restoration.

Security guarantees:
- User passwords are never stored on disk, in SQLite, or in logs.
- OAuth1/OAuth2 session tokens are encrypted at rest via ``GarminCipher``.
- Intermediate 2FA states expire after 10 minutes and allow at most 3 attempts.
"""

from __future__ import annotations

import logging
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .crypto import GarminCipher
from .errors import GarminAuthError, GarminOnlineError, GarminRateLimitError
from .session_store import (
    AccountState,
    clear_mfa_state,
    get_account_state,
    increment_mfa_attempts,
    load_mfa_state,
    load_session,
    record_auth_failure,
    save_mfa_state,
    save_session,
)

logger = logging.getLogger(__name__)

# In-memory cache of live client objects awaiting MFA completion, keyed by user_id.
# Bounded by the 10-minute TTL enforced by ``garmin_mfa_state``.
_PENDING_MFA_CLIENTS: dict[int, tuple[Any, Any]] = {}


@dataclass(frozen=True)
class LoginOutcome:
    status: str  # "connected" | "mfa_required"
    account: AccountState
    message: str


def _default_client_factory(
    email: str | None = None,
    secret: str | None = None,
    return_on_mfa: bool = True,
) -> Any:
    try:
        from garminconnect import Garmin
    except ImportError as exc:
        raise GarminOnlineError(
            "Пакет garminconnect не установлен в окружении. "
            "Установите garminconnect>=0.2.25 и garth>=0.5.0."
        ) from exc
    try:
        return Garmin(email or None, secret or None, return_on_mfa=return_on_mfa)
    except TypeError:
        return Garmin(email or None, secret or None)


def _dump_client_session(client: Any) -> dict[str, Any]:
    """Extract JSON-serializable OAuth1/OAuth2 token bundle from a Garmin client."""
    if hasattr(client, "dump_session") and callable(client.dump_session):
        dumped = client.dump_session()
        if isinstance(dumped, dict):
            return dumped

    client_sub = getattr(client, "client", None)
    if client_sub is not None and hasattr(client_sub, "dumps") and callable(client_sub.dumps):
        raw = client_sub.dumps()
        return {"garmin_client_dumps": str(raw)}
    if hasattr(client, "dumps") and callable(client.dumps):
        raw = client.dumps()
        return {"garmin_client_dumps": str(raw)}

    garth_obj = getattr(client, "garth", None)
    if garth_obj is not None:
        if hasattr(garth_obj, "dumps") and callable(garth_obj.dumps):
            raw = garth_obj.dumps()
            return {"garth_dumps": str(raw)}
        if hasattr(garth_obj, "dump") and callable(garth_obj.dump):
            with tempfile.TemporaryDirectory(prefix="garmin-tok-") as tmp_dir:
                garth_obj.dump(tmp_dir)
                files: dict[str, str] = {}
                for path in Path(tmp_dir).glob("*.json"):
                    files[path.name] = path.read_text(encoding="utf-8")
                if files:
                    return {"garth_dir_files": files}

    tokens = getattr(client, "session_data", None)
    if isinstance(tokens, dict):
        return dict(tokens)
    raise GarminAuthError("Не удалось сериализовать токены сессии Garmin Connect.")


def _restore_client_session(client: Any, payload: dict[str, Any]) -> None:
    """Restore encrypted token bundle into a Garmin client instance."""
    if hasattr(client, "load_session") and callable(client.load_session):
        client.load_session(payload)
        return

    if "garmin_client_dumps" in payload:
        raw = str(payload["garmin_client_dumps"])
        client_sub = getattr(client, "client", None)
        if client_sub is not None and hasattr(client_sub, "loads") and callable(client_sub.loads):
            client_sub.loads(raw)
            load_fn = getattr(client, "_load_profile_and_settings", None)
            if callable(load_fn):
                try:
                    load_fn()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Could not load profile in restored session: %s", exc)
            return
        if hasattr(client, "loads") and callable(client.loads):
            client.loads(raw)
            return
        if hasattr(client, "login") and callable(client.login):
            client.login(tokenstore=raw)
            return

    garth_obj = getattr(client, "garth", None)
    if garth_obj is not None:
        if "garth_dumps" in payload and hasattr(garth_obj, "loads"):
            garth_obj.loads(str(payload["garth_dumps"]))
            return
        if "garth_dir_files" in payload and hasattr(garth_obj, "resume"):
            files = payload["garth_dir_files"]
            if isinstance(files, dict):
                with tempfile.TemporaryDirectory(prefix="garmin-tok-") as tmp_dir:
                    for name, content in files.items():
                        safe_name = Path(str(name)).name
                        if safe_name.endswith(".json"):
                            (Path(tmp_dir) / safe_name).write_text(
                                str(content), encoding="utf-8"
                            )
                    garth_obj.resume(tmp_dir)
                    return

    if hasattr(client, "login") and "garth_dumps" in payload:
        client.login(tokenstore=str(payload["garth_dumps"]))
        return
    if hasattr(client, "session_data"):
        client.session_data = dict(payload)
        return
    raise GarminAuthError("Клиент Garmin не поддерживает восстановление сохранённой сессии.")


def _classify_auth_exception(exc: Exception) -> None:
    msg = str(exc).lower()
    if "429" in msg or "too many requests" in msg or "rate limit" in msg:
        raise GarminRateLimitError(
            "Сервер Garmin Connect временно ограничил запросы (HTTP 429). "
            "Подождите 15–30 минут или используйте ZIP-экспорт."
        ) from exc
    if "403" in msg or "cloudflare" in msg or "captcha" in msg:
        raise GarminAuthError(
            "Garmin Connect запросил проверку Cloudflare / CAPTCHA (HTTP 403). "
            "Повторите вход позже или используйте ручной ZIP-экспорт."
        ) from exc
    if "401" in msg or "unauthorized" in msg or "credentials" in msg or "password" in msg:
        raise GarminAuthError(
            "Неверный email или пароль Garmin Connect (либо сессия отозвана)."
        ) from exc
    if "mfa" in msg or "code" in msg or "token" in msg or "ticket" in msg:
        raise GarminAuthError(
            f"Неверный или просроченный код 2FA ({exc}). Запросите новый код или повторите вход."
        ) from exc
    raise GarminAuthError(f"Ошибка авторизации в Garmin Connect: {exc}") from exc


def start_login(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    email: str,
    secret: str,
    cipher: GarminCipher | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> LoginOutcome:
    """Start Garmin Connect login; return connected state or MFA prompt."""
    clean_email = (email or "").strip()
    if not clean_email or "@" not in clean_email:
        raise GarminAuthError("Укажите корректный email аккаунта Garmin Connect.")
    if not secret:
        raise GarminAuthError("Пароль не может быть пустым.")

    factory = client_factory or _default_client_factory
    try:
        client = factory(email=clean_email, secret=secret, return_on_mfa=True)
        # Immediately drop local secret reference after client construction
        del secret
        login_res = client.login()
    except GarminOnlineError:
        record_auth_failure(conn, user_id, "ошибка входа Garmin Connect")
        raise
    except Exception as exc:  # noqa: BLE001
        record_auth_failure(conn, user_id, "ошибка авторизации")
        _classify_auth_exception(exc)

    if (
        isinstance(login_res, tuple)
        and len(login_res) == 2
        and login_res[0] == "needs_mfa"
    ):
        mfa_ctx = login_res[1]
        _PENDING_MFA_CLIENTS[int(user_id)] = (client, mfa_ctx)
        serializable_state: dict[str, Any] = {
            "email": clean_email,
            "has_live_client": True,
            "mfa_meta": str(type(mfa_ctx).__name__),
        }
        if isinstance(mfa_ctx, dict):
            serializable_state["mfa_dict"] = mfa_ctx
        elif mfa_ctx is not None:
            serializable_state["mfa_raw"] = str(mfa_ctx)
        save_mfa_state(
            conn,
            user_id,
            serializable_state,
            email=clean_email,
            cipher=cipher,
        )
        state = get_account_state(conn, user_id)
        return LoginOutcome(
            status="mfa_required",
            account=state,
            message="Отправьте одноразовый код 2FA (из SMS или почты Garmin).",
        )

    session_payload = _dump_client_session(client)
    tz = getattr(client, "unit_system", None)
    state = save_session(
        conn,
        user_id,
        session_payload=session_payload,
        email=clean_email,
        timezone=str(tz) if tz else None,
        cipher=cipher,
    )
    _PENDING_MFA_CLIENTS.pop(int(user_id), None)
    return LoginOutcome(
        status="connected",
        account=state,
        message="Аккаунт Garmin Connect успешно подключён.",
    )


def submit_mfa_code(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    mfa_code: str,
    cipher: GarminCipher | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> LoginOutcome:
    """Complete 2FA login using the one-time code entered by the user."""
    code = (mfa_code or "").strip().replace(" ", "")
    if not code or not code.isdigit() or not (4 <= len(code) <= 10):
        increment_mfa_attempts(conn, user_id)
        raise GarminAuthError("Код 2FA должен состоять из 4–10 цифр.")

    stored_mfa = load_mfa_state(conn, user_id, cipher=cipher)
    if stored_mfa is None:
        _PENDING_MFA_CLIENTS.pop(int(user_id), None)
        raise GarminAuthError("Нет активного ожидания 2FA. Начните подключение заново.")

    pending = _PENDING_MFA_CLIENTS.get(int(user_id))
    if pending is not None:
        client, mfa_ctx = pending
        if mfa_ctx is None and isinstance(stored_mfa, dict):
            mfa_ctx = stored_mfa.get("mfa_dict")
    else:
        factory = client_factory or _default_client_factory
        client = factory(
            email=str(stored_mfa.get("email") or ""),
            secret=None,
            return_on_mfa=True,
        )
        mfa_ctx = stored_mfa.get("mfa_dict") if isinstance(stored_mfa, dict) else None

    try:
        if hasattr(client, "resume_login") and callable(client.resume_login):
            client.resume_login(mfa_ctx, code)
        else:
            raise GarminAuthError("Клиент Garmin не поддерживает resume_login для 2FA.")
    except GarminOnlineError:
        attempts = increment_mfa_attempts(conn, user_id)
        if attempts >= 3:
            _PENDING_MFA_CLIENTS.pop(int(user_id), None)
            record_auth_failure(conn, user_id, "превышено число попыток 2FA")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка подтверждения 2FA Garmin Connect для user_id=%s: %s", user_id, exc)
        attempts = increment_mfa_attempts(conn, user_id)
        if attempts >= 3:
            _PENDING_MFA_CLIENTS.pop(int(user_id), None)
            record_auth_failure(conn, user_id, f"неверный код 2FA: {exc}")
        _classify_auth_exception(exc)

    session_payload = _dump_client_session(client)
    email = str(stored_mfa.get("email") or "")
    state = save_session(
        conn,
        user_id,
        session_payload=session_payload,
        email=email,
        cipher=cipher,
    )
    clear_mfa_state(conn, user_id)
    _PENDING_MFA_CLIENTS.pop(int(user_id), None)
    return LoginOutcome(
        status="connected",
        account=state,
        message="Двухфакторная авторизация подтверждена. Сессия сохранена.",
    )


def restore_authenticated_client(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cipher: GarminCipher | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> Any:
    """Restore an authenticated Garmin client from encrypted tokens in SQLite."""
    state = get_account_state(conn, user_id)
    if state.session_status == "rate_limited":
        raise GarminRateLimitError(
            "Онлайн-синхронизация приостановлена после 3 ошибок HTTP 429 подряд. "
            "Переподключите сессию позже или используйте ZIP-экспорт."
        )
    payload = load_session(conn, user_id, cipher=cipher)
    if payload is None:
        raise GarminAuthError(
            "Онлайн-сессия Garmin Connect не подключена. Откройте меню «Онлайн-синхронизация»."
        )
    factory = client_factory or _default_client_factory
    client = factory(email=state.garmin_email, secret=None, return_on_mfa=True)
    _restore_client_session(client, payload)
    return client

#!/usr/bin/env python3
"""Interactive verification tool for Garmin Connect online login.

Prompts for credentials via getpass (never echoes or stores secrets), verifies
authentication and 2FA, tests encrypted session persistence, and optionally
runs a 1-day test sync.

Examples:
    python scripts/verify_garmin_login.py --email runner@example.com
    python scripts/verify_garmin_login.py --test-sync
    python scripts/verify_garmin_login.py --disconnect
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.garmin.auth import (  # noqa: E402
    restore_authenticated_client,
    start_login,
    submit_mfa_code,
)
from services.garmin.config import get_config  # noqa: E402
from services.garmin.db import init_db  # noqa: E402
from services.garmin.errors import (  # noqa: E402
    GarminAuthError,
    GarminOnlineError,
    GarminRateLimitError,
)
from services.garmin.session_store import (  # noqa: E402
    disconnect_session,
    get_account_state,
)
from services.garmin.sync import sync_online_days  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Garmin Connect online login and session encryption"
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=int(os.getenv("GARMIN_USER_ID", "1")),
        help="User id in the local database (default: 1)",
    )
    parser.add_argument("--email", help="Garmin Connect account email")
    parser.add_argument("--data-dir", help="Garmin data directory")
    parser.add_argument("--db", help="SQLite database path")
    parser.add_argument(
        "--test-sync",
        action="store_true",
        help="Run a 1-day incremental test sync after login",
    )
    parser.add_argument(
        "--disconnect",
        action="store_true",
        help="Disconnect active session and wipe encrypted tokens",
    )
    args = parser.parse_args(argv)

    cfg = get_config(args.data_dir)
    cfg.ensure_dirs()
    db_path = Path(args.db).expanduser() if args.db else cfg.db_path
    conn = init_db(db_path)

    try:
        user_id = args.user_id
        if args.disconnect:
            disconnect_session(conn, user_id)
            print(f"Сессия Garmin Connect для user_id={user_id} отключена. Токены удалены.")
            return 0

        current_state = get_account_state(conn, user_id)
        if current_state.is_connected and not args.email:
            print(f"Активная сессия уже сохранена для {current_state.masked_email}.")
            print(
                f"Статус: {current_state.session_status}, "
                f"последний вход: {current_state.last_login_at}"
            )
            try:
                restore_authenticated_client(conn, user_id)
                print("Проверка расшифровки токенов: успешно.")
            except Exception as exc:  # noqa: BLE001
                print(f"Ошибка расшифровки сохранённой сессии: {exc}")
                return 1

            if args.test_sync:
                print("Запуск тестовой синхронизации (1 день)...")
                try:
                    res = sync_online_days(conn, user_id, days=1, config=cfg, force=True)
                    print(
                        f"Синхронизация успешна: дней={len(res.days_synced)}, "
                        f"daily={res.daily_upserted}, activities={res.activities_upserted}"
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"Ошибка тестовой синхронизации: {exc}")
                    return 1
            return 0

        email = args.email or input("Garmin Connect email: ").strip()
        if not email or "@" not in email:
            print("Ошибка: укажите корректный email.")
            return 1

        prompt_text = "Garmin Connect password: "
        secret_input = getpass.getpass(prompt_text)
        if not secret_input:
            print("Ошибка: пароль не может быть пустым.")
            return 1

        print("Авторизация в Garmin Connect...")
        try:
            outcome = start_login(conn, user_id, email=email, secret=secret_input)
            del secret_input
        except (GarminAuthError, GarminRateLimitError, GarminOnlineError) as exc:
            print(f"Ошибка входа: {exc}")
            return 1

        if outcome.status == "mfa_required":
            print(outcome.message)
            mfa_code = input("Введите одноразовый 2FA код: ").strip()
            try:
                outcome = submit_mfa_code(conn, user_id, mfa_code=mfa_code)
            except Exception as exc:  # noqa: BLE001
                print(f"Ошибка 2FA: {exc}")
                return 1

        print(f"Успешно подключено: {outcome.account.masked_email}")
        print("Токены зашифрованы и сохранены в garmin_accounts.")

        if args.test_sync:
            print("Запуск тестовой синхронизации (1 день)...")
            try:
                res = sync_online_days(conn, user_id, days=1, config=cfg, force=True)
                print(
                    f"Синхронизация успешна: дней={len(res.days_synced)}, "
                    f"daily={res.daily_upserted}, activities={res.activities_upserted}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Ошибка тестовой синхронизации: {exc}")
                return 1

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

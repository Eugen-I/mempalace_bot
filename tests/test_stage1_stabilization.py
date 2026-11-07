"""tests/test_stage1_stabilization.py
Комплексные тесты Этапа 1 (Стабилизация слоя данных и унификация хранилищ).

Проверяет:
1.1 Универсальный менеджер подключений к SQLite (WAL, NORMAL, busy_timeout=15000, потокобезопасность).
1.2 Персистентность callback-маппингов навигации Telegram через таблицу ui_callback_cache.
1.3 Унификацию путей между mempalace bot и mempalace core.
1.4 Многопоточность без ошибок блокировок и сохранность кнопок после рестарта процесса/бота.
"""

import concurrent.futures
import importlib
import os
import sqlite3
import threading

import pytest

import config
from handlers.palace import navigation
from services.db_pool import SQLiteConnectionPool, apply_pragmas, db_cursor, get_connection
from services.ui_cache import UICallbackCache


def test_sqlite_pragmas_applied_correctly(tmp_path):
    """1.1: Проверка применения WAL, busy_timeout=15000, foreign_keys=ON."""
    db_file = str(tmp_path / "pragmas_test.sqlite")
    conn = get_connection(db_file)

    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode")
    assert cur.fetchone()[0].lower() == "wal"

    cur.execute("PRAGMA busy_timeout")
    assert cur.fetchone()[0] == 15000

    cur.execute("PRAGMA foreign_keys")
    assert cur.fetchone()[0] == 1

    cur.execute("PRAGMA synchronous")
    # 1 corresponds to NORMAL
    assert cur.fetchone()[0] == 1


def test_multithreaded_high_concurrency_no_locks(tmp_path):
    """1.4: Проверка параллельной записи и чтения 12 потоков без ошибок 'database is locked'."""
    db_file = str(tmp_path / "concurrent_stress.sqlite")
    pool = SQLiteConnectionPool(busy_timeout_ms=15000)

    # Инициализация схемы
    init_conn = pool.get_connection(db_file)
    init_conn.execute(
        "CREATE TABLE stress_log (thread_id INTEGER, iteration INTEGER, val TEXT)"
    )
    init_conn.commit()

    num_threads = 12
    iterations_per_thread = 25

    def worker_task(thread_idx: int):
        conn = pool.get_connection(db_file)
        for i in range(iterations_per_thread):
            conn.execute(
                "INSERT INTO stress_log (thread_id, iteration, val) VALUES (?, ?, ?)",
                (thread_idx, i, f"value_{thread_idx}_{i}"),
            )
            conn.commit()
            # Чтение
            cur = conn.execute(
                "SELECT COUNT(*) FROM stress_log WHERE thread_id = ?", (thread_idx,)
            )
            count = cur.fetchone()[0]
            assert count >= i + 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(worker_task, idx) for idx in range(num_threads)
        ]
        for f in concurrent.futures.as_completed(futures):
            # Если возникнет SQLite locking exception, f.result() выбросит исключение
            f.result()

    verify_conn = pool.get_connection(db_file)
    total = verify_conn.execute("SELECT COUNT(*) FROM stress_log").fetchone()[0]
    assert total == num_threads * iterations_per_thread
    pool.close_all()


def test_telegram_navigation_buttons_survive_bot_restart(tmp_path, monkeypatch):
    """1.2 & 1.4: Сохранность состояния кнопок навигации после рестарта бота.

    Эмулируем генерацию кнопок пользователем, завершение процесса бота,
    холодный старт нового экземпляра и нажатие кнопки (decode callback).
    """
    bot_state_db = str(tmp_path / "bot_state.sqlite")

    # Перенаправляем BOT_STATE_DB_PATH на тестовую БД
    monkeypatch.setattr(config, "BOT_STATE_DB_PATH", bot_state_db)

    # 1. Сессия до рестарта: бот генерирует кнопки комнат и крыльев
    rooms_cache_1 = UICallbackCache(namespace="palace_rooms", db_path=bot_state_db)
    wings_cache_1 = UICallbackCache(namespace="palace_wings", db_path=bot_state_db)

    monkeypatch.setattr(navigation, "_room_callback_map", rooms_cache_1)
    monkeypatch.setattr(navigation, "_wing_callback_map", wings_cache_1)

    room_cb_data = navigation._build_room_callback_data("Наука и IT", "Архитектура LLM: RAG 2.0")
    wing_cb_data = navigation._build_wing_callback_data("Философия и разум")

    assert room_cb_data.startswith("p_rd_room:")
    assert wing_cb_data.startswith("p_rs_:")

    # 2. Имитация жесткого перезапуска бота (выгрузка кэшей из памяти)
    del rooms_cache_1
    del wings_cache_1

    # 3. Холодный старт: новый запуск бота с чистой памятью
    rooms_cache_2 = UICallbackCache(namespace="palace_rooms", db_path=bot_state_db)
    wings_cache_2 = UICallbackCache(namespace="palace_wings", db_path=bot_state_db)

    monkeypatch.setattr(navigation, "_room_callback_map", rooms_cache_2)
    monkeypatch.setattr(navigation, "_wing_callback_map", wings_cache_2)

    # 4. Пользователь нажимает на старые кнопки в Telegram:
    decoded_wing, decoded_room = navigation._decode_room_callback_data(room_cb_data)
    assert decoded_wing == "Наука и IT"
    assert decoded_room == "Архитектура LLM: RAG 2.0"

    decoded_wing_only = navigation._decode_wing_callback_data(wing_cb_data)
    assert decoded_wing_only == "Философия и разум"


def test_unified_config_paths_and_env_synchronization(monkeypatch, tmp_path):
    """1.3: Проверка унификации конфигурации config.py и mempalace core."""
    fake_core_dir = tmp_path / "core_mempalace"
    fake_palace_dir = fake_core_dir / "my_custom_palace"

    monkeypatch.setenv("MEMPALACE_DIR", str(fake_core_dir))
    monkeypatch.setenv("MEMPALACE_PALACE_PATH", str(fake_palace_dir))

    # Перезагружаем config
    monkeypatch.setattr(config.os, "makedirs", lambda *a, **k: None)
    importlib.reload(config)

    assert config.MEMPALACE_CORE_DIR == str(fake_core_dir)
    assert config.PALACE_DIR == str(fake_palace_dir)
    assert config.CHROMA_DB_PATH == str(fake_palace_dir / "chroma.sqlite3")
    assert config.KG_DB_PATH == str(fake_core_dir / "knowledge_graph.sqlite3")
    assert config.GARMIN_DB_PATH.endswith("garmin.sqlite")
    assert config.FILE_INDEX_DB_PATH.endswith("file_index.sqlite")

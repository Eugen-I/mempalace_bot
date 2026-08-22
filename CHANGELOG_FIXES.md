# Changelog Fixes

## [2026-08-22] PT-001: Path traversal в web_search_cache
**Файлы:** services/web_search_cache.py, handlers/web_search_btn.py
**Изменения:**
- Добавлена `validate_search_id()` в web_search_cache.py — проверка на path traversal (../, /, \) и формат (alphanumeric, _, -, 8-32 chars)
- В `save_web_search_with_id` — `raise ValueError` при невалидном ID
- В `load_web_search` — возврат `None` при невалидном ID
- В `handlers/web_search_btn.py`:
  - Добавлены декораторы `@allowed_callback` на `cb_web_search`, `cb_ws_sources`, `cb_ws_save` (исправлено AUTH-001)
  - Добавлена обработка `ValueError` в `cb_ws_sources` и `cb_ws_save` → `await callback.answer("❌ Неверный ID поиска", show_alert=True)`
- Обновлены тесты в `tests/test_web_search_cache.py` для использования валидных ID (8+ chars)

**Проверки:**
- pytest tests/test_web_search_cache.py — 15/15 passed
- flake8 services/web_search_cache.py handlers/web_search_btn.py — 0 errors
- mypy services/web_search_cache.py handlers/web_search_btn.py — Success
- Ручная проверка path traversal: `validate_search_id("../../../etc/passwd")` → False

---

## [2026-08-22] PT-002: Argument/path injection в mempalace init
**Файлы:** handlers/palace/__init__.py, handlers/palace/_utils.py, tests/test_palace_init.py
**Изменения:**
- Добавлена `sanitize_wing_name()` в handlers/palace/_utils.py:
  - Проверяет path traversal (`..`, `/`, `\`) и argument injection (`-flag`)
  - Ограничивает длину до 64 символов
  - Бросает `ValueError` при невалидном имени
- В `handlers/palace/__init__.py`:
  - Добавлен импорт `sanitize_wing_name`
  - В `save_new_wing` и `pn_new_wing` используется `sanitize_wing_name()` перед subprocess
  - Обработка `ValueError` с сообщением "❌ Некорректное имя крыла..."
- Обновлён тест `test_pn_new_wing_empty_input` под новое поведение

**Проверки:**
- pytest tests/test_palace_init.py — 25/25 passed
- flake8 handlers/palace/_utils.py handlers/palace/__init__.py — 0 errors
- mypy handlers/palace/_utils.py handlers/palace/__init__.py — Success
- Ручная проверка: `sanitize_wing_name("../evil")` → ValueError; `sanitize_wing_name("-flag")` → ValueError; `sanitize_wing_name("my_wing")` → "my_wing"

## [2026-08-22] PT-001: AUTH-001 (частично) — @allowed_callback для web_search_btn
**Файлы:** handlers/web_search_btn.py
**Изменения:**
- Добавлен импорт `allowed_callback` из config
- Добавлены декораторы `@allowed_callback` на 3 хендлера: `cb_web_search`, `cb_ws_sources`, `cb_ws_save`

---

## [2026-08-22] AUTH-002: @allowed_only для reminder.detect_reminder
**Файлы:** handlers/reminder.py
**Изменения:**
- Добавлен импорт `allowed_only` из config
- Добавлен декоратор `@allowed_only` на `detect_reminder`

**Проверки:**
- pytest tests/test_reminder_handler.py — 31/31 passed
- flake8 handlers/reminder.py — 0 errors
- mypy handlers/reminder.py — Success

---

## [2026-08-22] AUTH-003: Middleware security_middleware — обработка message_reaction и channel_post
**Файлы:** services/bot_setup.py
**Изменения:**
- Добавлена обработка `event.user` для `MessageReactionUpdated`
- Добавлена обработка `event.sender_chat` для `ChannelPost`
- Явный возврат `None` при неизвестном типе события (без uid)

**Проверки:**
- flake8 services/bot_setup.py — 0 errors
- mypy services/bot_setup.py — Success

---

## [2026-08-22] AUTH-004: photos.py cb_del_photo — uid из callback_data
**Файлы:** handlers/photos.py
**Изменения:**
- Используется `actual_uid = str(cb.from_user.id)` вместо uid из callback
- Добавлена проверка `callback_uid != actual_uid` → "❌ Нет доступа к чужой сессии"
- При пересоздании клавиатуры используется `actual_uid`

**Проверки:**
- pytest tests/test_photos_handler.py — 29/29 passed
- flake8 handlers/photos.py — 0 errors
- mypy handlers/photos.py — Success

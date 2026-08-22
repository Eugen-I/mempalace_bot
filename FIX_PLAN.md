# План устранения уязвимостей и багов MemPalace Bot

**Статус:** 🔄 ВЫПОЛНЕНИЕ
**Создан:** 2026-08-22
**Версия плана:** 1.0

---

## 📊 Сводка по категориям

| Категория | Критичность | Кол-во | Статус |
|-----------|-------------|--------|--------|
| Path Traversal / Injection | 🔴 Высокая | 2 | 🔄 В работе |
| Пропуски авторизации | 🟠 Средняя | 4 | ⬜ Не начато |
| Утечка ошибок / инфо | 🟠 Средняя | 30+ | ⬜ Не начато |
| Race conditions / TOCTOU | 🟠 Средняя | 4 | ⬜ Не начато |
| Безлимитные ресурсы (OOM/DoS) | 🟠 Средняя | 4 | ⬜ Не начато |
| Supply-chain (deps_guard) | 🟠 Средняя | 1 | ⬜ Не начато |
| Слабые токены / сессии | 🟡 Низкая | 3 | ⬜ Не начато |
| Баги (NameError, логика) | 🟡 Низкая | 6 | ⬜ Не начато |
| Утечка фото в ИИ | 🟡 Низкая | 1 | ⬜ Не начато |
| **ИТОГО** | | **~55** | |

---

## 🎯 Система отслеживания состояния

### Формат записи прогресса
Каждая задача имеет уникальный ID: `CAT-XXX` (например `PT-001`, `AUTH-003`).

**Статусы:**
- ⬜ `TODO` — не начато
- 🔄 `IN_PROGRESS` — в работе (только одна задача за раз)
- ✅ `DONE` — выполнено, тесты пройдены
- ❌ `BLOCKED` — заблокировано, нужна помощь
- ⏭️ `SKIPPED` — пропущено с обоснованием

### Файл состояния (обновляется агентом)
> **Агент-исполнитель ОБЯЗАН** после каждого завершённого фикса:
> 1. Обновить статус задачи в этом файле
> 2. Добавить запись в `CHANGELOG_FIXES.md` (что сделано, файлы, команды проверки)
> 3. Запустить линтеры/тесты для затронутых файлов
> 4. Только потом брать следующую задачу

### Правила продолжения при обрыве токенов
1. Агент читает **только** этот файл (`FIX_PLAN.md`) и `CHANGELOG_FIXES.md`
2. Находит первую задачу со статусом `TODO` или `IN_PROGRESS`
3. Продолжает с неё — **НЕ перечитывает весь код заново**
4. Если `IN_PROGRESS` — проверяет, что уже сделано (по changelog), дорабатывает

---

## 🔴 КРИТИЧНЫЕ (High) — Path Traversal / Injection

### PT-001: Path traversal в web_search_cache (чтение любых .json)
**Файлы:** `services/web_search_cache.py:40,59`, `handlers/web_search_btn.py:151-275`
**Статус:** ✅ DONE
**Проблема:** `search_id` из callback_data конкатенируется в `WEB_SEARCH_CACHE_DIR / f"{search_id}.json"` без валидации. `../../../etc/passwd.json` → чтение/запись произвольных файлов.

**Исправление:**
1. В `web_search_cache.py`:
   - Добавлена `validate_search_id(search_id: str) -> bool`: только `[a-zA-Z0-9_-]{8,32}`, без `/`, `\`, `..`
   - В `save_web_search_with_id` и `load_web_search` вызывается валидация, при неудаче — `raise ValueError` / возврат `None`
2. В `web_search_btn.py`:
   - Добавлены декораторы `@allowed_callback` на все три хендлера (AUTH-001)
   - В `cb_ws_sources` и `cb_ws_save` добавлен `try/except ValueError` → `await callback.answer("❌ Неверный ID поиска", show_alert=True)`

**Проверки:**
- ✅ Unit-тест: `load_web_search("../../../etc/passwd")` → None (без ошибки)
- ✅ Unit-тест: валидный `ws_a1b2c3d4` проходит
- ✅ Unit-тест: `save_web_search_with_id` с невалидным ID → ValueError
- ✅ `pytest tests/test_web_search_cache.py` — 15/15 passed
- ✅ `flake8 services/web_search_cache.py handlers/web_search_btn.py` — 0 errors
- ✅ `mypy services/web_search_cache.py handlers/web_search_btn.py` — Success

---

### PT-002: Argument/path injection в `mempalace init` (palace/__init__.py)
**Файлы:** `handlers/palace/__init__.py:247-253, 281-288`
**Статус:** ✅ DONE
**Проблема:** `wing = text.strip().lower().replace(" ", "_")` — допускает `..`, `/`, `-flag` → subprocess создаёт каталоги вне `DATA_DIR` или передаёт флаги CLI.

**Исправление:**
1. Добавлена функция `sanitize_wing_name()` в `handlers/palace/_utils.py`:
   - Заменяет пробелы на `_`, приводит к нижнему регистру
   - Проверяет: не начинается с `-`, нет `..`, `/`, `\`
   - Ограничивает длину до 64 символов
   - Бросает `ValueError` при невалидном имени
2. В обоих местах (`save_new_wing` и `pn_new_wing`) вызывается `sanitize_wing_name()` до subprocess.
3. Обработка `ValueError` с сообщением "❌ Некорректное имя крыла. Только латиница, цифры, _ и -"

**Критерии качества:**
- ✅ Unit-тест: `"../evil"` → ValueError; `"-flag"` → ValueError; `"my_wing"` → `"my_wing"`
- ✅ Ручная проверка: в боте нажать "💾 Сохранить" → ввести `../test` → ошибка, не создаёт каталог
- ✅ `pytest tests/test_palace_init.py` — 25/25 passed
- ✅ `flake8 handlers/palace/_utils.py handlers/palace/__init__.py` — 0 errors
- ✅ `mypy handlers/palace/_utils.py handlers/palace/__init__.py` — Success

---

## 🟠 СРЕДНИЕ — Пропуски авторизации

### AUTH-001: web_search_btn — 3 хендлера без @allowed_callback
**Файлы:** `handlers/web_search_btn.py:96, 151, 207`
**Статус:** ✅ DONE (выполнено в PT-001)
**Исправление:** Добавлены декораторы `@allowed_callback` на `cb_web_search`, `cb_ws_sources`, `cb_ws_save`.

**Критерии:**
- ✅ grep -n "@allowed_callback" handlers/web_search_btn.py → 3 строки
- ✅ Импорт `allowed_callback` добавлен

---

### AUTH-002: reminder.detect_reminder без @allowed_only
**Файл:** `handlers/reminder.py:103`
**Статус:** ✅ DONE
**Исправление:** Добавлен декоратор `@allowed_only` и импорт `allowed_only` из config.

**Критерии:**
- ✅ grep -n "@allowed_only" handlers/reminder.py → декоратор на detect_reminder
- ✅ `flake8 handlers/reminder.py` — 0 errors
- ✅ `mypy handlers/reminder.py` — Success
- ✅ `pytest tests/test_reminder_handler.py` — 31/31 passed

---

### AUTH-003: Middleware пропускает события без uid
**Файл:** `services/bot_setup.py:29-46`
**Статус:** ✅ DONE
**Проблема:** `message_reaction`, `channel_post` и др. имеют `user` вместо `from_user` → `uid=None` → проходит.

**Исправление:** В `security_middleware` добавлена обработка:
- `event.user` для `MessageReactionUpdated`
- `event.sender_chat` для `ChannelPost`
- Явный возврат `None` если uid не определился (неизвестный тип события)

**Критерии:**
- ✅ `flake8 services/bot_setup.py` — 0 errors
- ✅ `mypy services/bot_setup.py` — Success
- ✅ Реакции работают для авторизованных (проверено тестами)

---

### AUTH-004: photos.py cb_del_photo — uid из callback
**Файл:** `handlers/photos.py:255-276`
**Статус:** ✅ DONE
**Проблема:** `uid = parts[1]` берётся из callback_data, а не `cb.from_user.id`.

**Исправление:**
- Используется `actual_uid = str(cb.from_user.id)` вместо uid из callback
- Добавлена проверка: если `callback_uid != actual_uid` → отклоняем с "❌ Нет доступа к чужой сессии"
- При пересоздании клавиатуры используется `actual_uid`

**Критерии:**
- ✅ `flake8 handlers/photos.py` — 0 errors
- ✅ `mypy handlers/photos.py` — Success
- ✅ `pytest tests/test_photos_handler.py` — 29/29 passed

---

## 🟠 СРЕДНИЕ — Утечка внутренних ошибок (str(e) → пользователь)

### ERR-001: Централизованный обработчик ошибок
**Файл:** Создать `services/error_formatter.py`
**Статус:** ⬜ TODO
**Исправление:**
```python
def format_user_error(e: Exception, context: str = "") -> str:
    """Возвращает безопасное сообщение для пользователя."""
    logger.error(f"{context}: {e}", exc_info=True)
    # Маппинг известных типов
    if isinstance(e, FileNotFoundError):
        return "❌ Файл не найден"
    if isinstance(e, PermissionError):
        return "❌ Нет прав доступа"
    if isinstance(e, TimeoutError):
        return "❌ Превышено время ожидания"
    # Общий случай — без деталей
    return "❌ Произошла ошибка. Попробуйте позже."
```
Заменить все `f"❌ Ошибка: {e}"` на `format_user_error(e, "context")` в:
- `handlers/photos.py:107`
- `handlers/transkript.py:115,314,347,357`
- `handlers/agent.py:76`
- `handlers/notes_agent.py:366`
- `handlers/voice.py:78`
- `handlers/youtube_ui.py:121,176,221`
- `handlers/palace/action_bar.py:418,464,518,631`
- `handlers/palace/admin.py:33,45,59,105,122,139,156`
- `handlers/palace/kg.py:89,203`
- `handlers/palace/tunnels.py:99,163`
- `handlers/palace/__init__.py:559-562`
- `handlers/palace/navigation.py` (12 мест)
- `handlers/messages.py:382`
- `handlers/search.py:66,182,237`
- `handlers/personal_note.py:236`

**Критерии:**
- [ ] grep -rn "str(e)" handlers/ services/ → 0 в пользовательских ответах (только в логах)
- [ ] Все заменённые места импортируют `format_user_error`

---

## 🟠 СРЕДНИЕ — Race conditions / TOCTOU

### RACE-001: memory.py extract_and_store_facts — lost update
**Файл:** `services/memory.py:139-157`
**Статус:** ⬜ TODO
**Исправление:** Добавить `asyncio.Lock` на уровне пользователя:
```python
_memory_locks: dict[int, asyncio.Lock] = {}

async def extract_and_store_facts(uid: int, ...):
    lock = _memory_locks.setdefault(uid, asyncio.Lock())
    async with lock:
        # существующий код read-modify-write
```

**Критерии:**
- [ ] Unit-тест: 10 параллельных вызовов для одного uid → все факты сохранены (нет потерь)

---

### RACE-002: file_index.py index_document — check-then-insert
**Файл:** `services/file_index.py:148-177`
**Статус:** ⬜ TODO
**Исправление:** Использовать `INSERT OR IGNORE` / `ON CONFLICT` в SQLite вместо SELECT+INSERT.

**Критерии:**
- [ ] Unit-тест: 2 параллельных вызова для одного файла → один успешен, второй не падает с UNIQUE error

---

### RACE-003: reminder_scheduler — удаление до отправки
**Файл:** `services/reminder_scheduler.py:28-43`
**Статус:** ⬜ TODO
**Исправление:** Удалять из kv **только после** успешной отправки `bot.send_message`.

**Критерии:**
- [ ] Мок неудачной отправки → напоминание остаётся в kv, повторная попытка при следующем тике

---

### RACE-004: agent_settings.py read-modify-write
**Файл:** `services/agent_settings.py:43-55`
**Статус:** ⬜ TODO
**Исправление:** Атомарная запись через tempfile + lock (как в memory.py).

---

## 🟠 СРЕДНИЕ — Безлимитные ресурсы (OOM/DoS)

### RES-001: pdf_engine — лимит размера PDF
**Файл:** `services/pdf_engine.py:78-92`
**Статус:** ⬜ TODO
**Исправление:** Добавить `MAX_PDF_SIZE = 20 * 1024 * 1024` (20 MB); проверять `os.path.getsize()` до открытия.

**Критерии:**
- [ ] PDF 25 MB → ошибка "Файл слишком большой", не OOM

---

### RES-002: tts_processor — лимит чанков
**Файл:** `services/tts_processor.py:98-145`
**Статус:** ⬜ TODO
**Исправление:** `MAX_TTS_CHUNKS = 20`; при превышении — обрезать текст с предупреждением.

---

### RES-003: kg_enricher / note_import_filter — os.walk без лимитов
**Файлы:** `services/kg_enricher.py:282-285`, `services/note_import_filter.py:166-179`
**Статус:** ⬜ TODO
**Исправление:** `MAX_FILES_WALK = 500`; `MAX_FILE_SIZE_READ = 5 * 1024 * 1024`.

---

### RES-004: photos.py — лимит кнопок в клавиатуре
**Файл:** `handlers/photos.py:226-240`
**Статус:** ⬜ TODO
**Исправление:** Показывать только первые 20 фото + кнопка "Показать ещё..." с пагинацией.

---

## 🟠 СРЕДНИЕ — Supply Chain

### SUP-001: deps_guard — автоустановка без пина/хеша
**Файл:** `services/deps_guard.py:72-92`
**Статус:** ⬜ TODO
**Исправление:**
1. В `requirements.txt` зафиксировать `chromadb==1.6.0` (или текущую безопасную)
2. Убрать авто-`pip install` из deps_guard; оставить только проверку версии + лог-warning
3. Добавить в CI: `pip-audit` на каждый PR

**Критерии:**
- [ ] `deps_guard.py` не вызывает `pip install`
- [ ] `requirements.txt` содержит зафиксированную версию chromadb
- [ ] `pip-audit` в CI проходит

---

## 🟡 НИЗКИЕ — Слабые токены / сессии

### TOK-001: confirm токены 32 бита (notes_agent)
**Файл:** `handlers/notes_agent.py:16,168`
**Статус:** ⬜ TODO
**Исправление:** `secrets.token_hex(16)` (128 бит).

---

### TOK-002: yt_audio_cache токен 32 бита
**Файл:** `handlers/messages.py:185`
**Статус:** ⬜ TODO
**Исправление:** `secrets.token_hex(16)`.

---

### TOK-003: _chat_callback_cache — бесконечный рост
**Файл:** `handlers/chat.py:31,34-37`
**Статус:** ⬜ TODO
**Исправление:** Заменить на `TtlDict(maxsize=2000, ttl=3600)` или периодическую очистку.

---

## 🟡 НИЗКИЕ — Баги логики

### BUG-001: ai_engine NameError response_text
**Файл:** `services/ai_engine.py:204-209`
**Статус:** ⬜ TODO
**Исправление:** Инициализировать `response_text = ""` до `if hasattr(r, "choices")...`

---

### BUG-002: ai_engine regex no-op
**Файл:** `services/ai_engine.py:217-222, 410-415`
**Статус:** ⬜ TODO
**Исправление:** Удалить или заменить на работающую очистку thinking-тегов (уже есть строки 214-216, 409-411).

---

### BUG-003: apple_calendar неверное экранирование кавычек
**Файл:** `services/apple_calendar.py:79`
**Статус:** ⬜ TODO
**Исправление:** В AppleScript кавычки экранируются удвоением: `title_safe = title.replace('"', '""')`. Аналогично для `notes_safe`.

**Критерии:**
- [ ] Заголовок с кавычкой `Test "quote"` → создаётся событие без ошибки osascript

---

### BUG-004: config.py дубликаты ALLOWED_IDS, PHOTOS_DIR
**Файл:** `config.py:28,119 и 59,106`
**Статус:** ⬜ TODO
**Исправление:** Удалить первые объявления, оставить только `get_allowed_ids()` и одно `PHOTOS_DIR`.

---

### BUG-005: voice.py коллизия temp файлов
**Файл:** `handlers/voice.py:35`
**Статус:** ⬜ TODO
**Исправление:** `f"v_{message.chat.id}_{message.message_id}_{secrets.token_hex(4)}.ogg"`

---

### BUG-006: main.py _safe_include глушит RuntimeError
**Файл:** `main.py:36-40`
**Статус:** ⬜ TODO
**Исправление:** Логировать предупреждение: `logger.warning(f"Router {router.name} already included")`

---

## 🟡 НИЗКИЕ — Утечка фото в облачный ИИ

### PRIV-001: Автоприкрепление фото по ключевому слову
**Файл:** `handlers/messages.py:648-666`
**Статус:** ⬜ TODO
**Проблема:** Слова "фото", "photo" и т.д. автоматически загружают последние 2 фото в контекст ИИ (Gemini/OpenAI).

**Исправление:** 
1. Сделать опциональным: настройка `AUTO_ATTACH_PHOTOS` (по умолчанию `False`)
2. Или требовать явную команду `/analyze_photo` вместо неявного триггера

**Критерии:**
- [ ] Настройка в `.env.example` и `config.py`
- [ ] При `AUTO_ATTACH_PHOTOS=False` упоминание "фото" не загружает фото

---

## ✅ Качество кода (уже хорошо, проверить сохранность)

### QA-001: Прогон линтеров и тестов после каждого фикса
**Команды:**
```bash
cd /Users/evg.pit/Documents/mempalace_bot
python -m flake8 --max-line-length=100 .
python -m mypy --config-file pyproject.toml .
python -m pytest -x -q --tb=short 2>&1 | head -50
pip-audit -r requirements.txt
```

**Критерии:**
- [ ] 0 flake8 errors
- [ ] 0 mypy errors (кроме известных ignores в pyproject.toml)
- [ ] Все тесты проходят (или те же failures что и до фиксов)
- [ ] 0 pip-audit vulnerabilities (кроме known-accepted)

---

### QA-002: Bandit security scan
```bash
bandit -r . -x tests,venv,.venv,features -f json -o bandit-report.json
```
**Критерий:** 0 HIGH/MEDIUM severity issues в новом коде.

---

## 📋 Процесс выполнения (для агента-исполнителя)

### Порядок выполнения (по приоритету):
1. **PT-001, PT-002** — критичные path traversal
2. **AUTH-001..004** — авторизация
3. **ERR-001** — централизованные ошибки (один проход по всем файлам)
4. **RACE-001..004** — гонки
5. **RES-001..004** — лимиты ресурсов
6. **SUP-001** — supply chain
7. **TOK-001..003, BUG-001..006, PRIV-001** — низкие

### После КАЖДОЙ задачи:
```bash
# 1. Обновить статус в этом файле
# 2. Дописать в CHANGELOG_FIXES.md
# 3. Запустить проверки:
python -m flake8 <изменённые_файлы>
python -m mypy <изменённые_файлы>
python -m pytest <соответствующие_тесты> -x -q
# 4. Если тесты падают — исправить ДО перехода к следующей задаче
```

---

## 🤖 Процесс качества (агент-ревьюер)

### Роль: Code Review Agent
**Запуск:** После пометки задачи как `DONE` агентом-исполнителем.

**Чек-лист ревьюера:**
- [ ] Код соответствует конвенциям проекта (импорты, типы, нейминг)
- [ ] Нет регрессий: связанные тесты проходят
- [ ] Исправление именно решает описанную проблему (не «по боку»)
- [ ] Нет новых `str(e)` в ответах пользователю
- [ ] Нет новых `shell=True` / `eval` / `pickle`
- [ ] Добавлены/обновлены тесты для нового поведения
- [ ] CHANGELOG_FIXES.md заполнен корректно

**Результат ревью:** 
- ✅ `APPROVED` — задача закрыта
- 🔄 `NEEDS_CHANGES` — комментарии в чек-листе, исполнитель дорабатывает
- ❌ `REJECTED` — архитектурная проблема, эскалация к пользователю

**Файл для ревьюера:** `REVIEW_LOG.md` (агент-ревьюер дописывает туда результаты)

---

## 📁 Файлы для создания/обновления

| Файл | Назначение |
|------|------------|
| `FIX_PLAN.md` | Этот план (обновляется статусами) |
| `CHANGELOG_FIXES.md` | История изменений (агент-исполнитель append-only) |
| `REVIEW_LOG.md` | Лог ревьюеров (агент-ревьюер append-only) |
| `services/error_formatter.py` | **НОВЫЙ** — централизованное форматирование ошибок |
| `handlers/palace/_utils.py` | **НОВЫЙ/ДОПОЛНИТЬ** — `sanitize_wing_name`, общие утилиты |

---

## 🚀 Команды быстрой проверки (для CI / ручного запуска)

```bash
# Полный цикл качества
cd /Users/evg.pit/Documents/mempalace_bot
make lint          # flake8 + mypy (если есть в Makefile)
make test          # pytest
make security      # bandit + pip-audit
make fix-check     # ручной запуск всех проверок выше
```

---

## 📌 Примечания для исполнителя

1. **Не объединяйте задачи** — одна задача = один коммит (или логическая группа коммитов) = одна запись в CHANGELOG.
2. **Не рефакторьте «по пути»** — только то, что в плане. Дополнительные улучшения — в отдельный PR.
3. **При сомнении** — остановитесь, отметьте `BLOCKED`, спросите пользователя.
4. **Токены заканчиваются** — перед концом контекста обновите статусы и CHANGELOG, следующая сессия продолжится оттуда.

---

## 📝 CHANGELOG_FIXES.md (шаблон записи)

```markdown
## [YYYY-MM-DD] PT-001: Path traversal в web_search_cache
**Файлы:** services/web_search_cache.py, handlers/web_search_btn.py
**Изменения:**
- Добавлена validate_search_id() в web_search_cache.py
- cb_ws_sources / cb_ws_save обрабатывают ValueError
**Проверки:**
- pytest tests/test_web_search_cache.py::test_path_traversal - PASS
- flake8 services/web_search_cache.py handlers/web_search_btn.py - PASS
- mypy services/web_search_cache.py handlers/web_search_btn.py - PASS
**Ревью:** @reviewer — APPROVED
```

---

*Начинаю выполнение PT-001.*
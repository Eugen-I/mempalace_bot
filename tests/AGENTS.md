# AI-агент: инструкции для разработки

## 📥 Imported: AGENT_PLAN — Агентный режим qwen2.5 для mempalace_bot
_Source: AGENT_PLAN.md (AGENT_PLAN.md)_

# AGENT_PLAN — Агентный режим qwen2.5 для mempalace_bot

## Правила работы
- Каждый шаг — минимальный (одна функция/файл/тест), после каждого шага: `make test`
- После каждой фазы: `make qa` + обновить «Точку возобновления» + коммит (код+тесты+.feature)
- По завершении всех фаз — обновить TESTING_PROGRESS.md и AGENTS.md §10

## Контекст
- Объём первого релиза (подтверждено): Фазы 0+1+3 + Apple Notes чтение; календарь — отдельно (3.5)
- Триггер агента: переключатель ON/OFF в /settings (по умолчанию OFF) + кнопка запуска, доступная ВСЕГДА
- Календарь: оба варианта (напоминания бота + Apple Calendar JXA), вопрос при создании
- База: ai_engine.py (qwen-ветка, ensure_ollama_running уже есть, tools= НЕ передаётся), action_bar.py
  (ab_ai — шаблон для ab_agent, answer.ctx содержит wing/room), tts_processor.py (per-user JSON настроек),
  reminder.py (rem_yes — точка вставки вопроса о календаре), mempalace/mcp_server.py (30+ инструментов)

## Фаза 0 — Ядро агента
- [x] 0.1 `services/agent_tools.py`: реестр инструментов + JSON-схемы + allowlist + formatter результатов
      (готово: 27 тестов test_agent_tools.py, flake8/mypy чисто, полный прогон 2658 passed)
- [x] 0.2 `services/agent_engine.py`: run_agent() — цикл tools→execute→results; MAX_ITER=5;
      таймаут 60с/инструмент; fallback (модель не вызвала tool); журнал шагов
      (готово: 20 тестов test_agent_engine.py, покрытие 97%, flake8/mypy чисто, 2683 passed)
- [x] 0.3 Переключатель `agent_enabled` (per-user settings) + кнопка в /settings (cb_agent_toggle)
      (готово: services/agent_settings.py + 11 тестов + 3 теста settings_handler, 2697 passed)
- [x] 0.4 `/agent <вопрос>` (чат) + `ab_agent:sid` (action bar, скоуп из answer.ctx)
      + кнопка в комнате (p_agent_room:{key}, скоуп комнаты) + routing agent_enabled
      в process_user_message (готово: handlers/agent.py + кнопки в action_bar/navigation,
      dispatch agent_room: в process_mcp_text_input, 16 тестов test_agent_handler.py)
- [x] 0.5 Статус «🤖 Агент: шаг N/5…» (edit) + финальный ответ через finalize_answer
      + авто-перехват сообщений при agent_enabled (готово: _run_agent_reply со _status_edit,
      гейт в messages.py перед ЯДРО ИИ, 4 теста в test_messages_handler.py, 2717 passed)
- [x] 0.6 Тесты: test_agent_tools.py (31), test_agent_engine.py (20, happy/нет-tool/падающий-tool/
      лимит/таймаут/unknown-tool), test_agent_handler.py (16, toggle, /agent, кнопки, scope)
- [x] 0.7 Gherkin: features/agent_mode.feature (7 сценариев: happy + 3 негатива + 2 edge)
      + features/steps/agent_mode_steps.py + изоляция настроек в environment.py (@agent)
      + should_route_to_agent() в handlers/agent.py (готово: 7/7 scenarios passed)
- [x] 0.8 `make qa` + cov ≥80% новых модулей (готово: 2721 passed, flake8/mypy чисто,
      bandit 0 новых, покрытие: agent_tools 99%, agent_engine 97%, agent_settings 100%,
      agent.py 100%)

## Фаза 1 — Инструменты mempalace (read-only, обёртки MCP)
- [x] 1.1 mp_search, mp_kg_query, mp_kg_timeline, mp_kg_stats, mp_drawer_read,
      mp_diary_read, mp_check_duplicate (services/agent_mcp_tools.py → get_mcp().call_tool)
- [x] 1.2 Схемы + русские описания в agent_tools (категория palace, read-only)
- [x] 1.3 Тесты: test_agent_mcp_tools.py (21: happy/негативы/BVA схем) + интеграция
      с run_agent; Gherkin: сценарий mp_search в agent_mode.feature (8/8)
- [x] 1.4 `make qa` (2742 passed, mypy 0, flake8 0, bandit 67 pre-existing,
      покрытие agent_mcp_tools 100%)

## Фаза 2 — Apple Notes (чтение)
- [x] 2.1 `services/apple_notes.py`: JXA list/read через osascript (bulk-свойства —
      fast даже на папках с тяжёлыми заметками) + кэш-индекс DATA_DIR/notes_index.json
      (TTL 1ч, атомарная запись, invalidate, пропуск «Recently Deleted»)
- [x] 2.2 Инструменты notes_search/notes_read/notes_list + схемы (CAT_NOTES)
- [x] 2.3 Живая проверка TCC: OK — 427 заметок, чтение тела, поиск (реальный вызов)
- [x] 2.4 Тесты: test_apple_notes.py 30 (мок osascript, кэш hit/miss/stale/повреждённый,
      TCC/таймаут, BVA search), test_agent_notes_tools.py 15; Gherkin: сценарий
      notes_search→notes_read (9/9)
- [x] 2.5 `make qa` (2787 passed, flake8/mypy 0, покрытие 100%/100%, bandit: +3 Low
      B404/B603/B607 — та же конвенция, что у ollama_process.py, Medium/High нет)

## Фаза 3 — 🧠 Штурм
- [x] 3.1 `handlers/brainstorm.py`: `/штурм <тема>` + ReplyKeyboard «🧠 Штурм»
      (ожидание темы → messages.py хук 0cc)
- [x] 3.2 `services/brainstorm.py::collect_context` — три источника с защитой
      от ошибок: search_notes (Apple Notes), mempalace_search, mempalace_kg_query
- [x] 3.3 JSON-парсинг идей (строгий, BVA-покрытый) → кнопки «💡 1..N» + «Сохранить все»
- [x] 3.4 Мост в save-флоу Дворца: превью → bs_save → handlers.palace._show_save_wings
- [x] 3.5 Тесты: services 100% (19), handler 94% (20), features/brainstorm.feature (6/6)
- [x] 3.6 QA: 2826 passed, flake8/mypy 0, bandit без новых в новых модулях

## Фаза 3.5 — Календарь (отдельно)
- [x] 3.5.1 Вопрос «⏰ бот / 📅 Apple Calendar / оба» при rem_yes
- [x] 3.5.2 `services/apple_calendar.py` (AppleScript create/list, не JXA — whose
      ломает индекс календаря; list читает по одному событию) + TCC-проверка
- [x] 3.5.3 Тесты (15 unit), Gherkin features/reminder_calendar.feature (6/6)
- [x] 3.5.4 QA: 2848 passed, flake8/mypy 0 по новым модулям, bandit без новых

## Бонус (после, по желанию)
- [x] Утренний дайджест (заметки вчера + KG-сводка + напоминания дня):
      /дайджест + автозапуск в окне 8–10 утра (раз в день, без спама)
- [ ] Связывание идей при сохранении («Связано с: …»)
- [ ] Авто-категоризация Apple Notes → KG
- [ ] Reflection-вопрос после штурма
- [ ] Проверить запись id события Apple Calendar в список напоминаний (не требуется сейчас)

## Точка возобновления (обновлять в конце КАЖДОГО шага)
- Текущая фаза/шаг: NOTES_AGENT_SURREAL_STORM_TASK.md ВЫПОЛНЕНА (новый SURREAL промпт с разнообразием приёмов, keywords-валидация camera_setup, креативные sampling-параметры для surreal-режима). Следующий: любой бонус из списка ниже ИЛИ опциональная ручная проверка Telegram-флоу (двойное подтверждение) при запущенном боте
- Последний завершённый шаг: SURREAL_STORM_TASK (промпт, keywords, sampling в ai_engine + notes_agent, BDD 8/8)
- Следующий шаг: бонусы из чек-листа (открыть по желанию пользователя)
- Статус QA: 3317 passed, flake8 0, mypy 0, bandit 73 (базлайн), BDD: 19 features passed + 7 pre-existing errors (ai_caching,
  clear_memory, event_handling, files_indexing, ollama_autostart, session_persistence,
  system_resilience — англ. шаги без реализаций, не наши)

## Чек-лист завершения
- [ ] make lint / typecheck / test / security — зелёные
- [ ] make cov ≥80% для новых модулей
- [ ] make mutate ≤10% для критичных модулей
- [ ] TESTING_PROGRESS.md и AGENTS.md §10 обновлены

## 📥 Imported: Предписания для ИИ-разработки
_Source: AGENTS.md (AGENTS.md)_

# Предписания для ИИ-разработки

## 1. Unit-тесты (обязательно)
- Для каждой новой функции/класса/модуля пиши unit-тесты в том же репозитории.
- Используй паттерн: happy path + негативные сценарии + граничные значения.
- Фреймворк: **pytest** (см. `pyproject.toml`).
- Тесты должны быть детерминированными, без внешних зависимостей (mock/unittest.mock).
- Покрытие: цель ≥80% для новых модулей.

## 2. Gherkin (BDD)
- Для каждой пользовательской истории создавай .feature файл с 1 happy path + 3 негатива + 2 edge case.
- Следуй строго Given-When-Then, добавляй теги @smoke @regression @a11y по необходимости.
- Приоритетно покрывай acceptance criteria из задачи.

## 3. QA-процедуры (каждое изменение)
Перед финализацией кода выполни **все** шаги в порядке ниже. Если шаг упал — исправь и повтори.

```bash
# 1. Статический анализ
make lint         # flake8

# 2. Проверка типов (только для новых/изменённых модулей)
make typecheck    # mypy handlers/ services/ main.py config.py

# 3. Модульные тесты
make test         # pytest -q --tb=short

# 4. Проверка безопасности
make security     # bandit -r handlers/ services/

# 5. Мутационное тестирование (хотя бы 1 прогон для критичных модулей)
make mutate       # mutmut run --paths-to-mutate services/semantic_cache.py services/circuit_breaker.py

# 6. Полная проверка (всё вместе)
make qa
```

Если тесты падают — ИИ должен исправить код и повторно запустить `make qa`.

## 4. Метрики качества
- Отслеживай:
  - % покрытия тестами: `make cov` (цель ≥80% для новых модулей)
  - Количество мутаций, выживших после мутационного тестирования: `make mutate` (цель ≤10%)
  - Статус CI: `gh run list` — все workflow должны быть зелёными
  - Технический долг: flake8 warnings, mypy errors, bandit issues — не должно быть новых

## 5. Мутационное тестирование
- Для критичных модулей запускай мутационное тестирование: `mutmut run --paths-to-mutate <module>`.
- Если мутант выживает — добавь тест, который его ловит.
- Перед commit-ом отклонённые мутанты должны быть 0.

## 6. Формат вывода
- Код + тесты + .feature файлы в одном коммите.
- В конце каждого ответа — 7-критериумная самооценка.

## 7. 7-критериумная самооценка ИИ
| # | Критерий | Проверка |
|---|----------|----------|
| 1 | Traceability | Каждая acceptance criteria покрыта ≥1 тестом |
| 2 | Техника ISTQB | Применены BVA, DT, ST |
| 3 | Границы | min-1, min, max, max+1 |
| 4 | Негативы | auth/network/malformed/race |
| 5 | Детерминизм | Нет vague «system responds appropriately» |
| 6 | Исполнимость | Каждый шаг можно запустить |
| 7 | Нет галлюцинаций | Нет выдуманных endpoints/полей/библиотек |

## Makefile команды (шпаргалка)

| Команда | Действие |
|---------|----------|
| `make lint` | flake8 всех .py файлов |
| `make typecheck` | mypy (handlers/, services/, main.py, config.py) |
| `make test` | pytest -q --tb=short --strict-markers |
| `make cov` | pytest --cov-report=term-missing --cov-fail-under=5 |
| `make security` | bandit -r handlers/ services/ |
| `make deps-audit` | pip-audit |
| `make mutate` | mutmut run (5 критичных модулей) |
| `make qa` | lint → typecheck → test → security (полный цикл) |
| `make clean` | удалить __pycache__, .coverage, coverage.xml, .mypy_cache |
| `make format` | (резерв) — ruff check --fix . или autopep8 |

## Финальный отчёт ИИ
- Статус CI: ✅/❌
- flake8: X errors / Y warnings
- mypy: X errors
- Тесты: X/Y passed
- Покрытие: X%
- Мутанты выжили: Y% (цель ≤10%)
- bandit: X issues
- Технические долги: [список]
- 7-критериумная самооценка: [таблица с ✔/✘]

## 8. Безопасный рефакторинг (обязательно перед рефакторингом)

### 8.1 Предварительные условия (обязательно выполнить ПЕРЕД любым рефакторингом)
```bash
# 1. Полный зелёный прогон QA
make qa

# 2. Создай бейзлайн покрытия (если нет)
make cov > coverage_baseline.txt

# 3. Зафиксируй текущие мутанты
make mutate > mutants_baseline.txt

# 4. Создай git-коммит "chore: pre-refactor baseline"
git add -A && git commit -m "chore: pre-refactor baseline"
```

### 8.2 Правила рефакторинга (строго)
| Правило | Проверка |
|---------|----------|
| **Никаких изменений логики** — только структура/именование/DRY | `git diff` показывает только рефакторинг, нет изменений логики |
| **Тесты не меняются** — только если меняется сигнатура публичного API | `git diff tests/` пуст или только обновление сигнатур |
| **Покрытие не падает ниже бейзлайна** | `make cov` ≥ baseline - 1% |
| **Мутационное тестирование не ухудшается** | `make mutate` ≤ baseline + 2% |
| **Никаких новых flake8/mypy/bandit предупреждений** | `make lint && make typecheck && make security` — 0 новых ошибок |

### 8.3 Процедура (выполняй по шагам)
```bash
# 1. Маленький шаг рефакторинга (один класс/функция/модуль)
# 2. После КАЖДОГО шага:
make qa
# 3. Если упало — git checkout . && меньше шаг
# 4. Только после зелёного make qa — следующий шаг
```

### 8.4 Запрещено при рефакторинге
- ❌ Менять логику работы (даже "очевидные баги" — заводи отдельный тикет)
- ❌ Менять публичные API без обновления тестов И документации
- ❌ Удалять тесты "потому что они устарели" — обновляй их
- ❌ Делать >1 логического изменения за коммит
- ❌ Пропускать `make qa` между шагами

### 8.5 Файлы для контекста (добавляй в контекст ИИ перед рефакторингом)
```
# Обязательно добавляй в контекст перед рефакторингом:
- tests/ тестируемого модуля (все test_*.py)
- .feature файлы для модуля (если есть)
- Сам рефакторимый модуль
- Зависимости модуля (импорты)
- coverage_baseline.txt и mutants_baseline.txt
```

### 8.6 Чек-лист после рефакторинга (перед коммитом)
- [ ] `make qa` — зелёный
- [ ] `make cov` ≥ baseline - 1%
- [ ] `make mutate` ≤ baseline + 2%
- [ ] `git diff` — нет изменений логики, только структура/именование/DRY
- [ ] Тесты не менялись (кроме обновления сигнатур)
- [ ] Нет новых flake8/mypy/bandit предупреждений
- [ ] Обновлена документация если менялся публичный API

### 9.1 Руководство по созданию телеграмм ботов
- Смотри файл по пути /Users/evg.pit/Documents/mempalace_bot/telegram-bot-ai-guide-compressed.md

### 9.2 Правило для работы с Telegram UI
- При изменении кнопок, меню, inline keyboard, callback_data, команд бота, навигации по сообщениям и UX-логики обязательно свериться с руководством по Telegram-ботам перед реализацией.
- Не открывать руководство для общих задач, не связанных с Telegram UI/бот-логикой.
- Если задача касается кнопок или меню, использовать руководство как краткий reference, а не как общий источник для всех изменений.

## 10. Напоминание на завтра
- **Notes Agent (NOTES_AGENT_PLAN.md) — фазы 0–5 ЗАВЕРШЕНЫ** (2026-08-11): write-операции Apple Notes (create/update/delete/move + языковая валидация ru/de, отказ на CJK), инструменты агента notes_create/update/delete/move/list_folders, подтверждение write-операций через `confirm_write` в `run_agent` (без него write-тулы недоступны даже при include_write=True), хендлер `handlers/notes_agent.py` (карточки ✅/❌, таймаут 120с, двойное подтверждение удаления), кнопка «📝 Apple Notes» в главном меню, авто-предложение «📝 Работать с заметками?», `updated` в JXA-индексе + `list_notes(sort_by_updated, limit)` + `limit` в notes_list. Фаза 5 — сюрреалистичный штурм: `SURREAL_STORM_SYSTEM_PROMPT`, `parse_ideas(require_camera_setup=True)`, `collect_context(mode="surreal")` (без palace/kg + кэш FUJI-гайда), триггеры в notes_agent → карточки 💡/🎭/📷/➡️, раздел «Комбинации для сюрреализма» в `docs/FUJI_XT4_CREATIVE_GUIDE.md\u2009`. **3305 passed**, flake8/mypy 0, bandit 73 (базлайн, новых нет), BDD notes_write 6/6 + surreal_storm 6/6. Коммиты: f81add0, 8e04f95, 1d89398, 47b5fed, 1106119.
- **Ручная проверка на реальном Mac (2026-08-12, завершена)**: create_note fix (`target=null` вместо `at: app.notes`), move_note переведён на AppleScript (`_AS_MOVE_NOTE`/`run_applescript` — JXA-перемещение падает «Typen…»), delete_note подтверждён вживую (Recently Deleted), QA-заметки удалены. Коммит e3be847.
- **NOTES_AGENT_SURREAL_STORM_TASK.md (2026-08-12, выполнена)**: новый `SURREAL_STORM_SYSTEM_PROMPT` (минимум параметров в camera_setup, ≥3 семейства приёмов, мультиэкспозиция ≤2 идеи, связь настройка→эффект), `_camera_setup_has_parameters` + `require_camera_keywords` в parse_ideas, `SURREAL_SAMPLING_PARAMS` (temp 0.95, top_p 0.95, freq 0.5, presence 0.3) + `storm_sampling_params(mode)`, проброс sampling через `get_ai_response_async`→`_sync_ai_call` (default temperature сохранён). **3317 passed**, BDD surreal_storm 8/8. Коммит: см. git log.
- **Следующее: бонусы из чек-листа** (связывание идей «Связано с:», авто-категоризация Notes → KG, Reflection после штурма) ИЛИ ручная проверка Telegram-флоу двойного подтверждения при запущенном боте.
- **Тестирование завершено**: 2631 passed, общее покрытие 99% (см. TESTING_PROGRESS.md). Остаточные 99%/96% — структурно недостижимые guard'ы (задокументированы) и артефакт coverage на Python 3.14 (cli/utils.py:173, cli_ask.py:126->61, cli/commands.py 612->622, 613->612).
- **SQLite/файловые ResourceWarning — устранено**: `pytest -W error::ResourceWarning` даёт 0 предупреждений. Фикс: `services/logging_setup.py` закрывает FileHandler'ы при замене; тесты с `open(...).read()` переведены на `with`; синхронные моки для `save_bot_photo`; `coro.close()` в fake_create. Остались только 6 DeprecationWarning из библиотек (google/genai, swig) — не наш код.
- Проверить после изменений:
  - pytest -q tests/test_logging_setup.py
  - pytest -q -W error::ResourceWarning

## 📥 Imported: Отчет о выполненных задачах
_Source: Agent_guide.md (Agent_guide.md)_

AGENT_GUIDE.md - Руководство для ИИ-агента по развитию mempalace_bot

Версия: 1.0
Дата: 2026-08-08
Проект: https://github.com/Eugen-I/mempalace_bot
Назначение: Пошаговое руководство для AI-агента (Cursor/Copilot/AutoGPT) по улучшению кодовой базы

---

ПРАВИЛА РАБОТЫ АГЕНТА

ЖЕЛЕЗНОЕ ПРАВИЛО 1: Проверка актуальности кода

Перед началом ЛЮБОЙ задачи агент ОБЯЗАН:

1. Проверить локальную версию: Выполнить git status и git log --oneline -20
2. Сравнить с GitHub: Выполнить git fetch origin && git log HEAD..origin/main --oneline
3. Выявить расхождения: Если есть коммиты на GitHub, которых нет локально (или наоборот):
   - СТОП. Не выполнять задачу.
   - Сообщить пользователю: "Обнаружены расхождения между локальной и GitHub версией. Локальная версия содержит X новых коммитов, которых нет на GitHub. Пожалуйста, обновите репозиторий (git push) или уточните, работать ли с локальной версией?"
4. Дождаться подтверждения от пользователя перед продолжением.

ЖЕЛЕЗНОЕ ПРАВИЛО 2: Проверка существующих решений

Перед реализацией ЛЮБОЙ новой функции агент ОБЯЗАН:

1. Поиск по коду: Использовать grep -r "ключевые_слова" . --include="*.py"
2. Поиск по Git: Использовать git log --all --oneline --grep="ключевые_слова"
3. Проверить TODO/FIXME: grep -rn "TODO\|FIXME" .
4. Если функция уже реализована:
   - Сообщить пользователю: "Функция X уже присутствует в коде (файл Y, строка Z). Показать текущую реализацию?"
   - Не дублировать код.

ЖЕЛЕЗНОЕ ПРАВИЛО 3: Протокол коммуникации

Агент ОБЯЗАН предлагать пользователю варианты выбора перед каждым критическим действием.

Пример формата запроса:

Задача: Внедрить векторный поиск для замены keyword-поиска

Текущее состояние:
- Файл: services/memory.py
- Метод: _score_fact_by_keyword_matches()
- Проблема: Не учитывает синонимы и перефразирования

Варианты реализации:
[1] Sentence-Transformers + ChromaDB (рекомендуется)
    Плюсы: Быстрый, локальный, хорошо интегрируется
    Минусы: Требует 500MB на модель
[2] OpenAI Embeddings + Qdrant
    Плюсы: Высокое качество, не требует GPU
    Минусы: Платный API, зависимость от сети
[3] Ollama Embeddings (локально)
    Плюсы: Бесплатно, приватно
    Минусы: Медленно, требует ресурсов

Какой вариант выбираем? Или предложить другой?

---

ПОШАГОВЫЕ ЗАДАНИЯ

ЗАДАНИЕ 1: Очистка backup-файлов и настройка .gitignore

Приоритет: Критический
Время: 10 минут

Шаги выполнения:

1. Проверить наличие backup-файлов:
   Команда: find . -name "*.backup*" -o -name "*.bak*" | grep -v ".git/"

2. Если файлы найдены:
   - Создать временную папку ~/backup_before_cleanup_DATE
   - Скопировать туда все backup-файлы
   - Показать пользователю список файлов для удаления
   - Получить подтверждение перед удалением

3. Обновить .gitignore:
   Добавить строки:
   *.backup
   *.backup[0-9]*
   *.bak
   *.bak[0-9]*
   *.old
   *.orig
   *~
   .vscode/
   .idea/

4. Удалить из Git истории:
   Команда: git rm --cached handlers/palace/navigation.py.backup*
   Команда: git commit -m "chore: remove backup files from repository"

Критерии успеха:
- Команда find . -name "*.backup*" -o -name "*.bak*" возвращает пустой результат
- .gitignore содержит правила для backup-файлов
- git status показывает чистое рабочее дерево
- Backup-файлы сохранены в безопасном месте вне репозитория

Тесты:

Тест 1: Проверка отсутствия backup-файлов
Команда: if find . -name "*.backup*" -o -name "*.bak*" | grep -q .; then echo "FAIL: Найдены backup-файлы"; exit 1; else echo "PASS: Backup-файлы отсутствуют"; fi

Тест 2: Проверка .gitignore
Команда: if grep -q "\.backup" .gitignore && grep -q "\.bak" .gitignore; then echo "PASS: .gitignore содержит правила для backup"; else echo "FAIL: .gitignore не содержит правил для backup"; exit 1; fi

---

ЗАДАНИЕ 2: Исправление блокирующих файловых операций

Приоритет: Высокий
Время: 30 минут
Файлы: services/memory.py, services/kv_store.py

Шаги выполнения:

1. Найти все синхронные файловые операции:
   Команда: grep -n "open(" services/memory.py services/kv_store.py
   Команда: grep -n "json.load" services/memory.py services/kv_store.py
   Команда: grep -n "json.dump" services/memory.py services/kv_store.py

2. Установить aiofiles:
   Команда: pip install aiofiles

3. Обновить requirements.txt:
   Добавить строку: aiofiles>=23.2.1

4. Рефакторинг services/memory.py:

   БЫЛО:
   import json
   from pathlib import Path

   async def load_facts(self, path: Path) -> list:
       if not path.exists():
           return []
       with open(path, 'r', encoding='utf-8') as f:
           return json.load(f)

   СТАЛО:
   import json
   from pathlib import Path
   import aiofiles

   async def load_facts(self, path: Path) -> list:
       if not path.exists():
           return []
       async with aiofiles.open(path, 'r', encoding='utf-8') as f:
           content = await f.read()
           return json.loads(content)

5. Рефакторинг services/kv_store.py: Аналогично заменить все open() на aiofiles.open().

Критерии успеха:
- Все open(), json.load(), json.dump() в async-функциях заменены на асинхронные аналоги
- Добавлен import aiofiles в измененные файлы
- aiofiles добавлен в requirements.txt
- Бот не блокирует event loop при чтении больших JSON-файлов

Тесты:

Создать файл test_async_io.py:
import ast
import sys

def check_sync_io_in_async(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        if child.func.id in ['open', 'json.load', 'json.dump']:
                            print(f"FAIL: Найдена синхронная операция {child.func.id} в async-функции (строка {child.lineno})")
                            return False
    return True

if not check_sync_io_in_async('services/memory.py'):
    sys.exit(1)
if not check_sync_io_in_async('services/kv_store.py'):
    sys.exit(1)

print("PASS: Все файловые операции в async-функциях асинхронные")

---

ЗАДАНИЕ 3: Надежный парсинг JSON от LLM

Приоритет: Высокий
Время: 45 минут
Файлы: services/kg_enricher.py, services/memory.py, создать services/json_parser.py

Шаги выполнения:

1. Создать утилиту services/json_parser.py:

import json
import re
from typing import Any, Union

def extract_json_from_text(text: str) -> Union[dict, list, None]:
    """
    Извлекает JSON из текста LLM, даже если он обернут в markdown или есть пояснения.
    """
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    markdown_pattern = r'```(?:json)?\s*([\s\S]*?)```'
    markdown_match = re.search(markdown_pattern, text, re.IGNORECASE)
    if markdown_match:
        try:
            return json.loads(markdown_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    json_obj_pattern = r'(\{[\s\S]*\}|\[[\s\S]*\])'
    json_match = re.search(json_obj_pattern, text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def safe_parse_llm_json(text: str, expected_type: type = None) -> Any:
    """Безопасный парсер JSON от LLM с валидацией типа."""
    result = extract_json_from_text(text)

    if result is None:
        return None

    if expected_type and not isinstance(result, expected_type):
        return None

    return result

2. Обновить services/kg_enricher.py:

   БЫЛО:
   result = await self.ai_engine.generate(prompt)
   entities = json.loads(result)  # Может упасть!

   СТАЛО:
   from services.json_parser import safe_parse_llm_json

   result = await self.ai_engine.generate(prompt)
   entities = safe_parse_llm_json(result, expected_type=list)

   if entities is None:
       logger.warning(f"Не удалось распарсить JSON от LLM: {result[:200]}")
       return []

3. Обновить services/memory.py: Аналогично заменить json.loads() на safe_parse_llm_json().

Критерии успеха:
- Создан файл services/json_parser.py с функциями парсинга
- Все вызовы json.loads() для данных от LLM заменены на safe_parse_llm_json()
- Бот не падает при получении невалидного JSON от LLM
- Логируются предупреждения о неудачном парсинге

Тесты:

Создать файл test_json_parser.py:
import pytest
from services.json_parser import extract_json_from_text, safe_parse_llm_json

def test_clean_json():
    text = '{"entities": ["entity1", "entity2"]}'
    result = extract_json_from_text(text)
    assert result == {"entities": ["entity1", "entity2"]}

def test_markdown_json():
    text = '''
    Вот результат:
    ```json
    {"entities": ["entity1", "entity2"]}
    ```
    '''
    result = extract_json_from_text(text)
    assert result == {"entities": ["entity1", "entity2"]}

def test_json_with_explanation():
    text = '''
    Я извлек следующие сущности:
    {"entities": ["entity1", "entity2"]}
    Надеюсь, это поможет!
    '''
    result = extract_json_from_text(text)
    assert result == {"entities": ["entity1", "entity2"]}

def test_invalid_json():
    text = 'Извините, я не смог выполнить запрос'
    result = extract_json_from_text(text)
    assert result is None

def test_type_validation():
    text = '{"key": "value"}'
    result = safe_parse_llm_json(text, expected_type=list)
    assert result is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

---

ЗАДАНИЕ 4: Безопасный парсинг веб-страниц

Приоритет: Средний
Время: 30 минут
Файлы: services/web_search.py

Шаги выполнения:

1. Проверить текущий метод парсинга:
   Команда: grep -A 10 "re.finditer" services/web_search.py

2. Установить selectolax (быстрый и безопасный):
   Команда: pip install selectolax

3. Обновить requirements.txt:
   Добавить строку: selectolax>=0.3.11

4. Рефакторинг парсинга:

   БЫЛО:
   import re

   for match in re.finditer(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
       url = match.group(1)
       title = re.sub(r'<[^>]+>', '', match.group(2))

   СТАЛО:
   from selectolax.parser import HTMLParser

   tree = HTMLParser(html)
   for node in tree.css('a[href]'):
       url = node.attributes.get('href', '')
       title = node.text(strip=True)

Критерии успеха:
- Все регулярные выражения для парсинга HTML заменены на selectolax
- selectolax добавлен в requirements.txt
- Парсинг работает быстрее и не ломается при изменении верстки

Тесты:

Создать файл test_web_search_parsing.py:
import pytest
from selectolax.parser import HTMLParser

def test_selectolax_parsing():
    html = '''
    <html>
        <body>
            <a href="https://example.com">Example Site</a>
            <a href="https://test.com">Test <b>Bold</b> Text</a>
        </body>
    </html>
    '''

    tree = HTMLParser(html)
    links = []
    for node in tree.css('a[href]'):
        url = node.attributes.get('href', '')
        title = node.text(strip=True)
        links.append({'url': url, 'title': title})

    assert len(links) == 2
    assert links[0]['url'] == 'https://example.com'
    assert links[0]['title'] == 'Example Site'
    assert links[1]['title'] == 'Test Bold Text'

def test_malformed_html():
    html = '<a href="https://example.com">Unclosed tag'
    tree = HTMLParser(html)
    links = list(tree.css('a[href]'))
    assert len(links) == 1

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

---

ЗАДАНИЕ 5: Внедрение векторного поиска

Приоритет: Высокий
Время: 2-3 часа
Файлы: создать services/vector_store.py, обновить services/memory.py

Шаги выполнения:

1. Предложить пользователю варианты:
   Варианты реализации векторного поиска:

   [1] Sentence-Transformers + ChromaDB (рекомендуется)
       Плюсы: Быстрый, локальный, хорошо интегрируется
       Минусы: Требует 500MB на модель
       Установка: pip install sentence-transformers chromadb

   [2] OpenAI Embeddings + Qdrant
       Плюсы: Высокое качество, не требует GPU
       Минусы: Платный API, зависимость от сети
       Установка: pip install openai qdrant-client

   [3] Ollama Embeddings (локально)
       Плюсы: Бесплатно, приватно
       Минусы: Медленно, требует ресурсов
       Установка: pip install ollama

   Какой вариант выбираем?

2. Дождаться выбора пользователя

3. Реализация для варианта [1] (Sentence-Transformers + ChromaDB):

   Команда установки: pip install sentence-transformers chromadb

   Создать services/vector_store.py:
   import chromadb
   from chromadb.config import Settings
   from sentence_transformers import SentenceTransformer
   from typing import List, Dict
   import logging

   logger = logging.getLogger(__name__)

   class VectorStore:
       def __init__(self, collection_name: str = "mempalace_facts"):
           self.client = chromadb.Client(Settings(
               chroma_db_impl="duckdb+parquet",
               persist_directory="./vector_db"
           ))

           self.collection = self.client.get_or_create_collection(
               name=collection_name,
               metadata={"hnsw:space": "cosine"}
           )

           logger.info("Загрузка модели эмбеддингов...")
           self.model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
           logger.info("Модель загружена")

       def add_facts(self, facts: List[Dict]) -> None:
           if not facts:
               return

           ids = [f"fact_{fact['id']}" for fact in facts]
           documents = [fact['text'] for fact in facts]
           metadatas = [fact.get('metadata', {}) for fact in facts]

           embeddings = self.model.encode(documents, convert_to_numpy=True).tolist()

           self.collection.add(
               ids=ids,
               embeddings=embeddings,
               documents=documents,
               metadatas=metadatas
           )

           logger.info(f"Добавлено {len(facts)} фактов в векторное хранилище")

       def search(self, query: str, top_k: int = 5) -> List[Dict]:
           query_embedding = self.model.encode([query], convert_to_numpy=True).tolist()[0]

           results = self.collection.query(
               query_embeddings=[query_embedding],
               n_results=top_k
           )

           formatted_results = []
           if results['documents'] and results['documents'][0]:
               for i, doc in enumerate(results['documents'][0]):
                   formatted_results.append({
                       'text': doc,
                       'score': results['distances'][0][i] if results['distances'] else 0,
                       'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                   })

           return formatted_results

       def delete_fact(self, fact_id: str) -> None:
           self.collection.delete(ids=[f"fact_{fact_id}"])
           logger.info(f"Удален факт {fact_id} из векторного хранилища")

4. Интеграция в services/memory.py:

   from services.vector_store import VectorStore

   class MemoryManager:
       def __init__(self):
           self.vector_store = VectorStore()

       async def search_facts(self, query: str, top_k: int = 5) -> List[Dict]:
           """Гибридный поиск: векторный + keyword"""
           vector_results = self.vector_store.search(query, top_k=top_k)
           keyword_results = await self._search_by_keywords(query)

           combined = vector_results + keyword_results

           seen = set()
           unique_results = []
           for result in combined:
               fact_id = result.get('metadata', {}).get('id')
               if fact_id and fact_id not in seen:
                   seen.add(fact_id)
                   unique_results.append(result)

           return unique_results[:top_k]

       async def add_fact(self, fact: Dict) -> None:
           await self._save_to_json(fact)
           self.vector_store.add_facts([fact])

Критерии успеха:
- Создан services/vector_store.py с интеграцией ChromaDB
- Векторное хранилище работает локально (папка ./vector_db)
- Поиск возвращает релевантные результаты по смыслу, а не только по словам
- Существующий keyword-поиск продолжает работать (гибридный режим)

Тесты:

Создать файл test_vector_store.py:
import pytest
from services.vector_store import VectorStore
import tempfile
import shutil

@pytest.fixture
def vector_store():
    temp_dir = tempfile.mkdtemp()
    store = VectorStore(collection_name="test_collection")
    yield store
    shutil.rmtree(temp_dir, ignore_errors=True)

def test_add_and_search(vector_store):
    facts = [
        {'id': 1, 'text': 'Python - это язык программирования'},
        {'id': 2, 'text': 'JavaScript используется для веб-разработки'},
        {'id': 3, 'text': 'Кофе - это напиток'},
    ]
    vector_store.add_facts(facts)

    results = vector_store.search("программирование", top_k=2)

    assert len(results) >= 1
    assert "Python" in results[0]['text'] or "язык" in results[0]['text']

def test_synonym_search(vector_store):
    facts = [
        {'id': 1, 'text': 'Я люблю читать книги'},
        {'id': 2, 'text': 'Мне нравится литература'},
    ]
    vector_store.add_facts(facts)

    results = vector_store.search("чтение", top_k=2)
    assert len(results) >= 1

def test_delete_fact(vector_store):
    facts = [{'id': 1, 'text': 'Test fact'}]
    vector_store.add_facts(facts)

    results_before = vector_store.search("test", top_k=1)
    assert len(results_before) > 0

    vector_store.delete_fact(1)

    results_after = vector_store.search("test", top_k=1)
    assert len(results_after) == 0 or 'Test fact' not in results_after[0]['text']

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

---

ИТОГОВЫЙ ЧЕК-ЛИСТ

После выполнения всех заданий агент ОБЯЗАН:

- Запустить все существующие тесты: pytest tests/ -v
- Запустить новые тесты из этого руководства
- Проверить отсутствие ошибок линтера: flake8 .
- Проверить отсутствие секретов в коде: python .git-hooks/check_no_secrets.py
- Запустить бота и проверить основные функции вручную
- Создать Git-коммит с описанием изменений
- Показать пользователю отчет о выполненных задачах

Отчет должен содержать:

## Отчет о выполненных задачах

### Выполнено:
1. Удалены backup-файлы (5 файлов)
2. Внедрен aiofiles для асинхронных файловых операций
3. Создан надежный парсер JSON от LLM
4. Заменен парсинг HTML регулярками на selectolax
5. Внедрен векторный поиск (ChromaDB + Sentence-Transformers)

### Результаты тестов:
- Пройдено: 45/45 тестов
- Покрытие кода: 78%
- Ошибок линтера: 0

### Следующие шаги (рекомендации):
1. Внедрить ReAct-паттерн для агентных функций
2. Добавить автономные фоновые задачи
3. Создать визуализацию графа знаний

### Внимание:
- Векторное хранилище занимает 500MB на диске
- Модель эмбеддингов загружается при первом запуске (30 сек)

---

ТРОУБЛШУТИНГ

Проблема: ChromaDB не устанавливается
Решение:
Команда: pip install --upgrade pip setuptools wheel
Команда: pip install chromadb

Проблема: Sentence-Transformers требует много памяти
Решение: Использовать меньшую модель:
self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')  # 80MB вместо 500MB

Проблема: aiofiles конфликтует с существующим кодом
Решение: Использовать asyncio.to_thread() как fallback:
async def load_facts(self, path: Path) -> list:
    if not path.exists():
        return []
    return await asyncio.to_thread(self._load_facts_sync, path)

def _load_facts_sync(self, path: Path) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

---

Конец руководства. Агент ОБЯЗАН следовать всем правилам и предлагать пользователю варианты выбора перед каждым критическим действием.

## 📥 Imported: TESTING_PROGRESS.md
_Source: TESTING_PROGRESS.md (TESTING_PROGRESS.md)_

# TESTING_PROGRESS.md

Прогресс по задаче «Проверить все файлы Telegram-бота через тестирование».

## Правила работы
- Порядок: сначала `services/`, потом `handlers/`.
- Цель: **≥80% покрытие** на каждый модуль.
- Падающие тесты чинить сразу, держать `make qa` зелёным.
- После каждого шага обновлять этот файл — чтобы продолжить завтра с того же места.
- QA-команды: `make lint`, `make typecheck`, `make test`, `make security`, `make qa`.

## Последний зелёный рубеж (checkpoint)
- **Дата**: 2026-08-07
- **Тесты**: **2631 passed**, 0 failed (было 2626)
- **Общее покрытие**: **99%**
- **lint**: flake8 0 новых (pre-existing: test_ai_engine W292, test_main F841, test_ollama_process F401/F811/W292) ✅ | **mypy**: Success, 68 source files ✅ | **bandit**: 67 issues (прежний базлайн, новых нет) ✅
- **Ollama живёт вместе с ботом (вечер 3b)**: пользователь хочет, чтобы `ollama serve`, поднятый ботом при AI-вызове, ЗАКРЫВАЛСЯ вместе с ботом (не висел как осиротевший). Было: `start_new_session=True` + ни реестра, ни cleanup → после остановки бота ollama осиротевал (PPID→1). Теперь:
  - **ollama_process.py**: модульный реестр `_SPAWNED` (list) + `_track()` + `stop_all()` (terminate всех поднятых серверов, идемпотентно) + `atexit.register(stop_all)`.
  - **main.py**: `stop_all()` в `finally` после polling + обработчик SIGTERM в `__main__` (`SystemExit` → корректный unwind → atexit/finally чистят ollama).
  - **PalaceManager_TelegrammBot.command**: `stop_bot` и `force_kill` дополнительно убивают `ollama serve` (покрывает жёсткий SIGKILL бота). Синхронизировано с копией в mempalace_bot/_scripts.
  - **Тесты**: +5 (registry: track при spawn / не track если сервер уже есть / stop_all terminate всех + idempotent; main: finally вызывает stop_all).
  - **Покрытие**: ollama_process 99% (модульный atexit-регистр), main 98% (KeyboardInterrupt-гард).

- **Предыдущий checkpoint (2026-08-07, 2626 passed)**:
- **Ollama autostart 2026-08-07 (вечер 3, из реального падения ИИ в Telegram)**:
  - **Root cause**: `.current_ai` = `qwen2.5:7b` (локальная Ollama), сервер не запущен → `openai.APIConnectionError: Connection error` (`[Errno 61] Connection refused`) в `_sync_ai_call` (services/ai_engine.py) → юзеру сырое «❌ Ошибка ИИ (qwen) после 1.50s». Launcher `PalaceManager_TelegrammBot.command` никогда не стартует `ollama serve` (только проверяет `ollama list` и молча глотает его падение); LaunchAgent отсутствовал.
  - **Окружение**: LaunchAgent `~/Library/LaunchAgents/com.mempalace.ollama.plist` (RunAtLoad + KeepAlive + ProcessType Background, лог `~/Documents/mempalace/ollama_serve.log`). ⚠️ Кейс: launchd падает с exit 78 EX_CONFIG и НЕ стартует процесс, если StandardOutPath указывает на файл, созданный НЕ launchd (проверено изоляцией вариантов plist; системный лог молчит) — лог-файл должен создавать сам launchd.
  - **ai_engine.py**: qwen-ветки `_sync_ai_call` и `_run_stream` перед запросом вызывают `ensure_ollama_running(model)` из `services/ollama_process.py` (авто-старт `ollama serve`, wait до 30с, pull модели если нет); при недоступности — дружелюбное «🧠 Не удалось подключиться к Ollama (localhost:11434). Запустите Ollama или переключите модель в /settings.» вместо сырой ошибки. Детект: `_is_ollama_unavailable` (RuntimeError с «Ollama» + классы APIConnectionError/ConnectError/ConnectTimeout); полный traceback остаётся в логе (exc_info=True).
  - **main.py**: при старте бота, если `.current_ai` — qwen-модель, prewarm Ollama в фоновом daemon-потоке (ошибка не роняет старт бота → «запуск бота = запуск Ollama»).
  - **Тесты**: +13 (autouse-моки `services.ollama_process.ensure_ollama_running` в test_ai_engine/test_main: ensure вызван с моделью / RuntimeError → friendly / APIConnectionError → friendly / gemini+openai не трогают ollama / `_is_ollama_unavailable` BVA / stream ensure + failure-чанк / prewarm started + failure continues + skipped for gemini). Gherkin: `features/ollama_autostart.feature` (1 happy + 3 neg + 2 edge, @smoke @regression).
  - **Покрытие**: services/ai_engine.py **100%**, services/ollama_process.py **100%**, main.py **98%** (недостижимый KeyboardInterrupt-гард 191-192).

- **Предыдущий checkpoint (2026-08-07, 2613 passed)**:
- **Общее покрытие**: **99%** (TOTAL 10170 stmts)
- **lint**: flake8 0 errors ✅ | **mypy**: Success, 68 source files ✅ | **bandit**: 67 issues (прежний базлайн, новых нет — сверено diff'ом локаций до/после)
- **KG-навигация 2026-08-07 (вечер 2, из реального использования)**:
  - **«📖 Читать записи» (p_kgr) только из графа**: NEW `_kg_read_sources` (handlers/palace/kg.py) — читает ТОЛЬКО файлы из `source_closet` фактов сущности (дедуп, порядок появления), каждый файл = одна запись с полным текстом через `_get_full_text_from_chroma`; без глобального `mempalace_search`. Факты без файлов → «Факты об этой сущности не привязаны к файлам» + кнопка «🔍 Поискать в заметках»; файлы не найдены → «❌ Файлы из фактов не найдены». +7 тестов
  - **«🔙 Вернуться к списку» — правильная цепочка**: NEW `cb_kg_facts` (`p_kgf`) перерисовывает страницу фактов; страница списка записей в режиме графа ведёт «Вернуться к списку» → `p_kgf` (факты), заголовок «📚 Записи графа знаний»; глобальный поиск (`p_kgrs`) сохраняет `p_kg` → меню. Цепочка: меню KG ← факты ← список записей ← полная запись. `action_bar._get_parent_handler` += `p_kgf`. +4 теста (+ обновлены test_cb_kg_read, not_allowed, dispatch, parent-handler keys)
- **Хотфиксы 2026-08-07 (вечер, из реального использования)**:
  - **Сырой JSON при добавлении факта в KG**: `cb_kg_add_confirm` теперь рендерит ответ `mempalace_kg_add` через `_format_kg_add_result` (handlers/palace/kg.py): success → «✅ Факт сохранён в графе знаний!» + fact с русским лейблом предиката (вместо JSON с `\u`-эскейпами); failure → «❌ Не удалось сохранить факт. <err>»; не-JSON → passthrough. +5 тестов
  - **Кнопка «📖 Читать записи» (p_kgr) не открывала записи**: `_kg_search_and_show` ждал от `mempalace_search` список, а движок возвращает dict `{"query":..., "results":[...]}` → TypeError на слайсе dict → клик молча падал, кнопки записей `p_krd:N` не появлялись. Теперь: `results` извлекается из dict (с fallback на список и на `[]` для не-JSON/ошибок); рендер читает `source_file`/`text` движка. +5 регрессионных тестов
- **Фичи 2026-08-07 (фаза MemPalace-UI)**:
  - **П.1 «Сессия истекла» на 2-м шаге KG**: `cb_kg_add_start`/`cb_kg_add_subject_prompt` создают `_kg_add_state[uid]` перед `_pending_mcp_input`; полный флоу-тест `test_kg_add_full_flow` (start → Шопенгауэр → influenced_by → Кант → confirm)
  - **П.5 «Сессия истекла» при открытии личной заметки**: `_reopen_pn_list(cb)` (try/except → «❌ Не удалось открыть список.») + graceful recovery для pn_v/pn_r/pn_tp/pn_q/pn_del/pn_del_yes; `cb_pn_list_back` — go_main_menu до pop state; 7 негативов + 2 новых теста
  - **П.2 кнопки «➕ Новое крыло/комната»**: `_show_pn_rooms`/`_show_pn_confirm` (выделены из тел cb_pn_wing/cb_pn_room), `cb_pn_wing_new`/`cb_pn_room_new`, ветки `pn_new_wing`/`pn_new_room` в `process_mcp_text_input` (handlers/palace/__init__.py); +11 тестов
  - **П.3 файл-интерпретатор RU↔EN**: NEW `services/interpreter.py` (JSON `~/Documents/mempalace/interpretation.json`, register/register_many/to_ru/to_en/display_name/seed_known_pairs, атомарная запись через .tmp+os.replace, threading.Lock); подключён в kg.py (register при confirm, display_name в stats) и main.py (seed в async main()); ~20 тестов в tests/test_interpreter.py
  - **bandit-чистота**: ветка `pn_new_wing` использует `logger.warning` вместо `except Exception: pass` — новых B110 нет
- **SQLite/файловые ResourceWarning устранены**: прогон `pytest -W error::ResourceWarning` — 0 предупреждений
  - **Production-фикс** `services/logging_setup.py`: `setup_logging` закрывает удаляемые FileHandler'ы (`handler.close()`), раньше каждый импорт `handlers/messages.py`/`main.py` навсегда оставлял открытым `bot_debug.log`
  - **Тесты**: 4 места `open(...).read()` без закрытия → `with open(...)` (test_web_search_btn_handler ×2, test_chat_handler, test_youtube, test_cli_utils)
  - **+2 теста** в test_logging_setup.py: повторный setup_logging закрывает старый FileHandler (stream.closed), StreamHandler'ы не закрываются
- **RuntimeWarning «coroutine never awaited» — устранены** (было 4): `test_photos_handler` мокал синхронную `save_bot_photo` как `async def` → `def` (multimodal.py:53 — синхронная); `test_pdf_handler` `fake_create` захватывал корутину таймера без await → `coro.close()`. Прогон `pytest -W error::RuntimeWarning` — 0 предупреждений нашего кода. Остались 6 библиотечных DeprecationWarning (google/genai `_UnionGenericAlias` → Python 3.17, swig в importlib) — исправить нельзя.
- **Фаза 3 закрыта**: main.py (0% → 100%), cli/ (0% → 100%), cli_ask.py (0% → 99%), cli_extras.py (32% → 100%)
- **Хвосты services доведены**: kv_store 95→100, note_linker 86→100, multimodal 90→100, memory 92→100, reminder_scheduler 92→100, kg_enricher 93→99, code_mode 97→100, event_bus 98→100, conversation_fsm 99→100, web_search_cache 96→100, tavily_search 98→100, config.py 87→100 (tests/test_config.py), mixing_rules 92→100
- **Известные артефакты coverage (не баги кода)**: `cli/utils.py:173` и `cli_ask.py:126->61` и `cli/commands.py:612->622, 613->612` — строки реально выполняются (тесты проходят, иначе были бы FileNotFoundError/бесконечный цикл), события теряются из-за бага numpy 2.x + coverage 7.x + Python 3.14 (C-extension «cannot load module more than once per process» при изолированном импорте cli под cov; полный прогон работает)
- **Структурно недостижимые ветки (задокументированы)**: note_import_filter.py 55/102/108 (дубли-проверки, первая всегда срабатывает), mixing_rules 169->174/174->180/183->186 (General Expert condition всегда True → active_rule никогда None), process_ai_query 662-700 (SEARCH-блок после `return answer` — мёртвый код)

## Фаза 3: main.py + cli/ (завершена)

- [x] `main.py` 0% → **100%**, 14 тестов (tests/test_main.py): import-guard `sys.exit(1)` при ADMIN_ID==0/дефолтном токене (через importlib.reload + мок sys.exit), _safe_include (успех/RuntimeError), cmd_start (kb «⚙️ Настройки»), cmd_palace_button/cmd_sync_button (3 ветки)/cmd_search_button (kb search:wing), cb_search_wing/cb_search_web (pending_web_search), main() (delete_webhook+mcp+prewarm+scheduler+start_polling, mcp start fail, prewarm fail). Моки рантайм-импортов через `"services.whisper_service.prewarm"` и т.п. (в main нет атрибута services!), ALLOWED_IDS мокается через config.
- [x] `cli/menu.py` 0% → **100%**, 9 тестов (tests/test_cli_menu.py): list_chats (нет папки/нет пути/сортировка mtime desc), load_chat (нет/список→миграция), save_chat (ok/ошибка), create_new_chat (авто-имя/кастомное). Фикстура создаёт каталог (NamedTemporaryFile требует существующий dir).
- [x] `cli/help_sections.py` 0% → **100%**, 5 тестов: структура 6 секций, show_help/show_section (валид/неизвестный без вывода)/show_all_help.
- [x] `cli/utils.py` 0% → **99%**, 34 теста (tests/test_cli_utils.py): format_for_terminal (все регэкспы), speak_text (disabled/пусто/успех Popen-аргументы/ошибка), load_chat миграция, save_code_from_text (нет папки/пустой блок/6 расширений py json js cpp html/ошибка записи), voice config (default/чтение/создание/merge), generate_summary_if_needed (не нужно/успех/ошибка — **мок get_ai_response_async должен быть async**), export_chat_to_md (summary/user/assistant/system-без-type), is_noise_input (11 кейсов: **«?»/«??»/«!!» фактически True** — punctuation-check срабатывает позже исключений; «~» False — «~» нет в punctuation-строке; зафиксировано фактическое поведение).
- [x] `cli/commands.py` 0% → **99%**, 83 теста (tests/test_cli_commands.py + test_cli_commands_ai.py): все palace-passthrough, mcp-команды через FakeMCP (start/call_tool/raise), cmd_enrich (все 5 веток — **progress_callback нужно await-ить в фейке**), cmd_settings (нет файла/отмена/выбор/вне диапазона/неверный ввод — мок builtins.open обёрткой), save_quick_note/save_extraction, cmd_web (немецкий/английский перевод/ошибка/русский без перевода — моки на `"services.ai_engine.get_ai_response_async"`), process_ai_query (явное/авто крыло, summary, memory±, coding activation/active±files, фото 4 ветки — **encode-мок по endswith("a.jpg")**, т.к. путь содержит «a»), вывод кода через rich Syntax.
- [x] `cli/dialog.py` 0% → **100%**, 57 тестов (tests/test_cli_dialog.py): CLICompleter (4 кейса), chat_loop — FakeSession с очередью ответов, autouse-мок всех 35 команд с записью вызовов; 27 команд-веток, h/секции/0, /web с под-промптом и пустой, /del (+нет файла), /new//chats, ~/#ctx (длинная/короткая), !/!!/??? (2 вызова save_extraction — «!!» и «???» оба проходят), noise-guard, EOF, key-bindings c-c/c-r через prompt_toolkit Keys.
- [x] `cli_ask.py` 0% → **99%**, 14 тестов (tests/test_cli_ask.py): main-цикл (q/EOF/new/номер/плохой номер/delete±/unknown/chats/deleted), **execv-ветка 19-23 покрыта** моком os.execv + importlib.reload с подменой os.path.exists (в противном случае импорт cli_ask РЕАЛЬНО заменяет процесс на venv-python — ~/Documents/mempalace/venv существует!). Из-за этого модуль импортируется ВНУТРИ фикстуры с патчем; FakePromptSession с class-очередью ответов (main сам создаёт session).
- [x] `cli_extras.py` 32% → **100%**, 44 теста (tests/test_cli_extras.py): cli_remind (5 веток, kv-mock), cli_pdfs (9 веток), cli_yt (6 веток), cli_tunnels (10 веток), cli_kgadd (3), cli_transkript (7 — мок `"config.TRANSKRIPT_DIR"`), cli_palace_cmd (6).

## Задача 1 (выполнена): починить 3 падавших теста
| Тест | Причина | Фикс |
|------|---------|------|
| `test_get_kv_store_singleton` | `KVStore.__init__(db_path=_DB_PATH)` привязывал дефолт при создании класса → monkeypatch `_DB_PATH` не работал, тест бил по живой БД бота | `db_path: str\|None = None`, резолв `db_path or _DB_PATH` в `__init__`; тест получил `tmp_path` |
| `test_get_kv_store_creates_instance` | та же причина (дефолт класса) | автоматически починился после фикса `__init__` |
| `test_parse_ai_answer_extracts_json_from_code_fence` | функция `_parse_ai_json_answer` удалена из `import_notes.py` (парсинг встроен в `ai_enrich`) | тест переписан на `ai_enrich` + mock `_ollama_generate`; добавлены негативы (invalid json / None / JSON-префикс) |

Изменённые файлы:
- `services/kv_store.py` (сигнатура `__init__`)
- `tests/test_services_singletons.py`
- `tests/test_import_notes_json_parsing.py`

## Фаза 2: services с низким покрытием (завершена)

- [x] 1. `services/ai_engine.py` — 14% → **93%**, 41 тест (tests/test_ai_engine.py): _load_models_config (нет файла/битый/валидный), get_current_ai (fallback/чтение файла/ollama→qwen/openai/tag не найден/ошибка чтения), invalidate_ai_cache, _sync_ai_call qwen (очистка deepseek/chatml/эхо user/китайский/system из messages/картинки/пустой/обрезан по length/сетевые ошибки), openai (ключ/успех), gemini, неизвестный движок, get_ai_response_async (успех/executor failure), stream (чанки qwen/openai/gemini/с картинками/ImportError/ошибки).
  - **Баг найден (зафиксирован тестом `test_sync_qwen_no_choices_field`)**: в `_sync_ai_call` при ответе без `choices` переменная `response_text` не инициализирована → `UnboundLocalError` (падает в except и возвращает «Ошибка ИИ» вместо «Пустой ответ»). Не исправлен — зафиксирован.
- [x] 2. `services/palace_bridge.py` — 24% → **96%**, 59 тестов (tests/test_palace_bridge.py): search_palace_context (+sources/без файла/пусто/схема открыта/ошибка), search_palace_with_sources, _search_palace_context_impl (пустой запрос/санитизация/API/крыло→глобально/CLI-fallback), _rank_hits (сортировка/без bm25/макс=0), _search_via_api (нет модуля/нет результатов/фильтр/исключение), _search_via_cli (успех/комната/возврат код/нет результатов/пусто/повтор глобально/исключение), _search_connected_rooms (туннели/себя/ошибки MCP), search_with_kg (+факты/пустые/схема открыта/ошибки), export_chat/n Отет_verbatim, _run_mempalace и 8 команд palace_*, sync_to_palace (пусто/mine/очистка схема/ошибки).
- [x] 3. `services/pdf_engine.py` — 13% → **99%**, 37 тестов (tests/test_pdf_engine.py): load_prompts (создание/чтение), _sync_extract_pdf (текст/OCR/ошибки/none), extract_pdf_async (мок executor), estimate_tokens, build_comparison_prompt, chunk_text (короткий/пустой/по предложению/абзацу/жёсткий стык/3 чанка), analyze_large_document (пусто/малый/чанки вкл/все ошибки/финал плохой), save_pdf_original (успех/ошибка/дозапись), list_archived_pdfs, remove_pdf_from_index, skip пустых страниц (пустая строка), OCR skip пустых/коротких. *Осталось 141->155 — недостижимо (выход из while только через break).*
- [x] 4. `services/sender.py` — 28% → **100%**, 18 тестов (tests/test_sender.py): _add_web_search_button (кнопки/None/ошибки), send_response_with_mode (text/voice/both/сплит длинного/ошибки answer/voice prepare empty/ошибка генерации/ошибка отправки голоса с удалением файла), send_text_only (мульти/ошибки), skip пустых частей (оба text-пути), remove-ошибка голоса игнорируется.
- [x] 5. `services/tts_processor.py` — 13% → **100%**, 26 тестов (tests/test_tts_processor.py): prepare_tts_text (пусто/блокировка ошибок/тех.эмодзи/эмоц.эмодзи→паузы/код-блоки/инлайн-код/ссылки/бэкслеши/абзацы/пробелы), split_tts_text (короткий/лимит/по границам/жёсткий/пустой/остаток обнуляется ровно), get/set_voice_settings (нет файла/существующий/дефолт/создание/обновление), generate_voice_async (пусто/say+ffmpeg успех/say fail/нет ogg/исключение/удаление aiff после ffmpeg).
- [x] 6. `services/web_search.py` — 9% → **92%**, 42 теста (tests/test_web_search.py): _parse_html_results (td table-snippet/result__snippet/дубли/пустые/короче 20/лимит max_results), _google_search (нет ключа/API/пусто/ошибка), _ddg_search (успех/нет results), _yahoo_search, _search_all_engines (пустой текст пропущен/дедуп/limit/склейка DDG+Yahoo/пусто/Google выключен), search_web (кэш fresh/старый перезаписан/ошибки парсинга/без результатов), deep_search_web (с источниками+AI/без источников/тайвили fallback/ai_engine ошибка), CACHE_DIR создаётся при инициализации, cleanup_old_cache (старые удалены/свежие остались/ошибки проглочены), get_sources_stats.
- [x] 7. `services/palace_mcp.py` — 14% → **100%**, 24 теста (tests/test_palace_mcp.py): start (создание subprocess/уже запущен/handshake fail), _send (не запущен/запись JSON строки), _notify, _reader (ответ в pending/битый JSON пропущен/EOF-потеря/readline exception/чужой id), _rpc (seq+ответ/timeout+cleanup), _ensure_alive (жив/мёртв→restart/ждёт ready), call_tool (текст из content/без параметров/ошибка MCP), stop (terminate+отмена reader/нет proc/исключение wait), get_mcp singleton+reset, начальное состояние.
- [x] 8. `services/youtube.py` — 40% → **100%**, 37 тестов (tests/test_youtube.py): _sanitize_filename (спецсимволы/пустой/длина 40/юникод), _yt_path/_tr_path (config dirs), download_video (mp4 создан/нет файла→mp4 путь/чужой файл в каталоге/webm-part/default title/формат 720-1080), download_audio (mp3+raw title/postprocessor/default "audio"), _format_transcription (группы/разрыв 2с/пунктуация/пустой текст/пусто), transcribe_audio (whisper small/название из title/из filename/файл записан), _compress_video (успех/ffmpeg fail/аргументы crf 28), compress_audio (успех/ffmpeg fail/аргументы -ac 1+libmp3lame), _media_duration (успех/не число/битый utf-8), split_media (≤лимит/нет duration/успех 3 части+удаление оригинала/-segment_time min 1.0/нет частей/remove OSError игнорируется).
- [x] 9. `services/text_formatter.py` — 63% → **100%**, 39 тестов (tests/test_text_formatter.py): safe_html_format (escape/заголовки/жирный/курсив/код inline+блок/списки/линии/strip), _adjust_split_to_safe_point (0/-5/незакрытый тег отступ/тег вне окна/пробелы после тега/до начала), split_message (пусто/короткий/ровно лимит/длинный/абзацы/предложения/баланс тегов/вложенные/reopen/нет разделителей/неизвестные теги/закрывающие без открытых/сплит на 0/хвост из пробелов/выход while по условию при пробельном остатке).
  - **Баг найден (зафиксирован тестом `test_format_code_block`)**: order regex — inline-код `\`…\`` выполняется раньше code-block ```` ``` ``` ```` и ломает тройные бэктики (блок кода никогда не форматируется как `<pre>`).
- [x] 10. `services/ollama_process.py` — 49% → **100%**, 26 тестов (tests/test_ollama_process.py): is_server_available (0/nonzero/TimeoutExpired/FileNotFound/OSError), is_model_available (base name/full name/нет/ошибки), wait_for_server (true/таймаут/default timeout), ensure_running (сервер есть/proc живой/нет CLI/timeout+stop/model есть — без pull/запуск+pull), stop (terminate/уже завершён/terminate fail→kill/kill тоже fail/нет proc), ensure_ollama_running (singleton factory), дефолты (qwen2.5:7b/порт/30с).
- [x] 11. `services/ai_cache.py` 21% → **100%**, 8 тестов (tests/test_ai_cache.py): roundtrip/нет чата/нет сообщения/мульти/изоляция чатов/вытеснение старейшего при >50/новейшие сохраняются.
- [x] 12. `services/ttl_dict.py` 90% → **100%**, 12 тестов (tests/test_ttl_dict.py): set/get/contains, истечение (KeyError/get default/contains false), pop (+expired), длина/итерация, дефолтный ttl 86400.
- [x] 13. `services/menu.py` 40% → **100%**, 7 тестов (tests/test_menu.py): go_main_menu через __main__/через main/None/fallback import/fallback success/ошибка cmd_start→уведомление/ошибка ответа глотается.
- [x] 14. `services/conversation_fsm.py` 67% → **100%**, 20 тестов (tests/test_conversation_fsm.py): IDLE/data пусто, set/get_state, истечение TTL, refresh при get, update_data (существующий/новый/истёкший), pop_data (ok/default/нет юзера/истёк), clear, __contains__ (+истечение/+refresh), setdefault (existing/new/истёк), active_count, default ttl 86400.
- [x] 15. `services/bot_setup.py` 40% → **100%**, 13 тестов (tests/test_bot_setup.py): set_logger, init_bot (возвращает глобальные bot/dp, регистрирует middleware), кэши (maxsize/ttl), security_middleware (allowed/blocked/без logger/uid из message/callback/no user id/message без from_user).
- [x] 16. `services/note_import_filter.py` 75% → **96%**, 36 тестов (tests/test_note_import_filter.py): _normalize_text/_word_count, _contains_meaningful_content (пусто/коротко/пунктуация/url/цифры+эмодзи/2 слова/служебные слова/junk-маркеры), should_import_note (None/спец. title/равные/низкий score/штрафы url/цифры/эмодзи/strict), filter_notes_in_folder (нет папки/dirs/не .md/utf8→latin1/unreadable/rtf+markdown/сортировка). *Осталось 55/102/108 — недостижимые дубли-проверки.*

## Следующий шаг (не начат)
**Тестировать `services/` модули с 0% покрытием:**
- [x] 1. `services/memory.py` — **92%**, 21 тест (tests/test_memory.py): файловые хранение, retrieve_facts (поиск/приоритет/лимит/пустые), get_memory_context, extract_and_store_facts (500-лимит/исключения), _extract_facts (мок ai_engine).
- [x] 2. `services/kg_enricher.py` — **93%**, 24 теста (tests/test_kg_enricher.py). **Найдены баги**: `_extract_from_filename` — `.txt` попадает в `author`/`book` («Гёте.txt»); автор после «—» не извлекается при наличии `.txt` в конце имени.
- [x] 3. `services/multimodal.py` — **90%**, 20 тестов (tests/test_multimodal.py): capabilities кэш/конфиг/ошибки, check_capability, encode base64 (ok/нет файла/пустой), save (copy+delete/нет файла), list (фильтр ext/лимит 10/сорт), delete.
- [x] 4. `services/note_linker.py` — **86%**, 12 тестов (tests/test_note_linker.py): escape MarkdownV2 (границы/кириллица), link_note_async (добавление блока/самоисключение/короткая/нет результатов/только себя/лимит 6/исключения).
- [x] 5. `services/reminder_scheduler.py` — **92%**, 8 тестов (tests/test_reminder_scheduler.py): отправка просроченных, пропуск будущих, ошибка отправки (не удаляет), отсутствие данных, граница remind_at=0, start/stop/idempotent таска.
- [ ] 6. `services/tavily_search.py` — 0%
- [x] 6. `services/tavily_search.py` — **98%**, 19 тестов (tests/test_tavily_search.py): нет ключа, пустой запрос, трим до 500, успех, 401/429/таймаут/HTTP-ошибка/общая ошибка, cap max_results 10, форматирование (пусто/ответ/без URL/fallback content/усечение/экранирование/лимит), fallback (ошибка/успех).
- [x] 7. `services/web_search_cache.py` — **96%**, 14 тестов (tests/test_web_search_cache.py): save (файл/id/title), save_with_id, load (ok/нет/битый), cleanup (старые удалены/свежие остались/не-json), list (пусто/парсинг/сорт по времени/битые пропущены).
- [x] 8. `services/whisper_service.py` — **100%**, 4 теста (tests/test_whisper_service.py): кэш одинаковой модели, разные размеры, prewarm base, idempotent.
- [x] 9. `services/wing_classifier.py` — **100%**, 33 теста (tests/test_wing_classifier.py): параметризация по 5 крыльям, пустые/короткие/None, неизвестная тема, регистр, конфликт по max score.
- [x] 10. `services/auto_sync.py` — **100%**, 4 теста (tests/test_auto_sync.py): успех/пустой экспорт/исключения sync и export.
- [x] 11. `services/code_mode.py` — **97%**, 35 тестов (tests/test_code_mode.py): блоки кода по языкам (py/json/js/cpp/html), пустые/мульти, детект кодинга (паттерны/слова/история), промпт, папки, файлы. **Баг зафиксирован**: `javascript` в блоке → `.py` (нет подстроки `js`), «функцию» не распознаётся (нужна «функция»).

**Все 11 0% модулей services закрыты.** → Следующая фаза: services с низким покрытием (ai_engine 14%, palace_bridge 24%, pdf_engine 13%, sender 28%, tts_processor 13%, web_search 9%, palace_mcp 14%, youtube 40%, text_formatter 63%, ollama_process 49%, ai_cache, conversation_fsm, bot_setup, menu, ttl_dict, ai_cache, note_import_filter 75%).

- [x] 17. `handlers/reactions.py` 0% → **99%**, 14 тестов (tests/test_reactions.py): not allowed/empty reactions/unknown emoji/не в кэше/сохранение note+insight+research/variation selector/ошибка сохранефия/не-эмодзи реакция/первая известная эмодзи решает action.
- [x] 18. `handlers/voice.py` 0% → **100%**, 13 тестов (tests/test_voice_handler.py): _process_audio_sync успех/пусто, full flow (распознано → process_user_message → delete), пустой транскрипт, edit_text падает (пустой/распознанный/ошибка), download fail, нет main-обработчика, cleanup temp-файлов, os.remove падает, delete падает.
- [x] 21. `handlers/notes.py` 0% → **100%**, 14 тестов (tests/test_notes_handler.py): /help allowed/not, cb_help, archive read (prefix known/unknown, empty, single, order by mtime, hidden files, split long note, not allowed).
- [x] 22. `handlers/youtube_ui.py` 0% → **100%**, 25 тестов (tests/test_youtube_ui_handler.py): меню видео/mp3, upload (small/empty/compress/split/error), remove fails ignored (4 участка), quality cb (success/no session/compress/split/error), transcribe cb (yes/no/short/missing cache/missing disk/error).
- [x] 23. `handlers/web_search_btn.py` 0% → **100%**, 42 теста (tests/test_web_search_btn_handler.py): форматирование free/tavily, search_with_ai_evaluation (free/tavily/error/no key), cb_web_search (last query/summary fallback/messages fallback/lines fallback/no query/exception/no message/chunks), cb_ws_sources (success/no id/missing/empty/clean_text/no snippet), cb_ws_save (cache/fallback/no data/без summary/без sources). **Баг исправлен**: `len(kb.buttons)` → `any(kb.export())` (generator нельзя len()).
- [x] 24. `handlers/photos.py` 0% → **100%**, 31 тест (tests/test_photos_handler.py): handle_photo (photo/document/non-image/no file/empty save/error/not allowed), cb_analyze_last (success/no photos/not multimodal/no b64/error/empty parts/HTML fail fallback/status.delete fail), show_links (ok/missing/no section/read error), cb_delete_photo, cmd_photos (empty/list/not allowed), cb_del_photo (bad format/no cache/already deleted/success last/delete fail).
- [x] 25. `handlers/reminder.py` 0% → **100%**, 33 теста (tests/test_reminder_handler.py): _is_reminder, _parse_time_description (today/offset), _clean_json (plain/fences/noise/invalid/fallback fails), _parse_reminder (full/no time), detect_reminder (not reminder→Skip, full/ask_text/ask_time/ask_all/parse error), cb_remind_confirm (ok/no session/missing data), cb_remind_cancel, handle_reminder_text (no pending/ask_text/ask_time ok+fail+bad json/ask_all 4 ветки/unknown step).
- [x] 26. `handlers/search.py` 0% → **100%**, 41 тест (tests/test_search_handler.py): _open_room_view (success/empty/error), cmd_wing_search_prompt, cb_search_wing, cb_wing_search_select (known/unknown/not allowed), cmd_search (no query/basic/--wing/invalid wing/empty/error/multi parts/not allowed), cb_search_source_open (success/not in cache/no wing-bad id/short/no data), cb_search_source_drawer (success/empty content/error/short/no data), _render_source_drawer_page (first/middle/stale/bad index), pagination, noop, all_drawers, back.
- [x] 27. `handlers/settings.py` 0% → **100%**, 42 теста (tests/test_settings_handler.py): build_settings_kb (default/ai.txt set/empty whitespace/missing), cmd_callback_handler (photos empty/list, analyze_photo no photos/not multimodal/no b64/whitespace part/HTML fallback/ai error, history/export/insights/research, sync no session/empty chat/success/unknown cmd), render_ollama_list (models/errors/active tag), cb_voice_toggle (cycles text→voice→both→text/not allowed), cb_speed (+10/-10/clamp 100/300/no data), cb_list_ollama, cb_set_ai (success/`invalidate_ai_cache`/write error), cb_back.
- [x] 28. `handlers/transkript.py` 0% → **100%**, 54 теста (tests/test_transkript_handler.py): _list_files (нет папки/фильтр .txt/сортировка mtime), cmd_transkript (пусто/файлы/не allowed), _show_page (message target/callback target реальный CallbackQuery/кнопки ◀️▶️ на границах/одна страница без навигации/длинное имя «..»), cb_tr_page (пусто/успех/не allowed), cb_tr_read (idx out of range/ошибка чтения/успех кэш), _show_content_page (нет кэша message+callback/idx clamp/навигация middle), cb_tr_content_page (noop/успех), _get_content (нет кэша/нет fname/ошибка чтения/успех), cb_tr_ai (нет кэша/успех+_tr_ai_waiting), cb_tr_ai_web (нет вопроса/нет кэша/успех с web), cb_tr_q (нет кэша/ошибка чтения/успех+_quote_waiting), cb_tr_save (нет контента/успех+_save_state+_show_save_wings), cb_tr_links (нет кэша/ошибка чтения/нет результатов/успех с кнопками источников/ошибка), cb_tr_del (подтверждение), cb_tr_del_yes (нет кэша/успех удаление/ошибка os.remove), _answer_tr_ai (ошибка чтения/пусто/без web с system-промптом/с web/пустой результат), handle_tr_ai_question.
- [x] 29. `handlers/pdf.py` 0% → **100%**, 54 теста (tests/test_pdf_handler.py): create_prompt_kb, cmd_compare (успех/не allowed), handle_pdf (не pdf/лимит 50MB/ошибка download/single меню/compare 1 файл ждёт/2 файла+таймер cancel/3 файла fall-through/2 файла без таймера), cb_show_prompts, cb_activate_compare (новый таск/cancel старого таймера), timeout_compare task (edit fail обе warning ветки/режим сменился/пришёл 2-й файл/нет файлов без сброса), cb_pdf_type (no data/пустой буфер/успех), send_long_response_parts (пусто/text/voice/both/voice send fail/tts error/tts error без текста/нет tts-текста/нет чанков), cb_read_next (no data/нет файла/последняя часть/успех text/кнопка Конец/voice/voice send fail/tts error/нет tts-текста), cmd_pdfs (пусто/список+усечение), cb_select_archived_pdf (no data/не в индексе/нет на диске/успех), run_analysis (пустой буфер/ошибка извлечения/пустой текст/успех+архив/❌-ответ/пустой final/ответ не отправился), run_comparison (пустой буфер/успех).
- [x] 30. `handlers/chat.py` 0% → **99%**, 61 тест (tests/test_chat_handler.py): _short_id (hex fallback), load_chat (новый/пустой/нет файла/list→dict миграция), save_chat (успех/ошибка), save_summary_file, export_chat_to_md (успех/ошибка), generate_fresh_summary (пусто/усечение 50 слов/ошибка), update_summary_if_needed (<5 сообщений/успех/усечение 40 слов/ошибка), cmd_new_chat, cmd_list_chats (пусто/не allowed), cb_select_chat (известный/неизвестный/не allowed), cb_delete_chat (успех+refresh/файл отсутствует/edit fail), cmd_context (новая сводка/существующая/длинная → кнопка expand/ошибка), cb_show_summary (файл+split+кэш/кэш/чат fallback/пусто/send fail), cb_show_full_chat (успех/мульти-часть/multi part/fail), cb_refresh_summary, cmd_sync_palace (пусто/успех/edit fail), get_ai_context (async, summary+recent 6), cmd_history (пусто/успех/не allowed), cmd_export (успех doc+caption/не allowed).
  - **Баг исправлен в коде**: `cmd_context` — `final_summary` не инициализировался на ветке существующей сводки → `UnboundLocalError` (падало для всех юзеров с сохранённой сводкой). Фикс: `final_summary = existing_summary`.
- [x] 31. `handlers/personal_note.py` 29% → **100%**, 100 тестов (tests/test_personal_note_handler.py + test_personal_note_room_select.py): get_whisper (создание/кэш), _transcribe_sync (успех/пусто), _taxonomy_for_prompt (dict/не-dict/пусто), _format_note, _classify_note (plain/fenced json/не json/None → fallback личные_мысли/inbox), process_note_input (успех+preview+kb/нет taxonomy/ошибка/ошибка edit), cmd_personal_note (allowed/not), cb_pn_save (нет данных/личное без копии/другое крыло + копия/invalid json/mcp error), cb_pn_room (нет данных/нет data/-1 inbox/индекс/вне диапазона/malformed/пустой список), cb_pn_cancel, cmd_cancel_note, cmd_list_personal_notes, _show_pn_page (пусто/навигация back+forward/последняя страница/пустой контент/uid из int/ошибка), cb_pn_page (нет data/с state/без state), cb_pn_list_back, cb_pn_view (нет data/нет state/idx вне диапазона/короткий/длинный >300/ошибка), cb_pn_read_full (нет drawer/успех multi-part/ошибка), cb_pn_back_to_list/_view (с/без state), cb_pn_to_palace (нет drawer/успех _save_state/ошибка), cb_pn_quote_prompt (короткий/длинный >500/ошибка), cb_pn_delete_confirm/execute (success/failure/empty/error), _save_quote_to_palace (нет данных/успех), все 15 callbacks not allowed.
- [x] 32. `handlers/palace/save.py` 25% → **100%**, 55 тестов (tests/test_palace_save.py): cb_save_start (html_text/reply/_ai_msg_cache с пустым чатом/все пустые/нет текста), cb_save_cancel, cb_save_all (с/без state), cb_save_quote_prompt, _show_save_wings (dict/list/mcp error), cb_save_wing_chosen (успех/bad idx/нет кэша/вне диапазона/нет state), cb_save_new_wing_prompt, _show_save_rooms (успех/нет state/нет комнат/ошибка), cb_save_back_to_wings, cb_save_room_chosen (успех/bad idx/нет кэша/вне диапазона/нет state), cb_save_new_room_prompt, _save_confirm (full/quote/нет state), cb_save_back_to_rooms, cb_save_confirm_execute (нет state/full/quote/ошибка), _format_save_result (не json/пусто/успех/failed/no error/list), 11 callbacks not allowed.
- [x] 33. `handlers/palace/shared.py` 37% → **100%**, 28 тестов (tests/test_palace_shared.py): _normalize_query (алиасы/подчёркивание), _get/_set/_pop_data, _FsmDict (get/set/getitem KeyError/pop/contains/setdefault), _send_kg_page (нет данных/первая страница+навигация/последняя/одна страница/строковые факты), _format_mcp_result (не json/пусто/scalar/nested/list/не-dict/invalid).
- [x] 34. `handlers/palace/_utils.py` 22% → **100%**, 27 тестов (tests/test_palace_utils.py): set_error_logging/_log_error (вкл/выкл), safe_edit_text/safe_answer/safe_answer_returning_message/safe_delete/safe_answer_voice/safe_send — success/None/InaccessibleMessage (model_construct)/ошибка+лог.
- [x] 35. `handlers/palace/hints.py` 43% → **100%**, 18 тестов (tests/test_palace_hints.py): suggest_tunnel_hint (короткий/нет совпадения/нет traverse/пустой traverse/успех+_hint_data/ошибка), cb_hint_show (нет данных/успех), cb_hint_read (нет данных/успех), cb_hint_dismiss (delete/delete fail→✅), _get_full_text_from_chroma (пусто/нет БД/нет совпадений/полный текст с \\-путём/дубликаты/ошибка sqlite — через фейковый os-модуль).
- [x] 36. `handlers/palace/admin.py` 30% → **100%**, 25 тестов (tests/test_palace_admin.py): _finalize_admin_result (текст/пусто), cb_palace_status/mcp/instructions (успех/ошибка), cb_palace_admin (кнопки), repair/compact/compress/wakeup (успех/ошибка через захват asyncio.create_task), 8 callbacks not allowed.
- [x] 37. `handlers/palace/tunnels.py` 16% → **100%**, 46 тестов (tests/test_palace_tunnels.py): _show_cross_rooms (успех/нет связей/ошибка/только себя/одиночный dict/не-dict узлы), cb_find_tunnels_wing_b, cb_find_tunnels_result (успех/любое крыло -/пустой raw/ошибка), cb_follow_tunnels_wing/room/result, _show_wing_buttons_for_tunnel (успех/exclude/нет крыльев/ошибка), cb_create_tunnel_source_wing/source_room/target_wing/target_room/label_prompt (все ветки: успех/нет комнат/ошибка/нет кэша/вне диапазона/нет state), 10 callbacks not allowed.
- [x] 38. `handlers/palace/kg.py` 24% → **100%**, 67 тестов (tests/test_palace_kg.py): cb_kg_menu/help, cb_kg_stats (dict/nested/не-dict/ошибка), cb_kg_add_* (start/cancel/subject/predicate menu+chosen/object/confirm успех+пусто+нет state+ошибка), cb_kg_query_prompt, cb_kg_continue/restart (с/без данных), cb_kg_read (успех/нет данных), cb_kg_back_to_search, cb_kg_read_search, _kg_search_and_show (успех/пусто/ошибка), _send_kg_search_page (нет данных/первая/вторая/последняя/12 results/пустые), cb_kg_read_result (нет данных/next/prev/bad param/вне диапазона/dict/строка/хрома-полный/пустая запись), cb_kg_read_back (full/full без source/нет state/другое), 18 callbacks not allowed.
  - **Баг исправлен в коде**: `cb_kg_add_predicate_chosen` — `cb.data[10:]` при префиксе «p_kga_pr:» (9 символов) срезал первую букву предиката («nfluenced_by»). `cb_kg_read_search` — `cb.data[8:]` при «p_kgrs:» (7 символов) терял первую букву сущности («нг»). Оба заменены на `len(prefix):`.
- [x] 39. `handlers/palace/action_bar.py` 90% → **100%**, 96 тестов (tests/test_palace_action_bar.py): _find_cut (абзац/перенос/пробел/фоллбек/слишком близко к началу), paginate (пусто/короткий/мульти/ровно лимит/чуть больше/хвост из пробелов), _render_page (plain/html/заголовок только на первой), build_action_bar (одна страница/пагинация first-middle-last/extra_rows/без parent_cb), finalize_answer (успех/is_html/ошибка edit), get_answer, _get_parent_handler (известный/неизвестный), _dispatch_parent (успех/нет handler/ошибка), cb_ab_pg_noop, cb_ab_page (нет данных/битые parts/bad idx/нет ответа/вне диапазона/успех/ошибка edit), cb_ab_back (нет данных/нет ответа/нет parent/dispatch успех+fail), cb_ab_ai (нет данных/нет ответа/успех с меню режимов), _build_ai_context (нет wing/кэш-саммари/MCP-выдвижные ящики/пустые/ошибка), cb_ab_ai_run (нет данных/bad parts/нет ответа/режим a+c/ошибка ИИ), cb_ab_web (нет ответа/успех/пустой запрос/ошибка ИИ), cb_ab_web_go (нет ответа/нет запроса/успех), _run_web_search_finalize (успех/пустые результаты/ошибка поиска/ошибка edit), cb_ab_web_edit (нет ответа/успех+_pending_mcp_input), run_web_search_with_query (нет ответа/успех), cb_ab_sv/sv_p/sv_n (нет ответа/успех/запись в файл/ошибка makedirs), no-data guard для 6 callbacks, 11 callbacks not allowed.
- [x] 40. `handlers/palace/navigation.py` 44% → **100%**, 206 тестов (tests/test_palace_navigation.py): codec-хелперы (encode/decode roundtrip/битый base64/битый json/не-dict/legacy wing+room), cb_nav_menu, cb_list_wings (dict/list/ошибка), cb_rooms_menu (успех/«ещё N»/(пусто)/edit fail→answer/ошибка), cb_rooms_select (нет данных/короткое/успех/51 комната/пусто/ошибка), cb_open_room_drawer (нет данных/пустая пара/успех), cb_get_drawer (успех/fallback search/ошибка), cb_cross_ai_article (нет сессии/нет записей/успех/ошибка), cb_continue_read(+noop), cb_taxonomy (dict/list/ошибка), cb_taxonomy_wing (bad idx/кэш/refetch/вне диапазона/нет комнат), cb_graph (с/без туннелей/ошибка), _show_drawers_page (пусто/успех с навигацией/ошибка), cb_read_drawer (все ветки + refetch + строка + нет content + ошибки), _show_drawer_content (успех/пусто/edit fail→answer), cb_read_drawer_back (с state/ctx/нет данных), delete confirm/cancel/page (все ветки), cb_ask_room_ai, _answer_room_ai (нет записей/полный флоу/пустая саммари/16 записей/35000-лимит/ошибка drawer/нет id/with_web с саммари и без), cb_room_ai_web, traverse (menu/manual/step), tunnels (menu/list/empty/trunc/между/traverse_tunnel/tow/ai_discuss/create/ai/detail/detail_both/delete/delete_confirm/follow_a/follow_b + все list-формы и no-data), 42 callbacks not allowed.
  - **Баг исправлен в коде**: `_decode_wing_callback_data` срезал `"p_rs_"` (5 символов) вместо `"p_rs_:"` (6) — map-лукап всегда промахивался и крыло превращалось в `:hexkey` (выбор крыла в комнатах был полностью сломан). Фикс: `data[len("p_rs_:"):]`.
- [x] 41. `handlers/palace/__init__.py` 7% → **100%**, 47 тестов (tests/test_palace_init.py): cmd_palace (меню), cb_palace_back, cb_palace_main_menu (sys.modules `__main__` и fallback-импорт из main), process_mcp_text_input — no action→False, list_rooms `*` (dict/list крыльев/кэш/extra_rows) и конкретное крыло (усечение 50 комнат), traverse (ошибка+подсказки/ошибка без подсказок/результаты/пусто/цифровая комната/hops из первой части), fallback save_state→save_new_room, fsm-pop+clear при не-IDLE состоянии, save_quote/save_new_wing (subprocess успех+ошибка)/save_new_room (с и без state), kg_add_subject (с и без state)/kg_add_object (с и без state), kg_query (нет фактов с p_kgrs/факты+_kg_page_data), find_tunnels (пустой/одно крыло/два крыла через перенос строки/найдены), follow_tunnels (короткий/успех), create_tunnel (нет state/метка/«-»/битый json), ask_room_ai (полный/короткий action), tunnel_discuss (нет ctx/не найден/успех/ошибка чтения drawer/ошибка ИИ), неизвестный action fall-through, топ-уровневая ошибка MCP.
- [x] 42. `handlers/messages.py` 7% → **100%**, 86 тестов (tests/test_messages_handler.py): _on_ai_complete (с/без данных), _on_ai_sent (успех/ошибка send), _auto_sync_wrapper, YouTube audio (video quality/audio успех/пусто/компрессия/split-части/очистка parts с ошибкой/download error), early-returns (mcp/reminder/quote/tr_ai/note), wing search (`p_src:s1`+`search:wing`), web search (deep_search_web: ai_summary/fallback/пусто/не-dict/error), Mac-команды, fast note `!` (show_links/ошибки linker/write), имя чата (создан/пустое/save error), auto-активация (Активирован/Создан чат/newest ch_*.json), префиксы `!!`/`???` (ext_/чаты), /web (использование/успех), полный AI-флоу (кэш/ошибки/send-fail/wings /dreams:/user-context drawer+rooms/degrade palace+memory/coding mode/photo images/summary/SEARCH-паттерн: delete-fail/error/кэш-cleanup/status edit fail/пустой drawer-raw/неименованные drawer'ы).
  - **Проверено и оставлено на 99% (недостижимый защитный guard)**: `chat.py` строка 423 (`full_text` всегда непустой при непустом messages — заголовок роли добавляется всегда) и `reactions.py` `82->exit` (elif-цепочка: ветка достижима только для action не из action_map, но тогда срабатывает ранний return).

## Важно
- Бот запущен (PID 42905) и держит `bot_state.sqlite` в корне. Не трогать её в тестах — всегда использовать `tmp_path`/мок.
- `kv_store.py` `__init__` теперь принимает `db_path: str | None = None`.

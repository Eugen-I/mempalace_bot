# AUDIT_FIX_PROGRESS — журнал устранения замечаний аудита

**Проект:** `/Users/evg.pit/Documents/mempalace_bot`
**План:** `AUDIT_FIX_PLAN.md`
**Создан:** 2026-10-25
**Статус работы:** в работе (9/45 шагов `DONE`)

> Это единственный источник истины о ходе работ.
> **Не удаляй старые записи и не переписывай историю** — только добавляй новые и меняй статусы в таблице.
> Шаг нельзя считать завершённым, пока в журнале нет записи по нему, commit hash и результата проверок.

---

## 1. Как вести журнал

### 1.1. Перед началом шага

1. Найди первый шаг со статусом `IN_PROGRESS`, `PARTIAL` или `BLOCKED`. Если таких нет — первый `TODO`.
2. Обнови «Текущий снимок»:
   - дата/время;
   - ветка и `HEAD`;
   - ID шага;
   - статус `IN_PROGRESS`;
   - бюджет шага.
3. В таблице шагов поставь `IN_PROGRESS`, дату и оценку.
4. Проверь `git status --short`; если есть чужие изменения — запиши их в «Текущий снимок», не трогай.

### 1.2. После завершения шага

1. Запусти проверки из плана (раздел 5).
2. В таблице поставь:
   - `DONE` — если AC выполнены, тесты зелёные, коммит есть;
   - `PARTIAL` — если токены/контекст закончились, но есть рабочее промежуточное состояние;
   - `BLOCKED` — если нужна помощь пользователя/внешнее решение;
   - `SKIPPED` — только с явным одобрением пользователя.
3. Заполни commit hash, дату, фактический/оценочный расход токенов.
4. Добавь запись в «Журнал шагов» по шаблону (раздел 6). Даже для `BLOCKED`/`PARTIAL` запись обязательна.
5. Если остановился из-за лимита токенов — заполни `HANDOFF` (раздел 8).

### 1.3. Жёсткие правила

- Один шаг = один логический набор изменений = один коммит (кроме WIP/handoff, явно помеченного).
- Не ставь `DONE` без реального вывода тестов. Строка «должно работать» запрещена.
- Не удаляй и не переписывай записи предыдущих сессий.
- Не меняй `AUDIT_FIX_PLAN.md` под текущий прогресс. Если план ошибся — запись в «Отклонения от плана».
- Если нашёл побочную проблему — не чини её в текущем шаге, добавь в «Найдено попутно».
- Не коммить `.env`, токены, `bot_state.sqlite`, `coverage.xml`, `mutants/`, чужие untracked-файлы.

---

## 2. Текущий снимок

> Обновлять в начале и конце каждого шага.

- **Дата последнего обновления:** 2026-10-27 00:07 CET
- **Ветка:** `fix/audit-2026-10-25`
- **HEAD:** последний code-коммит S1.12 — `df66c40`, docs-коммит — `ab495ed`
- **Текущий шаг:** `S1.12` — завершён
- **Статус:** `DONE`
- **Следующее действие:** `S2.1` — `has_active_button_session`: пустой список считается активной сессией
- **Бюджет текущего шага:** 30k
- **Израсходовано (оценка):** ~22k (прошлое время, UUID-ключи, JSON/таймзоны, 12 тестов, QA)
- **Незакоммиченные изменения:** только этот файл прогресса; `.env` и чужие untracked-файлы не трогать.
- **Резервная копия:** `~/Documents/mempalace_bot_backups/mempalace_bot_full_20261025_121520.tar.gz` (4.7 MB, sha256 `dd02b6a1...aab4ea`)
- **Известные блокеры:** нет. Pre-existing: `test_day_bounds_midnight` (date-dependent); флак `test_confirm_write_delete_requires_two_confirmations`; TTL-флак устранён в S1.9.
- **Последний QA:** 3621 passed / 0 failed, coverage 98%; `reminder.py` 98%; lint — 8 baseline, mypy — 1 baseline, bandit 72 Low (на 1 меньше)
- **Примечание:** номера строк в плане — якоря на дату аудита; перед правкой искать символы заново.

---

## 3. Статусы

| Статус | Значение |
|---|---|
| `TODO` | не начат |
| `IN_PROGRESS` | выполняется прямо сейчас |
| `DONE` | AC выполнены, тесты/QA зафиксированы, есть коммит |
| `PARTIAL` | работа приостановлена (токены/контекст), есть handoff |
| `BLOCKED` | нужна помощь пользователя или внешнее решение |
| `SKIPPED` | пропущен с явным одобрением пользователя |

---

## 4. Таблица шагов

> `Токены` — консервативная оценка расхода. Если харнесс показывает точное значение — записывай его.

| ID | Шаг | Приоритет | Бюджет | Статус | Коммит | Обновлено | Токены |
|---|---|---|---:|---|---|---|---|
| S0.1 | Baseline, ветка, фиксация состояния | P0 | 25k | DONE | `0eeeb41` | 2026-10-25 12:17 | ~15k |
| S0.2 | Общие тестовые фикстуры | P0 | 25k | DONE | `a813965` | 2026-10-25 12:25 | ~12k |
| S1.1 | Контракт ответа агента | P0 | 30k | DONE | `b5d72d1` | 2026-10-25 13:32 | ~18k |
| S1.2 | `safe_html_format` и `_TAG_RE` | P0 | 25k | DONE | `b2a5089` | 2026-10-25 15:26 | ~20k |
| S1.3 | Async-обёртка AI | P0 | 35k | DONE | `8d69c79` | 2026-10-25 15:46 | ~12k |
| S1.4a | Async AI в `palace/navigation.py` | P0 | 35k | DONE | `c2484f8` | 2026-10-25 15:55 | ~16k |
| S1.4b | Async AI в action_bar/palace/transkript | P0 | 30k | DONE | `c6da708` | 2026-10-25 16:04 | ~14k |
| S1.5 | `_sync_ai_call`: unbound/Gemini | P0 | 40k | DONE | `0ca9871` | 2026-10-25 16:11 | ~18k |
| S1.6 | Структурированный стриминг | P0 | 35k | DONE | `72f8ac7` | 2026-10-25 16:18 | ~16k |
| S1.7 | Не кэшировать ошибки стриминга | P0 | 35k | DONE | `4a9c086` | 2026-10-25 16:29 | ~20k |
| S1.8 | `palace_mcp`: stderr/timeout/lifecycle | P0 | 40k | DONE | `39f5e47` | 2026-10-25 16:39 | ~20k |
| S1.9 | Контекстный semantic cache | P0 | 35k | DONE | `62af728` | 2026-10-25 16:55 | ~30k |
| S1.10 | Токен и пути `.env` | P0 | 20k | DONE | `21953ac` | 2026-10-25 17:10 | ~18k |
| S1.11 | Circuit breaker: сброс счётчика | P0 | 15k | DONE | `c677438` | 2026-10-25 17:20 | ~10k |
| S1.12 | Напоминания: время/ключи/JSON | P0 | 30k | DONE | `df66c40` | 2026-10-27 00:05 | ~22k |
| S2.1 | Пустая button-сессия активна | P1 | 20k | TODO | — | — | — |
| S2.2 | `append_always_on` в историю | P1 | 25k | TODO | — | — | — |
| S2.3 | Убрать хардкод Gemini-модели | P1 | 20k | TODO | — | — | — |
| S2.4 | Ошибки `load_chat`/`save_chat` | P1 | 25k | TODO | — | — | — |
| S2.5 | Graceful degradation | P1 | 35k | TODO | — | — | — |
| S2.6 | Настройки: история | P1 | 35k | TODO | — | — | — |
| S2.7 | Настройки: экспорт | P1 | 35k | TODO | — | — | — |
| S2.8 | Настройки: инсайты | P1 | 35k | TODO | — | — | — |
| S2.9 | Настройки: исследования | P1 | 30k | TODO | — | — | — |
| S3.1 | Единый chat store | P2 | 40k | TODO | — | — | — |
| S3.2 | Единая синхронизация дворца | P2 | 25k | TODO | — | — | — |
| S3.3 | Единый список чатов | P2 | 30k | TODO | — | — | — |
| S3.4 | Единый summary | P2 | 45k | TODO | — | — | — |
| S3.5 | Единый wing registry | P2 | 20k | TODO | — | — | — |
| S3.6 | Единый palace bridge | P2 | 30k | TODO | — | — | — |
| S3.7 | Единый web search cache | P2 | 30k | TODO | — | — | — |
| S3.8a | AI engine: helpers | P2 | 35k | TODO | — | — | — |
| S3.8b | AI engine: общий pipeline | P2 | 45k | TODO | — | — | — |
| S3.9 | Reminder prompt/JSON | P2 | 25k | TODO | — | — | — |
| S3.10 | Palace utils/wrappers | P2 | 25k | TODO | — | — | — |
| S4.1 | Безопасные ruff autofix | P2 | 30k | TODO | — | — | — |
| S4.2 | Мёртвый код/unused/mypy | P2 | 25k | TODO | — | — | — |
| S4.3 | Критичные `except Exception` | P2 | 40k | TODO | — | — | — |
| S4.4 | Зависимости и flake8-конфиг | P2 | 20k | TODO | — | — | — |
| S4.5 | Garmin/mutants/untracked | P2 | 25k | TODO | — | — | — |
| S4.6 | CI quality gate | P2 | 30k | TODO | — | — | — |
| S4.7 | Покрытие критичных сервисов A | P2 | 40k | TODO | — | — | — |
| S4.8 | Покрытие критичных handler'ов B | P2 | 40k | TODO | — | — | — |
| S4.9 | Полный regression и отчёт | P0 | 40k | TODO | — | — | — |
| S4.10 | Smoke/acceptance | P1 | 20k | TODO | — | — | — |

---

## 5. Прогресс по фазам

| Фаза | Всего шагов | DONE | PARTIAL/BLOCKED | TODO |
|---|---:|---:|---:|---:|
| 0 — подготовка | 2 | 2 | 0 | 0 |
| 1 — P0 | 13 | 13 | 0 | 0 |
| 2 — P1 | 9 | 0 | 0 | 9 |
| 3 — P2 дублирование | 11 | 0 | 0 | 11 |
| 4 — чистота/тесты | 10 | 0 | 0 | 10 |
| **Итого** | **45** | **15** | **0** | **30** |

> Обновлять после каждого шага.

---

## 6. Журнал шагов

> Добавляй новый блок **в конец** раздела после каждого шага.
> Для `DONE` обязательны commit hash и вывод проверок. Для `PARTIAL`/`BLOCKED` — точное следующее действие.

### Шаблон записи

```text
### Sx.y — <название шага>
- Дата/время:
- Агент/модель:
- Ветка/HEAD:
- Статус: DONE | PARTIAL | BLOCKED | SKIPPED
- Бюджет/факт (оценка):
- Файлы:
- Что сделано:
- Тесты и команды:
  - `<команда>` → <результат>
- QA:
  - lint:
  - mypy:
  - bandit:
  - coverage:
- AC:
  - [x] ...
  - [ ] ...
- Коммит:
- Проблемы/решения:
- Найдено попутно (ID записи из раздела 9):
- Следующее действие:
```

### Пример заполненной записи (не удалять)

```text
### S0.0 — Пример
- Дата/время: 2026-10-25 12:00
- Агент/модель: <model>
- Ветка/HEAD: fix/audit-2026-10-25 / abc1234
- Статус: DONE
- Бюджет/факт (оценка): 25k / 18k
- Файлы: AUDIT_FIX_PROGRESS.md
- Что сделано: зафиксирован baseline, создана ветка.
- Тесты и команды:
  - `python3 -m pytest --collect-only -q` → 3498 tests collected
  - `make qa` → passed (кроме известного Garmin ImportError)
- QA:
  - lint: 0 новых
  - mypy: 0 новых
  - bandit: baseline без изменений
  - coverage: baseline записан
- AC:
  - [x] Baseline записан
  - [x] Ветка создана
- Коммит: abc1234
- Проблемы/решения: Garmin-фича не собирается — зафиксировано, не чинилось.
- Найдено попутно: —
- Следующее действие: S0.2
```

### S0.1 — Baseline, ветка, фиксация исходного состояния

- Дата/время: 2026-10-25 12:15–12:17 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `c7a8ca2`
- Статус: `DONE`
- Бюджет/факт (оценка): 25k / ~15k
- Файлы: `AUDIT_FIX_PLAN.md`, `AUDIT_FIX_PROGRESS.md`; резервная копия вне репозитория
- Что сделано:
  1. Создана полная резервная копия проекта:
     `~/Documents/mempalace_bot_backups/mempalace_bot_full_20261025_121520.tar.gz`
     (4.7 MB; исключены только `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `*.pyc`, `.DS_Store`; `.git`, `mutants/`, untracked-файлы включены).
     `gzip -t` → OK; sha256 `dd02b6a13de240a87cbffb0eafdc9849f29d2c517c08e6cd0c2e9de277aab4ea`.
  2. Создана рабочая ветка `fix/audit-2026-10-25` от `backup-before-garmin-sqlite-integration` (`c7a8ca2`).
  3. Снят baseline метрик и известных падений.
- Тесты и команды:
  - `python3 --version` → Python 3.14.3
  - `python3 -m pytest --collect-only -q` → **3498 tests collected in 5.75s**; coverage в этом режиме 15% — артефакт `--collect-only`, не показатель.
  - `make test` → **3496 passed, 2 failed, 6 warnings in 22.34s**, coverage **98%**.
    - `tests/test_digest.py::test_day_bounds_midnight` — `assert 1792969200.0 == (1792879200.0 + 86400)`.
    - `tests/test_notes_agent_handler.py::test_confirm_write_delete_requires_two_confirmations` — `AttributeError: 'NoneType' object has no attribute 'inline_keyboard'` (flaky/окружение).
  - `make lint` → exit 2, 9 замечаний:
    - `config.py:117` W391;
    - `models/garmin.py:198` W292;
    - `scripts/verify_garmin_login.py` F401/E402/E501×2/W292;
    - `services/deps_guard.py:84` W292.
    Часть замечаний — в untracked Garmin-файлах, которые не входят в текущую работу.
  - `make typecheck` → exit 2, 5 ошибок:
    - `handlers/chat.py:32` — `TtlDict` не generic;
    - `handlers/agent.py:76,80,84` — Return value expected;
    - `handlers/palace/__init__.py:589` — несовместимый тип.
  - `python3 -m ruff check handlers services main.py config.py --statistics` → **495 errors**; топ: 200 `BLE001`, 67 `RUF100`, 52 `S110`, 39 `G201`, 37 `I001`, 24 `DTZ005`, 22 `ASYNC230`, 14 `DTZ006`, 5 `PLW1510`, 4 `RUF059`.
  - `python3 -m ruff check . --statistics` → **1053 errors** (включает `tests/`, `features/`, `mutants/`; для source-базлайна использовать 495).
  - `make security` → exit 2; **74 Low, 0 Medium, 0 High**; `make` возвращает ошибку из-за наличия low-замечаний.
  - `python3 -m vulture handlers/ services/ main.py config.py` → exit 3, 315 строк findings (в основном 60% confidence, требует фильтрации).
- QA:
  - lint: baseline 9 (включая untracked Garmin)
  - mypy: baseline 5
  - bandit: baseline 74 Low
  - ruff: source baseline 495
  - coverage: 98% (`make test`), 3496/3498 passed
- AC:
  - [x] Ветка создана, HEAD записан.
  - [x] Baseline-метрики и известные падения занесены в журнал.
  - [x] Ни один untracked-файл пользователя не изменён и не закоммичен.
- Коммит: `0eeeb41` (`chore(step-0.1): add audit plan and baseline`)
- Проблемы/решения:
  - Baseline не зелёный (2 теста, lint/mypy/ruff/bandit) — это исходное состояние, не регрессия; чинится в шагах S1.x/S4.x.
  - `make lint` захватывает untracked `models/garmin.py` и `scripts/verify_garmin_login.py`; в S4.5 нужно решить их судьбу.
  - `pytest --collect-only` перезаписал `coverage.xml` (gitignored) — на код не влияет.
- Найдено попутно: —
- Следующее действие: `S0.2` — общие тестовые фикстуры для AI/async/JSON.

### S0.2 — Общие тестовые фикстуры для AI/async/JSON

- Дата/время: 2026-10-25 12:20–12:25 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `64f6d1e`
- Статус: `DONE`
- Бюджет/факт (оценка): 25k / ~12k
- Файлы: `tests/conftest.py`, `tests/test_audit_fixtures.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. В `tests/conftest.py` добавлены opt-in фикстуры, не влияющие на старые тесты:
     - `fake_ai_client` — управляемый `FakeAIClient` с `response`, `error`, `delay`, `calls`, методами `complete()` и `acomplete()`;
     - `heartbeat` — фабрика `Heartbeat` (async context manager), которая тикает в event loop и позволяет проверять, что `await` не блокируется;
     - `temp_chat_dir` — изолированный пустой каталог `tmp_path/chats`;
     - `fixed_clock` — `FixedClock` с управляемыми `now()`, `time()`, `advance()` без глобальной подмены времени.
  2. Добавлен `tests/test_audit_fixtures.py` — 6 smoke-тестов на все новые фикстуры, включая async-пример с heartbeat.
  3. Поведение production-кода не менялось.
- Тесты и команды:
  - `python3 -m pytest tests/test_audit_fixtures.py -q --tb=short --override-ini=addopts=-ra` → **6 passed in 2.20s**.
  - `make test` → **3503 passed, 1 failed, 6 warnings in 88.07s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight` (`assert 1792969200.0 == (1792879200.0 + 86400)`).
    - `test_confirm_write_delete_requires_two_confirmations` (флаки) в этом прогоне прошёл.
  - `python3 -m flake8 tests/conftest.py tests/test_audit_fixtures.py` → 0.
  - `python3 -m ruff check tests/conftest.py tests/test_audit_fixtures.py` → только 2 pre-existing замечания в старом import-guard (`BLE001`/`S110`, строки 40–41); новых нет.
  - `make typecheck` → те же 5 baseline-ошибок, новых нет.
  - `make lint` → те же 9 baseline-замечаний (untracked Garmin + `config.py` + `deps_guard.py`), новых нет.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 5, новых 0
  - bandit: не менялся (production-код не трогали)
  - coverage: 98%
- AC:
  - [x] Фикстуры не влияют на старые тесты.
  - [x] Есть пример async-теста с heartbeat.
  - [x] Полный `make test` не хуже baseline: 3503 passed / 1 pre-existing failed.
- Коммит: `a813965` (`test(step-0.2): add shared async/ai fixtures`)
- Проблемы/решения:
  - `make test` идёт ~88 с вместо baseline ~22 с — вероятно, нагрузка/кэш; новых падений нет.
  - В `tests/conftest.py` остались 2 pre-existing ruff-замечания в старом import-guard; чинить их в S0.2 не стал — это S4.3.
- Найдено попутно: —
- Следующее действие: `S1.1` — единый контракт ответа агента.

### S1.1 — Единый контракт ответа агента

- Дата/время: 2026-10-25 13:17–13:32 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `ae67d1b`
- Статус: `DONE`
- Бюджет/факт (оценка): 30k / ~18k
- Файлы: `services/agent_engine.py`, `handlers/agent.py`, `handlers/notes_agent.py`, `handlers/palace/__init__.py`, `tests/test_agent_handler.py`, `tests/test_notes_agent_handler.py`, `tests/test_palace_init.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. `AgentResult` получил контракт завершённости:
     - свойство `ok` — `True` только при `finished_reason == "answer"`;
     - classmethod `failure(error)` — безопасный результат с `final_answer=""`, `finished_reason="error"`, `error=<текст>`.
  2. `_run_agent_reply` теперь возвращает `AgentResult` на **всех** ветках:
     - `AgentEngineError` → `failure(str(exc))` + статус `⚠️ …`;
     - неожиданное исключение → `failure("Ошибка агента: …")` + статус `❌ …`;
     - `finished_reason == "error"` → возвращается сам результат, а не `None`;
     - `max_iterations` и успех — как раньше, возвращается результат.
  3. `_run_notes_agent_reply` приведён к тому же контракту (`-> ae.AgentResult`, ошибки через `failure`).
  4. Вызывающие обновлены:
     - `cb_ab_agent` и palace-button-сессия сохраняют ответ в историю только при `result.ok and result.final_answer`;
     - в `handlers/palace/__init__.py` локальная переменная агента переименована в `agent_result`, чтобы не конфликтовать с `result` от `_sync_ai_call` (это также убрало старую mypy-ошибку на строке 589).
  5. Поведение успешного ответа не изменилось; при ошибке пользователь видит понятный текст в статус-сообщении, traceback не показывается.
- Тесты и команды:
  - `python3 -m pytest tests/test_agent_handler.py tests/test_notes_agent_handler.py::test_run_notes_agent_wiring … tests/test_palace_init.py::test_process_mcp_text_input_button_agent_error_is_safe -q --tb=short --override-ini=addopts=-ra` → **31 passed**.
  - `make test` → **3508 passed, 1 failed, 6 warnings in 135.74s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - Флаки `test_confirm_write_delete_requires_two_confirmations` в полном прогоне прошёл; при отдельном запуске одного файла один раз упал по таймингу (см. «Найдено попутно»).
  - `make typecheck` → **1 error** (`handlers/chat.py:32`, `TtlDict` generic — S1.3); было 5, ошибки `handlers/agent.py` и `handlers/palace/__init__.py:589` устранены.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make security` → 74 Low, 0 Medium/High — baseline, новых нет.
  - `flake8` по изменённым файлам → 0.
- QA:
  - lint: baseline 9, новых 0
  - mypy: 5 → 1 (осталась несвязанная `TtlDict` в `handlers/chat.py`)
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%
- AC:
  - [x] Нет обращений к `.final_answer` у потенциально `None`: оба runner'а всегда возвращают `AgentResult`.
  - [x] `mypy` по `handlers/agent.py` без ошибок «Return value expected».
  - [x] Есть regression-тесты на `AgentEngineError`, неожиданное исключение и `finished_reason="error"`.
  - [x] `notes_agent` и palace-путь покрыты тестами.
- Коммит: `b5d72d1` (`fix(step-1.1): make agent reply contract total`)
- Проблемы/решения:
  - При первом целевом прогоне `test_confirm_write_delete_requires_two_confirmations` упал: `status.reply_markup is None` — тест ждёт карточку 50 мс, а `_note_title` успевает сходить в Apple Notes. Это pre-existing флак, не связан с контрактом; повторный запуск и полный `make test` прошли. Не чинил в S1.1, чтобы не смешивать изменения.
- Найдено попутно:
  - `tests/test_notes_agent_handler.py::test_confirm_write_delete_requires_two_confirmations` — тайминг-флак (ожидание 0.05 с после `_make_confirm_write`, внутри которого `_note_title` делает `asyncio.to_thread(apple_notes.list_notes)`). Кандидат на стабилизацию в S4.x.
  - `handlers/chat.py:32` — `TtlDict` не generic; остаётся единственной mypy-ошибкой, чинится в S1.3.
- Следующее действие: `S1.2` — `safe_html_format` и `_TAG_RE`.

### S1.2 — Исправление `safe_html_format` и `_TAG_RE`

- Дата/время: 2026-10-25 15:15–15:26 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `b2a5089`
- Статус: `DONE`
- Бюджет/факт (оценка): 25k / ~20k
- Файлы: `services/text_formatter.py`, `tests/test_text_formatter.py`, `tests/test_action_bar.py`, `tests/test_brainstorm.py`, `tests/test_brainstorm_handler.py`, `tests/test_digest.py`, `tests/test_notes_agent_handler.py`, `tests/test_palace_save_result.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. Удалено второе (перекрывавшее первое) определение `_TAG_RE`. Осталось одно модульное определение с capture-группой; его используют и sanitizer, и `split_message`.
  2. `_escape_outside_allowed_tags` переписан как безопасный sanitizer:
     - разрешённые теги из `ALLOWED_TAGS` сохраняются;
     - неизвестные теги (`<script>`, `<x>`, …) экранируются;
     - атрибуты отбрасываются, кроме `href` у `<a>`;
     - `href` допускается только со схемами `http://`, `https://`, `tg://`, `mailto:`, значение экранируется;
     - «висячие» закрывающие теги экранируются;
     - незакрытые разрешённые теги закрываются в конце, неправильный порядок вложенности нормализуется.
  3. Markdown-code вынимается до markdown-преобразований:
     - fenced code → `<pre><code>…</code></pre>`;
     - inline code → `<code>…</code>`;
     - содержимое кода экранируется и не форматируется (`**`, `*`, HTML-теги внутри кода остаются текстом);
     - язык fence'а распознаётся только в первой строке; fence без перевода строки не съедает код как «язык».
  4. `safe_html_format` теперь принимает `None` и возвращает `""`; старый баг с inline-regex, ломавшим тройные бэктики, устранён.
  5. Обновлены тесты, которые закрепляли ошибочное экранирование разрешённых тегов:
     - в `tests/test_text_formatter.py` `<b>` теперь проверяется как сохраняемый, а для проверки экранирования используются `<script>` и опасные ссылки;
     - в `test_action_bar`, `test_brainstorm`, `test_brainstorm_handler`, `test_digest`, `test_notes_agent_handler`, `test_palace_save_result` проверки «HTML экранирован» переведены на `<script>`; добавлены проверки, что разрешённые теги сохраняются.
     - Это не ослабление тестов: опасный HTML по-прежнему обязан экранироваться, а новый контракт отдельно проверяет whitelist.
  6. Добавлены regression-тесты: whitelist всех разрешённых тегов, безопасные/опасные ссылки, незакрытые и «висячие» теги, неправильная вложенность, `None`, code fence с HTML/Markdown, fence без newline, fence с языком `c#`.
- Тесты и команды:
  - `python3 -m pytest tests/test_text_formatter.py -q --tb=short --override-ini=addopts=-ra` → **58 passed in 0.07s**.
  - `python3 -m pytest tests/test_text_formatter.py tests/test_action_bar.py -q --tb=short --override-ini=addopts=-ra` → **168 passed in 3.02s**.
  - Подмножество затронутых файлов до финальной правки fence-regex → **472 passed, 1 pre-existing failed** (`test_day_bounds_midnight`).
  - `make test` → **3527 passed, 1 failed, 6 warnings in 15.75s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight` (`assert 1792969200.0 == (1792879200.0 + 86400)`).
  - `make lint` → те же 9 baseline-замечаний (untracked Garmin, `config.py:117`, `services/deps_guard.py:84`), новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32` (`TtlDict` generic), новых 0.
  - `make security` → **74 Low, 0 Medium, 0 High** — baseline, новых 0.
  - `python3 -m flake8 tests/test_text_formatter.py tests/test_action_bar.py` → 0.
  - `python3 -m ruff check services/text_formatter.py` → 0 (по изменённым production-файлам); в затронутых тестах остались pre-existing замечания (UP031/I001 и др.), новых от S1.2 нет.
  - `git diff --check` → чисто.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%; `services/text_formatter.py` — 97%
- AC:
  - [x] Разрешённый HTML не экранируется; опасный экранируется.
  - [x] Code fence преобразуется в `<pre><code>`, содержимое кода не ломается Markdown.
  - [x] Незакрытые/разорванные/неправильно вложенные теги не ломают итоговый HTML.
  - [x] Дублирующее определение `_TAG_RE` удалено.
  - [x] Тесты, закреплявшие баг, обновлены осознанно; причина зафиксирована здесь.
- Коммит: `b2a5089` (`fix(step-1.2): repair safe html formatting`)
- Проблемы/решения:
  - Pre-commit на изменённых тестовых файлах обнаружил два pre-existing flake8-замечания: F811 (дубликат `test_split_hard_limit_no_delimiters`) и F841 (`labels` без использования). Удалён байт-в-байт дубликат теста (покрытие не потеряно) и заменено бессмысленное присваивание на проверку markup. Это позволило коммиту пройти без ослабления тестов.
  - Один промежуточный полный прогон дал флаки `tests/test_semantic_cache.py::TestSemanticCache::test_ttl_eviction` (TTL=0, гонка `>`); отдельный повтор 5/5 прошёл, финальный `make test` — прошёл. Не связан с S1.2.
- Найдено попутно:
  - `test_semantic_cache.py::test_ttl_eviction` — тайминг-флак при `ttl=0`; кандидат на стабилизацию в S4.x.
  - Вызывающие, которые оборачивают результат `safe_html_format` в `<code>` (например, `drawer_id` в `handlers/palace/save.py`), могут получить nested allowed-тег внутри code. Для гарантированно литерального вывода таким вызывающим нужен `html.escape`, а не `safe_html_format`; отдельный шаг не входит в S1.2.
- Следующее действие: `S1.3` — async-обёртка AI.

### S1.3 — Async-обёртка для AI-вызовов

- Дата/время: 2026-10-25 15:43–15:46 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `8d69c79`
- Статус: `DONE`
- Бюджет/факт (оценка): 35k / ~12k
- Файлы: `services/ai_engine.py`, `tests/test_ai_engine.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. Добавлен сервисный адаптер `call_ai_async(engine, model, messages, context, user_query, has_images, *, timeout=None, **kwargs)`:
     - вызывает существующий `_sync_ai_call` через `asyncio.to_thread`;
     - оборачивает ожидание в `asyncio.wait_for` с таймаутом;
     - если `engine`/`model` не переданы, разрешает их через существующий `get_current_ai()`, без второй логики выбора;
     - таймаут по умолчанию — `DEFAULT_AI_TIMEOUT = 210.0` (чуть больше сетевого таймаута провайдеров 200 с);
     - неположительный таймаут отклоняется `ValueError`;
     - ошибки sync-вызова пробрасываются вызывающему без превращения в пользовательскую строку;
     - превышение таймаута выбрасывает `AITimeoutError` (наследник `TimeoutError`) с engine/model/длительностью.
  2. В docstring явно зафиксировано: отмена `asyncio.to_thread` не убивает рабочий поток; sync-вызов может продолжить работу, поэтому таймаут обязателен для долгих запросов.
  3. Существующие вызовы не мигрировались — это S1.4a/S1.4b. `get_ai_response_async` не менялся.
  4. Добавлены 7 тестов: возврат результата и проброс аргументов, разрешение engine/model через resolver, явный таймаут, таймаут по умолчанию, неположительный таймаут, проброс sync-исключения, отзывчивость event loop через `heartbeat`.
- Тесты и команды:
  - `python3 -m pytest tests/test_ai_engine.py -q --tb=short --override-ini=addopts=-ra` → **77 passed in 3.25s**.
  - `make test` → **3534 passed, 1 failed, 6 warnings in 15.40s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `services/ai_engine.py` — **100%** coverage.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **74 Low, 0 Medium, 0 High** — baseline, новых 0.
  - `python3 -m flake8 services/ai_engine.py tests/test_ai_engine.py` → 0.
  - `python3 -m mypy --explicit-package-bases services/ai_engine.py` → 0.
  - `git diff --check` → чисто.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%; `services/ai_engine.py` — 100%
- AC:
  - [x] Новая async-обёртка покрыта тестами.
  - [x] Нет нового блокирующего вызова в event loop (проверено heartbeat-тестом).
  - [x] Таймаут и исключения пробрасываются предсказуемо.
  - [x] Resolver переиспользован, второй логики выбора движка/модели нет.
- Коммит: `8d69c79` (`feat(step-1.3): add async ai call adapter`)
- Проблемы/решения:
  - `asyncio.to_thread` не умеет принудительно останавливать поток; это ограничение задокументировано, а не замаскировано. Для долгих вызовов выбран явный внешний таймаут.
  - Старый `get_ai_response_async` оставлен без изменений, чтобы S1.3 не превратился в миграцию всех вызовов.
- Найдено попутно:
  - `get_ai_response_async` по-прежнему не имеет таймаута и создаёт отдельный `ThreadPoolExecutor` на каждый вызов. Не менял в S1.3; кандидат на S1.4/S1.5 или отдельный шаг.
- Следующее действие: `S1.4a` — перевести `handlers/palace/navigation.py` на `call_ai_async`.

### S1.4a — Async AI в `handlers/palace/navigation.py`

- Дата/время: 2026-10-25 15:49–15:55 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `c2484f8`
- Статус: `DONE`
- Бюджет/факт (оценка): 35k / ~16k
- Файлы: `handlers/palace/navigation.py`, `services/ai_engine.py`, `tests/test_palace_navigation.py`, `tests/test_ai_engine.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. Удалён синхронный `_sync_ai_call_wrapper`. Все 5 прямых sync-вызовов в `navigation.py` переведены на `await call_ai_async(...)`:
     - статья по комнате (`cb_cross_ai_article`, сохранены `gemini`/`gemini-2.0-flash`);
     - ветка `with_web` в `_answer_room_ai`;
     - шаг 1 (саммари) в `_answer_room_ai`;
     - шаг 2 (ответ) в `_answer_room_ai`;
     - анализ туннелей (`cb_tunnels_ai`).
  2. Сохранены прежние сообщения, кнопки и порядок редактирования: «🌐 Ищу в интернете…» → «🧠 Составляю саммари…» → «🤔 Анализирую саммари…» → `finalize_answer`.
  3. Добавлен `_report_ai_error`: таймаут показывает «⏱️ ИИ не ответил вовремя. Попробуйте ещё раз.», прочие ошибки — «❌ Ошибка ИИ: …». Обработаны все три AI-вызова в `_answer_room_ai`, включая `with_web` и шаг 2; статус больше не остаётся «вечным». `cb_cross_ai_article`/`cb_tunnels_ai` сохранили прежний внешний `except` с «❌ Ошибка: …».
  4. Попутно поправлен `call_ai_async`: необязательные `context`, `user_query`, `has_images` передаются в `_sync_ai_call` только при непустых значениях. Это сохраняет семантику sync-дефолтов и совместимость с простыми тестовыми двойниками.
  5. Обновлены тесты, которые патчили удалённый wrapper, и добавлены проверки ошибок/таймаутов/отзывчивости loop.
- Тесты и команды:
  - `python3 -m pytest tests/test_ai_engine.py tests/test_palace_navigation.py tests/test_palace_navigation_callbacks.py tests/test_palace_language_prompts.py -q ...` → **313 passed**.
  - `make test` → **3542 passed, 1 failed, 6 warnings in 15.65s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `handlers/palace/navigation.py` — **100%**; `services/ai_engine.py` — **100%**.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **74 Low, 0 Medium, 0 High** — baseline, новых 0.
  - `python3 -m flake8 handlers/palace/navigation.py services/ai_engine.py tests/test_palace_navigation.py tests/test_ai_engine.py` → 0.
  - `git diff --check` → чисто.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%; изменённые `navigation.py` и `ai_engine.py` — 100%
- AC:
  - [x] В async-функциях `navigation.py` нет прямого `_sync_ai_call` (grep по файлу чист).
  - [x] Поведение UI на успешных путях не изменилось.
  - [x] Ошибки/таймауты не оставляют статус-сообщение в вечном состоянии.
  - [x] Event loop не блокируется (heartbeat-тест через реальный adapter).
- Коммит: `c2484f8` (`fix(step-1.4a): offload palace navigation ai calls`)
- Проблемы/решения:
  - Первая версия миграции всегда передавала в `_sync_ai_call` дефолтные `context`/`user_query`/`has_images`, из-за чего старые тестовые двойники с тремя аргументами падали. Исправлено в адаптере: дефолты не передаются.
  - Для `_answer_room_ai` выбран явный `except Exception` вокруг каждого AI-вызова с логированием; `CancelledError` (BaseException) не перехватывается.
- Найдено попутно:
  - В `tests/test_palace_navigation.py` был неиспользуемый импорт `SimpleNamespace`; удалён при правке файла.
- Следующее действие: `S1.4b` — `action_bar`, `palace/__init__`, `transkript`.

---

### S1.4b — Async AI в `action_bar`, `palace/__init__`, `transkript`

- Дата/время: 2026-10-25 16:00–16:04 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `c6da708`
- Статус: `DONE`
- Бюджет/факт (оценка): 30k / ~14k
- Файлы: `handlers/palace/action_bar.py`, `handlers/palace/__init__.py`, `handlers/transkript.py`, `tests/test_action_bar.py`, `tests/test_palace_action_bar.py`, `tests/test_transkript_handler.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. В `action_bar.py` переведены на `await call_ai_async(...)` все **3** прямых sync-вызова: режимы анализа `a`/`c` и финальный ответ web-поиска (`_run_web_search_finalize`). План указывал только 2 якоря; третий вызов найден по grep на строке 508.
  2. В `palace/__init__.py` переведён вызов анализа туннеля в `process_mcp_text_input`; локальный импорт `_sync_ai_call` удалён, `call_ai_async` импортируется на уровне модуля.
  3. В `transkript.py` `_answer_tr_ai` переведён на `await call_ai_async(...)` для обычного и `with_web` путей. Добавлена обработка ошибок: `AITimeoutError` → «⏱️ ИИ не ответил вовремя. Попробуйте ещё раз.», прочие исключения → `format_user_error`. Статус «🤔 Анализирую…» больше не остаётся вечным.
  4. Тесты `test_action_bar.py` и `test_palace_action_bar.py` переведены с патча sync-`_sync_ai_call` на async-`call_ai_async` через локальный helper `_async_ai`. В `test_transkript_handler.py` добавлены 3 теста: event loop не блокируется (heartbeat), обычная ошибка и таймаут заменяют статус.
  5. Попутно устранены два pre-existing E501 в `tests/test_transkript_handler.py` (строки 156 и 366), которые блокировали pre-commit flake8 после изменения файла. Только форматирование, логика не менялась.
- Тесты и команды:
  - `python3 -m pytest tests/test_action_bar.py tests/test_palace_action_bar.py tests/test_palace_init.py tests/test_transkript_handler.py tests/test_transkript_actions.py -q --tb=short --override-ini=addopts=-ra` → **333 passed, 1 warning in 3.63s**.
  - `python3 -m pytest tests/test_transkript_handler.py -q ...` после E501-правки → **57 passed, 1 warning in 3.05s**.
  - `make test` → **3545 passed, 1 failed, 6 warnings in 15.67s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `handlers/palace/action_bar.py` — **100%**, `handlers/transkript.py` — **100%**, `handlers/palace/__init__.py` — **96%**.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **74 Low, 0 Medium, 0 High** — baseline, новых 0.
  - `python3 -m flake8 <изменённые файлы>` → 0; `git diff --check` → чисто.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%; `action_bar.py` и `transkript.py` — 100%
- AC:
  - [x] В целевых файлах нет `_sync_ai_call`; `grep` находит только `call_ai_async`.
  - [x] Оставшиеся прямые sync-вызовы вне scope — документированные sync-места: `messages.py`/`photos.py` вызываются через `asyncio.to_thread`, `settings.py` уже использует `to_thread`.
  - [x] Targeted-тесты зелёные.
  - [x] Транскрипция не блокирует event loop (heartbeat-тест).
  - [x] Ошибки/таймауты AI не оставляют статус в вечном состоянии.
- Коммит: `c6da708` (`fix(step-1.4b): offload remaining handler ai calls`)
- Проблемы/решения:
  - В `action_bar.py` было 3 вызова, а не 2, как в якорях плана; мигрированы все, чтобы не оставить блокировку в web-пути.
  - Тесты патчили удалённый атрибут `ab._sync_ai_call`; обновлены на async-двойник, production-alias не добавлялся.
  - Упомянутый в плане mypy-конфликт на `palace/__init__.py:589` не воспроизвёлся: осталась только baseline-ошибка `handlers/chat.py:32`.
- Найдено попутно:
  - INC-3 частично закрыт: `call_ai_async` теперь используется в `navigation`, `action_bar`, `palace/__init__` и `transkript`; старый `get_ai_response_async` с `ThreadPoolExecutor` на каждый вызов остаётся.
- Следующее действие: `S1.5` — `_sync_ai_call`: инициализация текста и Gemini/мультимодальность.

---

### S1.5 — `_sync_ai_call`: неинициализированный текст и Gemini/мультимодальность

- Дата/время: 2026-10-25 16:07–16:11 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `0ca9871`
- Статус: `DONE`
- Бюджет/факт (оценка): 40k / ~18k
- Файлы: `services/ai_engine.py`, `tests/test_ai_engine.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. В qwen-ветке `response_text` больше не может быть unbound: `choices` читаются через `getattr`, пустой список/отсутствие поля сразу возвращают «❌ Пустой ответ от Ollama.». Текст ответа инициализируется как `choice.message.content or ""`.
  2. В Gemini-ветке `r.text` читается один раз; `None`/пустая строка возвращают «❌ Пустой ответ от Gemini.», а не `None` в вызывающий код.
  3. System-сообщение из `messages` теперь передаётся в Gemini через `system_instruction` и исключается из истории (раньше превращалось в `role="model"`).
  4. Изображения Gemini теперь поддерживаются: base64 JPEG передаются как inline `image/jpeg` через `Part.from_bytes` в первом user-сообщении. Контракт `images` (base64 JPEG без data-URL) задокументирован в docstring `_sync_ai_call`.
  5. Обновлены тестовые двойники (`FakePart.from_bytes`, захват `GenerateContentConfig`) и добавлены проверки: пустой `choices`, `None`-текст Gemini, system + image для Gemini. Успешные ответы qwen/openai/gemini остаются покрытыми прежними тестами.
- Тесты и команды:
  - `python3 -m pytest tests/test_ai_engine.py -q --tb=short --override-ini=addopts=-ra` → **81 passed, 1 warning in 2.86s**.
  - `make test` → **3548 passed, 1 failed, 6 warnings in 15.55s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `services/ai_engine.py` — **100%**.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **74 Low, 0 Medium, 0 High** — baseline, новых 0.
  - `python3 -m flake8 services/ai_engine.py tests/test_ai_engine.py` → 0; `mypy services/ai_engine.py` → Success; `git diff --check` → чисто.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%; `ai_engine.py` — 100%
- AC:
  - [x] Нет `UnboundLocalError` и `None` в тексте ответа: пустые `choices`/`r.text` дают контролируемые строки.
  - [x] Мультимодальный контракт явно определён в docstring и протестирован (system message + base64 JPEG).
  - [x] Формат успешного ответа не изменён.
- Коммит: `0ca9871` (`fix(step-1.5): harden sync ai response handling`)
- Проблемы/решения:
  - Для Gemini выбран вариант «поддержать изображения», а не отклонять: формат base64 JPEG уже был контрактом OpenAI-ветки, поэтому поведение унифицировано.
  - Якорь `services/ai_engine.py:204-209` сместился после предыдущих шагов; правка сделана по символам `response_text`/`choices`.
- Найдено попутно:
  - INC-4: Gemini-ветка `stream_ai_response_async` всё ещё игнорирует `images` и использует только сгенерированный `system_prompt`, не system-сообщение из `messages`; S1.5 касается только sync-пути.
- Следующее действие: `S1.6` — структурированный результат стриминга.

---

### S1.6 — Структурированный результат стриминга

- Дата/время: 2026-10-25 16:17–16:18 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `72f8ac7`
- Статус: `DONE`
- Бюджет/факт (оценка): 35k / ~16k
- Файлы: `services/ai_engine.py`, `tests/test_ai_engine.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. Добавлен `AIStreamEvent` (frozen dataclass) с полями `ok`, `text`, `error_code`, `error_message`.
  2. Добавлен `stream_ai_events_async`: текстовые чанки приходят событиями `ok=True`; ошибки — отдельными `ok=False` с кодами `stream_error`, `ollama_unavailable` или `empty_stream`. Ошибка больше не является строкой с префиксом `❌`.
  3. Ошибка до первого токена и ошибка в середине стрима различимы по позиции события; уже отданный частичный текст остаётся в предыдущих событиях.
  4. Пустой успешный стрим выдаёт событие `empty_stream`, чтобы его нельзя было спутать с успешным непустым ответом.
  5. Старый `stream_ai_response_async` сохранён как deprecated строковый адаптер: он транслирует новые события в прежние чанки/ошибки и не меняет поведение текущих обработчиков. Пустой стрим адаптер по-прежнему пропускает.
  6. Обработчики `handlers/messages.py` пока не менялись — их перевод на события и удаление проверок `startswith("❌")` входит в S1.7.
- Тесты и команды:
  - `python3 -m pytest tests/test_ai_engine.py -q --tb=short --override-ini=addopts=-ra` → **87 passed, 1 warning in 3.33s**.
  - `make test` → **3554 passed, 1 failed, 6 warnings in 15.57s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `services/ai_engine.py` — **100%**.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **74 Low, 0 Medium, 0 High** — baseline, новых 0.
  - `python3 -m flake8 services/ai_engine.py tests/test_ai_engine.py` → 0; `mypy services/ai_engine.py` → Success; `git diff --check` → чисто.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%; `ai_engine.py` — 100%
- AC:
  - [x] Ошибка и обычный текст различимы структурно (`ok` + `error_code`), без анализа префикса.
  - [x] Новый API не требует `startswith("❌")`; старый адаптер оставлен только для ещё не мигрированных обработчиков (S1.7).
  - [x] Покрыты успешный стрим, ошибка до первого токена, ошибка в середине с частичным текстом и пустой стрим.
- Коммит: `72f8ac7` (`refactor(step-1.6): structure ai stream results`)
- Проблемы/решения:
  - Пустой стрим выбран ошибкой `empty_stream`, а не успехом с нулём чанков: так обработчик может показать понятное сообщение, а старый адаптер сохраняет прежнее поведение (ни одного чанка).
  - Deprecated-адаптер помечен в docstring, без runtime-`DeprecationWarning`, чтобы не засорять логи и тесты при каждом вызове старых обработчиков.
- Найдено попутно:
  - INC-4 остаётся: Gemini-ветка внутри `stream_ai_events_async` (как и раньше в `stream_ai_response_async`) игнорирует `images` и system-сообщение из `messages`.
- Следующее действие: `S1.7` — обработчики стриминга: не кэшировать и не сохранять ошибки.

---

### S1.7 — Обработчики стриминга: ошибки не кэшируются и не сохраняются

- Дата/время: 2026-10-25 16:20–16:29 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `4a9c086`
- Статус: `DONE`
- Бюджет/факт (оценка): 35k / ~20k
- Файлы: `handlers/messages.py`, `tests/test_messages_handler.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. `handlers/messages.py` переведён с deprecated `stream_ai_response_async` на `stream_ai_events_async` / `AIStreamEvent`; проверки `answer.startswith("❌")` удалены.
  2. При событии `ok=False` обработчик запоминает структурированную ошибку, не кэширует ответ и не публикует `AI_RESPONSE_COMPLETE`/`AI_RESPONSE_SENT`; в историю не попадает ни ошибка, ни пользовательский вопрос без ответа.
  3. Пользователю показывается безопасное сообщение по `error_code`: отдельные тексты для `ollama_unavailable` и `empty_stream`, общий текст без технических деталей для `stream_error`.
  4. При ошибке после частичного текста сохраняется и отправляется только реально полученный фрагмент; затем показывается предупреждение об обрыве. Частичный ответ не кэшируется.
  5. Запись в semantic cache перенесена на финал успешного стрима: промежуточный `SEARCH: ...` и частичный текст не кэшируются; успешный ответ после web search кэшируется целиком.
  6. `_on_ai_sent` игнорирует пустой ответ и legacy-строки внутренних ошибок (`❌`, сообщение Ollama); `_is_internal_error_text` также отбрасывает старые ошибочные записи из semantic cache и запускает новый стрим.
- Тесты и команды:
  - `python3 -m pytest tests/test_messages_handler.py -q --no-cov` → **97 passed, 1 warning in 3.26s**.
  - `make test` → **3559 passed, 1 failed, 6 warnings in 16.20s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `handlers/messages.py` — **97%**, `services/ai_engine.py` — **100%**.
    - В одном промежуточном полном прогоне падал известный флак `test_confirm_write_delete_requires_two_confirmations`; отдельный запуск и финальный полный прогон прошли.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **74 Low, 0 Medium, 0 High** — baseline, новых 0.
  - `git diff --check` → чисто; pre-commit hooks (flake8, no-secrets) прошли.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: baseline 74 Low, новых 0
  - coverage: 98%; `messages.py` — 97%, `ai_engine.py` — 100%
- AC:
  - [x] В истории и semantic cache нет строк `❌` от внутренних ошибок: ошибки не сохраняются и не кэшируются, а legacy-записи игнорируются.
  - [x] UX ошибки не ухудшился: понятное сообщение по типу ошибки, без утечки внутренних деталей; частичный ответ сохраняется с предупреждением.
  - [x] Покрыты ошибка до первого токена, ошибка во втором стриме после web search, частичный стрим, пустой стрим и успешное кэширование финального ответа.
- Коммит: `4a9c086` (`fix(step-1.7): stop caching streaming errors`)
- Проблемы/решения:
  - Пустой стрим теперь трактуется как ошибка `empty_stream`: в историю не попадает строка «Пустой ответ от ИИ», пользователь видит её только как сообщение.
  - Для legacy-кэша добавлена проверка `_is_internal_error_text`: старые записи с `❌` не используются и не сохраняются, вместо них выполняется новый запрос.
  - Ошибка сохраняется как структурированный объект, а не как строка, поэтому частичный текст можно отделить от сообщения об ошибке.
- Найдено попутно:
  - INC-5: при исключении `search_web` обработчик оставляет в `answer` исходную `SEARCH: ...`-директиву и может сохранить/закэшировать её как обычный ответ. Старый тест `test_ai_search_pattern_error` это поведение закрепляет.
  - INC-4 остаётся: Gemini-ветка `stream_ai_events_async` по-прежнему игнорирует `images` и system-сообщение из `messages`.
- Следующее действие: `S1.8` — `palace_mcp`: stderr, handshake timeout, жизненный цикл.

---

### S1.8 — `palace_mcp`: stderr, handshake timeout, жизненный цикл

- Дата/время: 2026-10-25 16:31–16:38 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `39f5e47`
- Статус: `DONE`
- Бюджет/факт (оценка): 40k / ~20k
- Файлы: `services/palace_mcp.py`, `tests/test_palace_mcp.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. Добавлена отдельная задача `_read_stderr`, которая постоянно вычитывает stderr MCP-процесса и логирует строки с ограничением 500 символов; задача создаётся вместе с процессом и отменяется/дожидается в `stop()`.
  2. Handshake `_rpc("initialize")` и `_notify("notifications/initialized")` ограничены `_HANDSHAKE_TIMEOUT` (30 с); ожидание `_ready` в `_ensure_alive` ограничено `_READY_TIMEOUT` (10 с) с понятной ошибкой.
  3. При ошибке handshake, таймауте или сбое `_notify` `start()` вызывает общий `stop()`: процесс завершается, ожидается с ограниченным таймаутом, при необходимости убивается, reader/stderr-задачи отменяются и дожидаются, pending futures получают ошибку, состояние очищается.
  4. `stop()` получил bounded wait (`_STOP_TIMEOUT` 5 с) и kill-fallback; отменяет и дожидается обе задачи, очищает `_pending`, `_ready`, `_proc`, идемпотентен.
  5. `start()` корректно заменяет уже умерший процесс, а прежний safe-restart в `_ensure_alive` сохранён; повторный запуск после неудачного handshake покрыт тестом.
- Тесты и команды: 10 новых тестов (24 → 34 в `tests/test_palace_mcp.py`).
  - `python3 -m pytest tests/test_palace_mcp.py -q --no-cov` → **34 passed in 2.23s**.
  - `python3 -m flake8 services/palace_mcp.py tests/test_palace_mcp.py` → 0; `mypy services/palace_mcp.py` → Success.
  - `make test` → **3569 passed, 1 failed, 6 warnings in 16.12s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `services/palace_mcp.py` — **93%** (непокрыты редкие ветки исключений `terminate/kill/wait`).
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **73 Low, 0 Medium, 0 High**; было 74 Low, новых нет, один B110 удалён вместе со старым `except: pass`.
  - `git diff --check` → чисто; pre-commit hooks (flake8, no-secrets) прошли.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: 73 Low, новых 0 (улучшение на 1)
  - coverage: 98%; `palace_mcp.py` — 93%
- AC:
  - [x] Нет вечного ожидания: handshake, notify, ready и остановка процесса ограничены таймаутами; при сбое процесс, задачи и pending futures очищаются.
  - [x] stderr не переполняется: отдельная задача читает поток постоянно; покрыты молчащий и шумный stderr.
  - [x] Есть безопасный повторный запуск после падения handshake и умершего процесса.
- Коммит: `39f5e47` (`fix(step-1.8): harden palace mcp lifecycle`)
- Проблемы/решения:
  - `stop()` сначала очищает `_proc`, затем завершает процесс и отменяет задачи; это не даёт reader-циклу удерживать ссылку на уже остановленный процесс.
  - После `terminate()` ожидание ограничено, при таймауте вызывается `kill()` и повторное ограниченное ожидание.
  - `start()` не создаёт reader/stderr-задачи, если у fake/неполного процесса нет соответствующего pipe; для реального `create_subprocess_exec` оба pipe всегда есть.
- Найдено попутно:
  - INC-6: `start()`/`stop()` не защищены lifecycle-lock от одновременных вызовов; два конкурентных `start()` теоретически могут создать два процесса, последний затрёт ссылку. Текущие вызовы последовательные, поэтому в S1.8 не исправлялось.
- Следующее действие: `S1.9` — контекстный ключ semantic cache.

---

### S1.9 — Контекстный ключ semantic cache

- Дата/время: 2026-10-25 16:45–16:55 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `62af728`
- Статус: `DONE`
- Бюджет/факт (оценка): 35k / ~30k
- Файлы: `services/semantic_cache.py`, `handlers/messages.py`, `handlers/settings.py`, `tests/test_semantic_cache.py`, `tests/test_messages_handler.py`, `tests/test_settings_handler.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. `SemanticCache.get/set` теперь требуют контекст: `chat_id`, `wing`, `model`, `prompt_version` и `mode`. Если хотя бы один обязательный компонент пуст или отсутствует, `get()` возвращает промах, а `set()` ничего не сохраняет; бесконтекстной глобальной записи больше нет.
  2. Внутренний ключ стал составным `(scope, normalized_query)`. Семантическое сравнение ищет кандидатов только с точно совпадающим scope, поэтому похожий запрос из другого чата/крыла/модели не может дать попадание.
  3. `handlers/messages.py` передаёт `message.chat.id`, модель, режим (`chat`/`coding`, плюс digest изображений) и `prompt_version` вида `smart-prompt-v1:<sha256(system_instruction)[:16]>`; в wing входит целевое крыло и контекст пользователя `wing/room/drawer`, для явно глобального поиска используется отдельный scope `global`.
  4. При смене модели `handlers/settings.cb_set_ai` инвалидирует записи предыдущей модели через `SemanticCache.invalidate_model`; ключ с моделью дополнительно не даёт старым записям попасть в новую модель.
  5. Сохранены TTL, ограничение `max_size`, `invalidate()` и статистика; добавлен `RLock`, чтобы операции с общим кэшем были потокобезопасны. Async-safety сохранена: внутри методов нет `await`.
  6. TTL-тесты переведены с `sleep` на детерминированные часы, поэтому флак `test_ttl_eviction` больше не воспроизводится.
- Тесты и команды: 21 новый тест (19 в `tests/test_semantic_cache.py`, 2 в `tests/test_messages_handler.py`); всего в semantic cache 45 собранных тестов.
  - `python3 -m pytest tests/test_semantic_cache.py -q --no-cov` → **45 passed**.
  - `python3 -m pytest tests/test_semantic_cache.py tests/test_messages_handler.py tests/test_settings_handler.py -q --no-cov` → **189 passed, 1 warning**.
  - `make test` → **3590 passed, 1 failed, 6 warnings in 15.95s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `services/semantic_cache.py` — **100%**, `handlers/messages.py` — **97%**, `handlers/settings.py` — **99%**.
  - `make lint` → те же 9 baseline-замечаний, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **73 Low, 0 Medium, 0 High**, новых 0.
  - `git diff --check` → чисто; pre-commit hooks (flake8, no-secrets) прошли.
- QA:
  - lint: baseline 9, новых 0
  - mypy: baseline 1, новых 0
  - bandit: 73 Low, новых 0
  - coverage: 98%; `semantic_cache.py` — 100%
- AC:
  - [x] Нет кросс-чатовых/кросс-крыловых/кросс-модельных попаданий: сравнение ограничено scope, неполный ключ всегда даёт промах.
  - [x] Есть тесты на изоляцию по chat_id, wing, model, prompt_version и mode, а также на отсутствие глобального fallback.
  - [x] Есть TTL и инвалидация при смене модели.
  - [x] Потокобезопасность/async-безопасность не ухудшены.
- Коммит: `62af728` (`fix(step-1.9): scope semantic cache by context`)
- Проблемы/решения:
  - В `prompt_version` включён отпечаток фактического system prompt, а не только статическая версия: изменение промпта, памяти или palace-контекста автоматически делает старые записи недоступными. Это может уменьшить число попаданий, но соответствует принципу «лучше промах, чем чужой ответ».
  - Для запросов без определённого крыла используется явный scope `global`, а не ключ без wing; на уровне API пустой wing по-прежнему означает промах.
  - Смена модели защищена двумя механизмами: модель входит в ключ и старые записи дополнительно удаляются в настройках.
  - Граница TTL оставлена прежней (`now - timestamp > ttl`); тест на точную границу переименован в `test_evict_boundary_exact_ttl_is_not_expired`, чтобы имя соответствовало поведению.
- Найдено попутно:
  - INC-1 закрыт: TTL-тесты больше не зависят от планировщика/`sleep`.
  - Pre-commit flake8 на изменённом `tests/test_settings_handler.py` выявил 5 baseline-замечаний (неиспользуемый `os`, 4 длинные строки); они исправлены без изменения логики тестов.
- Следующее действие: `S1.10` — убрать опасный fallback `"test-token"` и проверить пути `.env`.

---

### S1.10 — Токен и `.env`: убрать опасный fallback

- Дата/время: 2026-10-25 17:00–17:10 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `21953ac`
- Статус: `DONE`
- Бюджет/факт (оценка): 20k / ~18k
- Файлы: `config.py`, `main.py`, `tests/test_config.py`, `tests/test_main.py`, `.env.example`, `README.md`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. `config.py` больше не подставляет `test-token` в production: при отсутствии `TELEGRAM_BOT_TOKEN` возвращается пустое значение. Fallback разрешён только при `PYTEST_CURRENT_TEST`/`PYTEST_VERSION` или явном `MEMPALACE_ALLOW_TEST_TOKEN=1`.
  2. Добавлен `validate_config()`: проверяет отсутствующий токен, пример `your_telegram_bot_token`, тестовый `test-token` вне тестового окружения и `ADMIN_ID=0`. Сообщение содержит переменную и оба ожидаемых пути `.env`.
  3. `main.py` вызывает `validate_config()` до импорта `services.bot_setup`; при ошибке печатает понятное сообщение и завершает процесс с кодом 1, не создавая `Bot` с пустым токеном.
  4. `.env` загружается в порядке: `.env` в корне проекта, затем legacy `~/Documents/mempalace/.env`. Используется `load_dotenv(override=False)`, поэтому существующие переменные окружения и значения корневого файла не перетираются legacy-файлом.
  5. Удалена неиспользуемая дублирующая `get_allowed_ids()`; `ALLOWED_IDS` по-прежнему строится из `ADMIN_ID` и `ALLOWED_USERS`.
  6. Порядок путей и приоритеты задокументированы в docstring `config.py`, `.env.example` и `README.md`.
- Тесты и команды: прирост 14 тестов (`tests/test_config.py` 11 → 24, `tests/test_main.py` 18 → 19); устаревшие тесты `get_allowed_ids` и reload-fallback заменены.
  - `python3 -m pytest tests/test_config.py tests/test_main.py -q --no-cov` → **43 passed, 6 warnings**.
  - Smoke без токена: `env TELEGRAM_BOT_TOKEN='' ... python3 main.py` → **exit 1**, сообщение содержит root и legacy пути, polling не запускается.
  - `make test` → **3604 passed, 1 failed, 6 warnings in 16.01s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `config.py` — **97%**, `main.py` — **96%**.
  - `python3 -m flake8 config.py main.py tests/test_config.py tests/test_main.py` → 0.
  - `make lint` → **8 baseline-замечаний** (было 9: удалён W391 в `config.py`), новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **73 Low, 0 Medium, 0 High**, новых 0.
  - `git diff --check` → чисто; pre-commit hooks (flake8, no-secrets) прошли.
- QA:
  - lint: baseline 8, новых 0
  - mypy: baseline 1, новых 0
  - bandit: 73 Low, новых 0
  - coverage: 98%; `config.py` — 97%
- AC:
  - [x] Нет тихого старта с `test-token`: production без токена завершается ошибкой до создания Bot.
  - [x] Пути `.env` документированы и покрыты тестами: root → legacy, приоритет env, legacy-only и отсутствие обоих файлов.
  - [x] Дублирующая `get_allowed_ids()` удалена.
- Коммит: `21953ac` (`fix(step-1.10): validate bot token and env paths`)
- Проблемы/решения:
  - Корневой `.env` загружается первым и имеет приоритет над legacy; внешние переменные окружения имеют приоритет над обоими файлами.
  - Явный тестовый флаг назван `MEMPALACE_ALLOW_TEST_TOKEN` и не включён по умолчанию.
  - Импорт `services.bot_setup` перенесён после валидации, чтобы aiogram не падал на пустом токене раньше понятного сообщения.
  - При отсутствии обоих `.env` выводится предупреждение с ожидаемыми путями; токен в лог не попадает.
- Найдено попутно:
  - Удалён baseline W391 в конце `config.py`; `make lint` улучшился с 9 до 8 замечаний.
- Следующее действие: `S1.11` — сброс счётчика circuit breaker после успешного вызова.

---

### S1.11 — Circuit breaker: сброс счётчика после успеха

- Дата/время: 2026-10-25 17:15–17:20 CET
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `c677438`
- Статус: `DONE`
- Бюджет/факт (оценка): 15k / ~10k
- Файлы: `services/circuit_breaker.py`, `tests/test_circuit_breaker.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. Успешный вызов теперь обнуляет `failure_count` не только при переходе `HALF_OPEN → CLOSED`, но и в состоянии `CLOSED`. Старые ошибки больше не накапливаются между успешными вызовами.
  2. Для `HALF_OPEN` сохранены прежние поведение и лог `HALF_OPEN → CLOSED (success)`, а также сброс `half_open_retries`.
  3. Порог `failure_threshold` не менялся: ошибки по-прежнему инкрементируют счётчик, `CLOSED → OPEN` срабатывает при достижении порога.
- Тесты и команды: 4 новых теста (20 → 24 в `tests/test_circuit_breaker.py`).
  - `python3 -m pytest tests/test_circuit_breaker.py tests/test_palace_bridge.py tests/test_services_singletons.py -q --no-cov` → **105 passed, 1 warning**.
  - `python3 -m pytest tests/test_circuit_breaker.py -q --cov=services.circuit_breaker` → **24 passed**, покрытие модуля в полном прогоне **100%**.
  - `make test` → **3608 passed, 1 failed, 6 warnings in 16.24s**, coverage **98%**.
    - Единственное падение — pre-existing `tests/test_digest.py::test_day_bounds_midnight`.
    - `services/circuit_breaker.py` — **100%**.
  - `python3 -m flake8 services/circuit_breaker.py tests/test_circuit_breaker.py` → 0; `mypy services/circuit_breaker.py` → Success.
  - `make lint` → **8 baseline-замечаний**, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **73 Low, 0 Medium, 0 High**, новых 0.
  - `git diff --check` → чисто; pre-commit hooks (flake8, no-secrets) прошли.
- QA:
  - lint: baseline 8, новых 0
  - mypy: baseline 1, новых 0
  - bandit: 73 Low, новых 0
  - coverage: 98%; `circuit_breaker.py` — 100%
- AC:
  - [x] Счётчик не накапливает старые ошибки после успеха: успех в `CLOSED` и `HALF_OPEN` обнуляет `failure_count`.
  - [x] Переходы `CLOSED → OPEN → HALF_OPEN → CLOSED` проверены, включая повторное открытие после успеха.
  - [x] Порог не изменён.
- Коммит: `c677438` (`fix(step-1.11): reset circuit breaker failures on success`)
- Проблемы/решения:
  - Сброс `failure_count` вынесен за ветку `HALF_OPEN`, чтобы одинаково работать для обоих успешных состояний.
  - `last_failure_time` на успехе не сбрасывается: он используется только для расчёта recovery timeout после открытия и перезаписывается при новом сбое.
  - Для проверки полного цикла используется fake clock, без `sleep`.
- Найдено попутно: нет.
- Следующее действие: `S1.12` — напоминания: прошлое время, уникальные ключи, безопасный JSON.

---

### S1.12 — Напоминания: прошлое время, ключи, JSON, часовой пояс

- Дата/время: 2026-10-25 17:30 — 2026-10-27 00:05 CET (сессия с паузами)
- Агент/модель: DeepSeek V4.1 Flash Free
- Ветка/HEAD: `fix/audit-2026-10-25` / `df66c40`
- Статус: `DONE`
- Бюджет/факт (оценка): 30k / ~22k
- Файлы: `handlers/reminder.py`, `tests/test_reminder_handler.py`, `AUDIT_FIX_PROGRESS.md`
- Что сделано:
  1. Добавлена проверка прошедшего времени (`_is_past`) на всех этапах: при разборе сообщения, при подтверждении, при сохранении и в шагах `ask_text`/`ask_time`/`ask_all`. Вместо создания/немедленной отправки пользователь получает `PAST_TIME_TEXT` с предложением будущего времени.
  2. Ключ напоминания теперь `rem<timestamp>_<uid>_<uuid4hex>`: два напоминания одного пользователя на одну секунду больше не перезаписывают друг друга.
  3. `_clean_json` защищён от не-строк, логирует битый JSON (без содержимого) и возвращает `{}`. В `ask_all` вызов `_parse_reminder` обёрнут в `try/except` с понятным fallback-сообщением и `logger.error(..., exc_info=True)`.
  4. `ask_time` больше не глотает исключения через `except: pass`: ошибка логируется.
  5. Время переведено на aware datetime: `_now_local()`, `_local_dt()`; `_parse_time_description` работает с aware-временем, отображение — через локальное aware-время. Naive/aware не смешиваются.
- Тесты и команды: 12 новых тестов (`tests/test_reminder_handler.py` 39 → 51). Покрыты прошлое время на всех входах, stale-подтверждение, уникальные ключи в одну секунду, битый/нестроковый JSON, ошибка AI в `ask_all`, aware datetime, будущее время.
  - `python3 -m pytest tests/test_reminder_handler.py tests/test_reminder_scheduler.py -q --no-cov` → **64 passed, 1 warning**.
  - `python3 -m flake8 handlers/reminder.py tests/test_reminder_handler.py` → 0; `mypy handlers/reminder.py` → Success.
  - `make test` (первый прогон) → **3620 passed, 1 failed, 6 warnings in 21.30s**; упал известный флак `tests/test_notes_agent_handler.py::test_confirm_write_delete_requires_two_confirmations`.
  - Этот тест отдельно 3 раза подряд → **3 passed**; полный повторный прогон → **3621 passed, 0 failed, 6 warnings in 21.87s**, coverage **98%**.
    - `handlers/reminder.py` — **98%** (непокрыты ветки без `cb.data` и обработка ошибок календаря).
  - `make lint` → **8 baseline-замечаний**, новых 0.
  - `make typecheck` → та же 1 baseline-ошибка `handlers/chat.py:32`, новых 0.
  - `make security` → **72 Low, 0 Medium, 0 High** (на 1 меньше: удалён `except: pass`/B110 в `ask_time`), новых 0.
  - `git diff --check` → чисто; pre-commit hooks (flake8, no-secrets) прошли.
- QA:
  - lint: baseline 8, новых 0
  - mypy: baseline 1, новых 0
  - bandit: 72 Low, новых 0 (один baseline B110 устранён)
  - coverage: 98%; `reminder.py` — 98%
- AC:
  - [x] Прошлое время не срабатывает немедленно: блокируется на вводе, подтверждении и сохранении.
  - [x] Нет коллизий ключей: UUID4 в ключе; тест с одинаковым `time.time()`.
  - [x] Нет необработанного JSON: битый JSON, не-строка и исключение AI дают fallback + лог.
  - [x] Часовой пояс: aware datetime без смешивания naive/aware.
- Коммит: `df66c40` (`fix(step-1.12): harden reminder scheduling`)
- Проблемы/решения:
  - Граница `ts == now` считается прошедшим временем (`<=`), чтобы не отправлять напоминание мгновенно.
  - Проверка добавлена и в callback-и: пользователь мог подтвердить напоминание уже после наступления времени.
  - UUID4 выбран вместо timestamp+random: не требует дополнительного состояния и не зависит от разрешения часов.
  - В лог пишется только длина невалидного JSON, без содержимого пользователя.
  - Первый полный прогон дал известный флак; повторный полный прогон полностью зелёный.
- Найдено попутно:
  - Удалён baseline B110 (`try/except/pass`) в `ask_time`, поэтому bandit: 73 → 72 Low.
- Следующее действие: `S2.1` — `has_active_button_session`: пустой список считается активной сессией.

---

## 7. Журнал сессий

| # | Дата | Агент/модель | Шаги | Результат | Токены (оценка) | Примечание |
|---:|---|---|---|---|---|---|
| 1 | 2026-10-25 12:15–12:17 | DeepSeek V4.1 Flash Free | S0.1 | DONE | ~15k | Backup + branch + baseline; 2 pre-existing test failures |
| 2 | 2026-10-25 12:20–12:25 | DeepSeek V4.1 Flash Free | S0.2 | DONE | ~12k | Fake AI / heartbeat / temp chats / fixed clock; 6 new tests |
| 3 | 2026-10-25 13:17–13:32 | DeepSeek V4.1 Flash Free | S1.1 | DONE | ~18k | Total AgentResult contract; 5 new regression tests; mypy 5→1 |
| 4 | 2026-10-25 15:15–15:26 | DeepSeek V4.1 Flash Free | S1.2 | DONE | ~20k | Safe HTML whitelist, code fence `<pre><code>`, unbalanced tags; 19 new tests |
| 5 | 2026-10-25 15:43–15:46 | DeepSeek V4.1 Flash Free | S1.3 | DONE | ~12k | `call_ai_async` + timeout + heartbeat; 7 new tests; ai_engine 100% |
| 6 | 2026-10-25 15:49–15:55 | DeepSeek V4.1 Flash Free | S1.4a | DONE | ~16k | 5 sync AI calls → `call_ai_async`; error statuses; 8 new tests; navigation/ai_engine 100% |
| 7 | 2026-10-25 16:00–16:04 | DeepSeek V4.1 Flash Free | S1.4b | DONE | ~14k | 5 sync AI calls → `call_ai_async` in action_bar/palace/transkript; 3 new tests; transcription heartbeat |
| 8 | 2026-10-25 16:07–16:11 | DeepSeek V4.1 Flash Free | S1.5 | DONE | ~18k | qwen empty choices, Gemini None-text, system+images contract; 3 new tests; ai_engine 100% |
| 9 | 2026-10-25 16:17–16:18 | DeepSeek V4.1 Flash Free | S1.6 | DONE | ~16k | `AIStreamEvent` + `stream_ai_events_async`; deprecated string adapter; 6 new tests; ai_engine 100% |
| 10 | 2026-10-25 16:20–16:29 | DeepSeek V4.1 Flash Free | S1.7 | DONE | ~20k | Handlers use structured stream events; errors not cached/saved; partial text preserved; 5 new tests; messages 97% |
| 11 | 2026-10-25 16:31–16:38 | DeepSeek V4.1 Flash Free | S1.8 | DONE | ~20k | MCP stderr drain, handshake/ready/stop timeouts, kill-fallback, task/process cleanup; 10 new tests; palace_mcp 93% |
| 12 | 2026-10-25 16:45–16:55 | DeepSeek V4.1 Flash Free | S1.9 | DONE | ~30k | Context-scoped semantic cache, model invalidation, prompt/image fingerprint; 21 new tests; semantic_cache 100% |
| 13 | 2026-10-25 17:00–17:10 | DeepSeek V4.1 Flash Free | S1.10 | DONE | ~18k | No production test-token, startup validation, root→legacy .env, env priority; 14 new tests; config 97% |
| 14 | 2026-10-25 17:15–17:20 | DeepSeek V4.1 Flash Free | S1.11 | DONE | ~10k | Reset failure_count on success in CLOSED/HALF_OPEN; 4 tests; circuit_breaker 100% |
| 15 | 2026-10-25 17:30–2026-10-27 00:05 | DeepSeek V4.1 Flash Free | S1.12 | DONE | ~22k | Past-time guards, UUID reminder keys, JSON fallbacks, aware datetime; 12 tests; reminder 98%; full suite green |

> Добавлять строку на каждую сессию/запуск. Если сессия закончилась handoff'ом — указать `PARTIAL`.

---

## 8. HANDOFF (заполняется при нехватке токенов)

> Если контекст/токены заканчиваются — остановись, заполни этот блок и статус `PARTIAL` в таблице.
> Следующая сессия обязана начать с этого блока, а не с начала плана.

```text
## HANDOFF
- Дата/время:
- Шаг:
- Статус: PARTIAL
- Ветка/HEAD:
- Текущий diff (`git status --short`):
- Что уже работает:
- Что не работает / не проверено:
- Какие команды уже запущены и их результат:
- Точное следующее действие (1–3 команды/правки):
  1.
  2.
  3.
- Риски:
- Что нельзя делать (например, не откатывать такие-то файлы):
- Бюджет следующей сессии (рекомендуемый):
```

### Чек-лист возобновления

- [ ] Прочитать «Текущий снимок» и этот HANDOFF.
- [ ] Проверить `git status --short`, `git log --oneline -5`, `git diff --stat`.
- [ ] Найти шаг в таблице; если `IN_PROGRESS`/`PARTIAL` — продолжить его, а не начинать следующий.
- [ ] Прочитать последнюю запись журнала по этому шагу.
- [ ] Прогнать targeted-тесты, чтобы понять текущее состояние.
- [ ] Продолжить с «Точное следующее действие».
- [ ] После завершения — обновить статус, журнал, HANDOFF (очистить/пометить закрытым).

---

## 9. Найдено попутно

> Сюда записывать баги/идеи, которые не входят в текущий шаг. Не чинить их здесь.

| ID | Дата | Файл/место | Проблема | Предлагаемый шаг | Статус |
|---|---|---|---|---|---|
| INC-1 | 2026-10-25 | `tests/test_semantic_cache.py` | `test_ttl_eviction` флаки при `ttl=0`: `set()` и `get()` могли попасть в один тик. В S1.9 тесты TTL переведены на детерминированные часы; логика TTL не менялась. | S4.x — стабилизировать тест/логику TTL | RESOLVED (S1.9) |
| INC-2 | 2026-10-25 | `handlers/palace/save.py:281`, `services/brainstorm.py:370`, `handlers/notes_agent.py:268` | Вызывающие оборачивают `safe_html_format(...)` в `<code>`; разрешённые теги внутри такого значения сохраняются как HTML, а не выводятся литерально. Для данных в code нужен `html.escape`. | S4.3 или отдельный шаг HTML-санитизации | TODO |
| INC-3 | 2026-10-25 | `services/ai_engine.py:396` | Старый `get_ai_response_async` не имеет таймаута и создаёт `ThreadPoolExecutor` на каждый вызов. `call_ai_async` уже внедрён в `navigation`, `action_bar`, `palace/__init__` и `transkript` (S1.4a/b); старый путь остаётся. | S3.8b или отдельный шаг | PARTIAL |
| INC-4 | 2026-10-25 | `services/ai_engine.py` (`stream_ai_events_async`) | Gemini-ветка стриминга игнорирует `images` и system-сообщение из `messages`, используя только `system_prompt`. Sync-путь исправлен в S1.5. | Отдельный шаг стримингового Gemini-контракта | TODO |
| INC-5 | 2026-10-25 | `handlers/messages.py` (ветка `search_web`) | При исключении `search_web` исходный ответ с `SEARCH: ...` остаётся в `answer` и может быть сохранён/закэширован как обычный ответ; `test_ai_search_pattern_error` закрепляет это поведение. | Отдельный шаг обработки ошибок web search | TODO |
| INC-6 | 2026-10-25 | `services/palace_mcp.py` (`start`/`stop`) | Нет lifecycle-lock: конкурентные `start()`/`stop()` могут гонять создание и завершение процесса; два одновременных `start()` теоретически оставят один процесс без ссылки. | Отдельный шаг сериализации lifecycle | TODO |

---

## 10. Отклонения от плана

> Если шаг пришлось разделить, объединить, пропустить или изменить — фиксировать здесь с причиной и одобрением пользователя.

| Дата | Шаг | Отклонение | Причина | Одобрено |
|---|---|---|---|---|
| — | — | — | — | — |

---

## 11. Финальная приёмка

- [ ] Все P0-шаги `DONE` (или `SKIPPED` с одобрением).
- [ ] Все P1-шаги `DONE` (или `SKIPPED` с одобрением).
- [ ] P2-шаги выполнены или осознанно отложены с записью.
- [ ] `make qa` не хуже baseline; новых падений нет.
- [ ] Каждый исправленный баг покрыт тестом.
- [ ] Нет новых секретов/мусора в git.
- [ ] Итоговый отчёт с метриками записан.
- [ ] Пользователь подтвердил приёмку.

**Итоговый статус:** не начато
**Дата приёмки:** —
**Подпись/подтверждение пользователя:** —

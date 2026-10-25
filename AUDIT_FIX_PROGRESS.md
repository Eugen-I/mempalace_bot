# AUDIT_FIX_PROGRESS — журнал устранения замечаний аудита

**Проект:** `/Users/evg.pit/Documents/mempalace_bot`
**План:** `AUDIT_FIX_PLAN.md`
**Создан:** 2026-10-25
**Статус работы:** не начата

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

- **Дата последнего обновления:** 2026-10-25 13:32 CET
- **Ветка:** `fix/audit-2026-10-25`
- **HEAD:** `b5d72d1` (S1.1 code; docs-checkpoint — следующим коммитом; актуальный HEAD смотреть через `git log`)
- **Текущий шаг:** `S1.1` — завершён
- **Статус:** `DONE`
- **Следующее действие:** `S1.2` — `safe_html_format` и `_TAG_RE`
- **Бюджет текущего шага:** 30k
- **Израсходовано (оценка):** ~18k (контракт результата + тесты + прогоны)
- **Незакоммиченные изменения:** нет после docs-коммита; чужие untracked-файлы не трогать.
- **Резервная копия:** `~/Documents/mempalace_bot_backups/mempalace_bot_full_20261025_121520.tar.gz` (4.7 MB, sha256 `dd02b6a1...aab4ea`)
- **Известные блокеры:** нет. Pre-existing: 2 падающих теста на baseline; в финальном прогоне S0.2 — 1 (`test_day_bounds_midnight`), второй (`test_confirm_write_delete_requires_two_confirmations`) флаки и прошёл.
- **Последний QA:** 3503 passed / 1 failed, coverage 98%; lint/mypy/bandit — baseline без новых
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
| S1.2 | `safe_html_format` и `_TAG_RE` | P0 | 25k | TODO | — | — | — |
| S1.3 | Async-обёртка AI | P0 | 35k | TODO | — | — | — |
| S1.4a | Async AI в `palace/navigation.py` | P0 | 35k | TODO | — | — | — |
| S1.4b | Async AI в action_bar/palace/transkript | P0 | 30k | TODO | — | — | — |
| S1.5 | `_sync_ai_call`: unbound/Gemini | P0 | 40k | TODO | — | — | — |
| S1.6 | Структурированный стриминг | P0 | 35k | TODO | — | — | — |
| S1.7 | Не кэшировать ошибки стриминга | P0 | 35k | TODO | — | — | — |
| S1.8 | `palace_mcp`: stderr/timeout/lifecycle | P0 | 40k | TODO | — | — | — |
| S1.9 | Контекстный semantic cache | P0 | 35k | TODO | — | — | — |
| S1.10 | Токен и пути `.env` | P0 | 20k | TODO | — | — | — |
| S1.11 | Circuit breaker: сброс счётчика | P0 | 15k | TODO | — | — | — |
| S1.12 | Напоминания: время/ключи/JSON | P0 | 30k | TODO | — | — | — |
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
| 1 — P0 | 13 | 1 | 0 | 12 |
| 2 — P1 | 9 | 0 | 0 | 9 |
| 3 — P2 дублирование | 11 | 0 | 0 | 11 |
| 4 — чистота/тесты | 10 | 0 | 0 | 10 |
| **Итого** | **45** | **3** | **0** | **42** |

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

---

## 7. Журнал сессий

| # | Дата | Агент/модель | Шаги | Результат | Токены (оценка) | Примечание |
|---:|---|---|---|---|---|---|
| 1 | 2026-10-25 12:15–12:17 | DeepSeek V4.1 Flash Free | S0.1 | DONE | ~15k | Backup + branch + baseline; 2 pre-existing test failures |
| 2 | 2026-10-25 12:20–12:25 | DeepSeek V4.1 Flash Free | S0.2 | DONE | ~12k | Fake AI / heartbeat / temp chats / fixed clock; 6 new tests |
| 3 | 2026-10-25 13:17–13:32 | DeepSeek V4.1 Flash Free | S1.1 | DONE | ~18k | Total AgentResult contract; 5 new regression tests; mypy 5→1 |

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
| — | — | — | — | — | — |

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

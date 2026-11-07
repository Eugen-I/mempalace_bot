# AUDIT_FIX_PLAN — устранение замечаний аудита `mempalace_bot`

**Версия:** 2.0 (добавлена Фаза 5: Пост-аудит, безопасность и архитектура, S5.1–S5.15)
**Дата:** 2026-11-06
**Проект:** `/Users/evg.pit/Documents/mempalace_bot`
**Журнал выполнения:** `AUDIT_FIX_PROGRESS.md`
**Основание:** read-only аудит проекта + пост-аудит безопасности и архитектуры (INC-2..INC-16, `main.py`, `cli_extras.py`).
**Статус:** Фазы 0–4 (`S0.1`–`S4.10`) полностью завершены (`DONE`). К исполнению — **Фаза 5 (`S5.1`–`S5.15`)**.

> Это файл-инструкция. **Не записывай сюда прогресс, даты, коммиты и заметки о выполнении** — для этого есть `AUDIT_FIX_PROGRESS.md`.
> Если план приходится менять, зафиксируй причину в разделе «Отклонения от плана» журнала и продолжи работу по обновлённому шагу.

---

## 0. Быстрый старт и анти-повтор (Экономия токенов!)

1. **НЕ ЧИТАЙ весь `AUDIT_FIX_PROGRESS.md` целиком!** Исторические записи шагов `S0.1`–`S4.10` занимают тысячи токенов и уже закрыты.
2. Прочитай в `AUDIT_FIX_PROGRESS.md` **только**:
   - Раздел `2. Текущий снимок` (строки 40–75);
   - Блок `4.1. Таблица шагов Фазы 5 (S5.1–S5.15)`;
   - Раздел `8. HANDOFF` (если предыдущая сессия прервалась на `PARTIAL`).
3. Проверь состояние репозитория:
   ```bash
   git status --short --branch
   git log -1 --oneline
   ```
4. Найди первый шаг Фазы 5 со статусом `IN_PROGRESS`, `PARTIAL` или `BLOCKED`. Если таких нет — бери первый `TODO` из таблицы `S5.1`–`S5.15`.
5. **ЗАПРЕЩЕНО возвращаться к шагам со статусом `DONE`**, перечитывать их диффы, перезапускать их старые целевые тесты или перепроверять их код. Доверяй статусу `DONE` в таблице!
6. Перед правкой найди нужный символ точечно через `grep -n` или чтение конкретного диапазона строк. Не читай крупные файлы целиком, если нужен один метод.
7. Выполняй шаги строго по одному. Бюджет одной сессии — **жёстко ≤ 50 000 токенов** (при ~40 000 токенов — стоп, запись `HANDOFF` и выход).

---

## 1. Границы работы и безопасность

- Работай только в рабочей директории проекта (`mempalace_bot`).
- **Не удаляй и не перезаписывай пользовательские артефакты**, которые не относятся к текущему шагу:
  - `.claude/`, `CLAUDE.md`, `exports/`, `models/`, `scripts/`;
  - Garmin-файлы (`features/garmin_integration.feature`, `features/steps/garmin_integration_steps.py`, `models/garmin.py`, `services/garmin/`, `tests/test_garmin_*.py`) — трогать только в целевом шаге `S5.14`;
  - `mutants/`, `coverage.xml`, `bot_state.sqlite`, `.env`.
- Не выполняй без явного подтверждения пользователя:
  - `git reset --hard`, `git clean -fd`, `git checkout .`, `git restore .`;
  - `rm -rf` по каталогам проекта;
  - `git add -A` и коммит чужих untracked-файлов.
- Не коммить секреты, `.env`, токены, `bot_state.sqlite`, `coverage.xml`, `mutants/`.
- Тесты не должны писать в реальные `~/Documents/mempalace`; используй `tmp_path` и mock.
- Внешние API (Telegram, LLM, MCP, web search) в unit-тестах только через mock/fake.
- Не логируй токены, содержимое `.env`, персональные данные и полные ответы моделей без необходимости.

---

## 2. Правила изменения кода

1. **Один шаг = одно логическое изменение + целевые тесты + один коммит.**
2. Сначала воспроизведи баг целевым тестом (RED), затем чини (GREEN).
3. Минимальное изменение: не переписывай модуль целиком, если достаточно локального фикса.
4. Не делай массовый реформат и не меняй стиль чужих строк «заодно».
5. Новый код — с типами и понятными именами.
6. **Запрещено подгонять тесты**: нельзя удалять/скипать/ослаблять корректный тест, чтобы он прошёл.
7. Для async-кода: не вызывай блокирующие функции (`open`, `os.listdir`, `os.path.getmtime`, sync network/DB) в event loop. Используй `aiofiles`, `asyncio.to_thread` или асинхронный клиент, таймауты и отмену.
8. Не оставляй после шага сломанный импорт, падающий тест или незакоммиченный мусор.

---

## 3. Протокол выполнения одного шага

### 3.1. До начала

1. Открой `AUDIT_FIX_PROGRESS.md` (только шапку и таблицу Фазы 5!) и запиши в «Текущий снимок»:
   - дату/время, ветку, `HEAD`, ID шага (`S5.x`);
   - статус `IN_PROGRESS`;
   - оценку бюджета (из карточки шага).
2. Проверь `git status --short`. Чужие untracked/modified файлы не трогай.
3. Прочитай только якорные функции/строки и целевой тестовый файл.

### 3.2. Во время работы (Контроль 50K токенов)

- Держи изменение строго в рамках шага.
- **Промежуточные тесты:** во время разработки запускай **только целевой тестовый файл** с флагом `--no-cov -q --tb=short` (например: `python3 -m pytest tests/test_main.py -q --no-cov --tb=short`), чтобы вывод не сжигал контекстное окно.
- Следи за бюджетом токенов (раздел 4). Как только суммарный расход сессии приближается к **40 000 токенов** — немедленно переходи к процедуре `HANDOFF`.

### 3.3. После работы

1. Запусти точечные проверки по изменённым файлам (`flake8`, `mypy`, `bandit`, `pytest` по целевым тестам). Полный прогон всех 3789+ тестов делай только в том случае, если позволяет остаток бюджета токенов (<35k израсходовано) или на финальном шаге `S5.15`.
2. Обнови `AUDIT_FIX_PROGRESS.md`:
   - в таблице шагов Фазы 5 поставь `DONE` (или `PARTIAL`/`BLOCKED`), укажи commit hash, дату и расход токенов;
   - обнови «Текущий снимок» (следующий шаг `TODO`);
   - добавь краткую (10–15 строк максимум!) запись в конец раздела 6.
3. Сделай атомарный коммит:
   ```bash
   git add <только файлы текущего шага>
   git commit -m "fix(step-S5.x): краткое описание"
   ```

---

## 4. Жёсткий лимит 50 000 токенов, чекпоинты и анти-повтор

**Жёсткий потолок одной сессии агента — 50 000 токенов.** Порог начала сохранения состояния — **40 000 токенов**.

### 4.1. Правила экономии токенов (Anti-Waste)

1. **Никогда не возвращайся к `DONE` шагам:** если в таблице `AUDIT_FIX_PROGRESS.md` у шага стоит `DONE` и указан коммит — работа принята. Не открывай файлы этого шага для «проверки».
2. **Не читай `AUDIT_FIX_PROGRESS.md` целиком:** используй `head -n 135 AUDIT_FIX_PROGRESS.md` и `tail -n 120 AUDIT_FIX_PROGRESS.md`, чтобы видеть только текущий снимок, таблицы статусов и конец журнала/HANDOFF.
3. **Точечный поиск вместо чтения файлов целиком:** для файлов >200 строк (`handlers/messages.py`, `handlers/chat.py`, `services/ai_engine.py`) используй `grep -n` и чтение нужных 50–80 строк вокруг якоря.
4. **Короткий вывод тестов:** всегда используй `-q --tb=short --no-cov` на промежуточных запусках.

### 4.2. Что делать при достижении ~40 000 токенов (Стоп-кран)

- Если текущий шаг `S5.x` завершён, а в запасе осталось **меньше 15 000 токенов** — **НЕ НАЧИНАЙ** следующий шаг `S5.(x+1)`. Закоммить текущий шаг со статусом `DONE`, очисти `HANDOFF`, укажи в «Текущем снимке» следующий шаг и заверши сессию.
- Если лимит ~40 000 токенов наступил **посередине шага**:
  1. Остановись на консистентной точке (код сохранен на диске, синтаксических ошибок нет).
  2. Поставь шагу в таблице статус `PARTIAL`.
  3. Заполни раздел `8. HANDOFF` в `AUDIT_FIX_PROGRESS.md`:
     - какой подпункт шага уже сделан на диске (чтобы следующий агент не делал его заново!);
     - какие строки в каких файлах уже изменены;
     - точная команда (1–2 строки), с которой нужно продолжить в следующей сессии.
  4. Если нужно зафиксировать промежуточный код в git, сделай `git commit -m "wip(step-S5.x): checkpoint before token limit"`.

---

## 5. Проверки

### 5.1. Быстрые команды для одного шага (экономия контекста)

```bash
# 1. Целевой тест без портянки coverage
python3 -m pytest tests/test_<target>.py -q --tb=short --no-cov

# 2. Линт и типы только по затронутым файлам
python3 -m flake8 <изменённые_файлы.py>
python3 -m mypy --explicit-package-bases <изменённые_файлы.py>
python3 -m bandit -q -ll <изменённые_production_файлы.py>
```

### 5.2. Полный QA (для финальной приёмки S5.15)

```bash
python3 -m pytest -q --tb=short --strict-markers --ignore-glob='tests/test_garmin_*.py'
python3 -m mypy --explicit-package-bases handlers/ services/ main.py config.py
git ls-files -z 'handlers/*.py' 'services/*.py' | xargs -0 python3 -m bandit -ll
```

---

## 6. Каталог шагов (Фазы 0–4 в архиве, Фаза 5 активна)

> **Примечание:** Шаги `S0.1`–`S4.10` (Фазы 0–4) полностью выполнены (`DONE`). Их описания сохранены ниже для истории. **Агенту: переходи сразу к разделу «Фаза 5 — Пост-аудит: безопасность, надёжность и архитектура (S5.1–S5.15)»!**

<details>
<summary>Архив выполненных шагов Фаз 0–4 (S0.1–S4.10) — НЕ ВЫПОЛНЯТЬ ПОВТОРНО</summary>

- **S0.1–S0.2:** Baseline, ветка, общие тестовые фикстуры (`DONE`).
- **S1.1–S1.12:** P0 критические исправления: `AgentResult`, `safe_html_format`, `call_ai_async`, стриминг `AIStreamEvent`, `palace_mcp`, `SemanticCache`, валидация токена, `CircuitBreaker`, напоминания (`DONE`).
- **S2.1–S2.9:** P1 логика и настройки: пустая button-сессия, `append_always_on`, модель из настроек, `load_chat`/`save_chat`, `graceful_degradation`, история/экспорт/инсайты/исследования (`DONE`).
- **S3.1–S3.10:** P2 устранение дублирования: `chat_store`, `chat_sync`, `list_chat_files`, `summary_service`, `wing_registry`, `palace_bridge`, `web_search_cache`, `ai_engine`, `reminder`, `safe_send` (`DONE`).
- **S4.1–S4.10:** P2/P0 чистота, CI, покрытие 100% целевых модулей, финальный отчёт и live smoke (`DONE`).

</details>

---

### Фаза 5 — Пост-аудит: безопасность, надёжность и архитектура (АКТИВНАЯ ФАЗА)

Каждый шаг спроектирован под бюджет **10k–25k токенов**, чтобы гарантированно укладываться в лимит 50k токенов с запасом на тесты и запись в журнал.

#### S5.1 — Безопасность HTML внутри `<code>` (INC-2)
- **Приоритет:** P0 (Безопасность / XSS-разметка)
- **Бюджет:** ≤15k токенов
- **Зависит от:** S1.2 (`DONE`)
- **Якоря:** `handlers/palace/save.py:281`, `services/brainstorm.py:370`, `handlers/notes_agent.py:268` (искать вхождения `<code>` рядом с `safe_html_format`)
- **Проблема:** Вызывающий код оборачивает результат `safe_html_format(...)` внутрь тега `<code>...</code>`. Так как `safe_html_format` пропускает разрешённые теги (`<b>`, `<i>`, `<a>`), внутри блока `<code>` они рендерятся как HTML-разметка, а не как литеральный текст, или ломают вложенность тегов Telegram.
- **Действия:**
  1. Найди через `grep -n "code>" handlers/ services/` все места, где динамические идентификаторы, пути или названия оборачиваются в `<code>...</code>`.
  2. В `handlers/palace/save.py`, `services/brainstorm.py`, `handlers/notes_agent.py` (и аналогичных местах для литеральных значений внутри `<code>`) замени `safe_html_format(val)` на `html.escape(str(val))`.
  3. Добавь unit-тесты, проверяющие, что значение вида `<b>test</b> & <script>` внутри `<code>` экранируется целиком (`&lt;b&gt;test&lt;/b&gt; &amp; &lt;script&gt;`).
- **AC:**
  - [ ] Внутри `<code>...</code>` пользовательские/системные строки экранируются через `html.escape`.
  - [ ] Целевые тесты в `test_palace_save_result.py`, `test_brainstorm.py`, `test_notes_agent_handler.py` зелёные.
- **Коммит:** `fix(step-5.1): escape literal values inside html code tags`.

#### S5.2 — Очистка PII, локальных путей и чувствительных данных в документации
- **Приоритет:** P0 (Приватность и безопасность данных)
- **Бюджет:** ≤15k токенов
- **Зависит от:** —
- **Якоря:** `GARMIN_INTEGRATION_PLAN.md` (разделы 8.2.1, 8.3, 8.11, 17.2, 17.4), `CLAUDE.md`, `AUDIT_FIX_PROGRESS.md`
- **Проблема:** В `GARMIN_INTEGRATION_PLAN.md` зафиксированы реальные медицинские данные и конкретные рецептурные препараты пользователя; в `CLAUDE.md` и документации присутствуют локальные пути `/Users/evg.pit/...` и реальный `ADMIN_ID`.
- **Действия:**
  1. В `GARMIN_INTEGRATION_PLAN.md` замени реальный медицинский профиль пользователя и конкретные названия его препаратов в разделах «Зафиксированный профиль пользователя» и «Ответы пользователя» на обезличенные синтетические примеры (например, `Medication A (sedative class)`, `Medication B (HR/BP class)`), сохранив справочную таблицу классов препаратов (раздел 21) как общую документацию.
  2. В `CLAUDE.md` и `GARMIN_INTEGRATION_PLAN.md` замени `/Users/evg.pit` на `~` или `/Users/<user>`.
  3. В `.gitignore` добавь паттерн `*.local.md` для хранения личных профилей вне Git.
- **AC:**
  - [ ] В отслеживаемых и планируемых `.md` файлах нет привязки личных рецептурных препаратов к конкретному пользователю и нет жёстких путей `/Users/evg.pit`.
- **Коммит:** `chore(step-5.2): sanitize personal medical profile and local paths in docs`.

#### S5.3 — Безопасность и неблокирующий I/O в `cli_extras.py`
- **Приоритет:** P0/P1 (Безопасность CLI / Event Loop)
- **Бюджет:** ≤25k токенов
- **Зависит от:** S1.12 (`DONE`)
- **Якоря:** `cli_extras.py` (`cli_yt`, `cli_remind`, `cli_transkript`)
- **Проблема:**
  1. `cli_yt` проверяет URL только через `url.startswith("http")`, допуская некорректные URL или аргументы с `-` при передаче в `yt-dlp`, и читает файл транскрипции синхронным `open()` в `async def`.
  2. `cli_remind` обходит валидацию прошедшего времени (`_is_past`), не генерирует уникальный ключ `rem<ts>_<uid>_<uuid4>` и перезаписывает массив `reminders` без блокировки.
  3. `cli_transkript` блокирует event loop синхронными `os.listdir`, `os.path.getmtime`, `os.path.getsize` и `open().read()`.
- **Действия:**
  1. Добавь в `cli_extras.py` функцию `_validate_http_url(url: str) -> str | None` на базе `urllib.parse.urlparse` (схема строго `http` или `https`, непустой `netloc`, не начинается с `-`). Используй её в `cli_yt`.
  2. В `cli_remind` проверяй `_is_past(parsed.get("unix_timestamp"))` (возвращай `PAST_TIME_TEXT` из `handlers.reminder`) и сохраняй напоминание с уникальным ключом `id` (`uuid4().hex`), аналогично `handlers/reminder.py`.
  3. В `cli_yt` и `cli_transkript` переведи файловые операции (`listdir`/`getmtime`/`read`) на `asyncio.to_thread` или `aiofiles`, добавь защиту от path traversal при чтении файла транскрипта.
- **Тесты:** создай/дополни `tests/test_cli_extras.py` (невалидный URL, прошлое время в `cli_remind`, чтение транскрипта).
- **AC:**
  - [ ] URL валидируется через `urlparse`.
  - [ ] `cli_remind` отклоняет прошлое время и генерирует уникальный ID.
  - [ ] В `async def` функциях `cli_extras.py` нет синхронного чтения файлов в основном потоке.
- **Коммит:** `fix(step-5.3): harden cli_extras url validation, reminders and async io`.

#### S5.4 — Корректный Graceful Shutdown в `main.py`
- **Приоритет:** P1 (Надёжность и жизненный цикл процессов)
- **Бюджет:** ≤20k токенов
- **Зависит от:** S1.8 (`DONE`)
- **Якоря:** `main.py` (`main()`, блок `finally`, `if __name__ == "__main__":`), `services/reminder_scheduler.py`
- **Проблема:** При остановке бота в `finally` вызывается только `stop_all()` для Ollama. Дочерний процесс MCP (`get_mcp().stop()`), планировщик напоминаний (`reminder_scheduler`) и сессия `bot.session` не закрываются корректно. Обработчик `SIGTERM` бросает синхронный `SystemExit` поверх event loop.
- **Действия:**
  1. Проверь `services/reminder_scheduler.py`: если нет функции `stop_scheduler()`, добавь безопасную отмену фоновой задачи планировщика.
  2. В `main.py` в блоке `finally:` функции `main()` последовательно и с `try/except Exception as e: logger.warning(...)` вызывай:
     - `stop_scheduler()`
     - `await get_mcp().stop()`
     - `stop_all()` (Ollama)
     - `await bot.session.close()` (если применимо и не ломает существующие моки в `tests/test_main.py`).
  3. Убедись, что обработка `SIGTERM` позволяет выполнить блок `finally` в `main()`.
- **Тесты:** дополни `tests/test_main.py` проверкой вызова `mcp.stop()` и `stop_scheduler()` при завершении `main()`.
- **AC:**
  - [ ] При выходе из `main()` гарантированно останавливаются MCP, планировщик и Ollama.
  - [ ] Все тесты в `tests/test_main.py` зелёные.
- **Коммит:** `fix(step-5.4): ensure graceful shutdown of mcp and scheduler in main`.

#### S5.5 — Сериализация жизненного цикла `palace_mcp` (INC-6)
- **Приоритет:** P1 (Конкурентность / Защита от утечки процессов)
- **Бюджет:** ≤15k токенов
- **Зависит от:** S1.8 (`DONE`)
- **Якоря:** `services/palace_mcp.py` (`__init__`, `start`, `stop`, `_ensure_alive`)
- **Проблема:** Методы `start()` и `stop()` не защищены общим `asyncio.Lock`. Два конкурентных вызова `start()` или `_ensure_alive()` могут запустить два дочерних процесса MCP, потеряв ссылку на первый (процесс-зомби).
- **Действия:**
  1. Добавь `self._lifecycle_lock = asyncio.Lock()` в `PalaceMCP.__init__`.
  2. Сериализуй `start()` и `stop()` через `async with self._lifecycle_lock:` (внутренний вызов `_stop_unlocked()` используй при ошибке внутри `start()`, чтобы избежать deadlock).
  3. В начале `start()` под локом проверяй, не стал ли процесс уже запущенным и готовым (`self._proc is not None and self._proc.returncode is None and self._ready.is_set()`), чтобы второй ожидавший корутин не перезапускал живой процесс.
- **Тесты:** добавь в `tests/test_palace_mcp.py` тест на `asyncio.gather(mcp.start(), mcp.start())` — процесс должен создаваться ровно 1 раз.
- **AC:**
  - [ ] Конкурентный `start()` создаёт ровно один subprocess.
  - [ ] Нет deadlock при сбое handshake внутри `start()`.
- **Коммит:** `fix(step-5.5): serialize palace_mcp start and stop with lifecycle lock`.

#### S5.6 — Удаление/миграция устаревшего `get_ai_response_async` (INC-3)
- **Приоритет:** P1 (Производительность и таймауты)
- **Бюджет:** ≤20k токенов
- **Зависит от:** S1.3 (`DONE`), S3.8b (`DONE`)
- **Якоря:** `services/ai_engine.py:396` (`get_ai_response_async`) и все вызовы по проекту (`grep -rn "get_ai_response_async" handlers/ services/ cli*`)
- **Проблема:** Старая функция `get_ai_response_async` создаёт новый `ThreadPoolExecutor` на каждый вызов и не имеет таймаута.
- **Действия:**
  1. Найди все оставшиеся вызовы `get_ai_response_async` в `handlers/`, `services/`, `cli/`.
  2. Внутри самой `get_ai_response_async` замени ручное создание `ThreadPoolExecutor` на делегирование в `await call_ai_async(..., timeout=DEFAULT_AI_TIMEOUT)` (сохранив сигнатуру для обратной совместимости с тестами), либо переведи оставшихся вызывающих напрямую на `call_ai_async`.
  3. Добавь тест в `tests/test_ai_engine.py`, подтверждающий, что `get_ai_response_async` использует таймаут и не создаёт `ThreadPoolExecutor`.
- **AC:**
  - [ ] Ни один async AI-вызов не создаёт одноразовый `ThreadPoolExecutor` без таймаута.
  - [ ] Покрытие `services/ai_engine.py` остаётся 100%.
- **Коммит:** `refactor(step-5.6): route get_ai_response_async through call_ai_async with timeout`.

#### S5.7 — Автовосстановление (cooldown) в Graceful Degradation (INC-9)
- **Приоритет:** P1 (Надёжность / Self-healing)
- **Бюджет:** ≤20k токенов
- **Зависит от:** S2.5 (`DONE`)
- **Якоря:** `services/graceful_degradation.py`, `tests/test_graceful_degradation.py`
- **Проблема:** После `report_failure("memory")` метод `should_use_memory()` навсегда возвращает `False` до ручного вызова `report_success("memory")`, а так как память отключена, повторная попытка чтения не происходит (deadlock деградации).
- **Действия:**
  1. Добавь в `DegradationManager` хранение времени последнего отказа компонента (`_last_failure_at: dict[str, float]`) и параметр `recovery_cooldown: float = 300.0` (5 минут, с возможностью передать `clock` для тестов).
  2. В `should_use_memory()` (и аналогичных проверках компонентов): если компонент помечен как упавший, но прошло `>= recovery_cooldown` секунд с момента отказа — разрешай пробную попытку (`return True`).
  3. Добавь детерминированные тесты (с fake clock) на автоматическую пробную попытку после истечения cooldown.
- **AC:**
  - [ ] Компонент `memory` не блокируется навечно после одиночного сбоя; через `recovery_cooldown` разрешается повторная попытка.
  - [ ] Тесты в `tests/test_graceful_degradation.py` зелёные.
- **Коммит:** `fix(step-5.7): add recovery cooldown for degraded memory component`.

#### S5.8 — Поддержка `images` и `system` в Gemini-стриминге (INC-4)
- **Приоритет:** P2 (Консистентность AI-пайплайна)
- **Бюджет:** ≤20k токенов
- **Зависит от:** S1.5 (`DONE`), S3.8b (`DONE`)
- **Якоря:** `services/ai_engine.py` (`_iter_ai_chunks`, `_build_gemini_contents`, ветка `stream=True` для `gemini`)
- **Проблема:** Sync-вызов Gemini (`stream=False`) корректно извлекает system-сообщение из `messages` в `system_instruction` и передаёт `images` через `Part.from_bytes`. Стриминговая ветка (`stream=True`) до сих пор игнорирует `images` и превращает system-сообщение из `messages` в `role="model"`.
- **Действия:**
  1. Унифицируй подготовку `contents` и `system_instruction` для Gemini в `_iter_ai_chunks` так, чтобы `stream=True` поддерживал передачу `images` (inline `image/jpeg`) и корректно объединял/использовал system-сообщение в `system_instruction` (не превращая `role="system"` в `role="model"`).
  2. Обнови и добавь тесты в `tests/test_ai_engine.py` на стриминг Gemini с изображением и system-сообщением в истории.
- **AC:**
  - [ ] Стриминг Gemini поддерживает `images` и `system` идентично sync-вызову.
  - [ ] Покрытие `services/ai_engine.py` — 100%.
- **Коммит:** `fix(step-5.8): support images and system messages in gemini streaming`.

#### S5.9 — Безопасная обработка сбоя `search_web` в стриминге (INC-5)
- **Приоритет:** P2 (Качество ответов и гигиена кэша)
- **Бюджет:** ≤20k токенов
- **Зависит от:** S1.7 (`DONE`)
- **Якоря:** `handlers/messages.py` (обработка паттерна `SEARCH: ...` и вызов `search_web`), `tests/test_messages_handler.py` (`test_ai_search_pattern_error`)
- **Проблема:** Если модель вернула директиву `SEARCH: <запрос>`, а вызов `search_web` выбросил исключение, в переменной `answer` остаётся сырая строка `SEARCH: ...`, которая затем сохраняется в историю чата и в `SemanticCache` как финальный ответ.
- **Действия:**
  1. При исключении в `search_web` внутри `handlers/messages.py` не сохраняй сырой `SEARCH: ...` в `SemanticCache` и историю чата.
  2. Выводи пользователю понятное сообщение о сбое веб-поиска (или очищай техническую директиву `SEARCH:` из ответа, помечая сбой флагом `search_failed = True`, запрещающим кэширование).
  3. Осознанно обнови тест `test_ai_search_pattern_error` в `tests/test_messages_handler.py` под новое безопасное поведение и зафиксируй это в журнале.
- **AC:**
  - [ ] Сырая директива `SEARCH: ...` при ошибке `search_web` никогда не попадает в `SemanticCache`.
  - [ ] Пользователь видит корректное уведомление об ошибке поиска.
- **Коммит:** `fix(step-5.9): prevent caching raw SEARCH directive on web search failure`.

#### S5.10 — Сохранение реплики пользователя в Always-On режиме (INC-7)
- **Приоритет:** P2 (Целостность истории диалога)
- **Бюджет:** ≤15k токенов
- **Зависит от:** S2.2 (`DONE`), S3.1 (`DONE`)
- **Якоря:** `handlers/messages.py` (ветка always-on агента), `services/agent_context.py` (`append_always_on`)
- **Проблема:** В always-on режиме при успешном ответе агента в chat file записывается только ответ `"assistant"`, а вопрос `"user"` не сохраняется, из-за чего в истории идут подряд ответы ассистента без вопросов.
- **Действия:**
  1. В always-on ветке `handlers/messages.py` при успешном ответе (`agent_result and agent_result.ok and agent_result.final_answer`) сохраняй через `ctx_store.append_always_on` сначала сообщение пользователя (`"user"`, `user_text`), а затем ответ ассистента (`"assistant"`, `agent_result.final_answer`).
  2. Убедись, что при ошибке агента ни вопрос, ни ошибка не засоряют историю.
  3. Обнови тесты always-on в `tests/test_messages_handler.py` и `tests/test_agent_context.py`.
- **AC:**
  - [ ] История чата после always-on ответа содержит пару `user` → `assistant`.
- **Коммит:** `fix(step-5.10): persist user message alongside assistant reply in always-on mode`.

#### S5.11 — Унификация хранилища чатов в CLI и проверка `save_chat` (INC-8, INC-10, INC-12)
- **Приоритет:** P2 (Устранение дублирования и потери ошибок записи)
- **Бюджет:** ≤25k токенов
- **Зависит от:** S3.1 (`DONE`), S3.3 (`DONE`)
- **Якоря:** `cli/menu.py`, `cli/utils.py`, `handlers/chat.py` (`generate_fresh_summary`, `cmd_context`, callback обновления саммари)
- **Проблема:**
  1. `cli/menu.py` и `cli/utils.py` содержат дублирующие реализации `load_chat`, `save_chat` и `list_chats` вместо использования `services/chat_store.py`.
  2. В `handlers/chat.py` при сохранении саммари игнорируется булев возврат `save_chat(...)`.
- **Действия:**
  1. Переведи `cli/menu.py` и `cli/utils.py` на делегирование в `services.chat_store` (`load_chat`, `save_chat`, `list_chat_files`), сохранив сигнатуры CLI-функций для обратной совместимости.
  2. В `handlers/chat.py` во всех местах сохранения саммари проверяй `if not save_chat(...):` — логируй предупреждение и при необходимости уведомляй пользователя.
- **Тесты:** тесты CLI и `tests/test_chat_handler.py` (сценарий, когда `save_chat` возвращает `False` при обновлении саммари).
- **AC:**
  - [ ] CLI использует `services.chat_store` без собственного дублирующего JSON I/O.
  - [ ] Отказ `save_chat` при сохранении саммари обрабатывается явно.
- **Коммит:** `refactor(step-5.11): unify cli chat storage and check summary save results`.

#### S5.12 — Перевод `auto_sync.py` на единый `sync_chat_file` (INC-11)
- **Приоритет:** P2 (Устранение дублирования)
- **Бюджет:** ≤15k токенов
- **Зависит от:** S3.2 (`DONE`)
- **Якоря:** `services/auto_sync.py`, `services/chat_sync.py` (`sync_chat_file`)
- **Проблема:** `services/auto_sync.py` самостоятельно вызывает `export_chat_verbatim` + `sync_to_palace`, дублируя пайплайн `services/chat_sync.py::sync_chat_file`.
- **Действия:**
  1. Переведи `services/auto_sync.py` на использование `sync_chat_file` (или общего внутреннего helper'а), сохранив тихую политику логирования без отправки сообщений в UI.
  2. Проверь и обнови `tests/test_auto_sync.py`.
- **AC:**
  - [ ] Логика `export_chat_verbatim` + `sync_to_palace` централизована.
  - [ ] Тесты `tests/test_auto_sync.py` зелёные.
- **Коммит:** `refactor(step-5.12): reuse sync_chat_file in auto_sync service`.

#### S5.13 — Стабилизация флаки-теста `notes_agent` и ужесточение `mypy`/`coverage`
- **Приоритет:** P2 (Качество тестов и конфигурация QA)
- **Бюджет:** ≤25k токенов
- **Зависит от:** —
- **Якоря:** `tests/test_notes_agent_handler.py` (`test_confirm_write_delete_requires_two_confirmations`), `pyproject.toml` (`[tool.coverage.report]`, `[[tool.mypy.overrides]]`)
- **Проблема:**
  1. Тест `test_confirm_write_delete_requires_two_confirmations` периодически падает в полных прогонах из-за фиксированного `asyncio.sleep(0.05)` при ожидании фонового вызова `_note_title` / `apple_notes.list_notes`.
  2. В `pyproject.toml` стоит `fail_under = 0` для coverage, а коды ошибок `mypy` (`union-attr`, `arg-type`, `index`) подавлены даже для `config` и `services.*`.
- **Действия:**
  1. В `tests/test_notes_agent_handler.py` замени `await asyncio.sleep(0.05)` на детерминированный опрос (retry loop до 0.5 с с шагом 0.01 с, пока `status.reply_markup is None`) или синхронизацию через `asyncio.Event`. Прогони тест 10 раз подряд.
  2. В `pyproject.toml` установи `fail_under = 80` в `[tool.coverage.report]`.
  3. Проверь `mypy` при сужении `[[tool.mypy.overrides]]` (оставить подавление `union-attr` только для `handlers.*` и `main`, убрав `config` и те `services.*`, которые проходят без ошибок).
- **AC:**
  - [ ] `test_confirm_write_delete_requires_two_confirmations` проходит 10/10 раз без флаков.
  - [ ] `mypy` проходит с 0 ошибок при более строгом конфиге.
  - [ ] В `pyproject.toml` зафиксирован порог покрытия `fail_under = 80`.
- **Коммит:** `test(step-5.13): stabilize notes_agent test and tighten coverage/mypy config`.

#### S5.14 — Гигиена Garmin WIP и закрытие Bandit B608 / Flake8
- **Приоритет:** P2 (Зелёный `make qa` и безопасность SQL)
- **Бюджет:** ≤25k токенов
- **Зависит от:** S4.5 (`DONE`)
- **Якоря:** `services/garmin/repository.py` (Bandit `B608`), `scripts/verify_garmin_login.py` (Flake8), `Makefile` / `pyproject.toml`
- **Проблема:** Полный локальный запуск `make qa`, `make lint` и `make security` падает из-за:
  1. 6 замечаний `flake8` в `scripts/verify_garmin_login.py` (F401, E402, E501, W292);
  2. 2 замечаний `bandit` уровня Medium (`B608` — динамический SQL) в `services/garmin/repository.py`;
  3. 10 ошибок сбора `pytest` в `tests/test_garmin_*.py`, если не установлен `fitparse` (или отсутствия `pytest.importorskip`).
- **Действия:**
  1. Почини 6 стилевых замечаний `flake8` в `scripts/verify_garmin_login.py` (и `models/garmin.py`, если остались W292).
  2. В `services/garmin/repository.py` добавь строгую валидацию динамических имён колонок по константному `frozenset` разрешённых полей перед сборкой SQL-запроса и задокументируй безопасность (чтобы `bandit -ll` давал 0 Medium/High).
  3. В тестовых файлах `tests/test_garmin_*.py`, требующих опциональные пакеты (`fitparse`, `reportlab`, `matplotlib`), используй `pytest.importorskip(...)` на уровне модуля (или настрой `conftest.py`), чтобы `make test` не падал с `CollectionError` при отсутствии опциональных пакетов.
- **AC:**
  - [ ] `python3 -m flake8 .` выдаёт **0 замечаний** по всему дереву.
  - [ ] `python3 -m bandit -ll -r handlers/ services/` выдаёт **0 Medium / 0 High**.
  - [ ] `python3 -m pytest --collect-only -q` собирается с **0 errors**.
- **Коммит:** `fix(step-5.14): resolve garmin lint, bandit B608 and pytest collection guards`.

#### S5.15 — Контроль CVE `chromadb` (INC-16) и финальный регрессионный прогон Фазы 5
- **Приоритет:** P0 (Финальный гейт безопасности и качества)
- **Бюджет:** ≤25k токенов
- **Зависит от:** S5.1–S5.14
- **Якоря:** `requirements.txt`, `pyproject.toml`, `.github/workflows/ci.yml`, `AUDIT_FIX_PROGRESS.md`
- **Действия:**
  1. Проверь доступность `chromadb>=1.6.0` через `python3 -m pip index versions chromadb`.
     - Если `1.6.0+` вышел — обнови пин в `requirements.txt` и `pyproject.toml`, убери `continue-on-error` с `pip-audit` в `.github/workflows/ci.yml`.
     - Если `1.6.0` ещё не вышел — в `.github/workflows/ci.yml` сделай шаг `pip-audit` **блокирующим для всех новых уязвимостей**, явно передав `--ignore-vuln` только для 4 известных ID `chromadb 1.5.9` (`PYSEC-2026-311`, `PYSEC-2026-3813`, `PYSEC-2026-3814`, `PYSEC-2026-3815`) с комментарием.
  2. Запусти финальные проверки:
     - `python3 -m flake8 .`
     - `python3 -m mypy --explicit-package-bases handlers/ services/ main.py config.py`
     - `python3 -m bandit -ll -r handlers/ services/`
     - Полный прогон `pytest`.
  3. Запиши сводный итог Фазы 5 в раздел `13. Итоговый отчёт Фазы 5` в `AUDIT_FIX_PROGRESS.md`.
- **AC:**
  - [ ] Все шаги `S5.1`–`S5.15` имеют статус `DONE`.
  - [ ] CI `pip-audit` блокирует любые новые CVE.
  - [ ] `flake8`, `mypy`, `bandit -ll` и `pytest` полностью зелёные.
- **Коммит:** `ci(step-5.15): enforce blocking pip-audit and complete phase 5 qa`.

---

## 7. Трассировка новых рекомендаций (Фаза 5)

| Рекомендация / Инцидент | Шаг Фазы 5 | Бюджет |
|---|---|---:|
| Экранирование HTML внутри `<code>` (INC-2) | S5.1 | ≤15k |
| Очистка личного медпрофиля и локальных путей в `.md` | S5.2 | ≤15k |
| Валидация URL, `cli_remind` и async I/O в `cli_extras.py` | S5.3 | ≤25k |
| Graceful shutdown (`mcp`, `scheduler`, `bot`) в `main.py` | S5.4 | ≤20k |
| `asyncio.Lock` для `palace_mcp.start/stop` (INC-6) | S5.5 | ≤15k |
| Таймаут и отказ от `ThreadPoolExecutor` в `get_ai_response_async` (INC-3) | S5.6 | ≤20k |
| Cooldown восстановления памяти в `graceful_degradation` (INC-9) | S5.7 | ≤20k |
| Поддержка `images` и `system` в стриминге Gemini (INC-4) | S5.8 | ≤20k |
| Запрет кэширования сырого `SEARCH:` при сбое веб-поиска (INC-5) | S5.9 | ≤20k |
| Сохранение реплики `user` в Always-On режиме (INC-7) | S5.10 | ≤15k |
| Единый `chat_store` в CLI и проверка `save_chat` саммари (INC-8, 10, 12) | S5.11 | ≤25k |
| Перевод `auto_sync.py` на `sync_chat_file` (INC-11) | S5.12 | ≤15k |
| Стабилизация флака `notes_agent` и пороги `coverage`/`mypy` | S5.13 | ≤25k |
| Починка `flake8`, `bandit B608` и `importorskip` для Garmin WIP | S5.14 | ≤25k |
| Блокирующий `pip-audit` (INC-16) и финальный регресс Фазы 5 | S5.15 | ≤25k |

---

## 8. Definition of Done для Фазы 5

- [ ] Все шаги `S5.1`–`S5.15` имеют статус `DONE` в `AUDIT_FIX_PROGRESS.md`.
- [ ] Инциденты `INC-2`..`INC-12` и `INC-16` переведены в статус `RESOLVED` в таблице раздела 9 `AUDIT_FIX_PROGRESS.md`.
- [ ] Ни одна сессия не превысила лимит 50 000 токенов; завершённые шаги не переделывались повторно.
- [ ] `flake8 .`, `mypy`, `bandit -ll` и `pytest` проходят без ошибок.

---

## 9. Шаблон итогового ответа агента после каждого шага

```text
Шаг: S5.x — <название>
Статус: DONE | PARTIAL | BLOCKED
Ветка/HEAD: <branch> / <hash>
Изменено: <файлы>
Тесты: <команда> → <результат>
QA: lint <...>, mypy <...>, bandit <...>
AC: <чеклист>
Коммит: <hash>
Расход токенов сессии: ~<k> / 50k (оценка)
Следующий шаг: <S5.y или HANDOFF>
```

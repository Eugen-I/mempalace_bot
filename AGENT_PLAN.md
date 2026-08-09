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
- [x] Связывание идей при сохранении («Связано с: …»):
      find_linked по контексту (notes/palace/kg), блок в превью bs_save
- [x] Авто-категоризация Apple Notes → KG
      services/auto_categorize.py: categorize_note (тип+темы, переисп. _extract_from_filename)
      + auto_categorize_notes (лимит, kv-отметки "categorized", факты topic→mempalace_kg_add,
      толерантность: index/kg/kv не роняют цикл, отметка только при успехе);
      подключение в reminder_scheduler раз в 720 циклов (~6ч)
- [x] Reflection-вопрос после штурма
      services/reflection.py (build_reflection_question, save_reflection_answer,
      kv-журнал "reflection"); после успешного сохранения идеи в Дворец
      (handlers/palace/save.py → maybe_ask_reflection) бот спрашивает
      «какая идея самая сильная и почему?», ответ перехватывается в
      messages.py (хук 0ccb), кнопка «⏭ Пропустить» (bs_reflect_skip)
- [x] Проверить запись id события Apple Calendar в список напоминаний (не требуется сейчас)

## Точка возобновления (обновлять в конце КАЖДОГО шага)
- Текущая фаза/шаг: ВСЕ ФАЗЫ 0–3.5 + БОНУСЫ ЗАВЕРШЕНЫ (2026-08-09). Следующий:
  Agent_guide.md — Задания 4 (selectolax web_search) и 5 (векторный поиск памяти)
- Последний завершённый шаг: семантический поиск Apple Notes (notes_embeddings.py,
  bge-m3 гибрид, commit 4f093c1)
- Следующий шаг: выполнить Задания 4-5 Agent_guide.md
- Статус QA: 3014 passed, BDD: 97 сценариев + 39 pre-existing errors (ai_caching,
  clear_memory — англ. шаги без реализаций, не наши); flake8/mypy 0, bandit без новых

## Чек-лист завершения
- [x] make lint / typecheck / test / security — зелёные
- [x] make cov ≥80% для новых модулей
- [ ] make mutate ≤10% для критичных модулей (заблокировано: mutmut крашится на Python 3.14)
- [x] TESTING_PROGRESS.md и AGENTS.md §10 обновлены

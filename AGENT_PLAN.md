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
- [ ] 2.1 `services/apple_notes.py`: JXA list_folders/list_notes/read_note/search + кэш-индекс
      ~/Documents/mempalace/notes_index.json (валидность/инвалидация)
- [ ] 2.2 Инструменты notes_search/notes_read/notes_list + схемы
- [ ] 2.3 Живая проверка TCC (первый вызов через бота)
- [ ] 2.4 Тесты (мок subprocess, кэш hit/miss/stale), Gherkin
- [ ] 2.5 `make qa`

## Фаза 3 — 🧠 Штурм
- [ ] 3.1 `/штурм <тема>` + кнопка
- [ ] 3.2 Сбор контекста: notes_search + mp_search + kg_query
- [ ] 3.3 5–7 идей с обоснованием → кнопки выбора (1..7 / все)
- [ ] 3.4 Подтверждение → сохранение (мост в существующие save-флоу)
- [ ] 3.5 Тесты, features/brainstorm.feature
- [ ] 3.6 `make qa`

## Фаза 3.5 — Календарь (отдельно)
- [ ] 3.5.1 Вопрос «⏰ бот / 📅 Apple Calendar / оба» при rem_yes
- [ ] 3.5.2 `services/apple_calendar.py` (JXA create/list) + TCC-проверка
- [ ] 3.5.3 Тесты, Gherkin
- [ ] 3.5.4 `make qa`

## Бонус (после, по желанию)
- [ ] Утренний дайджест (заметки вчера + новые KG-факты + напоминания дня)
- [ ] Связывание идей при сохранении («Связано с: …»)
- [ ] Авто-категоризация Apple Notes → KG
- [ ] Reflection-вопрос после штурма

## Точка возобновления (обновлять в конце КАЖДОГО шага)
- Текущая фаза/шаг: Фаза 1 ЗАВЕРШЕНА. Следующая: Фаза 2, шаг 2.1 (apple_notes JXA)
- Последний завершённый шаг: 1.4 — QA Фазы 1 (2742 passed, agent_mcp_tools 100%)
- Следующий шаг: 2.1 services/apple_notes.py + notes_index.json
- Статус QA: 2742 passed (было 2631), 8/8 BDD-сценариев

## Чек-лист завершения
- [ ] make lint / typecheck / test / security — зелёные
- [ ] make cov ≥80% для новых модулей
- [ ] make mutate ≤10% для критичных модулей
- [ ] TESTING_PROGRESS.md и AGENTS.md §10 обновлены

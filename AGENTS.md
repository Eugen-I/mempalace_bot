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

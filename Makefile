.PHONY: lint typecheck test cov security deps-audit mutate qa clean format help

# Интерпретатор venv бота (тот же, что в _scripts/start_bot.command).
# Переопределить: make test PY=python3
VENV_PY := $(HOME)/Documents/mempalace/venv/bin/python
PY ?= $(if $(wildcard $(VENV_PY)),$(VENV_PY),python3)

help:
	@grep -E '^[a-zA-Z_-]+:.*#' Makefile | sort | while read -r cmd rest; do \
		cmd=$${cmd%:}; \
		desc=$${rest#*# }; \
		printf "  \033[1;32m%-15s\033[0m %s\n" "$$cmd" "$$desc"; \
	done

lint: # flake8 всех .py файлов
	$(PY) -m flake8 .

typecheck: # mypy для новых/изменённых модулей
	$(PY) -m mypy --explicit-package-bases handlers/ services/ main.py config.py

test: # модульные тесты
	$(PY) -m pytest -q --tb=short --strict-markers

cov: # тесты с отчётом о покрытии
	$(PY) -m pytest --cov-report=term-missing --cov-fail-under=5

security: # статический анализ безопасности
	$(PY) -m bandit -r handlers/ services/

deps-audit: # аудит зависимостей
	$(PY) -m pip_audit

mutate: # мутационное тестирование
	$(PY) -m mutmut run

qa: lint typecheck test security # полный цикл проверки

clean: # удалить артефакты
	rm -rf .coverage coverage.xml .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

format: # автоформатирование (требует ruff или autopep8)
	@if command -v ruff >/dev/null 2>&1; then \
		$(PY) -m ruff check --fix .; \
	elif command -v autopep8 >/dev/null 2>&1; then \
		$(PY) -m autopep8 --in-place --recursive .; \
	else \
		echo "Установи ruff или autopep8: pip install ruff autopep8"; \
	fi

# --- Imported tools (managed by devkit) ---
-include .devkit/tools.mk

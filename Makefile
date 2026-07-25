.PHONY: lint typecheck test cov security deps-audit mutate qa clean format help

help:
	@grep -E '^[a-zA-Z_-]+:.*#' Makefile | sort | while read -r cmd rest; do \
		cmd=$${cmd%:}; \
		desc=$${rest#*# }; \
		printf "  \033[1;32m%-15s\033[0m %s\n" "$$cmd" "$$desc"; \
	done

lint: # flake8 всех .py файлов
	python3 -m flake8 .

typecheck: # mypy для новых/изменённых модулей
	python3 -m mypy --explicit-package-bases handlers/ services/ main.py config.py

test: # модульные тесты
	python3 -m pytest -q --tb=short --strict-markers

cov: # тесты с отчётом о покрытии
	python3 -m pytest --cov-report=term-missing --cov-fail-under=5

security: # статический анализ безопасности
	python3 -m bandit -r handlers/ services/

deps-audit: # аудит зависимостей
	python3 -m pip_audit

mutate: # мутационное тестирование
	python3 -m mutmut run --paths-to-mutate services/semantic_cache.py services/circuit_breaker.py services/event_bus.py services/kv_store.py services/graceful_degradation.py

qa: lint typecheck test security # полный цикл проверки

clean: # удалить артефакты
	rm -rf .coverage coverage.xml .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

format: # автоформатирование (требует ruff или autopep8)
	@if command -v ruff >/dev/null 2>&1; then \
		python3 -m ruff check --fix .; \
	elif command -v autopep8 >/dev/null 2>&1; then \
		python3 -m autopep8 --in-place --recursive .; \
	else \
		echo "Установи ruff или autopep8: pip install ruff autopep8"; \
	fi

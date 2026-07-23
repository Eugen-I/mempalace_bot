#!/bin/bash
cd "$HOME/Documents/mempalace_bot"
source "$HOME/Documents/mempalace/venv/bin/activate" || { echo "❌ Не удалось активировать venv."; exit 1; }
# Теперь запускаем бота, а он внутри себя проверит Ollama
python3 main.py
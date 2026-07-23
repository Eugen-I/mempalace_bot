#!/bin/bash
cd "$HOME/Documents/mempalace"
source venv/bin/activate
# Теперь запускаем бота, а он внутри себя проверит Ollama
python3 palace_bot.py
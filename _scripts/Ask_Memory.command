#!/bin/bash
cd "$HOME/Documents/mempalace"
source ~/.zshrc
source venv/bin/activate

# ПРОВЕРКА OLLAMA: если не запущена, запускаем приложение
if ! pgrep -x "ollama" > /dev/null; then
    echo "🔄 Ollama сервер не найден. Запускаю..."
    open -a Ollama
    sleep 4 # Ждем инициализации
fi
DATA_DIR="$HOME/Documents/mempalace"
BOT_DIR="$HOME/Documents/mempalace_bot"
cd "$DATA_DIR"
source venv/bin/activate

ACTIVE=$(cat .current_ai 2>/dev/null || echo "gemini")
echo "🤖 Запуск MemPalace CLI с моделью: $ACTIVE"
python3 "$BOT_DIR/cli_ask.py"
# Выводим текущую модель для контроля
ACTIVE=$(cat .current_ai 2>/dev/null || echo "gemini")
echo "🤖 Запуск MemPalace с моделью: $ACTIVE"

# Запускаем основной скрипт
#python3 ask_gemini.py

echo "---------------------------------------"
echo "Сессия завершена. Закрытие через 2 сек..."
sleep 3
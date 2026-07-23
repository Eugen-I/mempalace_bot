#!/bin/bash
DATA_DIR="$HOME/Documents/mempalace"
BOT_DIR="$HOME/Documents/mempalace_bot"

# ПРОВЕРКА OLLAMA: если не запущена, запускаем приложение
if ! pgrep -x "ollama" > /dev/null; then
    echo "🔄 Ollama сервер не найден. Запускаю..."
    open -a Ollama
    sleep 4 # Ждем инициализации
fi
cd "$DATA_DIR"
source "$DATA_DIR/venv/bin/activate" || { echo "❌ Не удалось активировать venv."; exit 1; }

ACTIVE=$(cat .current_ai 2>/dev/null || echo "gemini")
echo "🤖 Запуск MemPalace CLI с моделью: $ACTIVE"
python3 "$BOT_DIR/cli_ask.py"

echo "---------------------------------------"
echo "Сессия завершена. Закрытие через 2 сек..."
sleep 3
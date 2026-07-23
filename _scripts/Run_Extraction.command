#!/bin/bash
cd "$HOME/Documents/mempalace"
source venv/bin/activate

echo "======================================="
echo "   ЭКСТРАКЦИЯ ВАЖНЫХ МЫСЛЕЙ"
echo "======================================="

# Проверка, запущена ли Ollama
if ! pgrep -x "ollama" > /dev/null
then
    echo "(!) Ollama не запущена. Модель 7b недоступна."
    echo "Хотите запустить Ollama сейчас? (y/n)"
    read -n 1 run_ol
    echo ""
    if [ "$run_ol" == "y" ]; then
        open -a Ollama
        echo "Ждем запуска Ollama (10 сек)..."
        sleep 10
    fi
fi

#python3 extract_memories.py
python3 "$HOME/Documents/mempalace_bot/services/extract_memories.py"

echo "---------------------------------------"
echo "Завершено. Окно закроется через 3 секунды..."
sleep 5
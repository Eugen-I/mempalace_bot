#!/bin/bash
cd "$HOME/Documents/mempalace"
source venv/bin/activate

while true; do
    clear
    echo "======================================="
    echo "   УМНЫЙ ИМПОРТ ИЗ APPLE NOTES"
    echo "======================================="
    
    # Запускаем Python-скрипт, который мы обновили выше
    python3 import_notes.py

    echo "---------------------------------------"
    echo "Синхронизация новой информации..."
    python3 -m mempalace mine "my_notes"
    
    echo "---------------------------------------"
    echo "Обновление завершено."
    echo "---------------------------------------"
    
    echo "Хотите импортировать еще что-то? (y/n)"
    read -n 1 answer
    echo ""

    if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
        echo "Завершение работы..."
        sleep 2
        break
    fi
done
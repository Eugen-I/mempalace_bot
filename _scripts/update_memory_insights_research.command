#!/bin/bash
# 1. Переходим в рабочую папку
cd "$HOME/Documents/mempalace"

# 2. Активируем виртуальное окружение
source venv/bin/activate

# 3. Обновляем базу данных (майнинг всех папок)
echo "🔍 Индексация My Notes..."
python3 -m mempalace mine "/my_notes"

echo "🔍 Индексация Insights..."
python3 -m mempalace mine "/insights"

echo "🔍 Индексация Research..."
python3 -m mempalace mine "/research"

# 4. Показываем итоговый статус
python3 -m mempalace status

echo "---------------------------------------"
echo "База данных MemPalace полностью обновлена!"
echo "Нажмите Enter для выхода..."
read
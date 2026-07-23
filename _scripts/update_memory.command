#!/bin/bash
# 1. Переходим в новую папку в Документах
cd "$HOME/Documents/mempalace"

# 2. Активируем виртуальное окружение
source venv/bin/activate

# 3. Обновляем базу данных (майнинг)
python3 -m mempalace mine "$HOME/Documents/mempalace/my_notes"

# 4. Показываем текущий статус
python3 -m mempalace status

echo "---------------------------------------"
echo "База данных обновлена! Можно закрывать."
echo "Нажмите Enter для выхода..."
read
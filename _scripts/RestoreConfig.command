#!/bin/bash

# Переходим в папку скрипта
cd "$(dirname "$0")"

echo "=========================================="
echo "    MemPalace: Умное восстановление"
echo "=========================================="

# ПУТИ
BOT_DIR="$HOME/Documents/mempalace_bot"
PALACE_DIR="$HOME/Documents/mempalace"
VENV_PATH="$PALACE_DIR/venv/bin/activate"

# Список строк, которые ДОЛЖНЫ быть в файлах
# Используем одинарные кавычки для всего элемента массива, чтобы избежать проблем с экранированием
declare -a REQUIRED_CONFIG=(
'export PATH="/opt/homebrew/lib/ruby/gems/3.3.0/bin:$PATH"'
'export GEMINI_API_KEY="your_gemini_api_key"'
'alias mempalace="cd '$BOT_DIR' && source '$VENV_PATH' && python3 cli_ask.py"'
'alias up="cd '$BOT_DIR' && source '$VENV_PATH' && python3 -m mempalace mine \"my_notes\""'
'alias day="'$BOT_DIR'/daily.sh"'
'export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"'
)

files=("$HOME/.zprofile" "$HOME/.zshrc")

for file in "${files[@]}"; do
    if [ ! -f "$file" ]; then
        touch "$file"
        echo "📄 Создан новый файл: $file"
    fi

    echo "🔍 Проверка $file..."
    added_count=0

    for line in "${REQUIRED_CONFIG[@]}"; do
        # Проверяем наличие строки. 
        # Для alias mempalace проверяем по ключевому слову, так как точное совпадение может сбиться из-за пробелов
        if [[ "$line" == *"alias mempalace"* ]]; then
             if ! grep -q "alias mempalace=" "$file"; then
                 echo "" >> "$file"
                 echo "$line" >> "$file"
                 echo "➕ Добавлен алиас mempalace"
                 added_count=$((added_count + 1))
             fi
        elif [[ "$line" == *"alias up"* ]]; then
             if ! grep -q "alias up=" "$file"; then
                 echo "" >> "$file"
                 echo "$line" >> "$file"
                 echo "➕ Добавлен алиас up"
                 added_count=$((added_count + 1))
             fi
        else
            # Для остальных строк точное совпадение
            if ! grep -Fq "$line" "$file"; then
                echo "" >> "$file"
                echo "$line" >> "$file"
                echo "➕ Добавлено: ${line:0:40}..."
                added_count=$((added_count + 1))
            fi
        fi
    done

    if [ $added_count -eq 0 ]; then
        echo "✅ Все настройки MemPalace уже на месте."
    else
        echo "✨ Восстановлено $added_count строк."
    fi
done

echo "------------------------------------------"
echo "🔄 Обновляю окружение..."
source ~/.zprofile 2>/dev/null
source ~/.zshrc 2>/dev/null

echo "✅ Готово! Теперь команда 'mempalace' должна работать."
exit
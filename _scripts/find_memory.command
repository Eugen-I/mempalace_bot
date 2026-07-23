#!/bin/bash
# Переходим в папку проекта 
cd "$HOME/Documents/mempalace"

# Активируем виртуальное окружение 
source venv/bin/activate

while true; do
    clear
    echo "======================================="
    echo "   MemPalace: Бесконечный поиск        "
    echo "======================================="
    echo "Для выхода из скрипта нажмите Ctrl+C"
    echo ""

    # 1. Запрос поискового запроса
    echo -n "Введите поисковый запрос (или 'exit' для выхода): "
    read user_query

    # Проверка на выход
    if [[ "$user_query" == "exit" ]]; then
        echo "Выход из программы..."
        break
    fi

    # 2. Запрос количества результатов
    echo -n "Сколько ответов выдать? (по умолчанию 10): "
    read res_count
    res_count=${res_count:-10}

    # 3. Запрос порога соответствия
    echo -n "Минимальный порог (напр. 0.70, по умолчанию 0): "
    read threshold
    threshold=${threshold:-0.00}

    echo ""
    echo "Ищу: '$user_query' (Порог: $threshold, Лимит: $res_count)..."
    echo "---------------------------------------"

    # Запускаем поиск и фильтруем через awk для соблюдения порога соответствия
    python3 -m mempalace search --results "$res_count" "$user_query" | awk -v limit="$threshold" '
        /Match:/ { 
            score = $2; 
            if (score >= limit) { print_block = 1; print $0 } else { print_block = 0 }
            next 
        }
        /^  \[[0-9]+\]/ { 
            current_header = $0; next 
        }
        { 
            if (print_block) {
                if (current_header != "") { print current_header; current_header = "" }
                print $0 
            }
        }'

    echo "---------------------------------------"
    echo "Поиск завершен."
    echo "Нажмите Enter, чтобы начать новый поиск..."
    read
done
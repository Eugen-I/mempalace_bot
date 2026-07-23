#!/bin/bash
PROJECT_DIR="$HOME/Documents/mempalace"
CONFIG_FILE="$PROJECT_DIR/.current_ai"
MODELS_JSON="$PROJECT_DIR/models.json"

# Проверка наличия jq
if ! command -v jq &> /dev/null; then
    echo "❌ Ошибка: jq не установлен. Выполните: brew install jq"
    exit 1
fi

while true; do
    clear
    echo "======================================="
    echo "   ВЫБОР ИИ ДЛЯ MEMPALACE"
    echo "======================================="

    # Отображение текущей модели
    if [ -f "$CONFIG_FILE" ]; then
        CURRENT=$(cat "$CONFIG_FILE")
        # Подсвечиваем текущую модель зеленым цветом
        echo -e "ТЕКУЩАЯ МОДЕЛЬ: \033[1;32m$CURRENT\033[0m"
    else
        echo "ТЕКУЩАЯ МОДЕЛЬ: Не установлена"
    fi
    echo "======================================="

    # Чтение JSON в массивы (совместимо с macOS/Zsh/Bash)
    NAMES=()
    TAGS=()
    while IFS= read -r line; do NAMES+=("$line"); done < <(jq -r '.ollama[].name, .openai[].name, .gemini[].name' "$MODELS_JSON")
    while IFS= read -r line; do TAGS+=("$line"); done < <(jq -r '.ollama[].tag, .openai[].tag, .gemini[].tag' "$MODELS_JSON")

    # Вывод списка моделей
    for i in "${!NAMES[@]}"; do
        echo "$((i+1))) ${NAMES[$i]} (${TAGS[$i]})"
    done

    echo "======================================="
    echo "0) 🚪 ВЫХОД"
    echo "======================================="
    
    read -p "Выберите номер: " choice

    # Логика выхода
    if [[ "$choice" == "0" ]]; then
        echo "Завершение работы..."
        sleep 1
        exit 0
    fi

    # Проверка выбора и обновление файла
    if [[ $choice -ge 1 && $choice -le ${#NAMES[@]} ]]; then
        idx=$((choice-1))
        echo "${TAGS[$idx]}" > "$CONFIG_FILE"
        echo -e "\n✅ \033[1;32mУспешно установлено:\033[0m ${NAMES[$idx]}"
        echo "Обновление меню через 1 секунду..."
        sleep 1.5
    else
        echo -e "\n❌ \033[1;31mОшибка: Неверный выбор\033[0m"
        sleep 1.5
    fi
done
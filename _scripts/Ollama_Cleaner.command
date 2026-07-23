#!/bin/bash

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Функция для паузы
pause() {
    echo ""
    echo -e "${BLUE}Нажмите Enter, чтобы продолжить...${NC}"
    read
}

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Ollama Model Cleaner                  ${NC}"
echo -e "${GREEN}========================================${NC}"

# Проверка наличия ollama
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}Ошибка: Ollama не найден!${NC}"
    echo "Убедитесь, что Ollama установлен и запущен."
    pause
    exit 1
fi

while true; do
    clear # Очищаем экран для удобства
    
    echo -e "${YELLOW}Загрузка списка моделей...${NC}"
    
    # Получаем список моделей. Используем --format json если возможно, иначе обычный вывод
    # Попытка использовать jq для точности
    if command -v jq &> /dev/null; then
        mapfile -t model_names < <(ollama list --format json 2>/dev/null | jq -r '.models[].name' 2>/dev/null)
    else
        # Резервный вариант: парсим обычный вывод ollama list
        # Пропускаем первую строку (заголовок) и берем первое слово (имя модели)
        mapfile -t model_names < <(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')
    fi

    # Фильтруем пустые строки
    clean_models=()
    for name in "${model_names[@]}"; do
        if [[ -n "$name" && "$name" != "NAME" ]]; then
            clean_models+=("$name")
        fi
    done

    total=${#clean_models[@]}

    if [ "$total" -eq 0 ]; then
        echo -e "${RED}Модели не найдены или Ollama не запущен.${NC}"
        echo "Проверьте, запущен ли Ollama (иконка в меню баре)."
        pause
        exit 0
    fi

    echo -e "${GREEN}Установленные модели (${total}):${NC}"
    echo "----------------------------------------"
    
    # Вывод нумерованного списка
    for i in "${!clean_models[@]}"; do
        num=$((i + 1))
        printf "  %2d. %s\n" "$num" "${clean_models[$i]}"
    done
    echo "----------------------------------------"
    
    echo ""
    echo -e "${YELLOW}Введите номер модели для удаления:${NC}"
    echo -e "(или 'q' для выхода, 'r' для обновления списка)"
    read -p "> " choice

    # Выход
    if [[ "$choice" == "q" || "$choice" == "Q" ]]; then
        echo "Выход."
        exit 0
    fi
    
    # Обновление списка без удаления
    if [[ "$choice" == "r" || "$choice" == "R" ]]; then
        continue
    fi

    # Проверка на число
    if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
        echo -e "${RED}Ошибка: Введите корректный номер.${NC}"
        pause
        continue
    fi

    # Проверка диапазона
    if [ "$choice" -lt 1 ] || [ "$choice" -gt "$total" ]; then
        echo -e "${RED}Ошибка: Номер вне диапазона (1-${total}).${NC}"
        pause
        continue
    fi

    # Выбор модели
    index=$((choice - 1))
    selected_model="${clean_models[$index]}"

    echo ""
    echo -e "${RED}ВНИМАНИЕ!${NC}"
    echo -e "Вы собираетесь удалить модель: ${YELLOW}${selected_model}${NC}"
    read -p "Подтвердить удаление? (y/n): " confirm

    if [[ "$confirm" == "y" || "$confirm" == "Y" || "$confirm" == "да" ]]; then
        echo -e "${YELLOW}Удаление ${selected_model}...${NC}"
        
        # Выполняем удаление и показываем вывод
        output=$(ollama rm "$selected_model" 2>&1)
        exit_code=$?
        
        echo "$output"
        
        if [ $exit_code -eq 0 ]; then
            echo -e "${GREEN}Успешно удалено!${NC}"
        else
            echo -e "${RED}Ошибка при удалении.${NC}"
        fi
    else
        echo "Удаление отменено."
    fi

    pause
done
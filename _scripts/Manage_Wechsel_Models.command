#!/bin/bash

CONFIG_PATH="$HOME/Documents/mempalace/models.json"

# Создаем директорию и файл конфигурации, если их нет
mkdir -p "$(dirname "$CONFIG_PATH")"
if [ ! -f "$CONFIG_PATH" ]; then
    echo '{"ollama": []}' > "$CONFIG_PATH"
fi

# Функция чтения списка
show_models() {
    echo ""
    echo "Текущие локальные модели (из конфига):"
    # Проверяем, есть ли модели в файле
    local count
    count=$(jq '.ollama | length' "$CONFIG_PATH" 2>/dev/null)
    
    if [ "$count" -eq 0 ] || [ -z "$count" ]; then
        echo "  (Список пуст)"
    else
        jq -r '.ollama | to_entries[] | "\(.key + 1)) \(.value.name) (\(.value.tag))"' "$CONFIG_PATH"
    fi
    echo "---------------------------------------"
}

# Основной цикл меню
while true; do
    echo "======================================="
    echo "   УПРАВЛЕНИЕ МОДЕЛЯМИ MEMPALACE"
    echo "======================================="
    show_models
    echo "1) Добавить новую модель"
    echo "2) Удалить модель"
    echo "0) Выход"
    read -p "Выбор: " act

    case "$act" in
        1)
            read -p "Название (для меню): " mname
            read -p "Тег (из ollama list, например llama3:latest): " mtag
            read -p "Описание: " mdesc
            
            # Безопасное добавление через --arg (защита от спецсимволов в строках)
            jq --arg name "$mname" --arg tag "$mtag" --arg desc "$mdesc" \
               '.ollama += [{"name": $name, "tag": $tag, "desc": $desc}]' \
               "$CONFIG_PATH" > temp.json && mv temp.json "$CONFIG_PATH"
            
            echo "✅ Модель добавлена в конфиг!"
            
            # Предложение скачать
            read -p "Скачать её сейчас в Ollama? (y/n): " pull
            if [[ "$pull" =~ ^[Yy]$ ]]; then
                echo "⏳ Скачивание модели $mtag..."
                ollama pull "$mtag"
                echo "✅ Скачивание завершено."
            fi
            ;;
            
        2)
            # Получаем количество моделей
            local_count=$(jq '.ollama | length' "$CONFIG_PATH")
            
            if [ "$local_count" -eq 0 ]; then
                echo "❌ Список моделей пуст. Нечего удалять."
                continue
            fi

            read -p "Введите номер модели для удаления: " del_num
            
            # Проверка, что введено число
            if ! [[ "$del_num" =~ ^[0-9]+$ ]]; then
                echo "❌ Ошибка: введите корректный номер."
                continue
            fi

            # jq индексы начинаются с 0, поэтому вычитаем 1
            index=$((del_num - 1))
            
            # Проверяем, существует ли такой индекс
            if [ "$index" -lt 0 ] || [ "$index" -ge "$local_count" ]; then
                echo "❌ Ошибка: модель с таким номером не найдена."
                continue
            fi

            # Получаем тег удаляемой модели для возможного удаления из Ollama
            tag_to_delete=$(jq -r ".ollama[$index].tag" "$CONFIG_PATH")
            name_to_delete=$(jq -r ".ollama[$index].name" "$CONFIG_PATH")

            echo "Вы собираетесь удалить: $name_to_delete ($tag_to_delete)"
            read -p "Подтвердить удаление из конфига? (y/n): " confirm_conf
            if [[ "$confirm_conf" =~ ^[Yy]$ ]]; then
                # Удаляем элемент из массива по индексу
                jq "del(.ollama[$index])" "$CONFIG_PATH" > temp.json && mv temp.json "$CONFIG_PATH"
                echo "✅ Модель удалена из конфига."

                # Предложение удалить из системы (Ollama)
                read -p "Удалить саму модель из Ollama (освободить место)? (y/n): " delete_ollama
                if [[ "$delete_ollama" =~ ^[Yy]$ ]]; then
                    echo "⏳ Удаление модели $tag_to_delete из Ollama..."
                    ollama rm "$tag_to_delete"
                    echo "✅ Модель удалена из Ollama."
                fi
            else
                echo "Отмена удаления."
            fi
            ;;
            
        0)
            echo "Выход из программы."
            exit 0
            ;;
            
        *)
            echo "❌ Неверный выбор. Попробуйте снова."
            ;;
    esac
    echo "" # Пустая строка для красоты
done
#!/bin/bash

# Пути
CHATS_DIR="$HOME/Documents/mempalace/chats"
NOTES_DIR="$HOME/Documents/mempalace/my_notes"
PYTHON_SCRIPT="$HOME/Documents/mempalace/convert_chat.py"

# 1. Создаем вспомогательный Python-скрипт для красивой конвертации
cat << 'PYEOF' > "$PYTHON_SCRIPT"
import json
import sys
import os

def convert(json_path, txt_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"--- АРХИВ ДИАЛОГА: {os.path.basename(json_path)} ---\n")
        f.write(f"Дата переноса: {os.popen('date').read()}\n\n")
        
        for msg in data:
            role = "ВЫ" if msg['role'] == 'user' else "AI"
            f.write(f"[{role}]:\n{msg['content']}\n")
            f.write("-" * 30 + "\n")

if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
PYEOF

# 2. Логика выбора файла
echo "======================================="
echo "   АРХИВАЦИЯ ДИАЛОГА В ПАМЯТЬ"
echo "======================================="

# Получаем список последних 10 JSON файлов
cd "$CHATS_DIR"
files=($(ls -t *.json | head -n 10))

if [ ${#files[@]} -eq 0 ]; then
    echo "Чатов не найдено."
    sleep 2
    exit
fi

for i in "${!files[@]}"; do
    echo "$((i+1))) ${files[$i]}"
done

echo ""
read -p "Выберите номер чата для переноса (1-10): " choice
selected_file="${files[$((choice-1))]}"

if [ -z "$selected_file" ]; then
    echo "Ошибка выбора."
    exit
fi

# Имя для нового текстового файла
target_name="${selected_file%.json}.txt"
target_path="$NOTES_DIR/$target_name"

# Конвертируем
python3 "$PYTHON_SCRIPT" "$CHATS_DIR/$selected_file" "$target_path"

echo "---------------------------------------"
echo "Готово! Чат конвертирован и перенесен:"
echo "-> $target_path"
echo "---------------------------------------"
echo "Обновить общую память MemPalace сейчас? (y/n)"
read -n 1 answer
echo ""

if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
    cd "$HOME/Documents/mempalace"
    source venv/bin/activate
    python3 -m mempalace mine "my_notes"
    echo "Память обновлена!"
fi

sleep 2

#!/bin/bash
# ✅ Исправлены пути, активация venv и добавлена защита от ошибок
cd "$HOME/Documents/mempalace" || { echo "❌ Папка mempalace не найдена."; exit 1; }
source "$HOME/Documents/mempalace/venv/bin/activate" || { echo "❌ Не удалось активировать venv."; exit 1; }

echo "🔍 Индексация заметок с автоматической разметкой по крыльям..."

# Базовая папка
NOTES_DIR="$HOME/Documents/mempalace/my_notes"

# Проходим по всем подпапкам
for dir in "$NOTES_DIR"/*/; do
    [ -d "$dir" ] || continue
    folder_name=$(basename "$dir")
    
    # Маппинг имён папок → крылья (можно расширять)
    case "$folder_name" in
        *"Сон"*|*"Dream"*)       wing="dreams" ;;
        *"Сценарии"*|*"Script"*)  wing="creative" ;;
        *"Идеии"*|*"Idea"*)       wing="ideas" ;;
        *"Проект"*|*"Project"*) wing="projects" ;;
        *"Личность"*|*"Personal"*)  wing="personal" ;;
	*"Архетипы"*|*"Archetype"*)    wing="archetypes" ;;
	*"Философия"*|*"Philosophy"*)  wing="philosophy" ;;
        *)                      wing="general" ;;
    esac
    
    echo "📂 Индексирую: $folder_name → крыло: $wing"
    python3 -m mempalace mine "$dir" --wing "$wing" --mode convos
done

# Индексируем остальные папки
echo "🔍 Индексация Insights..."
python3 -m mempalace mine "$HOME/Documents/mempalace/insights" --wing insights --mode convos

echo "🔍 Индексация Research..."
python3 -m mempalace mine "$HOME/Documents/mempalace/research" --wing research --mode convos

echo "📊 Статус дворца:"
python3 -m mempalace status

echo "---------------------------------------"
echo "✅ База обновлена с разделением по крыльям!"
echo "Нажмите Enter для выхода..."
read
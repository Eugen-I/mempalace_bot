#!/bin/bash
# =============================================================================
# PalaceMaster.command — Единый командный центр управления MemPalace
#
# Работает из ЛЮБОГО места в системе (Finder, Терминал, любая папка).
# Автоматически находит:
#   - Виртуальное окружение Python (venv)
#   - Репозитории mempalace и mempalace_bot
#   - Базы данных ChromaDB и Knowledge Graph
#   - Папку заметок my_notes
# =============================================================================

# Заголовок окна терминала
echo -ne "\033]0;🏰 MemPalace Master Studio\007"

# 1. Определение рабочей директории и поиск palace_master.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"

SEARCH_PATHS=(
    "$SCRIPT_DIR/palace_master.py"
    "$HOME/Documents/Скрипты для повседневных задачь/_scripts/palace_master.py"
    "$HOME/Documents/mempalace/_scripts/palace_master.py"
    "$HOME/Documents/mempalace_bot/_scripts/palace_master.py"
)

PYTHON_SCRIPT=""
for p in "${SEARCH_PATHS[@]}"; do
    if [ -f "$p" ]; then
        PYTHON_SCRIPT="$p"
        break
    fi
done

if [ -z "$PYTHON_SCRIPT" ]; then
    echo "❌ Ошибка: Файл palace_master.py не найден ни в одной из стандартных папок."
    echo "Проверьте наличие скрипта в ~/Documents/mempalace/_scripts/ или ~/Documents/Скрипты для повседневных задачь/_scripts/"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

# 2. Поиск Python окружения (venv)
VENV_CANDIDATES=(
    "$HOME/Documents/mempalace/venv/bin/python3"
    "$HOME/Documents/mempalace_bot/venv/bin/python3"
    "$(which python3 2>/dev/null)"
)

PYTHON_BIN=""
for py in "${VENV_CANDIDATES[@]}"; do
    if [ -n "$py" ] && [ -x "$py" ]; then
        PYTHON_BIN="$py"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

# 3. Автоопределение директорий проектов
if [ -d "$HOME/Documents/mempalace_bot" ]; then
    export BOT_DIR="$HOME/Documents/mempalace_bot"
    export PYTHONPATH="$BOT_DIR:${PYTHONPATH:-}"
fi

if [ -d "$HOME/Documents/mempalace" ]; then
    export PALACE_DIR="$HOME/Documents/mempalace"
    export MEMPALACE_DATA_DIR="$HOME/Documents/mempalace"
fi

if [ -d "$HOME/.mempalace" ]; then
    export MEMPALACE_DIR="$HOME/.mempalace"
fi

# 4. Запуск Python скрипта
"$PYTHON_BIN" "$PYTHON_SCRIPT" "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "⚠️ Работа завершилась с кодом $EXIT_CODE."
    read -p "Нажмите Enter для закрытия терминала..."
fi

exit $EXIT_CODE

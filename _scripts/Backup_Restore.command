#!/bin/bash

# ═══════════════════════════════════════════════
#   MemPalace — Backup & Restore
# ═══════════════════════════════════════════════

BOT_DIR="$HOME/Documents/mempalace_bot"
PALACE_DIR="$HOME/Documents/mempalace"
DATA_DIR="$HOME/.mempalace"
BACKUP_DIR="$HOME/Documents"
TMP_BACKUP_DIR="/tmp"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

find_backup() {
    local dir
    dir=$(cd "$1" 2>/dev/null && pwd -P) || return
    find "$dir" -maxdepth 1 -name "mempalace_backup_*.tar.gz" 2>/dev/null | sort -r | head -1
}

show_menu() {
    clear
    echo "=========================================="
    echo "    MemPalace — Backup & Restore"
    echo "=========================================="
    echo ""
    echo " 1️⃣  Создать бэкап (перенести из /tmp в Documents)"
    echo " 2️⃣  Восстановить из бэкапа"
    echo " 0️⃣  Выход"
    echo ""
    echo "=========================================="
    echo ""
}

create_backup() {
    clear
    echo "📦 Поиск бэкапа в /tmp..."
    local backup
    backup=$(find_backup "$TMP_BACKUP_DIR")

    if [ -z "$backup" ]; then
        echo -e "${RED}❌ Бэкап в /tmp не найден.${NC}"
        echo "Сначала создайте бэкап через бота или вручную."
        echo ""
        echo -n "Нажмите Enter для возврата..."; read -r
        return
    fi

    local name
    name=$(basename "$backup")
    local dest="$BACKUP_DIR/$name"

    if [ -f "$dest" ]; then
        echo -e "${YELLOW}⚠️  В Documents уже есть файл: $name${NC}"
        echo -n "Перезаписать? (y/N): "; read -r answer
        if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
            echo "❌ Отменено."
            echo -n "Нажмите Enter для возврата..."; read -r
            return
        fi
        rm "$dest"
    fi

    cp "$backup" "$dest"
    echo -e "${GREEN}✅ Бэкап скопирован:${NC}"
    echo "   $dest"
    ls -lh "$dest" | awk '{print "   Размер: " $5}'

    echo ""
    echo -n "Удалить исходный бэкап из /tmp? (y/N): "; read -r answer
    if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
        rm "$backup"
        echo -e "${GREEN}🗑️  /tmp/$name удалён.${NC}"
    fi

    echo ""
    echo -n "Нажмите Enter для возврата..."; read -r
}

restore_backup() {
    clear
    echo "🔍 Поиск бэкапа в Documents..."
    local backup
    backup=$(find_backup "$BACKUP_DIR")

    if [ -z "$backup" ]; then
        echo -e "${RED}❌ Бэкап в Documents не найден.${NC}"
        echo "Сначала переместите бэкап (пункт 1)."
        echo ""
        echo -n "Нажмите Enter для возврата..."; read -r
        return
    fi

    local name
    name=$(basename "$backup")
    echo -e "Найден: ${CYAN}$name${NC}"
    ls -lh "$backup" | awk '{print "Размер: " $5}'
    echo ""

    echo -e "${YELLOW}⚠️  Будет восстановлено:${NC}"
    echo "   • $BOT_DIR     — код бота"
    echo "   • $PALACE_DIR  — заметки и CLI"
    echo "   • $DATA_DIR    — конфиг и граф знаний"
    echo -e "${YELLOW}   Все текущие файлы в этих папках будут ЗАМЕНЕНЫ.${NC}"
    echo ""

    echo -n "Начать восстановление? (y/N): "; read -r answer
    if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
        echo "❌ Отменено."
        echo -n "Нажмите Enter для возврата..."; read -r
        return
    fi

    # Шаг 1: распаковка
    clear
    echo "📦 Шаг 1/5. Распаковка архива..."
    local tmp_extract="/tmp/mempalace_restore_$$"
    rm -rf "$tmp_extract"
    mkdir -p "$tmp_extract"
    tar -xzf "$backup" -C "$tmp_extract"

    if [ ! -d "$tmp_extract/bot" ] || [ ! -d "$tmp_extract/mempalace" ]; then
        echo -e "${RED}❌ Архив повреждён или имеет неверную структуру.${NC}"
        rm -rf "$tmp_extract"
        echo -n "Нажмите Enter для возврата..."; read -r
        return
    fi

    # Шаг 2: копирование файлов
    echo "📁 Шаг 2/5. Копирование файлов..."
    rm -rf "$BOT_DIR" "$PALACE_DIR" "$DATA_DIR"
    cp -a "$tmp_extract/bot/" "$BOT_DIR/"
    cp -a "$tmp_extract/mempalace/" "$PALACE_DIR/"
    mkdir -p "$DATA_DIR"
    cp -a "$tmp_extract/mempalace_data/"* "$DATA_DIR/" 2>/dev/null
    rm -rf "$tmp_extract"
    echo -e "${GREEN}✅ Файлы скопированы.${NC}"

    # Шаг 3: venv бота
    echo "🐍 Шаг 3/5. Виртуальное окружение бота..."
    cd "$BOT_DIR" || exit 1
    python3.12 -m venv venv 2>/dev/null || python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt --quiet 2>&1 | tail -1
    echo -e "${GREEN}✅ Зависимости бота установлены.${NC}"

    # Шаг 4: venv mempalace
    echo "🐍 Шаг 4/5. Виртуальное окружение MemPalace..."
    cd "$PALACE_DIR" || exit 1
    python3.12 -m venv venv 2>/dev/null || python3 -m venv venv
    source venv/bin/activate
    pip install -e . --quiet 2>&1 | tail -1
    echo -e "${GREEN}✅ MemPalace CLI установлен.${NC}"

    # Шаг 5: repair
    echo "🏗️  Шаг 5/5. Перестроение векторного индекса (repair)..."
    echo -e "${YELLOW}Это может занять несколько минут.${NC}"
    cd "$PALACE_DIR" || exit 1
    source venv/bin/activate
    mempalace repair 2>&1
    echo -e "${GREEN}✅ База знаний перестроена.${NC}"

    echo ""
    echo "═══════════════════════════════════════════"
    echo -e "${GREEN}🎉 Восстановление завершено!${NC}"
    echo ""
    echo "Запустите бота:"
    echo "   cd $BOT_DIR && source venv/bin/activate && python3 main.py"
    echo "═══════════════════════════════════════════"
    echo ""
    echo -n "Нажмите Enter для возврата..."; read -r
}

# ═══════════════════════════════

while true; do
    show_menu
    echo -n "Выберите действие (0-2): "
    read -r choice
    case "$choice" in
        1) create_backup ;;
        2) restore_backup ;;
        0)
            clear
            exit 0
            ;;
        *)
            echo -e "${RED}Неверный выбор.${NC}"
            sleep 1
            ;;
    esac
done

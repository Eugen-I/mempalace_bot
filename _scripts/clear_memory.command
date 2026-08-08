#!/bin/bash

# ═══════════════════════════════════════════════
#   MemPalace — Очистка базы и данных
#   Полная очистка / крылья / комнаты / папки /
#   база данных / временные файлы
# ═══════════════════════════════════════════════

# Можно переопределить для тестов или нестандартной установки:
#   MEMPALACE_DIR=/path/to/mempalace MEMPALACE_DATA_DIR=/path/.mempalace ./clear_memory.command
PALACE_DIR="${MEMPALACE_DIR:-$HOME/Documents/mempalace}"
DATA_DIR="${MEMPALACE_DATA_DIR:-$HOME/.mempalace}"
BACKUP_DIR="$HOME/Documents"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Пользовательские папки данных (помимо крыльев)
USER_FOLDERS="my_notes insights research chats memory_store photos pdf_archive transkript voice_replies audio_downloads long_responses web_search_cache palace_sync"
# Временные/кэш данные
TEMP_ITEMS="temp_media web_search_cache locks"
# Временные файлы-логи
LOG_FILES="bot_debug.log nohup.out"

# ── Утилиты ────────────────────────────────────────────

hr() { # читаемый размер для du -k
    local kbytes="$1"
    awk -v kb="$kbytes" 'BEGIN {
        if (kb >= 1048576) printf "%.1fG", kb/1048576;
        else if (kb >= 1024) printf "%.1fM", kb/1024;
        else printf "%dK", kb;
    }'
}

size_of() { # размер пути в KB (или 0)
    [ -e "$1" ] || { echo 0; return; }
    du -sk "$1" 2>/dev/null | awk '{print $1}'
}

size_hr() { # печать размера пути в человеческом виде
    local p="$1"
    if [ -e "$p" ]; then
        echo -e "${CYAN}$(hr "$(size_of "$p")")${NC}"
    else
        echo -e "${GREEN}—${NC}"
    fi
}

heading() {
    clear
    echo "══════════════════════════════════════════════"
    echo "   $1"
    echo "══════════════════════════════════════════════"
    echo ""
}

confirm_yes() { # $1 = сообщение; 0 если подтверждено
    local msg="$1"
    echo -e "${YELLOW}$msg${NC}"
    echo -n "Подтвердить? (y/N): "
    read -r ans
    [ "$ans" = "y" ] || [ "$ans" = "Y" ]
}

pause() {
    echo ""
    echo -n "Нажмите Enter для продолжения..."
    read -r
}

check_bot_running() {
    local procs
    procs=$(pgrep -fl "main\.py" | grep -v "clear_memory" || true)
    if [ -n "$procs" ]; then
        echo -e "${RED}⚠️  Похоже, бот сейчас запущен:${NC}"
        echo "$procs" | sed 's/^/   /'
        echo -e "${YELLOW}Во время очистки бот должен быть остановлен,"
        echo "иначе файлы могут быть заблокированы или перезаписаны."
        echo -e "Рекомендую: KillPalaceBot.command → затем повторить.${NC}"
        echo ""
        if ! confirm_yes "Продолжить, не останавливая бот?"; then
            return 1
        fi
    fi
    return 0
}

# ── Списки данных ──────────────────────────────────────

wings() { # список крыльев (папки с mempalace.yaml)
    local f w
    find "$PALACE_DIR" -maxdepth 2 -name "mempalace.yaml" -type f 2>/dev/null | while read -r f; do
        w=$(dirname "$f")
        if [ "$(dirname "$w")" = "$PALACE_DIR" ]; then
            echo "$w"
        fi
    done | sort
}

rooms_of() { # комнаты крыла (подпапки, не скрытые)
    local wing="$1"
    find "$wing" -mindepth 1 -maxdepth 1 -type d ! -name ".*" 2>/dev/null | sort
}

existing_user_folders() {
    local d
    for d in $USER_FOLDERS; do
        [ -e "$PALACE_DIR/$d" ] && echo "$PALACE_DIR/$d"
    done
}

existing_temp_items() {
    local t
    for t in $TEMP_ITEMS; do
        [ -e "$PALACE_DIR/$t" ] && echo "$PALACE_DIR/$t"
    done
    [ -e "$DATA_DIR/locks" ] && echo "$DATA_DIR/locks"
}

db_items() { # части базы данных в ~/.mempalace
    local d
    for d in palace knowledge_graph.sqlite3 wal palace_backup tunnels.json locks; do
        [ -e "$DATA_DIR/$d" ] && echo "$DATA_DIR/$d"
    done
    [ -e "$PALACE_DIR/knowledge_graph.sqlite3" ] && echo "$PALACE_DIR/knowledge_graph.sqlite3"
}

all_targets() { # всё для полной очистки
    wings
    existing_user_folders
    db_items
    existing_temp_items
    echo "$PALACE_DIR/bot_debug.log"
    echo "$PALACE_DIR/nohup.out"
}

total_size() { # суммарный размер списка путей
    local p total
    total=0
    while read -r p; do
        [ -n "$p" ] || continue
        total=$((total + $(size_of "$p")))
    done
    echo "$total"
}

# ── Меню-выбор нескольких пунктов ──────────────────────

select_multiple() { # $1 = максимум; печатает выбранные номера (по одному в строке)
    local max="$1" in
    echo -n "Введите номера через запятую (или 0 — отмена): " >&2
    read -r in
    echo "$in" | tr ',;' ' ' | tr -s ' ' | while read -r tok; do
        [ -n "$tok" ] || continue
        case "$tok" in
            ''|*[!0-9]*) continue ;;
        esac
        if [ "$tok" -ge 1 ] 2>/dev/null && [ "$tok" -le "$max" ] 2>/dev/null; then
            echo "$tok"
        fi
    done
}

# ── Удаление с подтверждением и отчётом ────────────────

delete_paths() { # $1 = описание; $2... = пути
    local desc="$1" p before
    shift
    before=0
    for p in "$@"; do
        before=$((before + $(size_of "$p")))
    done
    if [ "$before" -eq 0 ]; then
        echo -e "${GREEN}✅ Ничего не было ($desc) — уже пусто.${NC}"
        return
    fi
    echo -e "${YELLOW}Будет удалено ($desc): ~$(hr $before)${NC}"
    for p in "$@"; do
        echo "   • $(basename "$p") — $(size_hr "$p")"
    done
    echo ""
    if ! confirm_yes "Удалить?"; then
        echo -e "${RED}❌ Отменено.${NC}"
        return 1
    fi
    for p in "$@"; do
        rm -rf "$p" 2>/dev/null
    done
    echo -e "${GREEN}✅ Удалено: ~$(hr "$before")${NC}"
}

# ── Бэкап ──────────────────────────────────────────────

ask_backup() { # $1 = список путей для бэкапа (по одному в строке)
    local paths="$1" name dest file
    echo -e "${CYAN}Рекомендую сначала сделать бэкап.${NC}"
    if ! confirm_yes "Создать бэкап перед очисткой?"; then
        return 0
    fi
    name="mempalace_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    dest="$BACKUP_DIR/$name"
    echo "📦 Создаю $name (это может занять время)..."
    tar -czf "$dest" --exclude='venv' --exclude='__pycache__' --exclude='.git' \
        -C "$(dirname "$PALACE_DIR")" \
        $(echo "$paths" | sed "s|^$PALACE_DIR|$(basename "$PALACE_DIR")|; s|^$DATA_DIR|$(basename "$DATA_DIR")|") \
        2>/dev/null
    if [ -f "$dest" ]; then
        file=$(du -sk "$dest" | awk '{print $1}')
        echo -e "${GREEN}✅ Бэкап: $dest (${CYAN}$(hr "$file")${GREEN})${NC}"
    else
        echo -e "${RED}❌ Бэкап не создан — продолжаю без него.${NC}"
    fi
}

# ═══════════════════════════════════════════════
#   Действия
# ═══════════════════════════════════════════════

summary() { # сводка занимаемого места
    echo -e "${CYAN}📊 Занимаемое место:${NC}"
    local w u d t total total_hr
    w=$(wings | total_size)
    u=$(existing_user_folders | total_size)
    d=$(db_items | total_size)
    t=$(existing_temp_items | total_size)
    total=$((w + u + d + t))
    total_hr=$(hr "$total")
    echo "   🏛  Крылья (wings):         $(hr "$w")"
    echo "   📁 Пользовательские папки: $(hr "$u")"
    echo "   🗄  База данных (~/.mempalace): $(hr "$d")"
    echo "   🧹 Временные/кэш:          $(hr "$t")"
    echo -e "   ${GREEN}Σ Итого: ${total_hr}${NC}"
    echo ""
}

full_wipe() {
    heading "🗑  ПОЛНАЯ ОЧИСТКА — всё как новое"
    check_bot_running || { pause; return; }

    echo -e "${RED}⚠️  Будет удалено БЕЗВОЗВРАТНО:${NC}"
    echo "   • Все крылья:  $(wings | xargs -n1 basename | tr '\n' ' ')"
    echo "   • Все пользовательские папки: $(existing_user_folders | xargs -n1 basename | tr '\n' ' ')"
    echo "   • База данных: $DATA_DIR (palace, граф знаний, туннели, locks, конфиг)"
    echo "   • knowledge_graph.sqlite3 в папке MemPalace"
    echo "   • Временные файлы: temp_media, кэши, логи"
    echo ""
    summary

    ask_backup "$(all_targets | sort -u)"

    echo -e "${RED}Для полной очистки нужно подтверждение ДВА раза.${NC}"
    if ! confirm_yes "Первое подтверждение: удалить ВСЁ?"; then
        echo -e "${RED}❌ Отменено.${NC}"
        pause
        return
    fi
    if ! confirm_yes "Второе подтверждение: вы уверены на 100%?"; then
        echo -e "${RED}❌ Отменено.${NC}"
        pause
        return
    fi

    echo ""
    echo "🗑  Очищаю..."
    local target total db_before
    db_before=$(size_of "$DATA_DIR")
    total=$db_before
    while read -r target; do
        [ -n "$target" ] || continue
        total=$((total + $(size_of "$target")))
        rm -rf "$target" 2>/dev/null
    done < <(all_targets | sort -u)
    rm -rf "$DATA_DIR"
    rm -f "$PALACE_DIR/bot_debug.log" "$PALACE_DIR/nohup.out" 2>/dev/null

    echo -e "${GREEN}✅ Полная очистка завершена! Освобождено: ~$(hr "$total")${NC}"
    echo ""
    echo "══════════════════════════════════════════════"
    echo "Как заполнить базу заново:"
    echo "   cd $PALACE_DIR"
    echo "   source venv/bin/activate"
    echo "   mempalace init .      # создать структуру"
    echo "   mempalace mine .      # проиндексировать папки"
    echo ""
    echo "Либо просто создайте новые папки-крылья и запустите обновление памяти."
    echo "══════════════════════════════════════════════"
    pause
}

wipe_wings() { # очистка крыльев или комнат
    local wing_list wing_num wing n room rooms room_num
    heading "🕸  Очистка крыльев и комнат"
    wing_list=$(wings)
    if [ -z "$wing_list" ]; then
        echo -e "${YELLOW}Крылья не найдены (нет mempalace.yaml).${NC}"
        pause
        return
    fi
    echo "Крылья:"
    n=1
    while read -r wing; do
        [ -n "$wing" ] || continue
        echo -e "  $n) ${CYAN}$(basename "$wing")${NC} — $(size_hr "$wing")"
        eval "wing_$n=$wing"
        n=$((n + 1))
    done <<< "$wing_list"
    echo ""
    echo -n "Выберите крыло (1-$((n - 1))), 0 — назад: "
    read -r wing_num
    case "$wing_num" in
        ''|*[!0-9]*) echo "Неверный выбор."; pause; return ;;
    esac
    [ "$wing_num" -ge 1 ] 2>/dev/null && [ "$wing_num" -le $((n - 1)) ] 2>/dev/null || { echo "Неверный выбор."; pause; return; }
    eval "wing=\$wing_$wing_num"

    heading "🪪  Крыло: $(basename "$wing")"
    echo -e "Размер крыла: $(size_hr "$wing")"
    echo ""
    rooms=$(rooms_of "$wing")
    if [ -z "$rooms" ]; then
        echo -e "${YELLOW}Комнат нет — можно удалить крыло целиком.${NC}"
    else
        echo "Комнаты:"
        n=1
        while read -r room; do
            [ -n "$room" ] || continue
            echo -e "  $n) ${CYAN}$(basename "$room")${NC} — $(size_hr "$room")"
            eval "room_$n=$room"
            n=$((n + 1))
        done <<< "$rooms"
        echo ""
        echo -e "  ${YELLOW}0) назад | w) удалить ВСЁ крыло | N) номер комнаты (можно несколько через запятую)${NC}"
        echo -n "Выбор: "
        read -r room_num
        if [ "$room_num" = "0" ] || [ -z "$room_num" ]; then
            return
        fi
        if [ "$room_num" = "w" ] || [ "$room_num" = "W" ]; then
            echo ""
            if confirm_yes "Удалить всё крыло $(basename "$wing")?"; then
                rm -rf "$wing"
                echo -e "${GREEN}✅ Крыло удалено: $(hr "$(size_of "$wing")")${NC}"
            fi
            pause
            return
        fi
        local sel=""
        sel=$(select_multiple $((n - 1)) <<< "$room_num")
        if [ -z "$sel" ]; then
            echo "Ничего не выбрано."
            pause
            return
        fi
        echo ""
        local chosen="" idx
        while read -r idx; do
            [ -n "$idx" ] || continue
            eval "chosen=\"\$chosen \$room_$idx\""
        done <<< "$sel"
        # shellcheck disable=SC2086
        delete_paths "комнаты крыла $(basename "$wing")" $chosen
        pause
        return
    fi
    # комнат нет — предложить удалить крыло
    echo ""
    if confirm_yes "Удалить крыло $(basename "$wing") целиком?"; then
        rm -rf "$wing"
        echo -e "${GREEN}✅ Крыло удалено: $(hr "$(size_of "$wing")")${NC}"
    fi
    pause
}

wipe_user_folders() {
    local folders n f i sel chosen
    folders=$(existing_user_folders)
    heading "📁 Пользовательские папки"
    if [ -z "$folders" ]; then
        echo -e "${YELLOW}Пользовательские папки не найдены.${NC}"
        pause
        return
    fi
    echo "Папки данных бота:"
    n=1
    while read -r f; do
        [ -n "$f" ] || continue
        echo -e "  $n) ${CYAN}$(basename "$f")${NC} — $(size_hr "$f")"
        eval "folder_$n=$f"
        n=$((n + 1))
    done <<< "$folders"
    echo ""
    echo -e "  ${YELLOW}0) назад | a) все | N) номера через запятую${NC}"
    echo -n "Выбор: "
    read -r i
    [ "$i" = "0" ] || [ -z "$i" ] && return
    if [ "$i" = "a" ] || [ "$i" = "A" ]; then
        sel="$folders"
    else
        sel=""
        local idx
        while read -r idx; do
            [ -n "$idx" ] || continue
            eval "sel=\"\$sel \$folder_$idx\""
        done <<< "$(select_multiple $((n - 1)) <<< "$i")"
        [ -n "$sel" ] || { echo "Ничего не выбрано."; pause; return; }
    fi
    echo ""
    # shellcheck disable=SC2086
    delete_paths "пользовательские папки" $sel
    pause
}

wipe_db() {
    local items n it i sel chosen
    items=$(db_items)
    heading "🗄  База данных MemPalace"
    echo -e "Конфиг ${CYAN}config.json${NC} и ${CYAN}identity.txt${NC} удаляться НЕ будут (нужны для работы)."
    echo ""
    if [ -z "$items" ]; then
        echo -e "${GREEN}База уже пуста.${NC}"
        pause
        return
    fi
    echo "Части базы:"
    n=1
    while read -r it; do
        [ -n "$it" ] || continue
        local label="${it#$DATA_DIR/}"
        echo -e "  $n) ${CYAN}$label${NC} — $(size_hr "$it")"
        eval "db_$n=$it"
        n=$((n + 1))
    done <<< "$items"
    echo ""
    echo -e "  ${YELLOW}0) назад | a) все | N) номера через запятую${NC}"
    echo -n "Выбор: "
    read -r i
    [ "$i" = "0" ] || [ -z "$i" ] && return
    if [ "$i" = "a" ] || [ "$i" = "A" ]; then
        chosen="$items"
    else
        chosen=""
        local idx
        while read -r idx; do
            [ -n "$idx" ] || continue
            eval "chosen=\"\$chosen \$db_$idx\""
        done <<< "$(select_multiple $((n - 1)) <<< "$i")"
        [ -n "$chosen" ] || { echo "Ничего не выбрано."; pause; return; }
    fi
    echo ""
    # shellcheck disable=SC2086
    delete_paths "база данных" $chosen
    echo ""
    echo -e "${CYAN}После очистки базы запустите: mempalace mine . (в папке MemPalace)${NC}"
    pause
}

wipe_temp() {
    local items
    items=$(existing_temp_items)
    heading "🧹 Временные файлы и кэши"
    local logs="" l
    for l in $LOG_FILES; do
        [ -e "$PALACE_DIR/$l" ] && logs="$logs $PALACE_DIR/$l"
    done
    # автосаммари чатов (*_summary.txt) — тоже временные
    local summaries=""
    summaries=$(find "$PALACE_DIR/chats" -maxdepth 1 -name "*_summary.txt" 2>/dev/null)
    echo "Временные данные:"
    local n f
    n=1
    while read -r f; do
        [ -n "$f" ] || continue
        echo -e "  $n) ${CYAN}${f#$PALACE_DIR/}${NC} — $(size_hr "$f")"
        eval "tmp_$n=$f"
        n=$((n + 1))
    done <<< "$items"
    for l in $logs; do
        echo -e "  $n) ${CYAN}лог: $(basename "$l")${NC} — $(size_hr "$l")"
        eval "tmp_$n=$l"
        n=$((n + 1))
    done
    for s in $summaries; do
        echo -e "  $n) ${CYAN}chats/$(basename "$s")${NC} — $(size_hr "$s")"
        eval "tmp_$n=$s"
        n=$((n + 1))
    done
    if [ $((n - 1)) -eq 0 ]; then
        echo -e "${GREEN}Временных файлов нет.${NC}"
        pause
        return
    fi
    echo ""
    echo -e "  ${YELLOW}0) назад | a) все | N) номера через запятую${NC}"
    echo -n "Выбор: "
    read -r i
    [ "$i" = "0" ] || [ -z "$i" ] && return
    local chosen=""
    if [ "$i" = "a" ] || [ "$i" = "A" ]; then
        local k
        for k in $(seq 1 $((n - 1))); do
            eval "chosen=\"\$chosen \$tmp_$k\""
        done
    else
        local idx
        while read -r idx; do
            [ -n "$idx" ] || continue
            eval "chosen=\"\$chosen \$tmp_$idx\""
        done <<< "$(select_multiple $((n - 1)) <<< "$i")"
        [ -n "$chosen" ] || { echo "Ничего не выбрано."; pause; return; }
    fi
    echo ""
    # shellcheck disable=SC2086
    delete_paths "временные файлы" $chosen
    pause
}

backup_only() {
    heading "📦 Создать бэкап"
    ask_backup "$(all_targets | sort -u)"
    pause
}

# ═══════════════════════════════════════════════
#   Главное меню
# ═══════════════════════════════════════════════

if [ ! -d "$PALACE_DIR" ]; then
    echo -e "${RED}❌ Папка MemPalace не найдена: $PALACE_DIR${NC}"
    echo "Укажите её через MEMPALACE_DIR=/путь/к/папке"
    read -r
    exit 1
fi

while true; do
    clear
    echo "=========================================="
    echo -e "   ${CYAN}MemPalace — Очистка базы данных${NC}"
    echo "=========================================="
    summary
    echo " 1️⃣  Полная очистка (всё как новое)"
    echo " 2️⃣  Очистить крыло / комнаты"
    echo " 3️⃣  Очистить пользовательские папки"
    echo " 4️⃣  Очистить базу данных (~/.mempalace)"
    echo " 5️⃣  Очистить временные файлы и кэши"
    echo " 6️⃣  Создать бэкап"
    echo " 0️⃣  Выход"
    echo "=========================================="
    echo -n "Выберите действие (0-6): "
    read -r choice
    case "$choice" in
        1) full_wipe ;;
        2) wipe_wings ;;
        3) wipe_user_folders ;;
        4) wipe_db ;;
        5) wipe_temp ;;
        6) backup_only ;;
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

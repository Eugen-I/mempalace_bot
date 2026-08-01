#!/bin/bash

# 📂 Пути
DATA_DIR="$HOME/Documents/mempalace"
BOT_DIR="$HOME/Documents/mempalace_bot"
VENV_DIR="$DATA_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python3"
FULL_BOT_PATH="$BOT_DIR/main.py"
LOG_FILE="$BOT_DIR/nohup.out"
VOICE_DIR="$DATA_DIR/voice_replies"
PID_FILE="$BOT_DIR/bot.pid"

# Переходим в папку бота
cd "$BOT_DIR" || exit 1

# 🎨 Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # Без цвета

show_menu() {
    clear
    echo "=========================================="
    echo "    MemPalace Bot Control Center"
    echo "=========================================="

    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -z "$PID" ] || ! ps -p "$PID" >/dev/null 2>&1; then
        echo -e " СТАТУС: ${RED}🔴 ОСТАНОВЛЕН${NC}"
        rm -f "$PID_FILE"
    else
        echo -e " СТАТУС: ${GREEN}🟢 РАБОТАЕТ (PID: $PID)${NC}"
    fi
    echo "------------------------------------------"
    echo " Бот:      $FULL_BOT_PATH"
    echo " Python:   ${PYTHON_BIN:-НЕ НАЙДЕН}"
    echo " Логи:     $LOG_FILE"
    echo " VoiceDir: $VOICE_DIR"
    echo "------------------------------------------"
    echo "1. Запустить (ИНТЕРАКТИВНО)"
    echo "2. Запустить (ФОН + caffeinate)"
    echo "3. ОСТАНОВИТЬ (Мягко)"
    echo "4. ЛОГИ"
    echo "5. Очистить логи"
    echo -e "6. ${YELLOW}ПРИНУДИТЕЛЬНО УБИТЬ ПРОЦЕССЫ${NC}"
    echo "7. ВОССТАНОВИТЬ настройки системы (.zprofile/.zshrc)"
    echo "8. Очистить временные аудиофайлы"
    echo "0. ВЫХОД"
    echo "------------------------------------------"
    printf "Выбор: "
}

stop_bot() {
    echo "🛑 Проверка и остановка бота..."
    killed_any=false
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if [ -n "$PID" ] && ps -p "$PID" >/dev/null 2>&1; then
            kill "$PID" 2>/dev/null
            sleep 1
            if ps -p "$PID" >/dev/null 2>&1; then
                echo -e "${YELLOW}⚠️ Процесс не завершился мягко, применяем SIGKILL${NC}"
                kill -9 "$PID" 2>/dev/null
            fi
            echo "✅ Процесс остановлен (PID: $PID)."
            killed_any=true
        else
            echo "ℹ️ Записанный PID недействителен или процесс уже останован."
        fi
        rm -f "$PID_FILE"
    fi
    
    # Fallback: always try to find and kill any remaining processes
    echo "ℹ️ Проверяю оставшиеся процессы..."
    pids=$(pgrep -f "main.py" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "Найдено процессы: $pids"
        echo "$pids" | xargs kill 2>/dev/null
        sleep 1
        remaining=$(echo "$pids" | while read pid; do
            if ps -p "$pid" >/dev/null 2>&1; then
                echo "$pid"
            fi
        done)
        if [ -n "$remaining" ]; then
            echo -e "${YELLOW}⚠️ Некоторые процессы не завершились, применяем SIGKILL${NC}"
            echo "$remaining" | xargs kill -9 2>/dev/null
        fi
        echo "✅ Все связанные процессы остановлены."
        killed_any=true
    fi
    
    if [ "$killed_any" = false ]; then
        echo "ℹ️ Активных процессов бота не найдено."
    fi
}

force_kill() {
    echo -e "${RED}💀 Выполняю полную очистку памяти от процессов...${NC}"
    pids=$(pgrep -f "main.py" 2>/dev/null)
    if [ -n "$pids" ]; then
        echo "Найдено PID: $pids"
        echo "$pids" | xargs kill -9 2>/dev/null
        echo -e "${GREEN}✅ Все связанные процессы уничтожены.${NC}"
    else
        echo "Зависших процессов не обнаружено."
    fi
    rm -f "$PID_FILE"
}

cleanup_voice_files() {
    echo "🧹 Проверка временных аудиофайлов..."
    if [ ! -d "$VOICE_DIR" ]; then
        echo "ℹ️ Папка не найдена: $VOICE_DIR"
        return
    fi

    FILES=$(find "$VOICE_DIR" -type f \( -name "*.mp3" -o -name "*.aiff" \) -print)
    if [ -z "$FILES" ]; then
        echo "✅ Временных аудиофайлов не найдено."
        return
    fi

    echo "Найдены файлы:"
    echo "$FILES"
    echo "------------------------------------------"
    read -p "Удалить их? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        find "$VOICE_DIR" -type f \( -name "*.mp3" -o -name "*.aiff" \) -delete
        echo "✅ Временные аудиофайлы удалены."
    else
        echo "ℹ️ Удаление отменено."
    fi
}

while true; do
    show_menu
    read choice
    case $choice in
        1)
            stop_bot
            if [ -f "$FULL_BOT_PATH" ]; then
                if [ -x "$PYTHON_BIN" ]; then
                    echo "🚀 Запуск: $FULL_BOT_PATH"
                    echo -e " СТАТУС: ${GREEN}🟢 РАБОТАЕТ (ИНТЕРАКТИВНЫЙ РЕЖИМ)${NC}"
                    
                    # Активация venv и проверка Ollama
                    source "$VENV_DIR/bin/activate"
                    
                    # Проверка наличия активной модели в .current_ai
                    CURRENT_MODEL=$(cat "$DATA_DIR/.current_ai" 2>/dev/null || echo "none")
                    if [ "$CURRENT_MODEL" != "none" ]; then
                        echo "🔍 Проверка модели Ollama: $CURRENT_MODEL"
                        if ! ollama list | grep -q "$CURRENT_MODEL"; then
                            echo -e "${YELLOW}⚠️ Модель $CURRENT_MODEL не найдена в Ollama. Скачиваю...${NC}"
                            ollama pull "$CURRENT_MODEL"
                        fi
                    fi
                    
                    # Запуск бота в фоновом режиме, записываем PID, затем ждем завершения
                    "$PYTHON_BIN" "$FULL_BOT_PATH" &
                    BPID=$!
                    echo "$BPID" > "$PID_FILE"
                    wait $BPID
                    RESULT=$?
                    rm -f "$PID_FILE"
                    if [ $RESULT -ne 0 ]; then
                        echo -e "${RED}❌ Бот завершился с кодом $RESULT${NC}"
                    else
                        echo "🛑 Бот остановлен пользователем."
                    fi
                else
                    echo -e "${RED}❌ ОШИБКА: Python не найден или не исполняем: $PYTHON_BIN${NC}"
                fi
            else
                echo -e "${RED}❌ ОШИБКА: Файл $FULL_BOT_PATH не найден${NC}"
            fi
            read -p "Нажми Enter для возврата..."
            ;;
        2)
            stop_bot
            if [ -f "$FULL_BOT_PATH" ]; then
                if [ -x "$PYTHON_BIN" ]; then
                    cd "$BOT_DIR" || exit 1
                    # ИСПРАВЛЕНО: 2>&1 перенаправляет stderr (логи Python) в файл
                    nohup caffeinate -isum "$PYTHON_BIN" "$FULL_BOT_PATH" > "$LOG_FILE" 2>&1 &
                    echo -e "${GREEN}✅ Бот запущен в фоне. Логи пишутся в $LOG_FILE${NC}"
                    echo $! > "$PID_FILE"
                else
                    echo -e "${RED}❌ ОШИБКА: Python не найден или не исполняем: $PYTHON_BIN${NC}"
                fi
            else 
                echo -e "${RED}❌ ОШИБКА: Файл не найден.${NC}"
            fi
            sleep 2
            ;;
        3)
            stop_bot
            read -p "Нажми Enter..."
            ;;
        4)
            if [ -f "$LOG_FILE" ] && [ -s "$LOG_FILE" ]; then
                echo "📜 Открываю логи... (для выхода нажмите q)"
                less -R +G "$LOG_FILE"
            else
                echo "📄 Лог-файл пуст или не создан. Запустите бота в фоне (пункт 2)."
                sleep 2
            fi
            ;;
        5)
            cat /dev/null > "$LOG_FILE"
            echo "Логи очищены."
            sleep 1
            ;;
        6)
            force_kill
            ;;
        7)
            ./RestoreConfig.command
            ;;
        8)
            cleanup_voice_files
            read -p "Нажми Enter..."
            ;;
        0)
            echo "Выход..."
            exit 0
            ;;
        *)
            echo "Неверный выбор."
            sleep 1
            ;;
    esac
done

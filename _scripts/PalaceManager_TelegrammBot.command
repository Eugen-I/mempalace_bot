#!/bin/bash

# 📂 Пути
DATA_DIR="$HOME/Documents/mempalace"
BOT_DIR="$HOME/Documents/mempalace_bot"
VENV_DIR="$DATA_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python3"
FULL_BOT_PATH="$BOT_DIR/main.py"
LOG_FILE="$BOT_DIR/nohup.out"
VOICE_DIR="$DATA_DIR/voice_replies"

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

    PID=$(pgrep -f "$FULL_BOT_PATH")

    if [ -z "$PID" ]; then
        echo -e " СТАТУС: ${RED}🔴 ОСТАНОВЛЕН${NC}"
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
    echo "🛑 Проверка и остановка..."
    PIDS=$(pgrep -f "$FULL_BOT_PATH")
    if [ ! -z "$PIDS" ]; then
        kill -9 $PIDS > /dev/null 2>&1
        sleep 1
        echo "✅ Процессы завершены."
    else
        echo "ℹ️ Активных процессов не найдено."
    fi
}

force_kill() {
    echo -e "${RED}💀 Выполняю полную очистку памяти от процессов...${NC}"
    PIDS=$(pgrep -f "$FULL_BOT_PATH")
    if [ ! -z "$PIDS" ]; then
        echo "Найдено: $PIDS"
        kill -9 $PIDS
        echo -e "${GREEN}✅ Все связанные процессы уничтожены.${NC}"
    else
        echo "Зависших процессов не обнаружено."
    fi
    sleep 2
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
                    
                    # ✅ Активация venv и проверка Ollama
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
                    
                    # Запуск бота
                    "$PYTHON_BIN" "$FULL_BOT_PATH"
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
                    # ✅ ИСПРАВЛЕНО: 2>&1 перенаправляет stderr (логи Python) в файл
                    nohup caffeinate -isum "$PYTHON_BIN" "$FULL_BOT_PATH" > "$LOG_FILE" 2>&1 &
                    echo -e "${GREEN}✅ Бот запущен в фоне. Логи пишутся в $LOG_FILE${NC}"
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
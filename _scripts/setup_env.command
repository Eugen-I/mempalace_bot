#!/bin/zsh
# ==============================================================================
# 🦾 MemPalace Configuration Manager
# Скрипт для безопасного управления .env файлом на macOS (M1/M2/M3)
# ==============================================================================

# Пути
ENV_DIR="$HOME/Documents/mempalace"
ENV_FILE="$ENV_DIR/.env"

# Цвета для интерфейса
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ------------------------------------------------------------------------------
# 🛠️ ФУНКЦИИ
# ------------------------------------------------------------------------------

# Создание структуры, если нет
ensure_env_file() {
    mkdir -p "$ENV_DIR"
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "# 🦾 MemPalace Configuration" > "$ENV_FILE"
        echo "# Создано: $(date)" >> "$ENV_FILE"
        echo "" >> "$ENV_FILE"
    fi
}

# Чтение значения (возвращает пустую строку, если нет)
get_env_value() {
    local key=$1
    grep "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | tr -d '\r'
}

# Безопасное обновление или добавление ключа
update_env_key() {
    local key=$1
    local value=$2
    
    # Экранирование спецсимволов для sed
    local escaped_value=$(printf '%s\n' "$value" | sed 's/[&/\]/\\&/g')
    
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        # macOS sed требует '' после -i
        sed -i '' "s|^${key}=.*|${key}=${escaped_value}|" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

# Маскировка ключа для отображения
mask_value() {
    local val=$1
    if [[ -z "$val" ]]; then
        echo "${RED}⦰ Не задан${NC}"
    elif [[ ${#val} -le 6 ]]; then
        echo "${YELLOW}****${NC}"
    else
        echo "${CYAN}${val:0:4}...${val: -4}${NC}"
    fi
}

# Закрытие окна терминала
close_terminal() {
    echo -e "\n${GREEN}✅ Конфигурация сохранена. Закрываю терминал...${NC}"
    sleep 1
    # AppleScript для закрытия текущего окна
    osascript -e 'tell application "Terminal" to close first window' 2>/dev/null
    exit 0
}

# ------------------------------------------------------------------------------
# 🚀 ОСНОВНОЙ ЦИКЛ
# ------------------------------------------------------------------------------

ensure_env_file

while true; do
    clear
    echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  🦾 MemPalace: Меню управления конфигурацией${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════════════════${NC}\n"
    
    # Получаем текущие значения
    TG_TOKEN=$(get_env_value "TELEGRAM_BOT_TOKEN")
    ADMIN_ID=$(get_env_value "ADMIN_ID")
    GEMINI_KEY=$(get_env_value "GEMINI_API_KEY")
    OPENAI_KEY=$(get_env_value "OPENAI_API_KEY")
    ALLOWED_USERS=$(get_env_value "ALLOWED_USERS")
    TTS_ENGINE=$(get_env_value "TTS_ENGINE")
    
    # Меню
    echo -e " 1. TELEGRAM_BOT_TOKEN  $(mask_value "$TG_TOKEN")"
    echo -e " 2. ADMIN_ID            ${YELLOW}${ADMIN_ID:-0}${NC}"
    echo -e " 3. GEMINI_API_KEY      $(mask_value "$GEMINI_KEY")"
    echo -e " 4. OPENAI_API_KEY      $(mask_value "$OPENAI_KEY")"
    echo -e " 5. TTS_ENGINE          ${YELLOW}${TTS_ENGINE:-system}${NC} (system/openai/elevenlabs)"
    echo -e " 6. MEMPALACE_DATA_DIR     ${YELLOW}${MEMPALACE_DATA_DIR:-$HOME/Documents/mempalace}${NC}"
    echo -e " 7. ALLOWED_USERS       ${YELLOW}${ALLOWED_USERS:-0}${NC} (ID через запятую)"
    echo ""
    echo -e " ${RED}Q${NC}. Выход и закрытие окна"
    echo -e "${CYAN}──────────────────────────────────────────────────────────────${NC}"
    echo -ne "\n${GREEN}➤ Выберите пункт: ${NC}"
    
    read -r choice
    
    case "$choice" in
        1)
            echo -ne "\n🤖 Введите TELEGRAM_BOT_TOKEN: "
            read -r val
            if [[ -n "$val" ]]; then
                update_env_key "TELEGRAM_BOT_TOKEN" "$val"
                echo -e "${GREEN}✅ Telegram токен обновлен.${NC}"
            fi
            ;;
        2)
            echo -ne "\n👤 Введите ADMIN_ID (число): "
            read -r val
            if [[ "$val" =~ ^[0-9]+$ ]]; then
                update_env_key "ADMIN_ID" "$val"
                echo -e "${GREEN}✅ Admin ID обновлен.${NC}"
            else
                echo -e "${RED}❌ Ошибка: ID должен быть числом.${NC}"
            fi
            ;;
        3)
            echo -ne "\n✨ Введите GEMINI_API_KEY: "
            read -r val
            if [[ -n "$val" ]]; then
                update_env_key "GEMINI_API_KEY" "$val"
                echo -e "${GREEN}✅ Gemini ключ обновлен.${NC}"
            fi
            ;;
        4)
            echo -ne "\n🔑 Введите OPENAI_API_KEY: "
            read -r val
            if [[ -n "$val" ]]; then
                update_env_key "OPENAI_API_KEY" "$val"
                echo -e "${GREEN}✅ OpenAI ключ обновлен.${NC}"
            fi
            ;;
        5)
            echo -e "\n🔊 Выберите TTS_ENGINE:"
            echo "   1) system (macOS say)"
            echo "   2) openai"
            echo "   3) elevenlabs"
            echo -ne "   Выбор (1-3): "
            read -r tts_choice
            case "$tts_choice" in
                1) update_env_key "TTS_ENGINE" "system" ;;
                2) update_env_key "TTS_ENGINE" "openai" ;;
                3) update_env_key "TTS_ENGINE" "elevenlabs" ;;
                *) echo -e "${RED}❌ Неверный выбор.${NC}" ;;
            esac
            ;;
	6)
    	    echo -ne "\n📂 Введите путь к MEMPALACE_DATA_DIR: "
            read -r val
            if [[ -n "$val" ]]; then
            update_env_key "MEMPALACE_DATA_DIR" "$val"
            echo -e "${GREEN}✅ Путь обновлен.${NC}"
            fi
            ;;
        [Qq])
            close_terminal
            ;;
	7)
    	    echo -ne "\n👥 Введите ALLOWED_USERS (ID Telegram через запятую): "
    	    read -r val
    	    if [[ -n "$val" ]]; then
            update_env_key "ALLOWED_USERS" "$val"
            echo -e "${GREEN}✅ Список пользователей обновлен.${NC}"
    	    fi
    	    ;;
        *)
            echo -e "\n${RED}⚠️ Неверный ввод. Попробуйте снова.${NC}"
            sleep 1
            ;;
    esac
    
    echo -e "\n${YELLOW}⏳ Нажмите Enter для продолжения...${NC}"
    read -r
done

#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Без цвета

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Установка HA Telegram Bot для Linux${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Переход в директорию скрипта
cd "$(dirname "$0")"

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ОШИБКА] Python3 не найден!${NC}"
    echo -e "${YELLOW}Установите Python3:${NC}"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  CentOS/Fedora: sudo dnf install python3 python3-pip"
    echo "  Arch:          sudo pacman -S python python-pip"
    exit 1
fi

# Проверка версии Python
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${YELLOW}[ПРЕДУПРЕЖДЕНИЕ] Требуется Python 3.11+, у вас $PYTHON_VERSION${NC}"
    echo -e "${YELLOW}Бот может работать некорректно${NC}"
    read -p "Продолжить установку? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Создание виртуального окружения
if [ ! -d "venv" ]; then
    echo -e "${BLUE}[INFO] Создаю виртуальное окружение...${NC}"
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ОШИБКА] Не удалось создать venv${NC}"
        exit 1
    fi
fi

# Активация окружения
echo -e "${BLUE}[INFO] Активирую виртуальное окружение...${NC}"
source venv/bin/activate

# Обновление pip
echo -e "${BLUE}[INFO] Обновляю pip...${NC}"
python -m pip install --upgrade pip --quiet

# Установка зависимостей
echo -e "${BLUE}[INFO] Устанавливаю зависимости...${NC}"
pip install --upgrade "python-telegram-bot>=21" httpx pydantic python-dotenv --quiet

if [ $? -ne 0 ]; then
    echo -e "${RED}[ОШИБКА] Не удалось установить зависимости${NC}"
    exit 1
fi

# Создание .env, если его нет
if [ ! -f ".env" ]; then
    echo -e "${BLUE}[INFO] Создаю шаблон .env файла...${NC}"
    cat > .env << 'EOF'
# Telegram bot token (от @BotFather)
TELEGRAM_BOT_TOKEN=

# Home Assistant settings
HA_BASE_URL=http://localhost:8123
HA_ACCESS_TOKEN=

# Ваш Telegram ID (защита от чужих пользователей)
ALLOWED_USER_ID=

# Язык по умолчанию: ru или en
DEFAULT_LANG=ru
EOF
    
    echo
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  ВАЖНО! Откройте файл .env и заполните его!${NC}"
    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}Команда: nano .env${NC}"
fi

# Создание папки для логов
mkdir -p logs

# Установка прав выполнения на скрипты
echo -e "${BLUE}[INFO] Устанавливаю права выполнения на скрипты...${NC}"
chmod +x install.sh start.sh start_log.sh stop.sh uninstall.sh 2>/dev/null

echo
echo -e "${GREEN}✅ Установка завершена!${NC}"
echo
echo -e "${BLUE}Следующие шаги:${NC}"
echo "  1. Отредактируйте файл .env: nano .env"
echo "  2. Запустите бота: ./start.sh"
echo
echo -e "${YELLOW}Для автозапуска через systemd выполните:${NC}"
echo "  sudo ./install_service.sh"
echo
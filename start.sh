#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Запуск HA Telegram Bot${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Переход в директорию скрипта
cd "$(dirname "$0")"

# Проверка виртуального окружения
if [ ! -d "venv" ]; then
    echo -e "${RED}[ОШИБКА] Виртуальное окружение не найдено!${NC}"
    echo -e "${YELLOW}Запустите сначала: ./install.sh${NC}"
    exit 1
fi

# Проверка .env файла
if [ ! -f ".env" ]; then
    echo -e "${RED}[ОШИБКА] Файл .env не найден!${NC}"
    echo -e "${YELLOW}Создайте файл .env с настройками${NC}"
    exit 1
fi

# Проверка заполнения .env
if ! grep -q "TELEGRAM_BOT_TOKEN=." .env || ! grep -q "HA_ACCESS_TOKEN=." .env; then
    echo -e "${RED}[ОШИБКА] Не заполнены обязательные параметры в .env!${NC}"
    echo -e "${YELLOW}Откройте .env и укажите:${NC}"
    echo "  - TELEGRAM_BOT_TOKEN"
    echo "  - HA_ACCESS_TOKEN"
    exit 1
fi

# Предупреждение, если не задан список разрешённых пользователей
if ! grep -qE '^(ALLOWED_USER_IDS|ALLOWED_USER_ID)=.' .env; then
    if grep -qE '^ALLOW_ALL_USERS=1' .env; then
        echo -e "${YELLOW}[WARNING] ALLOWED_USER_IDS не задан, ALLOW_ALL_USERS=1 — доступ к боту разрешён ВСЕМ!${NC}"
    else
        echo -e "${RED}[ОШИБКА] Не заданы ALLOWED_USER_IDS — бот не запустится!${NC}"
        echo -e "${YELLOW}Укажите Telegram ID в .env или явно разрешите открытый доступ: ALLOW_ALL_USERS=1${NC}"
        exit 1
    fi
    echo
fi

# Активация окружения
source venv/bin/activate

# Создание папок для логов и данных
mkdir -p logs data

echo -e "${GREEN}[INFO] Запуск бота...${NC}"
echo -e "${YELLOW}[INFO] Для остановки нажмите Ctrl+C${NC}"
echo

# Запуск бота
python bot.py

# Если бот упал
echo
echo -e "${YELLOW}[INFO] Бот остановлен${NC}"
read -p "Нажмите Enter для выхода..."

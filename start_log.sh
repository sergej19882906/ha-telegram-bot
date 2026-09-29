#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Запуск HA Telegram Bot (с логированием)${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Переход в директорию скрипта
cd "$(dirname "$0")"

# Проверки
if [ ! -d "venv" ]; then
    echo -e "${RED}[ОШИБКА] Виртуальное окружение не найдено!${NC}"
    echo -e "${YELLOW}Запустите сначала: ./install.sh${NC}"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo -e "${RED}[ОШИБКА] Файл .env не найден!${NC}"
    exit 1
fi

# Активация окружения
source venv/bin/activate

# Создание папок для логов и данных
mkdir -p logs data

# Имя лог-файла с датой
LOGFILE="logs/bot_$(date +%Y%m%d_%H%M%S).log"

echo -e "${GREEN}[INFO] Запуск бота...${NC}"
echo -e "${BLUE}[INFO] Логи пишутся в: $LOGFILE${NC}"
echo -e "${YELLOW}[INFO] Для остановки нажмите Ctrl+C${NC}"
echo

# Запуск с записью в лог и выводом в консоль
python bot.py 2>&1 | tee "$LOGFILE"

echo
echo -e "${YELLOW}[INFO] Бот остановлен (таймеры сохранены в data/timers.json)${NC}"
echo -e "${BLUE}[INFO] Полный лог сохранён в: $LOGFILE${NC}"
read -p "Нажмите Enter для выхода..."

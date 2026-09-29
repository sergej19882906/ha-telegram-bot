#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${RED}========================================${NC}"
echo -e "${RED}  Удаление HA Telegram Bot${NC}"
echo -e "${RED}========================================${NC}"
echo

cd "$(dirname "$0")"

echo -e "${YELLOW}[ВНИМАНИЕ] Это действие удалит:${NC}"
echo "  - Виртуальное окружение (venv/)"
echo "  - Логи (logs/)"
echo "  - Папку данных (data/): языки пользователей и активные таймеры"
echo "  - Systemd-службу (если установлена)"
echo
echo -e "${RED}Файлы bot.py, .env, скрипты и документация будут сохранены${NC}"
echo

read -p "Вы уверены? (y/N) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Остановка бота, если запущен (чтобы успели сохраниться таймеры)
    if pgrep -f "python.*bot.py" > /dev/null; then
        echo -e "${BLUE}[INFO] Останавливаю бота...${NC}"
        ./stop.sh
        sleep 1
    fi

    # Удаление systemd службы — делегируем отдельному скрипту
    if [ -f "/etc/systemd/system/ha-telegram-bot.service" ]; then
        echo -e "${BLUE}[INFO] Удаляю systemd службу...${NC}"
        SKIP_CONFIRM=1 ./uninstall_service.sh
    fi

    # Удаление файлов
    echo -e "${BLUE}[INFO] Удаляю файлы...${NC}"
    rm -rf venv/
    rm -rf logs/
    rm -rf data/
    rm -f user_langs.json timers.json

    echo
    echo -e "${GREEN}✅ Удаление завершено${NC}"
    echo -e "${YELLOW}Для полного удаления проекта выполните: cd .. && rm -rf ha-telegram-bot${NC}"
else
    echo -e "${BLUE}[INFO] Удаление отменено${NC}"
fi

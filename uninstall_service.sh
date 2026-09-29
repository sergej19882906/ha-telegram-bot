#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${RED}========================================${NC}"
echo -e "${RED}  Удаление systemd службы HA Telegram Bot${NC}"
echo -e "${RED}========================================${NC}"
echo

# Проверка root прав
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ОШИБКА] Этот скрипт требует прав root${NC}"
    echo -e "${YELLOW}Запустите: sudo ./uninstall_service.sh${NC}"
    exit 1
fi

SERVICE_NAME="ha-telegram-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${YELLOW}[INFO] Служба $SERVICE_NAME не установлена — удалять нечего${NC}"
    exit 0
fi

echo -e "${YELLOW}Будет удалена служба: $SERVICE_NAME${NC}"
echo -e "${BLUE}Файлы проекта (bot.py, .env, venv) НЕ затрагиваются${NC}"
echo

if [ "$SKIP_CONFIRM" != "1" ]; then
    read -p "Продолжить? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}[INFO] Отменено${NC}"
        exit 0
    fi
fi

echo -e "${BLUE}[INFO] Останавливаю службу (таймеры сохранятся в data/timers.json)...${NC}"
systemctl stop "$SERVICE_NAME" 2>/dev/null

# Даём боту до 10 секунд на штатное завершение
for i in $(seq 1 10); do
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        break
    fi
    sleep 1
done

echo -e "${BLUE}[INFO] Отключаю автозапуск...${NC}"
systemctl disable "$SERVICE_NAME" 2>/dev/null

echo -e "${BLUE}[INFO] Удаляю файл службы...${NC}"
rm -f "$SERVICE_FILE"

echo -e "${BLUE}[INFO] Перезагружаю systemd...${NC}"
systemctl daemon-reload

# Финальная проверка
if systemctl cat "$SERVICE_NAME" &>/dev/null; then
    echo -e "${RED}[ОШИБКА] Служба не удалена полностью${NC}"
    exit 1
fi

echo
echo -e "${GREEN}✅ Служба $SERVICE_NAME удалена${NC}"
echo -e "${YELLOW}Бот можно запускать вручную: ./start.sh${NC}"

#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Установка systemd службы${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Проверка root прав
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ОШИБКА] Этот скрипт требует прав root${NC}"
    echo -e "${YELLOW}Запустите: sudo ./install_service.sh${NC}"
    exit 1
fi

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)
CURRENT_USER=$SUDO_USER

if [ -z "$CURRENT_USER" ]; then
    echo -e "${RED}[ОШИБКА] Не удалось определить пользователя${NC}"
    exit 1
fi

echo -e "${BLUE}[INFO] Директория проекта: $PROJECT_DIR${NC}"
echo -e "${BLUE}[INFO] Пользователь: $CURRENT_USER${NC}"
echo

# Создание файла службы
SERVICE_FILE="/etc/systemd/system/ha-telegram-bot.service"

echo -e "${BLUE}[INFO] Создаю файл службы...${NC}"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=HA Telegram Bot
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Установка прав
chmod 644 "$SERVICE_FILE"

# Перезагрузка systemd
echo -e "${BLUE}[INFO] Перезагружаю systemd...${NC}"
systemctl daemon-reload

# Включение автозапуска
echo -e "${BLUE}[INFO] Включаю автозапуск...${NC}"
systemctl enable ha-telegram-bot

# Запуск службы
echo -e "${BLUE}[INFO] Запускаю службу...${NC}"
systemctl start ha-telegram-bot

# Проверка статуса
sleep 2
if systemctl is-active --quiet ha-telegram-bot; then
    echo
    echo -e "${GREEN}✅ Служба успешно установлена и запущена!${NC}"
    echo
    echo -e "${BLUE}Полезные команды:${NC}"
    echo "  sudo systemctl status ha-telegram-bot    # Статус"
    echo "  sudo systemctl stop ha-telegram-bot      # Остановить"
    echo "  sudo systemctl restart ha-telegram-bot   # Перезапустить"
    echo "  sudo journalctl -u ha-telegram-bot -f    # Логи в реальном времени"
else
    echo
    echo -e "${RED}[ОШИБКА] Служба не запустилась${NC}"
    echo -e "${YELLOW}Проверьте логи: sudo journalctl -u ha-telegram-bot -n 50${NC}"
fi
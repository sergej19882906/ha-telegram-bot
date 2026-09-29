#!/bin/bash

# Обновление HA Telegram Bot на сервере:
#   git pull -> зависимости -> перезапуск службы -> хвост лога
#
# Использование:
#   ./deploy.sh            # полное обновление (код + зависимости + рестарт)
#   ./deploy.sh --no-deps  # только код и рестарт (быстрее)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Обновление HA Telegram Bot${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Переход в директорию скрипта
cd "$(dirname "$0")"

# --- Проверка, что это git-репозиторий ---
if [ ! -d ".git" ]; then
    echo -e "${RED}[ОШИБКА] Это не git-репозиторий. deploy.sh работает только с установкой через git clone.${NC}"
    exit 1
fi

# --- Обновление кода ---
echo -e "${BLUE}[INFO] Получаю обновления из git...${NC}"
if ! git pull; then
    echo
    echo -e "${RED}[ОШИБКА] git pull не выполнен.${NC}"
    echo -e "${YELLOW}Возможные причины: локальные изменения (git status), конфликты или нет сети.${NC}"
    exit 1
fi

# --- Зависимости ---
if [ "$1" != "--no-deps" ]; then
    if [ -d "venv" ]; then
        echo -e "${BLUE}[INFO] Обновляю зависимости...${NC}"
        # shellcheck disable=SC1091
        source venv/bin/activate
        python -m pip install --upgrade -r requirements.txt --quiet \
            || echo -e "${YELLOW}[WARNING] Не удалось обновить зависимости (продолжаю с текущими)${NC}"
    else
        echo -e "${YELLOW}[WARNING] venv не найден — пропускаю обновление зависимостей${NC}"
    fi
else
    echo -e "${BLUE}[INFO] Пропускаю зависимости (--no-deps)${NC}"
fi

# --- Перезапуск ---
if ! command -v systemctl &> /dev/null; then
    echo -e "${YELLOW}[WARNING] systemctl не найден — перезапустите бота вручную: ./stop.sh && ./start.sh${NC}"
    exit 0
fi

SUDO=""
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
fi

if systemctl list-unit-files 2>/dev/null | grep -q "^ha-telegram-bot.service"; then
    echo -e "${BLUE}[INFO] Перезапускаю службу ha-telegram-bot...${NC}"
    $SUDO systemctl restart ha-telegram-bot
    sleep 2

    if systemctl is-active --quiet ha-telegram-bot; then
        echo -e "${GREEN}✅ Служба перезапущена и работает${NC}"
    else
        echo -e "${RED}[ОШИБКА] Служба не запустилась. Логи ниже.${NC}"
        echo
        $SUDO journalctl -u ha-telegram-bot -n 30 --no-pager
        exit 1
    fi

    echo
    echo -e "${BLUE}=== Последние строки лога ===${NC}"
    $SUDO journalctl -u ha-telegram-bot -n 15 --no-pager
else
    echo -e "${YELLOW}[WARNING] Служба ha-telegram-bot не установлена.${NC}"
    echo -e "${YELLOW}Запустите бота вручную (./start.sh) или установите службу: sudo ./install_service.sh${NC}"
fi

echo
echo -e "${GREEN}✅ Готово${NC}"

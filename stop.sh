#!/bin/bash

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Остановка HA Telegram Bot${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Поиск процессов бота
PIDS=$(pgrep -f "venv/bin/python.*bot.py" 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}[INFO] Бот не запущен${NC}"
    exit 0
fi

echo -e "${BLUE}[INFO] Найдены процессы:${NC}"
echo "$PIDS"
echo
echo -e "${BLUE}[INFO] Останавливаю (активные таймеры сохранятся)...${NC}"

# Мягкая остановка (SIGTERM) — бот успеет сохранить таймеры в data/timers.json
kill $PIDS 2>/dev/null

# Ожидание завершения (до 10 секунд)
for i in $(seq 1 10); do
    if ! pgrep -f "venv/bin/python.*bot.py" > /dev/null; then
        break
    fi
    sleep 1
done

# Принудительная остановка, если не завершился
if pgrep -f "venv/bin/python.*bot.py" > /dev/null; then
    echo -e "${YELLOW}[WARNING] Процессы не завершились за 10 секунд, принудительная остановка...${NC}"
    pkill -9 -f "venv/bin/python.*bot.py"
    sleep 1
fi

# Финальная проверка
if pgrep -f "venv/bin/python.*bot.py" > /dev/null; then
    echo -e "${RED}[ОШИБКА] Не удалось остановить бота${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Бот успешно остановлен (таймеры сохранены в data/timers.json)${NC}"
fi

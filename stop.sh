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
PIDS=$(pgrep -f "python.*bot.py" 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo -e "${YELLOW}[INFO] Бот не запущен${NC}"
    exit 0
fi

echo -e "${BLUE}[INFO] Найдены процессы:${NC}"
echo "$PIDS"
echo

# Остановка процессов
echo -e "${BLUE}[INFO] Останавливаю процессы...${NC}"
kill $PIDS 2>/dev/null

# Ожидание завершения
sleep 2

# Проверка
if pgrep -f "python.*bot.py" > /dev/null; then
    echo -e "${YELLOW}[WARNING] Процессы не завершились, принудительная остановка...${NC}"
    pkill -9 -f "python.*bot.py"
    sleep 1
fi

# Финальная проверка
if pgrep -f "python.*bot.py" > /dev/null; then
    echo -e "${RED}[ОШИБКА] Не удалось остановить бота${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Бот успешно остановлен${NC}"
fi
FROM python:3.11-slim

# Версия бота берётся из hamqttbot/config.py и передаётся сборкой:
#   --build-arg BOT_VERSION=$(grep -oP 'BOT_VERSION\s*=\s*"\K[^"]+' hamqttbot/config.py)
ARG BOT_VERSION=3.0.1

LABEL maintainer="sergej19882906"
LABEL description="Telegram bot for Home Assistant with notifications receiver"
LABEL version="${BOT_VERSION}"
LABEL org.label-schema.vcs-url="https://github.com/sergej19882906/ha-telegram-bot"
LABEL com.centurylinklabs.watchtower.enable="true"
LABEL com.centurylinklabs.watchtower.scope="ha-telegram-bot"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data

WORKDIR /app

# Точные версии зависимостей — сборка воспроизводима (requirements.lock).
# Диапазоны для разработки остаются в requirements.txt.
COPY requirements.lock .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.lock

RUN groupadd -r botuser && useradd -r -g botuser -d /app -s /sbin/nologin botuser

COPY bot.py .
COPY hamqttbot/ hamqttbot/
COPY healthcheck.py .

RUN mkdir -p /app/data /app/logs && \
    chown -R botuser:botuser /app

USER botuser

# Персистентные данные: языки пользователей и активные таймеры
VOLUME ["/app/data"]

# Если приёмник уведомлений включён (NOTIFY_PORT > 0) — пробуем HTTP-запрос
# к /notify: ответ любого вида значит, что процесс жив и event loop не завис.
# Иначе — проверка, что главный процесс (PID 1) жив.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "healthcheck.py"]

# Порт приёмника задаётся через NOTIFY_PORT (по умолчанию выключен),
# поэтому EXPOSE намеренно не фиксируем — порты пробрасывайте в compose/run.

CMD ["python", "bot.py"]

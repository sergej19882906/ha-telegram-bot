FROM python:3.11-slim

LABEL maintainer="sergej19882906"
LABEL description="Telegram bot for Home Assistant with notifications receiver"
LABEL version="2.1.5"
LABEL org.label-schema.vcs-url="https://github.com/sergej19882906/ha-telegram-bot"
LABEL com.centurylinklabs.watchtower.enable="true"
LABEL com.centurylinklabs.watchtower.scope="ha-telegram-bot"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN groupadd -r botuser && useradd -r -g botuser -d /app -s /sbin/nologin botuser

COPY bot.py .

RUN mkdir -p /app/data /app/logs && \
    chown -R botuser:botuser /app

USER botuser

# Персистентные данные: языки пользователей и активные таймеры
VOLUME ["/app/data"]

# Проверка жизнеспособности процесса: python работает как PID 1 (exec-форма CMD),
# поэтому os.kill(1, 0) бросит OSError, если главный процесс мёртв или завис
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os; os.kill(1, 0)"]

# Порт приёмника задаётся через NOTIFY_PORT (по умолчанию выключен),
# поэтому EXPOSE намеренно не фиксируем — порты пробрасывайте в compose/run.

CMD ["python", "bot.py"]

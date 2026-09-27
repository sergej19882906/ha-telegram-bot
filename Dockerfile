FROM python:3.11-slim

LABEL maintainer="sergej19882906"
LABEL description="Telegram bot for Home Assistant"
LABEL version="1.0"
LABEL org.label-schema.vcs-url="https://github.com/sergej19882906/ha-telegram-bot"
LABEL com.centurylinklabs.watchtower.enable="true"
LABEL com.centurylinklabs.watchtower.scope="ha-telegram-bot"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

EXPOSE 8080

CMD ["python", "bot.py"]
# 🐳 Инструкция по запуску HA Telegram Bot в Docker

Запуск бота в контейнере Docker — изолированно и с автоматическим перезапуском.

---

## 📋 Содержание

- [Требования](#-требования)
- [Готовый образ из GHCR](#-готовый-образ-из-github-container-registry-без-сборки)
- [Вариант 1: docker run](#-вариант-1-docker-run-сборка-из-исходников)
- [Вариант 2: docker-compose](#-вариант-2-docker-compose-рекомендуется)
- [Сборка под ARM (Raspberry Pi, Orange Pi)](#-сборка-под-arm-raspberry-pi-orange-pi)
- [Настройка .env](#-настройка-env)
- [Уведомления из Home Assistant](#-уведомления-из-home-assistant)
- [Логи и мониторинг](#-логи-и-мониторинг)
- [Обновление](#-обновление)
- [Решение проблем](#-решение-проблем)

---

## 📦 Требования

- Docker 20.10+ и Docker Compose v2 (для варианта с compose)
- Доступ к Docker: пользователь в группе `docker` или `sudo`

Проверка установки:

```bash
docker --version
docker compose version
```

---

## ⚙️ Настройка .env

Перед запуском создайте файл `.env` рядом с `Dockerfile`:

```env
# Telegram bot token (от @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Home Assistant settings
HA_BASE_URL=http://192.168.1.100:8123
HA_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Разрешённые пользователи — Telegram ID через запятую
# Бот НЕ СТАРТУЕТ без списка! Открытый доступ всем — только через ALLOW_ALL_USERS=1
ALLOWED_USER_IDS=123456789

# Язык по умолчанию: ru или en
DEFAULT_LANG=ru

# --- Приёмник уведомлений из HA ---
NOTIFY_PORT=8099
NOTIFY_HOST=0.0.0.0
NOTIFY_TOKEN=длинная_случайная_строка
```

> 💡 **Получение токенов и ID** — см. [README.md](README.md), раздел «Настройка».

---

## 📥 Готовый образ из GitHub Container Registry (без сборки)

После каждого релиза образ публикуется автоматически в GHCR:

```bash
docker pull ghcr.io/sergej19882906/ha-telegram-bot:latest

docker run -d \
  --name ha-telegram-bot \
  --restart unless-stopped \
  --env-file .env \
  -v ha_bot_data:/app/data \
  -p 8099:8099 \
  ghcr.io/sergej19882906/ha-telegram-bot:latest
```

> 💡 Образ в GHCR публичный — `docker login` не требуется. Тег `latest` соответствует последнему релизу; конкретную версию можно взять по тегу, например `:2.1`.

---

## 🚀 Вариант 1: docker run (сборка из исходников)

### Шаг 1: Соберите образ

```bash
git clone https://github.com/sergej19882906/ha-telegram-bot.git
cd ha-telegram-bot
docker build -t ha-telegram-bot .
```

### Шаг 2: Запустите контейнер

```bash
docker run -d \
  --name ha-telegram-bot \
  --restart unless-stopped \
  --env-file .env \
  -v ha_bot_data:/app/data \
  -p 8099:8099 \
  ha-telegram-bot
```

Флаги:

| Флаг | Назначение |
|---|---|
| `-d` | фоновый режим |
| `--restart unless-stopped` | автоперезапуск при сбоях и после перезагрузки хоста |
| `--env-file .env` | переменные окружения из файла |
| `-v ha_bot_data:/app/data` | том с данными (языки пользователей, таймеры) |
| `-p 8099:8099` | порт приёмника уведомлений (не указывайте, если `NOTIFY_PORT=0`) |

### Шаг 3: Проверьте, что бот запустился

```bash
docker logs -f ha-telegram-bot
```

В логе должно быть: `Бот запущен, загружаю список устройств...` и `Загружено устройств: N`.

---

## 🚀 Вариант 2: docker-compose (рекомендуется)

В репозитории уже есть готовый `docker-compose.yml` (сборка из исходников):

```yaml
services:
  ha-telegram-bot:
    build: .
    image: ha-telegram-bot:latest
    container_name: ha-telegram-bot
    restart: unless-stopped
    env_file: .env
    volumes:
      - ha_bot_data:/app/data
    ports:
      - "8099:8099"   # приёмник уведомлений; удалите строку, если NOTIFY_PORT=0

volumes:
  ha_bot_data:
```

> 💡 Чтобы использовать готовый образ вместо сборки, замените `build: .` на
> `image: ghcr.io/sergej19882906/ha-telegram-bot:latest`.

Запуск и управление:

```bash
docker compose up -d          # сборка + запуск
docker compose logs -f        # логи в реальном времени
docker compose restart        # перезапуск
docker compose down           # остановка
docker compose up -d --build  # пересборка после обновления кода
```

---

## 🍓 Сборка под ARM (Raspberry Pi, Orange Pi)

Базовый образ `python:3.11-slim` мультиархитектурный — бот работает на
`linux/amd64` и `linux/arm64` (Raspberry Pi 3/4/5, Orange Pi и другие
ARM-платы). Зависимости чисто Python — ничего нативно компилировать не нужно.

### Сборка для конкретной платформы (например, прямо на Raspberry Pi)

```bash
docker build -t ha-telegram-bot .
```

На ARM-плате docker сам возьмёт ARM-слой базового образа — отдельных
флагов не требуется.

### Сборка для обеих платформ сразу (buildx)

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ha-telegram-bot:latest .
```

Чтобы собрать **и опубликовать** multi-arch образ в registry:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/<user>/ha-telegram-bot:latest \
  --push .
```

Готовый manifest поддерживает обе платформы: ARM-устройство сделает
`docker pull` и автоматически вытянет нужный слой — выбирать платформу
вручную не нужно.

> 💡 В репозитории есть `./deploy.sh --docker` — он обновляет код и собирает
> образ сразу для обеих платформ; с переменной `DOCKER_REGISTRY=user/repo`
> образ ещё и публикуется.

---

## 🚨 Уведомления из Home Assistant

Когда контейнер запущен с `-p 8099:8099`, в `configuration.yaml` HA добавьте:

```yaml
rest_command:
  telegram_notify:
    url: "http://<IP_хоста_с_Docker>:8099/notify"
    method: POST
    headers:
      Authorization: "Bearer <NOTIFY_TOKEN_из_.env>"
    content_type: application/json
    # tojson экранирует кавычки и переводы строк в тексте сообщения
    payload: '{"text": {{ message | tojson }}}'
```

Если Home Assistant тоже работает в Docker на том же хосте, используйте IP хоста или `host.docker.internal` (Docker Desktop) — адрес `localhost` внутри контейнера HA указывает на сам контейнер HA.

Подробности и примеры автоматизаций — в [README.md](README.md), раздел «Уведомления из Home Assistant».

---

## 📊 Логи и мониторинг

```bash
# Логи в реальном времени
docker logs -f ha-telegram-bot

# Последние 100 строк
docker logs --tail 100 ha-telegram-bot

# Статус контейнера
docker ps -f name=ha-telegram-bot
docker inspect -f '{{.State.Status}} {{.State.RestartCount}}' ha-telegram-bot
```

В логах видно каждый запрос: `Запрос user=123456789: /on свет`.

---

## 🔄 Обновление

**Если используете готовый образ из GHCR:**
```bash
docker pull ghcr.io/sergej19882906/ha-telegram-bot:latest
docker stop ha-telegram-bot && docker rm ha-telegram-bot
# и запустите заново той же командой docker run (см. выше)
```

**Если собираете из исходников:**
```bash
cd ha-telegram-bot
git pull

# docker compose
docker compose up -d --build

# или docker run
docker stop ha-telegram-bot
docker rm ha-telegram-bot
docker build -t ha-telegram-bot .
docker run -d --name ha-telegram-bot --restart unless-stopped \
  --env-file .env -v ha_bot_data:/app/data -p 8099:8099 ha-telegram-bot
```

> ✅ Данные (языки пользователей, активные таймеры) хранятся в томе `ha_bot_data` и переживают пересоздание контейнера.

---

## 🔧 Решение проблем

| Проблема | Решение |
|---|---|
| Контейнер перезапускается в цикле | `docker logs ha-telegram-bot` — обычно не заполнен `.env` или неверный токен |
| `ModuleNotFoundError: aiohttp` | Образ собран старым Dockerfile: пересоберите `docker build --no-cache -t ha-telegram-bot .` |
| Бот молчит | Ваш ID не в `ALLOWED_USER_IDS`. Проверьте через @userinfobot, обновите `.env`, `docker compose up -d` |
| Ошибка `401` от HA в логах | Просроченный `HA_ACCESS_TOKEN` — создайте новый long-lived token |
| HA не достукивается до `:8099` | Проверьте `-p 8099:8099`, firewall хоста и `NOTIFY_TOKEN` |
| «Данные кнопки устарели» в боте | Кнопки живут до перезапуска бота — отправьте `/menu` заново |
| `Error response from daemon: conflict` | Контейнер с таким именем уже есть: `docker rm -f ha-telegram-bot` |

---

## ✅ Итог

Контейнер с ботом обеспечивает:

- ✅ Изоляцию от системы (Python, зависимости — всё внутри образа)
- ✅ Автоперезапуск через `--restart unless-stopped`
- ✅ Персистентность данных через том `ha_bot_data`
- ✅ Healthcheck и удобное обновление

**Приятного использования! 🏠✨**

---

*Документация актуальна на сентябрь 2026 года. Версия бота: 2.1*

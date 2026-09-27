# 🐳 HA Telegram Bot — Docker Deployment

Полное руководство по развёртыванию Telegram-бота для Home Assistant в Docker-контейнере с автоматическим обновлением через Watchtower.

![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)
![Watchtower](https://img.shields.io/badge/Watchtower-AutoUpdate-green)
![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Compatible-blue?logo=home-assistant)

## 📋 Содержание

- [Преимущества Docker](#-преимущества-docker)
- [Требования](#-требования)
- [Быстрый старт](#-быстрый-старт)
- [Подробная настройка](#-подробная-настройка)
- [Структура проекта](#-структура-проекта)
- [Управление контейнерами](#-управление-контейнерами)
- [Watchtower — автообновление](#-watchtower--автообновление)
- [Мониторинг и логи](#-мониторинг-и-логи)
- [Обновление бота](#-обновление-бота)
- [Решение проблем](#-решение-проблем)
- [Безопасность](#-безопасность)

---

## ✨ Преимущества Docker

| Аспект | Без Docker | С Docker |
|--------|------------|----------|
| **Установка** | Python, venv, зависимости | Только Docker |
| **Изоляция** | Зависимости в системе | Полная изоляция |
| **Переносимость** | Настройка на каждой ОС | Работает везде одинаково |
| **Обновление** | Вручную | Автоматически через Watchtower |
| **Автозапуск** | systemd / Task Scheduler | Встроено в Docker |
| **Откат** | Сложно | Один образ — один клик |
| **Ресурсы** | Не ограничены | Можно ограничить CPU/RAM |
| **Логи** | Файлы на диске | Централизованно через Docker |

---

## 📦 Требования

### Обязательные
- **Docker Engine** 20.10 или новее
- **Docker Compose** v2 (обычно включён в Docker Desktop)
- **Доступ в интернет** для загрузки образов и связи с Telegram API

### Проверка установки

```bash
# Проверка Docker
docker --version
# Должно быть: Docker version 20.10.x или новее

# Проверка Docker Compose
docker compose version
# Должно быть: Docker Compose version v2.x.x
```

### Установка Docker (если не установлен)

**Ubuntu/Debian:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Перелогиньтесь для применения прав
```

**Windows:**
1. Скачайте [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Установите и запустите
3. В настройках включите "Use Docker Compose V2"

**macOS:**
```bash
brew install --cask docker
```

---

## 🚀 Быстрый старт

Три команды для запуска бота:

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/sergej19882906/ha-telegram-bot.git
cd ha-telegram-bot

# 2. Создайте .env файл и заполните его
cp .env.example .env
nano .env

# 3. Запустите
docker compose up -d
```

Готово! Бот работает в фоне и автоматически перезапускается при сбоях.

### Проверка работы

```bash
# Статус контейнеров
docker compose ps

# Логи в реальном времени
docker compose logs -f ha-telegram-bot
```

---

## ⚙️ Подробная настройка

### Шаг 1: Получение токенов

#### Telegram Bot Token
1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/newbot` и следуйте инструкциям
3. Скопируйте токен (формат: `123456789:ABCdefGHI...`)

#### Home Assistant Access Token
1. Откройте веб-интерфейс Home Assistant
2. Перейдите в **Профиль** (иконка человека внизу слева)
3. Прокрутите до **"Long-Lived Access Tokens"**
4. Нажмите **"Create Token"** → введите имя → скопируйте токен

> ⚠️ Токен показывается только один раз! Сохраните его сразу.

#### Telegram User ID
1. Напишите [@userinfobot](https://t.me/userinfobot) в Telegram
2. Скопируйте ваш числовой ID

### Шаг 2: Создание .env файла

```bash
cp .env.example .env
nano .env
```

Содержимое `.env`:

```env
# Telegram Bot Token (от @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Home Assistant URL
# Если HA на том же сервере: http://localhost:8123
# Если HA на другом сервере: http://192.168.1.100:8123
HA_BASE_URL=http://192.168.1.100:8123

# Home Assistant Long-Lived Access Token
HA_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Ваш Telegram ID (защита от посторонних)
ALLOWED_USER_ID=123456789

# Язык по умолчанию: ru или en
DEFAULT_LANG=ru

# Часовой пояс (для таймеров и логов)
TZ=Europe/Moscow

# Папка для данных (в Docker)
DATA_DIR=/app/data
```

### Шаг 3: Создание папок

```bash
mkdir -p data logs
```

- `data/` — сохранение настроек языков пользователей
- `logs/` — локальные логи (опционально, основные логи в Docker)

### Шаг 4: Сборка и запуск

```bash
# Сборка образа
docker compose build

# Запуск всех сервисов (бот + watchtower)
docker compose up -d

# Проверка статуса
docker compose ps
```

Ожидаемый вывод:
```
NAME                IMAGE                    STATUS
ha-telegram-bot     ha-telegram-bot          Up (healthy)
watchtower          containrrr/watchtower    Up
```

---

## 📁 Структура проекта

```
ha-telegram-bot/
├── bot.py                    # Основной код бота
├── Dockerfile                # Описание Docker-образа
├── docker-compose.yml        # Конфигурация сервисов
├── .dockerignore             # Исключения для Docker
├── .env                      # Конфигурация (НЕ в git!)
├── .env.example              # Шаблон конфигурации
├── requirements.txt          # Python-зависимости
├── README.md                 # Основная документация
├── README_DOCKER.md          # Этот файл
│
├── data/                     # Данные (volume, сохраняется)
│   └── user_langs.json       # Выбранные языки пользователей
│
└── logs/                     # Логи (volume, опционально)
    └── bot.log
```

---

## 🎮 Управление контейнерами

### Основные команды

```bash
# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск
docker compose restart

# Перезапуск только бота
docker compose restart ha-telegram-bot

# Просмотр статуса
docker compose ps

# Просмотр логов
docker compose logs -f                    # Все сервисы
docker compose logs -f ha-telegram-bot    # Только бот
docker compose logs -f watchtower         # Только watchtower

# Последние 100 строк
docker compose logs --tail=100 ha-telegram-bot

# Логи за последний час
docker compose logs --since 1h

# Использование ресурсов (CPU, RAM)
docker stats

# Вход в контейнер (для отладки)
docker compose exec ha-telegram-bot /bin/bash
```

### Остановка и удаление

```bash
# Остановка без удаления данных
docker compose down

# Полная очистка (контейнеры + образы + volumes)
docker compose down -v --rmi all

# Удаление только неиспользуемых образов
docker image prune -a
```

---

## 🔄 Watchtower — автообновление

Watchtower автоматически проверяет наличие новых версий образа и обновляет контейнер без потери данных.

### Как это работает

1. Каждые **60 минут** Watchtower проверяет Docker Hub
2. Если есть новая версия — скачивает её
3. Останавливает старый контейнер
4. Запускает новый с теми же настройками
5. Сохраняет все данные из volumes (`data/`, `logs/`)
6. Удаляет старый образ

### Настройка интервала

В `docker-compose.yml` измените:

```yaml
# Проверка каждый час (по умолчанию)
command: --interval 3600 --cleanup --scope ha-telegram-bot

# Проверка каждые 6 часов
command: --interval 21600 --cleanup --scope ha-telegram-bot

# Проверка раз в сутки
command: --interval 86400 --cleanup --scope ha-telegram-bot

# Проверка каждые 30 минут
command: --interval 1800 --cleanup --scope ha-telegram-bot
```

После изменения:
```bash
docker compose up -d watchtower
```

### Ручная проверка обновлений

```bash
# Остановить watchtower
docker compose stop watchtower

# Запустить проверку один раз
docker compose run --rm watchtower --run-once --cleanup

# Снова запустить watchtower
docker compose up -d watchtower
```

### Уведомления в Telegram

Чтобы получать уведомления об обновлениях:

1. Создайте отдельного бота через [@BotFather](https://t.me/BotFather)
2. Получите его токен
3. Узнайте свой Chat ID через [@userinfobot](https://t.me/userinfobot)
4. Добавьте в `docker-compose.yml`:

```yaml
watchtower:
  environment:
    - WATCHTOWER_NOTIFICATIONS=shoutrrr
    - WATCHTOWER_NOTIFICATION_URL=telegram://TOKEN@telegram?channels=CHAT_ID
```

Замените `TOKEN` и `CHAT_ID` на свои значения.

### Просмотр логов Watchtower

```bash
docker compose logs -f watchtower
```

Пример вывода при успешной проверке:
```
time="2026-09-27T10:00:00Z" level=info msg="Session done"
```

Пример вывода при обновлении:
```
time="2026-09-27T11:00:00Z" level=info msg="Found new image"
time="2026-09-27T11:00:05Z" level=info msg="Stopping container"
time="2026-09-27T11:00:10Z" level=info msg="Creating container"
```

---

## 📊 Мониторинг и логи

### Проверка здоровья контейнера

```bash
# Статус healthcheck
docker inspect --format='{{.State.Health.Status}}' ha-telegram-bot

# Детальная информация
docker inspect ha-telegram-bot | grep -A 10 "Health"
```

Возможные статусы:
- `healthy` — всё работает ✅
- `unhealthy` — есть проблемы ❌
- `starting` — контейнер запускается 🔄

### Просмотр логов

**Основные команды:**
```bash
# Логи в реальном времени
docker compose logs -f ha-telegram-bot

# Последние 50 строк
docker compose logs --tail=50 ha-telegram-bot

# Логи с определённого времени
docker compose logs --since "2026-09-27T10:00:00"

# Логи за последний час
docker compose logs --since 1h
```

**Пример типичного вывода:**
```
ha-telegram-bot  | 2026-09-27 10:00:00,123 [INFO] ha-bot: Бот запущен, загружаю список устройств...
ha-telegram-bot  | 2026-09-27 10:00:01,456 [INFO] ha-bot: Загружено устройств: 702
ha-telegram-bot  | 2026-09-27 10:00:01,789 [INFO] telegram.ext.Application: Application started
```

### Мониторинг ресурсов

```bash
# Использование CPU/RAM всеми контейнерами
docker stats

# Только наш бот
docker stats ha-telegram-bot
```

Пример вывода:
```
CONTAINER           CPU %     MEM USAGE / LIMIT     MEM %
ha-telegram-bot     0.15%     85.5MiB / 512MiB      16.7%
watchtower          0.02%     12.3MiB / 512MiB      2.4%
```

### Очистка старых образов

```bash
# Удаление неиспользуемых образов
docker image prune -a

# Полная очистка системы
docker system prune -a --volumes
```

> ⚠️ Watchtower автоматически удаляет старые образы (`WATCHTOWER_CLEANUP=true`), но периодическая ручная очистка не помешает.

---

## 🔄 Обновление бота

### Автоматическое обновление (через Watchtower)

Если вы опубликовали новый образ на Docker Hub:

1. Watchtower проверит обновления (каждый час по умолчанию)
2. Скачает новый образ
3. Перезапустит контейнер
4. Данные из `data/` сохранятся

### Ручное обновление (локальная сборка)

Если вы изменили `bot.py` локально:

```bash
# 1. Остановите бота
docker compose stop ha-telegram-bot

# 2. Пересоберите образ
docker compose build --no-cache ha-telegram-bot

# 3. Запустите заново
docker compose up -d ha-telegram-bot

# 4. Проверьте логи
docker compose logs -f ha-telegram-bot
```

### Обновление через Git

```bash
# 1. Получите последние изменения
git pull

# 2. Пересоберите и перезапустите
docker compose build --no-cache
docker compose up -d

# 3. Проверьте работу
docker compose ps
docker compose logs -f
```

### Откат к предыдущей версии

Если новая версия работает некорректно:

```bash
# 1. Остановите контейнер
docker compose down

# 2. Откатите код
git checkout v1.0.0  # или другой тег

# 3. Пересоберите
docker compose build --no-cache

# 4. Запустите
docker compose up -d
```

---

## 🔧 Решение проблем

### Ошибка: "Cannot connect to the Docker daemon"

**Причина:** Docker не запущен.

**Решение:**
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

### Ошибка: "Permission denied" при docker compose

**Причина:** Пользователь не в группе docker.

**Решение:**
```bash
sudo usermod -aG docker $USER
newgrp docker
# Или перелогиньтесь
```

### Бот не видит Home Assistant

**Причина 1:** Неправильный `HA_BASE_URL` в `.env`.

**Решение:**
- Если HA на том же сервере: `HA_BASE_URL=http://localhost:8123` или `http://172.17.0.1:8123`
- Если HA на другом сервере: `HA_BASE_URL=http://192.168.1.100:8123`

**Причина 2:** Docker не имеет доступа к сети HA.

**Решение:** Используйте `network_mode: host` в `docker-compose.yml` (уже настроено).

### Ошибка: "TELEGRAM_BOT_TOKEN and HA_ACCESS_TOKEN are required"

**Причина:** Файл `.env` не найден или не заполнен.

**Решение:**
```bash
# Проверьте, что .env существует
ls -la .env

# Проверьте содержимое
cat .env

# Убедитесь, что нет пробелов вокруг "="
# Правильно: TELEGRAM_BOT_TOKEN=123456:ABC
# Неправильно: TELEGRAM_BOT_TOKEN = 123456:ABC
```

### Контейнер постоянно перезапускается

**Причина:** Ошибка в коде или конфигурации.

**Решение:**
```bash
# Посмотрите логи
docker compose logs ha-telegram-bot

# Проверьте .env
docker compose config

# Запустите в foreground для отладки
docker compose up ha-telegram-bot
```

### Watchtower не обновляет контейнер

**Причина 1:** Образ не опубликован на Docker Hub.

**Решение:** Используйте ручное обновление (см. выше).

**Причина 2:** Неправильные метки.

**Решение:** Проверьте, что в `Dockerfile` и `docker-compose.yml` одинаковый scope:
```yaml
labels:
  - "com.centurylinklabs.watchtower.scope=ha-telegram-bot"
```

### Потеря данных после пересоздания контейнера

**Причина:** Volumes не настроены.

**Решение:** Убедитесь, что в `docker-compose.yml` есть:
```yaml
volumes:
  - ./data:/app/data
  - ./logs:/app/logs
```

### Как посмотреть, что внутри контейнера

```bash
# Вход в контейнер
docker compose exec ha-telegram-bot /bin/bash

# Внутри контейнера
ls -la /app
cat /app/data/user_langs.json
exit
```

---

## 🔐 Безопасность

### Защита секретов

✅ **Правильно:**
- Токены хранятся в `.env`
- `.env` добавлен в `.gitignore`
- `.env` не публикуется в Git

❌ **Неправильно:**
- Токены в коде
- `.env` в Git
- Токены в логах

### Непривилегированный пользователь

В `Dockerfile` бот запускается от пользователя `botuser` (не root):

```dockerfile
RUN groupadd -r botuser && useradd -r -g botuser ...
USER botuser
```

Это ограничивает ущерб в случае компрометации контейнера.

### Ограничение ресурсов

В `docker-compose.yml` настроены лимиты:

```yaml
deploy:
  resources:
    limits:
      cpus: '0.5'      # Максимум 50% CPU
      memory: 512M     # Максимум 512 MB RAM
    reservations:
      cpus: '0.1'      # Гарантировано 10% CPU
      memory: 128M     # Гарантировано 128 MB RAM
```

### Изоляция сети

Используется `network_mode: host` для прямого доступа к Home Assistant. Если HA на другом сервере, можно использовать bridge-сеть для дополнительной изоляции.

### Регулярные обновления

Watchtower автоматически обновляет образы, что включает исправления безопасности. Рекомендуется:
- Проверять логи Watchtower раз в неделю
- Подписываться на security-уведомления используемых библиотек

---

## 📝 Полезные команды (шпаргалка)

### Ежедневные операции

```bash
# Запуск
docker compose up -d

# Остановка
docker compose down

# Перезапуск
docker compose restart

# Логи
docker compose logs -f
```

### Обслуживание

```bash
# Обновление кода
git pull && docker compose build --no-cache && docker compose up -d

# Очистка
docker system prune -a

# Проверка здоровья
docker inspect --format='{{.State.Health.Status}}' ha-telegram-bot
```

### Отладка

```bash
# Вход в контейнер
docker compose exec ha-telegram-bot /bin/bash

# Логи с timestamp
docker compose logs --tail=100 --timestamps

# Использование ресурсов
docker stats
```

---

## 🎯 Сравнение с другими способами развёртывания

| Способ | Сложность | Автообновление | Переносимость | Рекомендация |
|--------|-----------|----------------|---------------|--------------|
| **Docker** | ⭐⭐ | ✅ Watchtower | 🌍 Отличная | ✅ **Рекомендуется** |
| systemd (Linux) | ⭐⭐⭐ | ❌ Вручную | 🖥 Только Linux | Для опытных |
| NSSM (Windows) | ⭐⭐⭐ | ❌ Вручную | 🪟 Только Windows | Для Windows |
| Прямой запуск | ⭐ | ❌ Вручную | 🖥 Зависит от ОС | Только для тестов |

---

## 📚 Дополнительные ресурсы

- [Документация Docker](https://docs.docker.com/)
- [Docker Compose Guide](https://docs.docker.com/compose/)
- [Watchtower Documentation](https://containrrr.github.io/watchtower/)
- [Home Assistant API](https://developers.home-assistant.io/docs/api/rest/)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)

---

## 🤝 Поддержка

Если возникли проблемы:
1. Проверьте раздел [Решение проблем](#-решение-проблем)
2. Посмотрите логи: `docker compose logs -f`
3. Создайте issue в [репозитории GitHub](https://github.com/sergej19882906/ha-telegram-bot/issues)

---

## 📄 Лицензия

Этот проект распространяется под лицензией MIT.

---

**Приятного использования! 🏠✨**

*Документация актуальна на сентябрь 2026 года.*
*Версия бота: 1.0*

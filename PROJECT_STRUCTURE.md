# 📁 Структура проекта HA Telegram Bot

Полная карта репозитория: файлы, назначение и связи между компонентами.

---

## Дерево проекта

```
ha-telegram-bot/
│
├── 📄 bot.py                    # Точка входа: main(), регистрация хендлеров, запуск polling
├── 📦 hamqttbot/                # Пакет с логикой бота (бывший монолитный bot.py)
│   ├── __init__.py              # Re-export имён пакета (обратная совместимость: import bot)
│   ├── config.py                # Логирование, Config, parse_int_env/parse_allowed_users, константы
│   ├── storage.py               # Файлы данных в data/ (языки, чаты), миграция legacy-файлов
│   ├── messages.py              # Локализация MESSAGES (ru/en), t(), esc()
│   ├── ha_client.py             # HAClient: REST-вызовы к Home Assistant (httpx)
│   ├── registry.py              # EntityRegistry: кеш устройств, алиасы, комнаты, сцены
│   └── bot_core.py              # HATelegramBot: команды, меню, таймеры, приёмник уведомлений
├── 📄 requirements.txt          # Зависимости Python (диапазоны, для разработки)
├── 📄 requirements.lock         # Точные версии для воспроизводимой сборки Docker-образа
├── 📄 healthcheck.py            # Проверка жизнеспособности контейнера (HTTP /notify или PID 1)
├── 🧪 tests/test_smoke.py       # Постоянные тесты (unittest, без внешних зависимостей)
├── 📄 Dockerfile                # Сборка Docker-образа (multi-arch: amd64 + arm64)
├── 📄 docker-compose.yml        # Запуск через Docker Compose
├── 📄 .dockerignore             # Исключения из build-контекста
├── 📄 .gitignore                # Исключения для git
├── 📄 .env.example              # Шаблон конфигурации (копируется в .env)
│
├── 🐧 Linux-скрипты (.sh)
│   ├── install.sh               # Установка: venv + зависимости + .env + папки
│   ├── uninstall.sh             # Полное удаление (кроме кода и .env)
│   ├── start.sh                 # Запуск бота
│   ├── start_log.sh             # Запуск с логированием в logs/
│   ├── stop.sh                  # Мягкая остановка (сохраняет таймеры)
│   ├── install_service.sh       # Установка systemd-службы
│   ├── uninstall_service.sh     # Удаление systemd-службы
│   └── deploy.sh                # Обновление: git pull + зависимости + рестарт + лог (--docker: multi-arch образ)
│
├── 🪟 Windows-скрипты (.bat)
│   ├── install.bat              # Установка: venv + зависимости + .env
│   ├── uninstall.bat            # Полное удаление
│   ├── start.bat                # Запуск бота
│   ├── start_log.bat            # Запуск с логированием
│   ├── stop.bat                 # Принудительная остановка
│   ├── install_service.bat      # Установка службы через NSSM
│   ├── uninstall_service.bat    # Удаление службы
│   ├── service_status.bat       # Статус службы и процесса
│   ├── service_restart.bat      # Перезапуск службы
│   └── service_log.bat          # Логи службы в реальном времени
│
├── 📚 Документация
│   ├── README.md                # Основная: возможности, Linux, ссылки
│   ├── README_LINUX.md          # Детальная инструкция по Linux
│   ├── README_DOCKER.md         # Запуск в Docker / docker-compose
│   ├── README_WINDOWS.md        # Установка на Windows
│   ├── README_WINDOWS_SERVICE.md# Служба Windows (NSSM / Планировщик)
│   └── UPDATE_NOTES.md          # Changelog: что нового в v2.0
│
└── 🔧 Создаются при работе (не коммитятся)
    ├── .env                     # Конфигурация с секретами (gitignored)
    ├── venv/                    # Виртуальное окружение (gitignored)
    ├── logs/                    # Логи (gitignored)
    └── data/                    # Языки, чаты для уведомлений и таймеры (gitignored)
        ├── user_langs.json
        ├── known_chats.json
        └── timers.json
```

---

## Назначение компонентов

### `bot.py` и пакет `hamqttbot/` — ядро

`bot.py` — тонкая точка входа: `main()`, сборка `Config` из окружения, регистрация
хендлеров PTB, post_init/post_shutdown, запуск polling. Вся логика — в пакете
`hamqttbot/` (зависимости текут в одну сторону: config/storage → ha_client/registry → bot_core → bot.py).

| Модуль | Класс / раздел | Назначение |
|---|---|---|
| `hamqttbot/messages.py` | `MESSAGES`, `t()` | Локализация (ru/en) |
| `hamqttbot/config.py` | `Config` / `parse_allowed_users()` | Конфигурация из переменных окружения |
| `hamqttbot/storage.py` | `USER_LANGS`, load/save, `migrate_legacy_data_files()` | Файлы данных в data/ |
| `hamqttbot/ha_client.py` | `HAClient` | Асинхронный клиент REST API Home Assistant (httpx) |
| `hamqttbot/registry.py` | `EntityRegistry` | Кеш устройств, алиасы, поиск, комнаты (area_registry), сцены |
| `hamqttbot/bot_core.py` | `HATelegramBot` | Все команды, inline-меню, таймеры, приёмник уведомлений |

`import bot` продолжает работать: bot.py реэкспортирует имена из пакета
(`bot.Config`, `bot.HATelegramBot`, `bot.MESSAGES`, `bot.TIMERS_FILE` и т.д.).

### Конфигурация (`.env`, шаблон — `.env.example`)

| Переменная | Обязательность | Назначение |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | Токен от @BotFather |
| `HA_BASE_URL` | ✅ | Адрес Home Assistant |
| `HA_ACCESS_TOKEN` | ✅ | Long-Lived Access Token |
| `ALLOWED_USER_IDS` | ✅ | Белый список Telegram ID (через запятую) |
| `DEFAULT_LANG` | ➖ | Язык по умолчанию (`ru`/`en`) |
| `NOTIFY_PORT` | ➖ | Порт приёмника уведомлений (`0` = выкл) |
| `NOTIFY_HOST` | ➖ | Интерфейс приёмника |
| `NOTIFY_TOKEN` | ⚠️ при NOTIFY_PORT≠0 | Авторизация приёмника |
| `NOTIFY_WATCHDOG_INTERVAL` | ➖ | Интервал сторожа уведомлений, сек (мин. 60, 0 = выкл) |
| `NOTIFY_WATCHDOG_COMMAND` | ⚠️ при заданном интервале | rest_command HA для проверки цепочки |
| `HA_TIMEOUT` | ➖ | Таймаут запросов к HA, сек (по умолчанию 15) |
| `DATA_DIR` | ➖ | Папка данных (Docker: `/app/data`) |

### Потоки данных

```
Пользователь (Telegram)
        │  команды / кнопки / текст
        ▼
    bot.py  ───────────────┐
        │                  │ HTTP /notify
        ▼                  ▼
   Home Assistant   Приёмник уведомлений
   (REST API)      (aiohttp, NOTIFY_PORT)
        ▲                  │
        └──────────────────┘ отправка уведомлений
                           обратно в Telegram

bot.py ──> data/user_langs.json   (языки, per user)
bot.py ──> data/known_chats.json  (чаты для уведомлений, per user)
bot.py ──> data/timers.json       (таймеры: при каждом изменении и при shutdown)
```

---

## Платформенная матрица

| Задача | Linux | Windows | Docker |
|---|---|---|---|
| Установка | `install.sh` | `install.bat` | `docker build` |
| Запуск | `start.sh` | `start.bat` | `docker compose up -d` |
| Логи в файл | `start_log.sh` | `start_log.bat` | `docker compose logs -f` |
| Остановка | `stop.sh` (мягкая) | `stop.bat` (жёсткая) | `docker compose down` |
| Автозапуск | systemd (`install_service.sh`) | NSSM (`install_service.bat`) | `--restart unless-stopped` |
| Удаление службы | `uninstall_service.sh` | `uninstall_service.bat` | — |
| Полное удаление | `uninstall.sh` | `uninstall.bat` | `docker compose down -v` |

---

## Правила для контрибьюторов

1. **Не коммитьте** `.env`, `venv/`, `logs/`, `data/` — они в `.gitignore`
2. Новые переменные окружения: добавить в `.env.example`, `Config`, парсинг в `main()`, README
3. Новые команды бота: обработчик в `HATelegramBot`, регистрация `CommandHandler` в `main()`, строки в `MESSAGES` (ru + en), `/help`, README
4. Новые скрипты: добавить в `chmod +x` в `install.sh` и в этот файл
5. Изменения логики — обновить `UPDATE_NOTES.md`
6. Перед коммитом прогнать `python -m unittest discover -s tests -v` (тесты — в `tests/`)

---

*Актуально на сентябрь 2026 года. Версия 3.0.0*

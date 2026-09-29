# 🤖 HA Telegram Bot

Telegram-бот для управления [Home Assistant](https://www.home-assistant.io/): устройства, сцены, комнаты, таймеры и уведомления из HA в Telegram.

---

## ✨ Возможности

- 🎛 **Управление устройствами** — включение/выключение/переключение света, розеток, вентиляторов, штор (по командам, inline-кнопкам и текстовому поиску)
- 🌡 **Установка значений** — яркость света в %, температура термостатов (`/set`)
- 🏠 **Комнаты** — настоящие area из Home Assistant (area_registry), fallback на атрибуты устройств
- 🎬 **Сцены** — активация по имени или из меню
- ⏳ **Таймеры** — автовыключение через N минут, **сохраняются при перезапуске бота**
- 🚨 **Уведомления из HA** — HTTP-приёмник: любая автоматизация Home Assistant может прислать сообщение в Telegram
- 🔎 **Поиск** — наберите часть имени устройства, бот покажет совпадения
- 🌐 **Два языка** — русский и английский (выбор на пользователя, `/lang`)
- 👥 **Несколько пользователей** — белый список Telegram ID
- ✅ **Безопасность** — доступ только для разрешённых ID, токен уведомлений, экранирование HTML

---

## 📚 Другие инструкции

- [🐳 Установка и запуск в Docker](README_DOCKER.md)
- [🪟 Установка на Windows](README_WINDOWS.md)
- [🛠️ Запуск как служба Windows](README_WINDOWS_SERVICE.md)
- [🐧 Linux: детальная инструкция](README_LINUX.md)

---

## 📋 Содержание

- [Требования](#-требования)
- [Быстрая установка](#-быстрая-установка)
- [Настройка](#-настройка)
- [Команды бота](#-команды-бота)
- [Запуск бота](#-запуск-бота)
- [Автозапуск через systemd](#-автозапуск-через-systemd)
- [Уведомления из Home Assistant](#-уведомления-из-home-assistant)
- [Мониторинг и логи](#-мониторинг-и-логи)
- [Обновление](#-обновление)
- [Безопасность](#-безопасность)
- [Удаление](#-удаление)
- [Решение проблем](#-решение-проблем)

---

## 📦 Требования

### Системные требования

- **ОС:** Ubuntu 20.04+, Debian 11+, CentOS 8+, Fedora 35+, Arch Linux
- **Python:** 3.11 или выше
- **Права:** обычный пользователь для установки, root для systemd
- **Сеть:** исходящие HTTPS-соединения (порт 443); порт для приёмника уведомлений — если используете

### Установка Python по дистрибутивам

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git
```

**CentOS/RHEL/Fedora:**
```bash
sudo dnf install python3 python3-pip git
```

**Arch Linux:**
```bash
sudo pacman -S python python-pip git
```

---

## 🚀 Быстрая установка

### Шаг 1: Клонируйте репозиторий

```bash
cd /opt  # или ~/projects, или любую другую папку
git clone https://github.com/sergej19882906/ha-telegram-bot.git
cd ha-telegram-bot
```

### Шаг 2: Сделайте скрипты исполняемыми

```bash
chmod +x *.sh
```

### Шаг 3: Запустите установку

```bash
./install.sh
```

Скрипт автоматически:

- Создаст виртуальное окружение (`venv/`)
- Установит все зависимости Python (включая `aiohttp` для приёмника уведомлений)
- Создаст шаблон файла `.env`
- Создаст папку для логов (`logs/`)

### Шаг 4: Заполните конфигурацию

```bash
cp .env.example .env   # если .env ещё не создан
nano .env
```

```env
# Telegram bot token (от @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Home Assistant settings
HA_BASE_URL=http://192.168.1.100:8123
HA_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Разрешённые пользователи — Telegram ID через запятую
ALLOWED_USER_IDS=123456789,987654321

# Язык по умолчанию: ru или en
DEFAULT_LANG=ru

# --- Приёмник уведомлений из HA (опционально; 0 = выключен) ---
NOTIFY_PORT=8099
NOTIFY_HOST=0.0.0.0
NOTIFY_TOKEN=длинная_случайная_строка
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

> ⚠️ Если `ALLOWED_USER_IDS` не задан, **доступ к боту разрешён всем**. Всегда заполняйте этот параметр!

### Шаг 5: Запустите бота

```bash
./start.sh
```

---

## ⚙️ Настройка

### Получение Telegram Bot Token

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather)
2. Отправьте команду `/newbot`
3. Следуйте инструкциям и скопируйте токен

### Получение Telegram User ID

1. Откройте [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте любое сообщение
3. Скопируйте ваш числовой ID — добавьте его в `ALLOWED_USER_IDS`

### Получение Home Assistant Access Token

1. Откройте веб-интерфейс Home Assistant
2. Нажмите на свой профиль (иконка человека в левом нижнем углу)
3. Прокрутите вниз до раздела **"Long-Lived Access Tokens"**
4. Нажмите **"Create Token"** и скопируйте токен

> Токену нужны права на вызов сервисов и чтение состояний. Для работы комнат через area_registry права суперпользователя не обязательны, но рекомендуются.

### Защита файла .env

```bash
chmod 600 .env
```

---

## 📱 Команды бота

| Команда | Действие |
|---|---|
| `/start` | Приветствие + кнопки меню внизу чата |
| `/menu` | Главное inline-меню |
| `/hide` | Скрыть кнопки меню |
| `/lang` | Сменить язык (ru/en) |
| `/on <имя>` | Включить устройство |
| `/off <имя>` | Выключить устройство |
| `/toggle <имя>` | Переключить устройство |
| `/set <имя> <значение>` | Яркость света в % (0–100) или температура климата |
| `/state [имя]` | Статус устройства (без имени — все устройства, живые данные) |
| `/room <комната>` | Устройства в комнате |
| `/scene <имя>` | Активировать сцену |
| `/timer <мин> <имя>` | Таймер автовыключения |
| `/alloff` | Выключить весь свет/розетки (с подтверждением) |
| `/status` | Проверка доступности HA |
| `/help` | Список команд |

**Имена устройств** можно указывать по `entity_id` (`light.kitchen`) или по дружественному имени («Свет на кухне»). Необязательно писать точно — бот ищет по подстроке и предложит варианты.

**Примеры:**
```
/on свет на кухне
/set подсветка 40
/timer 30 свет в спальне
/room кухня
```

---

## ▶️ Запуск бота

### Вариант 1: Обычный запуск

```bash
./start.sh
```

Для остановки нажмите `Ctrl+C`.

### Вариант 2: С логированием в файл

```bash
./start_log.sh
```

Логи: `logs/bot_YYYYMMDD_HHMMSS.log` + консоль.

### Вариант 3: В фоне (screen)

```bash
sudo apt install screen
screen -S habot
./start.sh
# Отсоединиться: Ctrl+A, затем D
# Вернуться: screen -r habot
```

### Вариант 4: В фоне (tmux)

```bash
sudo apt install tmux
tmux new -s habot
./start.sh
# Отсоединиться: Ctrl+B, затем D
# Вернуться: tmux attach -t habot
```

---

## 🔄 Автозапуск через systemd

Рекомендуемый способ для продакшена: автостарт при загрузке системы и перезапуск при сбоях.

### Установка службы

```bash
sudo ./install_service.sh
```

### Ручная установка (если нужно)

```bash
sudo nano /etc/systemd/system/ha-telegram-bot.service
```

```ini
[Unit]
Description=HA Telegram Bot
After=network.target

[Service]
Type=simple
User=ваш_пользователь
WorkingDirectory=/opt/ha-telegram-bot
Environment="PATH=/opt/ha-telegram-bot/venv/bin"
ExecStart=/opt/ha-telegram-bot/venv/bin/python /opt/ha-telegram-bot/bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ha-telegram-bot
sudo systemctl start ha-telegram-bot
```

### Управление службой

```bash
sudo systemctl status ha-telegram-bot    # статус
sudo systemctl start ha-telegram-bot     # запуск
sudo systemctl stop ha-telegram-bot      # остановка
sudo systemctl restart ha-telegram-bot   # перезапуск
sudo systemctl enable ha-telegram-bot    # автозапуск вкл
sudo systemctl disable ha-telegram-bot   # автозапуск выкл

# Быстрая проверка
systemctl is-active ha-telegram-bot
systemctl is-enabled ha-telegram-bot
```

---

## 🚨 Уведомления из Home Assistant

Бот поднимает HTTP-приёмник (порт `NOTIFY_PORT`), куда Home Assistant может отправлять уведомления.

### Настройка в Home Assistant (`configuration.yaml`)

```yaml
rest_command:
  telegram_notify:
    url: "http://<IP_сервера_с_ботом>:8099/notify"
    method: POST
    headers:
      Authorization: "Bearer <NOTIFY_TOKEN_из_.env>"
    content_type: application/json
    payload: '{"text": "{{ message }}"}'
```

Перезагрузите HA: **Developer Tools → YAML → Reload rest commands**.

### Использование в автоматизациях

```yaml
- alias: Уведомление о протечке
  triggers:
    - trigger: state
      entity_id: binary_sensor.leak_sensor
      to: "on"
  actions:
    - service: rest_command.telegram_notify
      data:
        message: "🚨 Протечка в ванной!"
```

### Дополнительные параметры payload

```json
{
  "text": "<b>Жирный текст</b>",
  "parse_mode": "HTML",
  "chat_ids": [123456789]
}
```

- `parse_mode` — `HTML` или `MarkdownV2` (необязательно)
- `chat_ids` — отправка конкретным пользователям (необязательно; по умолчанию — всем, кто общался с ботом)

---

## 📊 Мониторинг и логи

### journalctl

```bash
# Последние 50 строк
sudo journalctl -u ha-telegram-bot -n 50

# В реальном времени
sudo journalctl -u ha-telegram-bot -f

# За сегодня / период
sudo journalctl -u ha-telegram-bot --since today
sudo journalctl -u ha-telegram-bot --since "2026-09-27 10:00" --until "2026-09-27 12:00"
```

В логах видно каждый запрос: `Запрос user=123456789: /on свет` — удобно для аудита.

### Файлы логов (при запуске через start_log.sh)

```bash
ls -lh logs/
tail -f logs/bot_*.log
grep -i error logs/bot_*.log
```

### Ротация логов

```bash
sudo nano /etc/logrotate.d/ha-telegram-bot
```

```
/opt/ha-telegram-bot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 user user
}
```

---

## 🔄 Обновление

```bash
sudo systemctl stop ha-telegram-bot
cd /opt/ha-telegram-bot
git pull
source venv/bin/activate
pip install --upgrade -r requirements.txt
deactivate
sudo systemctl start ha-telegram-bot
sudo systemctl status ha-telegram-bot
```

---

## 🛡️ Безопасность

1. **`.env` только для владельца:** `chmod 600 .env`
2. **Отдельный пользователь, не root:**
   ```bash
   sudo useradd -r -s /bin/false habotuser
   sudo chown -R habotuser:habotuser /opt/ha-telegram-bot
   # в systemd-файле: User=habotuser
   sudo systemctl daemon-reload
   sudo systemctl restart ha-telegram-bot
   ```
3. **Всегда задавайте `ALLOWED_USER_IDS`** — иначе бот доступен всем.
4. **Всегда задавайте `NOTIFY_TOKEN`**, если включён приёмник уведомлений — иначе любой в сети сможет слать сообщения от имени бота.
5. **Firewall** — бот сам ничего не слушает, кроме порта уведомлений:
   ```bash
   sudo ufw allow out 443/tcp                                   # Telegram API
   sudo ufw allow out to 192.168.1.100 port 8123                # Home Assistant
   sudo ufw allow from 192.168.1.100 to any port 8099           # приёмник (только с HA)
   ```
6. **Проверка открытых портов:**
   ```bash
   sudo ss -tulpn | grep python
   ```

---

## 🗑️ Удаление

```bash
./uninstall.sh        # venv, логи, user_langs.json, systemd-служба
cd .. && rm -rf ha-telegram-bot   # полное удаление проекта
```

Файлы `bot.py`, `.env` и документация сохраняются при `./uninstall.sh`. Таймеры хранятся в `data/timers.json` — удалите его при полном удалении.

---

## 🔧 Решение проблем

| Проблема | Решение |
|---|---|
| `ModuleNotFoundError: No module named 'aiohttp'` | `source venv/bin/activate && pip install -r requirements.txt` |
| `python3: command not found` | `sudo apt install python3 python3-pip python3-venv` |
| `venv/bin/activate: No such file or directory` | Запустите `./install.sh` |
| `Permission denied` при запуске скриптов | `chmod +x *.sh` |
| Бот молчит / не отвечает | Ваш ID не в `ALLOWED_USER_IDS`. Проверьте через @userinfobot, обновите `.env`, `sudo systemctl restart ha-telegram-bot` |
| Бот не стартует через systemd | `sudo journalctl -u ha-telegram-bot -n 100 --no-pager` — проверьте пути в `WorkingDirectory`/`ExecStart`, пользователя `User=` и заполненность `.env` |
| `Cannot send a request, as the client has been closed` | `source venv/bin/activate && pip install --upgrade "python-telegram-bot>=21" httpx` |
| Ошибка `401` от HA | Неверный/просроченный `HA_ACCESS_TOKEN` — создайте новый long-lived token |
| Комнаты не находятся | Убедитесь, что у устройств в HA назначены areas (**Настройки → Области и зоны**). Без area_registry используются атрибуты `room_name`/`area`/`area_name`/`location` |
| «Данные кнопки устарели» | Кнопки живут до перезапуска бота — отправьте `/menu` заново |
| Порт 8099 занят / приёмник не стартует | Проверьте `sudo ss -tulpn | grep 8099`, смените `NOTIFY_PORT` |
| Таймеры не срабатывают после рестарта | Проверьте права на файл `data/timers.json` (должен быть доступен пользователю службы) |
| Высокое потребление памяти | Увеличьте интервал обновления в `bot.py`: `await asyncio.sleep(60)` → `await asyncio.sleep(300)` |

---

## 📁 Структура файлов

```
/opt/ha-telegram-bot/
├── bot.py                    # Основной файл бота
├── .env                      # Конфигурация (права 600; создаётся из .env.example)
├── .env.example              # Шаблон конфигурации со всеми переменными
├── .gitignore                # Исключения для git (.env, venv, логи, data)
├── requirements.txt          # Зависимости Python
├── README.md                 # Эта документация
├── install.sh                # Установка
├── start.sh                  # Запуск
├── start_log.sh              # Запуск с логированием
├── stop.sh                   # Остановка
├── uninstall.sh              # Удаление
├── install_service.sh        # Установка systemd-службы
├── venv/                     # Виртуальное окружение (авто)
├── logs/                     # Логи (авто)
├── data/                     # Данные (авто; в Docker: /app/data)
│   ├── user_langs.json       # Языки пользователей
│   └── timers.json           # Активные таймеры (при shutdown)
└── Dockerfile                # Сборка Docker-образа
```

---

## 💡 Советы по эксплуатации

- Регулярно смотрите логи: `sudo journalctl -u ha-telegram-bot -f`
- Бэкап конфигурации: `tar -czf ha-bot-backup-$(date +%Y%m%d).tar.gz .env bot.py data/`
- Мониторинг через cron (автоперезапуск при падении + письмо):

```bash
#!/bin/bash
# check_bot.sh
if ! systemctl is-active --quiet ha-telegram-bot; then
    echo "HA Telegram Bot не работает!" | mail -s "Alert" your@email.com
    sudo systemctl restart ha-telegram-bot
fi
```

```
*/5 * * * * /path/to/check_bot.sh
```

- Для серверов с < 1 ГБ RAM: увеличьте интервал обновления реестра до 5–10 минут, используйте `start.sh` вместо `start_log.sh`.

---

## 🔗 Полезные ссылки

- [Документация Home Assistant](https://www.home-assistant.io/docs/)
- [REST API Home Assistant](https://developers.home-assistant.io/docs/api/rest/)
- [Документация python-telegram-bot](https://docs.python-telegram-bot.org/)
- [REST Command в HA (для уведомлений)](https://www.home-assistant.io/integrations/rest_command/)
- [Инструкция по Docker](README_DOCKER.md)
- [Инструкция по Windows](README_WINDOWS.md) и [служба Windows](README_WINDOWS_SERVICE.md)

---

## ✅ Итог

Полностью настроенный бот с:

- ✅ Управлением устройствами, сценами и комнатами
- ✅ Таймерами, переживающими перезапуск
- ✅ Уведомлениями из Home Assistant в Telegram
- ✅ Мультиязычностью и несколькими пользователями
- ✅ Автозапуском через systemd, логированием и мониторингом

**Приятного использования! 🏠✨**

---

*Документация актуальна на сентябрь 2026 года.*
*Версия бота: 2.0*
*Поддерживаемые ОС: Ubuntu 20.04+, Debian 11+, CentOS 8+, Fedora 35+, Arch Linux*

# 🐧 Инструкция по установке HA Telegram Bot на Linux

Полная инструкция по установке, запуску и настройке бота на Linux-системах.

---

## 📋 Содержание

- [Требования](#-требования)
- [Быстрая установка](#-быстрая-установка)
- [Настройка](#-настройка)
- [Запуск бота](#-запуск-бота)
- [Автозапуск через systemd](#-автозапуск-через-systemd)
- [Управление службой](#-управление-службой)
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
- **Сеть:** исходящие HTTPS-соединения (порт 443)

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
# Перейдите в нужную папку
cd /opt  # или ~/projects, или любую другую

# Клонируйте репозиторий
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
- Установит все зависимости Python
- Создаст шаблон файла `.env`
- Создаст папку для логов (`logs/`)

### Шаг 4: Заполните конфигурацию

```bash
nano .env
```

Заполните файл:
```env
# Telegram bot token (от @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Home Assistant settings
HA_BASE_URL=http://192.168.1.100:8123
HA_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Ваш Telegram ID (защита от чужих пользователей)
ALLOWED_USER_ID=123456789

# Язык по умолчанию: ru или en
DEFAULT_LANG=ru
```

Сохраните: `Ctrl+O`, `Enter`, `Ctrl+X`

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

### Получение Home Assistant Access Token

1. Откройте веб-интерфейс Home Assistant
2. Нажмите на свой профиль (иконка человека в левом нижнем углу)
3. Прокрутите вниз до раздела **"Long-Lived Access Tokens"**
4. Нажмите **"Create Token"** и скопируйте токен

### Получение Telegram User ID

1. Откройте [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте любое сообщение
3. Скопируйте ваш числовой ID

### Защита файла .env

```bash
chmod 600 .env
```

---

## ▶️ Запуск бота

### Вариант 1: Обычный запуск

```bash
./start.sh
```

Бот будет работать в текущем терминале. Для остановки нажмите `Ctrl+C`.

### Вариант 2: Запуск с логированием

```bash
./start_log.sh
```

Логи будут сохраняться в файл `logs/bot_YYYYMMDD_HHMMSS.log` и одновременно выводиться в консоль.

### Вариант 3: Запуск в фоне (screen)

```bash
# Установите screen
sudo apt install screen  # Ubuntu/Debian
sudo dnf install screen  # CentOS/Fedora

# Создайте сессию
screen -S habot

# Запустите бота
./start.sh

# Отсоединитесь от сессии: Ctrl+A, затем D
# Бот продолжит работать в фоне

# Вернитесь к сессии:
screen -r habot
```

### Вариант 4: Запуск в фоне (tmux)

```bash
# Установите tmux
sudo apt install tmux
sudo dnf install tmux

# Создайте сессию
tmux new -s habot

# Запустите бота
./start.sh

# Отсоединитесь: Ctrl+B, затем D
# Вернитесь: tmux attach -t habot
```

---

## 🔄 Автозапуск через systemd

Это **рекомендуемый способ** для продакшена. Бот будет запускаться автоматически при старте системы и перезапускаться при сбоях.

### Установка службы

```bash
sudo ./install_service.sh
```

Скрипт автоматически:
- Создаст файл службы `/etc/systemd/system/ha-telegram-bot.service`
- Включит автозапуск при старте системы
- Запустит службу

### Ручная установка systemd

Если хотите настроить вручную:

```bash
sudo nano /etc/systemd/system/ha-telegram-bot.service
```

Вставьте содержимое (замените пути и пользователя):
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

Активируйте:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ha-telegram-bot
sudo systemctl start ha-telegram-bot
```

---

## 🎛️ Управление службой

### Основные команды

```bash
# Статус службы
sudo systemctl status ha-telegram-bot

# Запуск
sudo systemctl start ha-telegram-bot

# Остановка
sudo systemctl stop ha-telegram-bot

# Перезапуск
sudo systemctl restart ha-telegram-bot

# Отключить автозапуск
sudo systemctl disable ha-telegram-bot

# Включить автозапуск
sudo systemctl enable ha-telegram-bot
```

### Быстрая проверка

```bash
# Работает ли бот?
systemctl is-active ha-telegram-bot

# Включён ли автозапуск?
systemctl is-enabled ha-telegram-bot
```

---

## 📊 Мониторинг и логи

### Просмотр логов через journalctl

```bash
# Последние 50 строк
sudo journalctl -u ha-telegram-bot -n 50

# Логи в реальном времени
sudo journalctl -u ha-telegram-bot -f

# Логи за сегодня
sudo journalctl -u ha-telegram-bot --since today

# Логи за вчерашний день
sudo journalctl -u ha-telegram-bot --since yesterday

# Логи за конкретный период
sudo journalctl -u ha-telegram-bot --since "2026-09-27 10:00:00" --until "2026-09-27 12:00:00"
```

### Просмотр файлов логов

Если бот запущен через `start_log.sh`:
```bash
# Список всех логов
ls -lh logs/

# Просмотр последнего лога
tail -f logs/bot_*.log

# Поиск ошибок
grep -i error logs/bot_*.log
```

### Ротация логов

Для автоматической ротации логов создайте файл `/etc/logrotate.d/ha-telegram-bot`:

```bash
sudo nano /etc/logrotate.d/ha-telegram-bot
```

Вставьте:
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

### Автоматическое обновление

```bash
# Остановите службу
sudo systemctl stop ha-telegram-bot

# Перейдите в папку проекта
cd /opt/ha-telegram-bot

# Обновите код
git pull

# Обновите зависимости
source venv/bin/activate
pip install --upgrade -r requirements.txt
deactivate

# Запустите снова
sudo systemctl start ha-telegram-bot

# Проверьте статус
sudo systemctl status ha-telegram-bot
```

### Обновление только зависимостей

```bash
sudo systemctl stop ha-telegram-bot
source venv/bin/activate
pip install --upgrade "python-telegram-bot>=21" httpx pydantic python-dotenv
deactivate
sudo systemctl start ha-telegram-bot
```

---

## 🛡️ Безопасность

### 1. Ограничьте права доступа к `.env`

```bash
chmod 600 .env
```

### 2. Запускайте от отдельного пользователя (не root)

```bash
# Создайте пользователя для бота
sudo useradd -r -s /bin/false habotuser

# Измените владельца папки
sudo chown -R habotuser:habotuser /opt/ha-telegram-bot

# Обновите systemd файл (User=habotuser)
sudo nano /etc/systemd/system/ha-telegram-bot.service
# Измените строку User=ваш_пользователь на User=habotuser

sudo systemctl daemon-reload
sudo systemctl restart ha-telegram-bot
```

### 3. Настройте firewall

Бот работает только с исходящими соединениями, но для явного разрешения:

**UFW (Ubuntu/Debian):**
```bash
sudo ufw allow out 443/tcp  # HTTPS для Telegram API
sudo ufw allow out to 192.168.1.100 port 8123  # Home Assistant
```

**firewalld (CentOS/Fedora):**
```bash
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 4. Проверка открытых портов

```bash
# Бот НЕ должен слушать никаких портов (он только исходящий)
sudo netstat -tulpn | grep python
```

---

## 🗑️ Удаление

### Полное удаление

```bash
./uninstall.sh
```

Скрипт удалит:
- Виртуальное окружение (`venv/`)
- Логи (`logs/`)
- Файл `user_langs.json`
- Systemd службу (если установлена)

Файлы `bot.py`, `.env` и документация будут сохранены.

### Полное удаление проекта

```bash
./uninstall.sh
cd ..
rm -rf ha-telegram-bot
```

---

## 🔧 Решение проблем

### Ошибка: `python3: command not found`

**Решение:** Установите Python 3:
```bash
sudo apt install python3 python3-pip python3-venv  # Ubuntu/Debian
sudo dnf install python3 python3-pip              # CentOS/Fedora
```

### Ошибка: `venv/bin/activate: No such file or directory`

**Решение:** Запустите установку:
```bash
./install.sh
```

### Ошибка: `Permission denied` при запуске скриптов

**Решение:** Сделайте скрипты исполняемыми:
```bash
chmod +x *.sh
```

### Бот не запускается через systemd

**Проверка:**
```bash
# Статус службы
sudo systemctl status ha-telegram-bot

# Подробные логи
sudo journalctl -u ha-telegram-bot -n 100 --no-pager
```

**Частые причины:**
1. Неверный путь в `WorkingDirectory` или `ExecStart`
2. Неправильный пользователь в `User=`
3. Не заполнен `.env` файл

### Ошибка: `Cannot send a request, as the client has been closed`

**Решение:** Обновите зависимости:
```bash
source venv/bin/activate
pip install --upgrade "python-telegram-bot>=21" httpx pydantic python-dotenv
```

### Бот работает, но не отвечает на команды

**Причина:** Ваш Telegram ID не совпадает с `ALLOWED_USER_ID`.

**Решение:**
1. Узнайте свой ID через [@userinfobot](https://t.me/userinfobot)
2. Обновите `ALLOWED_USER_ID` в файле `.env`
3. Перезапустите бота: `sudo systemctl restart ha-telegram-bot`

### Высокое использование памяти

**Решение:** Увеличьте интервал обновления в `bot.py`:
```python
# Найдите строку:
await asyncio.sleep(60)
# Измените на:
await asyncio.sleep(300)  # 5 минут вместо 1
```

---

## 📁 Структура файлов на Linux

```
/opt/ha-telegram-bot/
├── bot.py                    # Основной файл бота
├── .env                      # Конфигурация (права 600)
├── requirements.txt          # Зависимости Python
├── README.md                 # Основная документация
├── README_LINUX.md           # Эта инструкция
├── install.sh                # Скрипт установки
├── start.sh                  # Скрипт запуска
├── start_log.sh              # Запуск с логированием
├── stop.sh                   # Скрипт остановки
├── uninstall.sh              # Скрипт удаления
├── install_service.sh        # Установка systemd службы
├── venv/                     # Виртуальное окружение (авто)
└── logs/                     # Логи (авто)
    └── bot_YYYYMMDD_HHMMSS.log
```

---

## 🔗 Полезные ссылки

- [Документация Home Assistant](https://www.home-assistant.io/docs/)
- [Документация python-telegram-bot](https://docs.python-telegram-bot.org/)
- [Systemd для начинающих](https://www.digitalocean.com/community/tutorials/systemd-essentials-working-with-services-units-and-the-journal)
- [Linux команды для начинающих](https://linuxcommand.org/)

---

## 💡 Советы по эксплуатации

### 1. Регулярно проверяйте логи
```bash
sudo journalctl -u ha-telegram-bot -f
```

### 2. Создайте резервную копию конфигурации
```bash
tar -czf ha-bot-backup-$(date +%Y%m%d).tar.gz .env bot.py
```

### 3. Мониторинг через cron

Создайте скрипт проверки `check_bot.sh`:
```bash
#!/bin/bash
if ! systemctl is-active --quiet ha-telegram-bot; then
    echo "HA Telegram Bot не работает!" | mail -s "Alert" your@email.com
    sudo systemctl restart ha-telegram-bot
fi
```

Добавьте в crontab:
```bash
crontab -e
# Добавьте строку (проверка каждые 5 минут)
*/5 * * * * /path/to/check_bot.sh
```

### 4. Оптимизация для слабых серверов

Если у вас мало RAM (< 1GB):
- Увеличьте интервал обновления до 5-10 минут
- Отключите подробное логирование
- Используйте `start.sh` вместо `start_log.sh`

---

## ✅ Итог

Теперь у вас есть полностью настроенный бот на Linux с:
- ✅ Автоматической установкой зависимостей
- ✅ Автозапуском через systemd
- ✅ Логированием и мониторингом
- ✅ Безопасной конфигурацией
- ✅ Удобными скриптами управления

**Приятного использования! 🏠✨**

---

*Документация актуальна на сентябрь 2026 года.*
*Версия бота: 1.0*
*Поддерживаемые ОС: Ubuntu 20.04+, Debian 11+, CentOS 8+, Fedora 35+, Arch Linux*

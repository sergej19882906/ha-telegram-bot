# 🪟 Инструкция по установке HA Telegram Bot на Windows

Полная инструкция по установке и запуску бота на Windows 10/11.

---

## 📋 Содержание

- [Требования](#-требования)
- [Быстрая установка](#-быстрая-установка)
- [Настройка](#-настройка)
- [Запуск бота](#-запуск-бота)
- [Решение проблем](#-решение-проблем)

---

## 📦 Требования

- **ОС:** Windows 10 (1909+) или Windows 11
- **Python:** 3.11 или выше
- **Git:** [git-scm.com](https://git-scm.com/download/win) (или скачайте ZIP репозитория)

---

## 🚀 Быстрая установка

### Шаг 1: Установите Python

1. Скачайте установщик с [python.org/downloads](https://www.python.org/downloads/)
2. При установке **обязательно** отметьте галочку **"Add python.exe to PATH"**
3. Проверьте в PowerShell:

```powershell
python --version
```

Должно быть `Python 3.11.x` или новее. Если команда не найдена — переустановите Python с галочкой PATH (или используйте `py` вместо `python`).

### Шаг 2: Получите код бота

**Вариант А — через Git:**
```powershell
cd $env:USERPROFILE\Documents
git clone https://github.com/sergej19882906/ha-telegram-bot.git
cd ha-telegram-bot
```

**Вариант Б — через ZIP:**
1. Откройте https://github.com/sergej19882906/ha-telegram-bot
2. **Code → Download ZIP**
3. Распакуйте архив, например в `Documents\ha-telegram-bot`
4. В PowerShell: `cd Documents\ha-telegram-bot`

### Шаг 3: Установите зависимости

**Простой способ — дважды кликните `install.bat`** (или запустите в PowerShell: `.\install.bat`). Скрипт создаст виртуальное окружение, установит зависимости и подготовит шаблон `.env`.

**Или вручную через PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

> ⚠️ Если PowerShell выдаёт ошибку «execution of scripts is disabled on this system», выполните один раз:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
> и повторите активацию.

### Шаг 4: Заполните конфигурацию

Создайте файл `.env` в папке проекта (через Блокнот: **Файл → Сохранить как → тип: "Все файлы", имя: `.env`**):

```env
# Telegram bot token (от @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Home Assistant settings
HA_BASE_URL=http://192.168.1.100:8123
HA_ACCESS_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Разрешённые пользователи — Telegram ID через запятую
# ВНИМАНИЕ: если не задать, доступ к боту будет разрешён ВСЕМ!
ALLOWED_USER_IDS=123456789

# Язык по умолчанию: ru или en
DEFAULT_LANG=ru

# --- Приёмник уведомлений из HA (опционально) ---
NOTIFY_PORT=8099
NOTIFY_HOST=0.0.0.0
NOTIFY_TOKEN=длинная_случайная_строка
```

### Шаг 5: Запустите бота

```powershell
python bot.py
```

В логе появится: `Бот запущен... Загружено устройств: N`. Откройте Telegram, найдите своего бота и отправьте `/start`.

Остановка: `Ctrl+C` в окне PowerShell.

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

---

## ▶️ Запуск бота

В папке проекта есть удобные bat-скрипты (аналоги Linux-скриптов):

| Файл | Действие |
|---|---|
| `install.bat` | Установка: venv + зависимости + шаблон `.env` |
| `start.bat` | Обычный запуск бота |
| `start_log.bat` | Запуск с записью лога в `logs\bot_<дата>.log` и выводом в консоль |
| `stop.bat` | Принудительная остановка запущенного бота |

### Обычный запуск

Дважды кликните `start.bat` — или в PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
python bot.py
```

Остановка: `Ctrl+C` в окне — бот успеет сохранить активные таймеры в `data\timers.json`.

### Запуск с логированием в файл

Дважды кликните `start_log.bat` — или вручную:

```powershell
.\venv\Scripts\Activate.ps1
python bot.py 2>&1 | Tee-Object -FilePath "logs\bot_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
```

(Папку `logs` предварительно создайте: `mkdir logs`.)

### Firewall

Бот работает только с исходящими соединениями. Порт приёмника уведомлений (если включён) нужно разрешить в брандмауэре Windows:

```powershell
# Только из локальной сети (пример для NOTIFY_PORT=8099)
New-NetFirewallRule -DisplayName "HA Telegram Bot Notify" -Direction Inbound -Protocol TCP -LocalPort 8099 -RemoteAddress 192.168.1.0/24 -Action Allow
```

Или через **Панель управления → Брандмауэр → Правила для входящих → Создать правило → Порт → TCP, 8099**.

---

## 🔄 Обновление

```powershell
cd $env:USERPROFILE\Documents\ha-telegram-bot
git pull
.\venv\Scripts\Activate.ps1
pip install --upgrade -r requirements.txt
python bot.py
```

---

## 🔧 Решение проблем

| Проблема | Решение |
|---|---|
| `python` не распознаётся | Python не в PATH: переустановите с галочкой «Add to PATH» или используйте `py` вместо `python` |
| «execution of scripts is disabled» | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, затем повторите активацию venv |
| `No module named 'dotenv'` | Активируйте venv: `.\venv\Scripts\Activate.ps1` и установите зависимости заново |
| Бот молчит | Ваш ID не в `ALLOWED_USER_IDS`. Проверьте через @userinfobot, перезапустите бота |
| Ошибка `401` от HA | Неверный/просроченный `HA_ACCESS_TOKEN` — создайте новый long-lived token |
| HA не достукивается до `:8099` | Разрешите порт в брандмауэре Windows, проверьте `NOTIFY_PORT` и `NOTIFY_TOKEN` |
| .bat закрывается сразу после запуска | Запускайте из PowerShell: `.\start.bat` — увидите текст ошибки; чаще всего не заполнен `.env` |
| Таймеры не срабатывают после закрытия окна | Таймеры сохраняются только при штатной остановке (Ctrl+C). Для постоянной работы используйте службу — см. [README_WINDOWS_SERVICE.md](README_WINDOWS_SERVICE.md) |

---

## ✅ Итог

Бот запущен. Для **постоянной работы в фоне** (запуск при входе в систему или как служба Windows) перейдите к [README_WINDOWS_SERVICE.md](README_WINDOWS_SERVICE.md).

**Приятного использования! 🏠✨**

---

*Документация актуальна на сентябрь 2026 года. Версия бота: 2.0*

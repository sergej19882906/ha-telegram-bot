# 🛠️ HA Telegram Bot как служба Windows

Запуск бота в фоне: автостарт при загрузке системы, перезапуск при сбоях, работа без входа пользователя.

Доступно два способа:

| Способ | Когда выбирать |
|---|---|
| **A. Планировщик заданий** | Бот должен стартовать при входе пользователя. Без сторонних программ. |
| **B. NSSM (служба Windows)** | Бот должен работать всегда, даже без входа пользователя. Рекомендуется. |

---

## 📋 Содержание

- [Общая подготовка](#-общая-подготовка)
- [Способ A: Планировщик заданий](#-способ-a-планировщик-заданий)
- [Способ B: Служба через NSSM](#-способ-b-служба-через-nssm-рекомендуется)
- [Управление и логи](#-управление-и-логи)
- [Решение проблем](#-решение-проблем)

---

## 🔧 Общая подготовка

Убедитесь, что бот уже установлен и запускается вручную (см. [README_WINDOWS.md](README_WINDOWS.md)):

```powershell
cd $env:USERPROFILE\Documents\ha-telegram-bot
.\venv\Scripts\Activate.ps1
python bot.py
```

Если бот отвечает в Telegram — можно настраивать автозапуск.

Запомните пути (подставьте свои):

- Проект: `C:\Users\<Имя>\Documents\ha-telegram-bot`
- Python: `C:\Users\<Имя>\Documents\ha-telegram-bot\venv\Scripts\python.exe`

---

## 📅 Способ A: Планировщик заданий

Бот стартует при входе пользователя в систему и перезапускается при сбоях.

### Шаг 1: Создайте папку для логов

```powershell
mkdir $env:USERPROFILE\Documents\ha-telegram-bot\logs
```

### Шаг 2: Создайте задачу через PowerShell (администратор не нужен)

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Users\$env:USERNAME\Documents\ha-telegram-bot\venv\Scripts\python.exe" `
    -Argument "bot.py" -WorkingDirectory "C:\Users\$env:USERNAME\Documents\ha-telegram-bot"

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "HA Telegram Bot" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Telegram-бот для Home Assistant" -Force
```

### Шаг 3: Запустите задачу

```powershell
Start-ScheduledTask -TaskName "HA Telegram Bot"
```

Проверка статуса:

```powershell
Get-ScheduledTask -TaskName "HA Telegram Bot"
(Get-ScheduledTask -TaskName "HA Telegram Bot").State   # Running = работает
```

### Управление

```powershell
Start-ScheduledTask  -TaskName "HA Telegram Bot"   # запуск
Stop-ScheduledTask   -TaskName "HA Telegram Bot"   # остановка
Unregister-ScheduledTask -TaskName "HA Telegram Bot" -Confirm:$false  # удаление
```

Или через **Панель управления → Администрирование → Планировщик заданий**.

---

## ⚙️ Способ B: Служба через NSSM (рекомендуется)

[NSSM](https://nssm.cc) (Non-Sucking Service Manager) превращает любую программу в настоящую службу Windows: запуск до входа пользователя, автоперезапуск, перенаправление логов.

### Шаг 1: Установите NSSM

```powershell
winget install nssm
```

Или вручную: скачайте с [nssm.cc/download](https://nssm.cc/download), распакуйте `nssm.exe` (из папки `win64`) в `C:\Tools` и добавьте её в PATH.

Проверка:

```powershell
nssm version
```

### Шаг 2: Установите службу

**Через GUI (проще всего):**

```powershell
nssm install "HATelegramBot"
```

В открывшемся окне заполните:

| Поле | Значение |
|---|---|
| **Path** | `C:\Users\<Имя>\Documents\ha-telegram-bot\venv\Scripts\python.exe` |
| **Startup directory** | `C:\Users\<Имя>\Documents\ha-telegram-bot` |
| **Arguments** | `bot.py` |

Вкладка **I/O**:

| Поле | Значение |
|---|---|
| **Output (stdout)** | `C:\Users\<Имя>\Documents\ha-telegram-bot\logs\service.log` |
| **Error (stderr)** | `C:\Users\<Имя>\Documents\ha-telegram-bot\logs\service-error.log` |

(Папку `logs` создайте заранее: `mkdir logs`.)

Вкладка **Details**:

- **Display name:** `HA Telegram Bot`
- **Description:** `Telegram-бот для управления Home Assistant`
- **Startup type:** `Automatic`

Нажмите **Install service**.

**Или полностью через командную строку:**

```powershell
$dir = "C:\Users\$env:USERNAME\Documents\ha-telegram-bot"
nssm install "HATelegramBot" "$dir\venv\Scripts\python.exe" "bot.py"
nssm set "HATelegramBot" AppDirectory "$dir"
nssm set "HATelegramBot" AppStdout "$dir\logs\service.log"
nssm set "HATelegramBot" AppStderr "$dir\logs\service-error.log"
nssm set "HATelegramBot" AppRotateFiles 1
nssm set "HATelegramBot" AppRotateBytes 10485760
nssm set "HATelegramBot" Start SERVICE_AUTO_START
nssm set "HATelegramBot" Description "Telegram-бот для управления Home Assistant"
```

### Шаг 3: Запустите службу

```powershell
nssm start "HATelegramBot"
```

---

## 🎛️ Управление и логи

### Планировщик заданий

```powershell
Start-ScheduledTask -TaskName "HA Telegram Bot"
Stop-ScheduledTask  -TaskName "HA Telegram Bot"
```

Логи пишутся в журнал событий: **Просмотр событий → Журналы приложений и служб → Microsoft → Windows → TaskScheduler**.

### Служба NSSM

```powershell
nssm start    "HATelegramBot"   # запуск
nssm stop     "HATelegramBot"   # остановка (мягкая, таймеры сохранятся)
nssm restart  "HATelegramBot"   # перезапуск
nssm status   "HATelegramBot"   # статус
nssm remove   "HATelegramBot" confirm  # удаление службы
```

Логи (если настроены в I/O):

```powershell
Get-Content "$env:USERPROFILE\Documents\ha-telegram-bot\logs\service.log" -Wait -Tail 50
```

Общие команды Windows для службы:

```powershell
Get-Service "HATelegramBot"
Stop-Service "HATelegramBot"   # штатная остановка
```

> ✅ **Таймеры:** при штатной остановке (NSSM stop / Stop-Service) бот успевает сохранить активные таймеры в `data\timers.json` и восстановит их при следующем запуске.

---

## 🔄 Обновление

```powershell
cd $env:USERPROFILE\Documents\ha-telegram-bot
nssm stop "HATelegramBot"        # или Stop-ScheduledTask -TaskName "HA Telegram Bot"
git pull
.\venv\Scripts\Activate.ps1
pip install --upgrade -r requirements.txt
Deactivate
nssm start "HATelegramBot"       # или Start-ScheduledTask -TaskName "HA Telegram Bot"
```

---

## 🔧 Решение проблем

| Проблема | Решение |
|---|---|
| Служба стартует и сразу останавливается | Смотрите `logs\service-error.log` — чаще всего не заполнен `.env` или неверный токен |
| `nssm` не распознаётся | Добавьте папку с `nssm.exe` в PATH или указывайте полный путь: `C:\Tools\nssm.exe install ...` |
| Служба не стартует с ошибкой 1073/1072 | Служба уже существует: `nssm remove "HATelegramBot" confirm` и установите заново |
| Бот работает, но не отвечает | Ваш ID не в `ALLOWED_USER_IDS` — обновите `.env` и перезапустите службу |
| HA не достукивается до `:8099` | Разрешите порт в брандмауэре и проверьте, что `NOTIFY_PORT` в `.env` совпадает с открытым портом |
| Лог-файлы не создаются | Проверьте, что папка `logs` существует и у службы есть права на запись |
| Порт 8099 занят | `netstat -ano | findstr :8099` — смените `NOTIFY_PORT` в `.env` |

---

## ✅ Итог

| | Планировщик (A) | NSSM-служба (B) |
|---|---|---|
| Старт без входа пользователя | ❌ | ✅ |
| Перезапуск при сбое | ✅ | ✅ |
| Штатная остановка (сохранение таймеров) | ✅ | ✅ |
| Зависимости | нет | nssm.exe (один файл) |

**Приятного использования! 🏠✨**

---

*Документация актуальна на сентябрь 2026 года. Версия бота: 2.0*

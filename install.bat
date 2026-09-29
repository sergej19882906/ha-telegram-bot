@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Установка HA Telegram Bot (Windows)
echo   v2.0
echo ========================================
echo.

REM --- Проверка Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в PATH.
    echo Установите Python 3.11+ с https://www.python.org/downloads/
    echo ВАЖНО: отметьте галочку "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [ПРЕДУПРЕЖДЕНИЕ] Требуется Python 3.11+
    python --version
    echo.
)

REM --- Создание виртуального окружения ---
if not exist venv\Scripts\python.exe (
    echo [INFO] Создаю виртуальное окружение...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv
        pause
        exit /b 1
    )
)

REM --- Установка зависимостей ---
echo [INFO] Устанавливаю зависимости...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
if exist requirements.txt (
    pip install --upgrade -r requirements.txt --quiet
) else (
    pip install --upgrade "python-telegram-bot>=21" httpx pydantic python-dotenv aiohttp --quiet
)
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости
    pause
    exit /b 1
)

REM --- Создание .env ---
if not exist .env (
    if exist .env.example (
        echo [INFO] Копирую .env.example в .env...
        copy /y .env.example .env >nul
    ) else (
    echo [INFO] Создаю шаблон .env...
    (
        echo # Telegram bot token (от @BotFather^)
        echo TELEGRAM_BOT_TOKEN=
        echo.
        echo # Home Assistant settings
        echo HA_BASE_URL=http://localhost:8123
        echo HA_ACCESS_TOKEN=
        echo.
        echo # Разрешённые пользователи — Telegram ID через запятую (узнать ID: @userinfobot^)
        echo # ВНИМАНИЕ: если не задать, доступ к боту будет разрешён ВСЕМ!
        echo ALLOWED_USER_IDS=
        echo.
        echo # Язык по умолчанию: ru или en
        echo DEFAULT_LANG=ru
        echo.
        echo # --- Приёмник уведомлений из Home Assistant (опционально^) ---
        echo # NOTIFY_PORT=0 — приёмник выключен.
        echo NOTIFY_PORT=0
        echo NOTIFY_HOST=0.0.0.0
        echo NOTIFY_TOKEN=
    ) > .env
    echo.
    echo ============================================
    echo   ВАЖНО! Откройте файл .env и заполните его!
    echo ============================================
    echo Правый клик по .env -^> Открыть с помощью -^> Блокнот
    )
)

REM --- Папки для логов и данных ---
if not exist logs mkdir logs
if not exist data mkdir data

echo.
echo ========================================
echo   Установка завершена!
echo ========================================
echo.
echo Следующие шаги:
echo   1. Заполните .env (обязательно ALLOWED_USER_IDS!)
echo   2. Запустите: start.bat
echo.
pause

@echo off
chcp 65001 >nul
title Установка HA Telegram Bot

echo ==========================================
echo   Установка зависимостей бота
echo ==========================================
echo.

cd /d "%~dp0"

:: Создание виртуального окружения, если его нет
if not exist "venv" (
    echo [INFO] Создаю виртуальное окружение...
    python -m venv venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать venv. Убедитесь, что Python установлен.
        pause
        exit /b 1
    )
)

:: Активация
call venv\Scripts\activate.bat

:: Обновление pip
echo [INFO] Обновляю pip...
python -m pip install --upgrade pip

:: Установка зависимостей
echo [INFO] Устанавливаю зависимости...
pip install --upgrade "python-telegram-bot>=21" httpx pydantic python-dotenv

:: Создание .env, если его нет
if not exist ".env" (
    echo.
    echo [INFO] Создаю шаблон .env файла...
    (
        echo # Telegram bot token (от @BotFather^)
        echo TELEGRAM_BOT_TOKEN=
        echo.
        echo # Home Assistant settings
        echo HA_BASE_URL=http://localhost:8123
        echo HA_ACCESS_TOKEN=
        echo.
        echo # Ваш Telegram ID (защита от чужих пользователей^)
        echo ALLOWED_USER_ID=
        echo.
        echo # Язык по умолчанию: ru или en
        echo DEFAULT_LANG=ru
    ) > .env
    echo.
    echo ============================================
    echo  ВАЖНО! Откройте файл .env и заполните его!
    echo ============================================
)

echo.
echo [OK] Установка завершена!
echo Теперь запустите start.bat
pause
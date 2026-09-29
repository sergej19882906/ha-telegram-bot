@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Запуск HA Telegram Bot
echo ========================================
echo.

if not exist venv\Scripts\python.exe (
    echo [ОШИБКА] Виртуальное окружение не найдено!
    echo Запустите сначала: install.bat
    pause
    exit /b 1
)

if not exist .env (
    echo [ОШИБКА] Файл .env не найден!
    echo Запустите install.bat или создайте .env вручную.
    pause
    exit /b 1
)

findstr /R /C:"^TELEGRAM_BOT_TOKEN=." .env >nul
if errorlevel 1 (
    echo [ОШИБКА] В .env не заполнен TELEGRAM_BOT_TOKEN
    pause
    exit /b 1
)

findstr /R /C:"^HA_ACCESS_TOKEN=." .env >nul
if errorlevel 1 (
    echo [ОШИБКА] В .env не заполнен HA_ACCESS_TOKEN
    pause
    exit /b 1
)

findstr /R /C:"^ALLOWED_USER" .env | findstr /R "=[0-9]" >nul
if errorlevel 1 (
    echo [WARNING] Не заданы ALLOWED_USER_IDS - доступ к боту разрешён ВСЕМ!
    echo Рекомендуется указать Telegram ID в .env
    echo.
)

if not exist logs mkdir logs
if not exist data mkdir data

echo [INFO] Запуск бота... (для остановки нажмите Ctrl+C)
echo.
call venv\Scripts\activate.bat
python bot.py

echo.
echo [INFO] Бот остановлен
pause

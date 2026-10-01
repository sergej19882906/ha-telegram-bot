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
    findstr /R /C:"^ALLOW_ALL_USERS=1" .env >nul
    if errorlevel 1 (
        echo [ОШИБКА] Не заданы ALLOWED_USER_IDS - бот не запустится!
        echo Укажите Telegram ID в .env или явно разрешите открытый доступ: ALLOW_ALL_USERS=1
        pause
        exit /b 1
    ) else (
        echo [WARNING] ALLOWED_USER_IDS не задан, ALLOW_ALL_USERS=1 - доступ к боту разрешён ВСЕМ!
        echo.
    )
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

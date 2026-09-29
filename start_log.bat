@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Запуск HA Telegram Bot (с логированием)
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
    pause
    exit /b 1
)

if not exist logs mkdir logs
if not exist data mkdir data

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set LOGFILE=logs\bot_%TS%.log

echo [INFO] Логи пишутся в: %LOGFILE%
echo [INFO] Для остановки нажмите Ctrl+C
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0venv\Scripts\python.exe' bot.py 2>&1 | Tee-Object -FilePath '%~dp0%LOGFILE%'"

echo.
echo [INFO] Бот остановлен (лог: %LOGFILE%^)
pause

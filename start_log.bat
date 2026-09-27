@echo off
chcp 65001 >nul
title HA Telegram Bot (с логированием)

cd /d "%~dp0"
call venv\Scripts\activate.bat

if not exist "logs" mkdir logs
set LOGFILE=logs\bot.log

echo [INFO] Запуск бота. Логи пишутся в %LOGFILE%
python bot.py > %LOGFILE% 2>&1

pause
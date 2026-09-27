@echo off
echo Останавливаю все процессы python bot.py...
taskkill /F /FI "WINDOWTITLE eq HA Telegram Bot*" >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq HA Telegram Bot*" >nul 2>&1
echo Готово.
pause
@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Удаление HA Telegram Bot (Windows)
echo ========================================
echo.

echo [ВНИМАНИЕ] Это действие удалит:
echo   - Виртуальное окружение (venv\^)
echo   - Логи (logs\^)
echo   - Папку данных (data\^): языки пользователей и активные таймеры
echo   - Службу Windows (если установлена)
echo.
echo Файлы bot.py, .env, скрипты и документация будут сохранены.
echo.
set /p CONF=Вы уверены? [y/N]: 
if /i not "%CONF%"=="y" (
    echo Отменено.
    pause
    exit /b 0
)

REM --- Остановка запущенного бота ---
echo.
echo [INFO] Останавливаю бота...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*bot.py*' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force } }" >nul 2>nul

REM --- Удаление службы ---
sc query HATelegramBot >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Удаляю службу Windows...
    call "%~dp0uninstall_service.bat" >nul 2>nul
)

REM --- Удаление файлов ---
echo [INFO] Удаляю файлы...
if exist venv rmdir /s /q venv
if exist logs rmdir /s /q logs
if exist data rmdir /s /q data
del /q user_langs.json timers.json >nul 2>nul

echo.
echo ========================================
echo   Удаление завершено!
echo ========================================
echo Для полного удаления проекта удалите папку вручную.
echo.
pause

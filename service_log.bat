@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist logs\service.log (
    echo Лог не найден: %~dp0logs\service.log
    echo Служба пишет лог, если была установлена через install_service.bat
    echo.
    pause
    exit /b 1
)

echo Последние 50 строк лога (^Ctrl+C для выхода^):
echo.
powershell -NoProfile -Command "Get-Content '%~dp0logs\service.log' -Wait -Tail 50"

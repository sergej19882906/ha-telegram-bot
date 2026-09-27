@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: Цвета
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

echo %BLUE%========================================%NC%
echo %BLUE%  Логи службы HA Telegram Bot%NC%
echo %BLUE%========================================%NC%
echo.

cd /d "%~dp0"

if not exist "logs\service.log" (
    echo %YELLOW%[INFO] Файл логов не найден%NC%
    echo %YELLOW%Служба ещё не записывала логи%NC%
    pause
    exit /b 0
)

echo %BLUE%Последние 50 строк из service.log:%NC%
echo.

:: Вывод последних 50 строк
powershell -Command "Get-Content 'logs\service.log' -Tail 50"

echo.
echo %YELLOW%Полный лог: %CD%\logs\service.log%NC%
echo.

set /p OPEN="Открыть полный лог в Блокноте? (y/N): "
if /i "!OPEN!"=="y" (
    start notepad "logs\service.log"
)

pause
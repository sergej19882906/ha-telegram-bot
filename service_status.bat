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
echo %BLUE%  Статус службы HA Telegram Bot%NC%
echo %BLUE%========================================%NC%
echo.

set "SERVICE_NAME=HA-Telegram-Bot"

:: Проверка наличия NSSM
set "NSSM_PATH="
where nssm >nul 2>&1
if %errorLevel% equ 0 (
    set "NSSM_PATH=nssm"
) else if exist "nssm.exe" (
    set "NSSM_PATH=%CD%\nssm.exe"
) else (
    echo %RED%[ОШИБКА] NSSM не найден!%NC%
    pause
    exit /b 1
)

:: Получение статуса
echo %BLUE%Получение информации о службе...%NC%
echo.

"%NSSM_PATH%" status %SERVICE_NAME% >nul 2>&1
if %errorLevel% neq 0 (
    echo %RED%Служба не установлена%NC%
    echo.
    echo %YELLOW%Для установки выполните: install_service.bat%NC%
    pause
    exit /b 1
)

:: Вывод статуса
echo %BLUE%Имя службы: %SERVICE_NAME%%NC%
echo.
echo %BLUE%Статус:%NC%
"%NSSM_PATH%" status %SERVICE_NAME%
echo.

:: Получение дополнительных параметров
echo %BLUE%Конфигурация:%NC%
"%NSSM_PATH%" get %SERVICE_NAME% AppDirectory
"%NSSM_PATH%" get %SERVICE_NAME% DisplayName
"%NSSM_PATH%" get %SERVICE_NAME% Start
echo.

:: Проверка процесса
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq HA-Telegram-Bot*" >nul 2>&1
if %errorLevel% equ 0 (
    echo %GREEN%Процесс бота активен%NC%
) else (
    echo %YELLOW%Процесс бота не обнаружен%NC%
)

echo.
echo %YELLOW%Команды управления:%NC%
echo   net start %SERVICE_NAME%   - Запустить
echo   net stop %SERVICE_NAME%    - Остановить
echo   services.msc               - Открыть диспетчер служб
echo.

pause
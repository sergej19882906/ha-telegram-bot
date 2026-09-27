@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: Цвета
set "GREEN=[92m"
set "RED=[91m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "NC=[0m"

echo %RED%========================================%NC%
echo %RED%  Удаление службы HA Telegram Bot%NC%
echo %RED%========================================%NC%
echo.

:: Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo %RED%[ОШИБКА] Требуются права администратора!%NC%
    echo %YELLOW%Запустите скрипт от имени администратора%NC%
    pause
    exit /b 1
)

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
    echo %YELLOW%Невозможно удалить службу без NSSM%NC%
    pause
    exit /b 1
)

:: Проверка существования службы
"%NSSM_PATH%" status %SERVICE_NAME% >nul 2>&1
if %errorLevel% neq 0 (
    echo %YELLOW%[INFO] Служба %SERVICE_NAME% не найдена%NC%
    pause
    exit /b 0
)

echo %YELLOW%[ВНИМАНИЕ] Будет удалена служба: %SERVICE_NAME%%NC%
echo.
set /p CONFIRM="Вы уверены? (y/N): "
if /i not "!CONFIRM!"=="y" (
    echo %BLUE%[INFO] Удаление отменено%NC%
    pause
    exit /b 0
)

echo.
echo %BLUE%[INFO] Останавливаю службу...%NC%
"%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
timeout /t 2 /nobreak >nul

echo %BLUE%[INFO] Удаляю службу...%NC%
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >nul 2>&1

if %errorLevel% equ 0 (
    echo.
    echo %GREEN%========================================%NC%
    echo %GREEN%  Служба успешно удалена!%NC%
    echo %GREEN%========================================%NC%
    echo.
    echo %YELLOW%Примечание: Файлы проекта не были удалены.%NC%
    echo %YELLOW%Для полного удаления удалите папку проекта вручную.%NC%
) else (
    echo.
    echo %RED%[ОШИБКА] Не удалось удалить службу%NC%
    echo %YELLOW%Попробуйте удалить вручную через services.msc%NC%
)

echo.
pause
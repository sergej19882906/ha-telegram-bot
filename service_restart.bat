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
echo %BLUE%  Перезапуск службы HA Telegram Bot%NC%
echo %BLUE%========================================%NC%
echo.

:: Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo %RED%[ОШИБКА] Требуются права администратора!%NC%
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
    pause
    exit /b 1
)

:: Остановка
echo %BLUE%[INFO] Останавливаю службу...%NC%
"%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
timeout /t 2 /nobreak >nul

:: Запуск
echo %BLUE%[INFO] Запускаю службу...%NC%
"%NSSM_PATH%" start %SERVICE_NAME% >nul 2>&1
timeout /t 2 /nobreak >nul

:: Проверка
"%NSSM_PATH%" status %SERVICE_NAME% | findstr /I "SERVICE_RUNNING" >nul
if %errorLevel% equ 0 (
    echo.
    echo %GREEN%✅ Служба успешно перезапущена%NC%
) else (
    echo.
    echo %RED%❌ Ошибка при перезапуске службы%NC%
    echo %YELLOW%Проверьте логи в папке logs\%NC%
)

echo.
pause
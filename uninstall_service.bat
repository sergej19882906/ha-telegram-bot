@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo   Удаление службы Windows (NSSM)
echo   HA Telegram Bot
echo ========================================
echo.

REM --- Проверка прав администратора ---
net session >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Требуются права администратора.
    echo Правый клик -^> "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

REM --- Проверка, установлена ли служба ---
sc query HATelegramBot >nul 2>nul
if errorlevel 1 (
    echo [INFO] Служба HATelegramBot не установлена - удалять нечего.
    echo.
    pause
    exit /b 0
)

echo Будет удалена служба: HATelegramBot
echo Файлы проекта (bot.py, .env, venv) НЕ затрагиваются.
echo Активные таймеры сохранятся в data\timers.json.
echo.

if "%SKIP_CONFIRM%"=="1" goto :DO_REMOVE

set /p CONF=Продолжить? [y/N]: 
if /i not "%CONF%"=="y" (
    echo Отменено.
    pause
    exit /b 0
)

:DO_REMOVE
echo.
echo [INFO] Останавливаю службу...
nssm stop HATelegramBot

REM Даём до 10 секунд на штатное завершение (сохранение таймеров)
powershell -NoProfile -Command "foreach ($i in 1..10) { $s = Get-Service -Name 'HATelegramBot' -ErrorAction SilentlyContinue; if ($null -eq $s -or $s.Status -ne 'Running') { break }; Start-Sleep -Seconds 1 }" >nul 2>nul

echo [INFO] Удаляю службу...
nssm remove HATelegramBot confirm

sc query HATelegramBot >nul 2>nul
if not errorlevel 1 (
    echo [ОШИБКА] Служба не удалена полностью
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Служба удалена!
echo ========================================
echo Бот можно запускать вручную: start.bat
echo.
pause

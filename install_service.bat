@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Установка службы Windows (NSSM)
echo   HA Telegram Bot
echo ========================================
echo.

REM --- Проверка прав администратора ---
net session >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Требуются права администратора.
    echo Правый клик по install_service.bat -^> "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

REM --- Проверка NSSM ---
where nssm >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] NSSM не найден в PATH.
    echo Установите:  winget install nssm
    echo Или скачайте с https://nssm.cc/download и добавьте папку с nssm.exe в PATH.
    echo.
    pause
    exit /b 1
)

REM --- Проверка виртуального окружения ---
if not exist venv\Scripts\python.exe (
    echo [ОШИБКА] Виртуальное окружение не найдено!
    echo Запустите сначала: install.bat
    echo.
    pause
    exit /b 1
)

REM --- Проверка, не установлена ли уже служба ---
sc query HATelegramBot >nul 2>nul
if not errorlevel 1 (
    echo [ОШИБКА] Служба HATelegramBot уже установлена.
    echo Для переустановки сначала выполните: uninstall_service.bat
    echo.
    pause
    exit /b 1
)

echo Будет установлена служба: HATelegramBot
echo   Программа:  %~dp0venv\Scripts\python.exe
echo   Папка:      %~dp0
echo   Логи:       %~dp0logs\service.log
echo   Автозапуск: включён
echo.
set /p CONF=Продолжить? [y/N]: 
if /i not "%CONF%"=="y" (
    echo Отменено.
    pause
    exit /b 0
)

if not exist logs mkdir logs
if not exist data mkdir data

echo.
echo [INFO] Устанавливаю службу...
nssm install HATelegramBot "%~dp0venv\Scripts\python.exe" bot.py
nssm set HATelegramBot AppDirectory "%~dp0"
nssm set HATelegramBot AppStdout "%~dp0logs\service.log"
nssm set HATelegramBot AppStderr "%~dp0logs\service-error.log"
nssm set HATelegramBot AppRotateFiles 1
nssm set HATelegramBot AppRotateBytes 10485760
nssm set HATelegramBot Start SERVICE_AUTO_START
nssm set HATelegramBot Description "Telegram-bot dlya upravleniya Home Assistant"
nssm set HATelegramBot DisplayName "HA Telegram Bot"

echo [INFO] Запускаю службу...
nssm start HATelegramBot

echo.
echo ========================================
echo   Готово!
echo ========================================
echo Полезные команды:
echo   service_status.bat   - статус службы
echo   service_restart.bat  - перезапуск
echo   service_log.bat      - логи в реальном времени
echo   uninstall_service.bat - удаление службы
echo.
pause

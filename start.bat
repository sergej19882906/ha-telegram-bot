@echo off
chcp 65001 >nul
title HA Telegram Bot

echo ==========================================
echo   Запуск Telegram-бота для Home Assistant
echo ==========================================
echo.

:: Переход в папку со скриптом (на случай запуска из другого места)
cd /d "%~dp0"

:: Проверка наличия виртуального окружения
if not exist "venv\Scripts\activate.bat" (
    echo [ОШИБКА] Виртуальное окружение не найдено!
    echo Запустите сначала install.bat
    pause
    exit /b 1
)

:: Активация виртуального окружения
call venv\Scripts\activate.bat

:: Проверка наличия .env файла
if not exist ".env" (
    echo [ОШИБКА] Файл .env не найден!
    echo Создайте файл .env с настройками (см. пример в .env.example)
    pause
    exit /b 1
)

:: Запуск бота
echo [INFO] Запуск бота...
echo [INFO] Для остановки нажмите Ctrl+C
echo.
python bot.py

:: Если бот упал с ошибкой — окно не закроется сразу
echo.
echo [INFO] Бот остановлен.
pause
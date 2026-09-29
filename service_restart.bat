@echo off
chcp 65001 >nul

REM --- Проверка прав администратора ---
net session >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Требуются права администратора.
    echo Правый клик -^> "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

where nssm >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] NSSM не найден в PATH.
    pause
    exit /b 1
)

sc query HATelegramBot >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Служба HATelegramBot не установлена.
    echo Установите: install_service.bat
    pause
    exit /b 1
)

echo Перезапуск службы HATelegramBot...
nssm restart HATelegramBot
echo Готово.
pause

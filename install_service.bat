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
echo %BLUE%  Установка HA Telegram Bot как службы%NC%
echo %BLUE%========================================%NC%
echo.

:: Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo %RED%[ОШИБКА] Требуются права администратора!%NC%
    echo %YELLOW%Запустите скрипт от имени администратора%NC%
    echo %YELLOW%(Правый клик - Запуск от имени администратора)%NC%
    pause
    exit /b 1
)

:: Переход в директорию скрипта
cd /d "%~dp0"
set "PROJECT_DIR=%CD%"

echo %BLUE%[INFO] Директория проекта: %PROJECT_DIR%%NC%
echo.

:: Проверка наличия venv
if not exist "venv\Scripts\python.exe" (
    echo %RED%[ОШИБКА] Виртуальное окружение не найдено!%NC%
    echo %YELLOW%Запустите сначала install.bat%NC%
    pause
    exit /b 1
)

:: Проверка .env
if not exist ".env" (
    echo %RED%[ОШИБКА] Файл .env не найден!%NC%
    echo %YELLOW%Создайте и заполните файл .env%NC%
    pause
    exit /b 1
)

:: Проверка заполнения .env
findstr /C:"TELEGRAM_BOT_TOKEN=" .env | findstr /V /C:"TELEGRAM_BOT_TOKEN=$" >nul
if %errorLevel% neq 0 (
    echo %RED%[ОШИБКА] Не заполнен TELEGRAM_BOT_TOKEN в .env!%NC%
    pause
    exit /b 1
)

:: Проверка наличия NSSM
set "NSSM_PATH="
where nssm >nul 2>&1
if %errorLevel% equ 0 (
    set "NSSM_PATH=nssm"
) else (
    :: Проверяем локальный nssm
    if exist "nssm.exe" (
        set "NSSM_PATH=%CD%\nssm.exe"
    ) else (
        echo %YELLOW%[INFO] NSSM не найден. Скачиваю...%NC%
        echo.
        
        :: Скачивание NSSM
        powershell -Command "& { $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile 'nssm.zip' }"
        
        if not exist "nssm.zip" (
            echo %RED%[ОШИБКА] Не удалось скачать NSSM%NC%
            echo %YELLOW%Скачайте вручную: https://nssm.cc/download%NC%
            echo %YELLOW%и поместите nssm.exe в папку проекта%NC%
            pause
            exit /b 1
        )
        
        :: Распаковка
        echo %BLUE%[INFO] Распаковываю NSSM...%NC%
        powershell -Command "Expand-Archive -Path 'nssm.zip' -DestinationPath '.' -Force"
        
        :: Поиск nssm.exe в распакованной папке
        for /f "delims=" %%i in ('dir /s /b nssm.exe 2^>nul') do (
            set "NSSM_PATH=%%i"
            goto :found_nssm
        )
        
        :found_nssm
        if not defined NSSM_PATH (
            echo %RED%[ОШИБКА] nssm.exe не найден после распаковки%NC%
            pause
            exit /b 1
        )
        
        :: Копирование в папку проекта
        copy "!NSSM_PATH!" "nssm.exe" >nul
        set "NSSM_PATH=%CD%\nssm.exe"
        
        :: Удаление временных файлов
        del nssm.zip >nul 2>&1
        rmdir /s /q nssm-2.24 >nul 2>&1
        
        echo %GREEN%[OK] NSSM установлен%NC%
        echo.
    )
)

echo %BLUE%[INFO] NSSM: %NSSM_PATH%%NC%
echo.

:: Установка службы
set "SERVICE_NAME=HA-Telegram-Bot"
set "SERVICE_DISPLAY=HA Telegram Bot"
set "SERVICE_DESC=Telegram bot for Home Assistant automation"

echo %BLUE%[INFO] Устанавливаю службу: %SERVICE_NAME%%NC%

:: Остановка службы, если уже существует
"%NSSM_PATH%" stop %SERVICE_NAME% >nul 2>&1
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >nul 2>&1

:: Установка службы
"%NSSM_PATH%" install %SERVICE_NAME% "%PROJECT_DIR%\venv\Scripts\python.exe" "\"%PROJECT_DIR%\bot.py\""
if %errorLevel% neq 0 (
    echo %RED%[ОШИБКА] Не удалось установить службу%NC%
    pause
    exit /b 1
)

:: Настройка параметров службы
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%"
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "%SERVICE_DISPLAY%"
"%NSSM_PATH%" set %SERVICE_NAME% Description "%SERVICE_DESC%"
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_PATH%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM_PATH%" set %SERVICE_NAME% AppRestartDelay 10000
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%PROJECT_DIR%\logs\service.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%PROJECT_DIR%\logs\service_error.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateOnline 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 10485760

:: Создание папки для логов
if not exist "logs" mkdir logs

:: Запуск службы
echo %BLUE%[INFO] Запускаю службу...%NC%
"%NSSM_PATH%" start %SERVICE_NAME%
if %errorLevel% neq 0 (
    echo %RED%[ОШИБКА] Не удалось запустить службу%NC%
    pause
    exit /b 1
)

:: Проверка статуса
timeout /t 2 /nobreak >nul
"%NSSM_PATH%" status %SERVICE_NAME% | findstr /I "SERVICE_RUNNING" >nul
if %errorLevel% equ 0 (
    echo.
    echo %GREEN%========================================%NC%
    echo %GREEN%  Служба успешно установлена!%NC%
    echo %GREEN%========================================%NC%
    echo.
    echo %BLUE%Имя службы: %SERVICE_NAME%%NC%
    echo %BLUE%Отображаемое имя: %SERVICE_DISPLAY%%NC%
    echo %BLUE%Автозапуск: Включен%NC%
    echo %BLUE%Логи: %PROJECT_DIR%\logs\%NC%
    echo.
    echo %YELLOW%Полезные команды:%NC%
    echo   %BLUE%Проверить статус:%NC% service_status.bat
    echo   %BLUE%Остановить службу:%NC% net stop %SERVICE_NAME%
    echo   %BLUE%Запустить службу:%NC% net start %SERVICE_NAME%
    echo   %BLUE%Перезапустить:%NC% net stop %SERVICE_NAME% ^&^& net start %SERVICE_NAME%
    echo   %BLUE%Удалить службу:%NC% uninstall_service.bat
    echo.
    echo %YELLOW%Управление через Windows:%NC%
    echo   services.msc - найти "%SERVICE_DISPLAY%"
    echo.
) else (
    echo.
    echo %RED%[ОШИБКА] Служба не запустилась%NC%
    echo %YELLOW%Проверьте логи: %PROJECT_DIR%\logs\service.log%NC%
    echo.
)

pause
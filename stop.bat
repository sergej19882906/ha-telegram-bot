@echo off
chcp 65001 >nul
echo ========================================
echo   Остановка HA Telegram Bot
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*bot.py*' }; if (-not $p) { Write-Host '[INFO] Бот не запущен' } else { $p | ForEach-Object { Write-Host ('Останавливаю PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force } }"

echo.
echo Готово.
echo ВНИМАНИЕ: принудительная остановка НЕ сохраняет активные таймеры.
echo Для сохранения таймеров останавливайте бота через Ctrl+C в его окне.
pause

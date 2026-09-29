@echo off
chcp 65001 >nul

powershell -NoProfile -Command "$s = Get-Service -Name 'HATelegramBot' -ErrorAction SilentlyContinue; if ($null -eq $s) { Write-Host 'Служба HATelegramBot: НЕ УСТАНОВЛЕНА' } else { Write-Host ('Служба HATelegramBot: ' + $s.Status) }; $p = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*bot.py*' }; if ($p) { $p | ForEach-Object { Write-Host ('Процесс бота:     python.exe, PID ' + $_.ProcessId) } } else { Write-Host 'Процесс бота:     не запущен' }"

echo.
pause

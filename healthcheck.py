"""Healthcheck для Docker-контейнера.

Логика:
- NOTIFY_PORT > 0 (приёмник уведомлений включён): HTTP-запрос к
  http://127.0.0.1:<NOTIFY_PORT>/notify. Любой HTTP-ответ (401/405/404/200)
  означает, что процесс жив и event loop отвечает. Connection refused —
  unhealthy.
- NOTIFY_PORT = 0 (приёмник выключен): бот не имеет HTTP-сервера, поэтому
  проверяем, что главный процесс (PID 1, python работает через exec-форму CMD)
  жив — os.kill(1, 0). На Windows проверка PID 1 бессмысленна — считаем
  контейнер здоровым (в образе всё равно Linux).

Exit 0 — healthy, exit 1 — unhealthy.
"""

import os
import sys
import urllib.error
import urllib.request


def check_notify_endpoint(port: int) -> bool:
    """GET к /notify: любой HTTP-ответ = процесс жив (GET даёт 405)."""
    url = f"http://127.0.0.1:{port}/notify"
    try:
        with urllib.request.urlopen(url, timeout=5):
            return True
    except urllib.error.HTTPError:
        return True  # 401/404/405/... — сервер отвечает
    except (urllib.error.URLError, OSError):
        return False  # connection refused / таймаут — процесс мёртв или завис


def check_pid_one() -> bool:
    """Проверка, что PID 1 жив (python запущен в exec-форме CMD)."""
    if os.name != "posix":
        # Windows-хост: PID 1 не существует, проверять нечего
        return True
    try:
        os.kill(1, 0)
    except OSError:
        return False
    return True


def main() -> int:
    raw = os.environ.get("NOTIFY_PORT", "0")
    try:
        port = int(raw)
    except ValueError:
        port = 0

    if port > 0:
        ok = check_notify_endpoint(port)
    else:
        ok = check_pid_one()

    if not ok:
        print("unhealthy", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

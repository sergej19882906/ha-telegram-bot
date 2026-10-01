"""Конфигурация: логирование, переменные окружения, общие константы."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

BOT_VERSION = "3.0.0"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ha-bot")

load_dotenv()


def parse_int_env(name: str, default: int, min_val: Optional[int] = None) -> int:
    """Читает целочисленную переменную окружения с защитой от мусорных значений."""
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        logger.warning("Неверный %s=%r, использую %d", name, raw, default)
        value = default
    if min_val is not None:
        value = max(min_val, value)
    return value


DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ru")

# Интервал обновления реестра устройств из HA, секунды (минимум 15)
REFRESH_INTERVAL = parse_int_env("REFRESH_INTERVAL", 60, min_val=15)

# Интервал автопроверки цепочки уведомлений, секунды (0 = выключено; минимум 60)
WATCHDOG_INTERVAL = parse_int_env("NOTIFY_WATCHDOG_INTERVAL", 0, min_val=60)
# Имя rest_command в HA для прогона проверки (обязательно при интервале > 0)
WATCHDOG_COMMAND = os.environ.get("NOTIFY_WATCHDOG_COMMAND") or None

# Атрибуты, по которым определяем комнату (fallback, если нет area_registry)
ROOM_ATTRS = ("room_name", "area", "area_name", "location")

# Повторные попытки идемпотентных вызовов к HA (turn_on/turn_off/toggle):
# HA_RETRY_ATTEMPTS — число ДОПОЛНИТЕЛЬНЫХ попыток после первой неудачной,
# HA_RETRY_BASE_DELAY — базовая пауза в секундах (растёт экспоненциально:
# base, base*2, ...). Для установки значений (яркость/температура) повторы
# НЕ применяются — при частичном применении повтор может навредить.
HA_RETRY_ATTEMPTS = parse_int_env("HA_RETRY_ATTEMPTS", 2, min_val=0)
HA_RETRY_BASE_DELAY = 1.0

# Маппинг коротких токенов callback_data: вытеснение самых старых токенов
# при превышении CB_TOKEN_MAP_MAX (за один раз удаляется CB_TOKEN_EVICT)
CB_TOKEN_MAP_MAX = 3000
CB_TOKEN_EVICT = 1000
# Домены, которыми можно управлять кнопками
CONTROLLABLE_DOMAINS = {"light", "switch", "fan", "cover"}
# Домены, выключаемые командой /alloff
ALLOFF_DOMAINS = {"light", "switch", "fan", "cover"}
# Допустимый диапазон температуры для /set (climate)
TEMP_RANGE = (4.0, 40.0)
# Пресеты яркости в карточке света
BRIGHTNESS_PRESETS = (25, 50, 75, 100)


@dataclass
class Config:
    """Конфигурация бота."""
    token: Optional[str] = None
    base_url: str = "http://localhost:8123"
    ha_token: Optional[str] = None
    allowed_users: Optional[set] = None  # None = разрешены все
    timeout: int = 15
    notify_host: str = "0.0.0.0"
    notify_port: int = 0  # 0 = приёмник уведомлений выключен
    notify_token: Optional[str] = None
    notify_watchdog_interval: int = 0  # 0 = сторож уведомлений выключен
    notify_watchdog_command: Optional[str] = None  # rest_command для проверки


def parse_allowed_users() -> Optional[set]:
    """Разбирает ALLOWED_USER_IDS (список через запятую) или ALLOWED_USER_ID (один).

    Возвращает None, если список пуст — это ещё не «доступ всем»:
    решение принимает require_allowed_users() с учётом ALLOW_ALL_USERS.
    """
    raw = os.environ.get("ALLOWED_USER_IDS", "")
    users = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                users.add(int(part))
            except ValueError:
                logger.warning("Пропускаю неверный ALLOWED_USER_IDS: %r", part)
    if users:
        return users
    single = os.environ.get("ALLOWED_USER_ID", "")
    if single.strip():
        try:
            return {int(single)}
        except ValueError:
            logger.warning("Неверный ALLOWED_USER_ID: %r", single)
    return None


def require_allowed_users() -> Optional[set]:
    """Возвращает разрешённых пользователей либо завершает запуск с ошибкой.

    Пустой allowlist без явного ALLOW_ALL_USERS=1 — ошибка конфигурации:
    бот с открытым доступом не должен стартовать незаметно. Открытый доступ
    разрешён только при осознанно заданной переменной ALLOW_ALL_USERS=1.
    """
    users = parse_allowed_users()
    if users is not None:
        return users
    if os.environ.get("ALLOW_ALL_USERS", "") == "1":
        logger.warning("ALLOW_ALL_USERS=1 — доступ к боту разрешён ВСЕМ!")
        return None
    raise SystemExit(
        "ALLOWED_USER_IDS не задан или пуст — доступ никому не разрешён. "
        "Укажите Telegram ID через запятую в ALLOWED_USER_IDS (см. .env.example) "
        "или явно разрешите открытый доступ переменной ALLOW_ALL_USERS=1."
    )

"""
Telegram-бот для Home Assistant с интерактивным меню и локализацией.
Поддержка Docker: данные сохраняются в /app/data (или DATA_DIR).

Возможности:
- Управление устройствами (on/off/toggle/set), сцены, комнаты (area_registry),
  таймеры (сохраняются между перезапусками), многоязычность (ru/en)
- Несколько разрешённых пользователей (ALLOWED_USER_IDS)
- HTTP-приёмник уведомлений из Home Assistant (NOTIFY_PORT / NOTIFY_TOKEN)
- Поиск устройств по подстроке, /alloff с подтверждением

Версия 2.1:
- /timers — список активных таймеров с кнопками отмены
- Пресеты яркости (25/50/75/100%) в карточке света
- Поиск по подстроке в командах /on /off /toggle /scene
- REFRESH_INTERVAL — интервал обновления реестра через .env
- Валидация диапазона температуры для /set (4–40)
- Приёмник уведомлений не роняет бота при занятом порте

Версия 2.1.1:
- Исправления: клавиатура на разбитых сообщениях, неоднозначные алиасы,
  битые записи таймеров, /scene без ответа, HA_TIMEOUT, локализация «мин»
- Таймеры сохраняются при каждом изменении (не только при shutdown)
- Rate limit на /notify (20 запросов/мин)

Версия 2.1.2:
- Реестры комнат: фолбэк с REST (404/410 в новых HA) на websocket API
- Warning о недоступности реестров пишется один раз, а не каждый цикл
- Фоновая задача обновления реестра без предупреждения PTB
"""

import asyncio
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# aiohttp нужен для приёмника уведомлений (NOTIFY_PORT) и websocket-запросов к HA
try:
    import aiohttp
    from aiohttp import web
except ImportError:
    aiohttp = None
    web = None

BOT_VERSION = "2.1.2"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ha-bot")

load_dotenv()


def esc(text) -> str:
    """Экранирует HTML-символы для безопасной отправки в Telegram."""
    return html.escape(str(text)) if text is not None else ""


# ---------- Локализация ----------

MESSAGES = {
    "ru": {
        "welcome": "👋 Привет! Я бот для управления вашим умным домом.\n\nОтправьте /menu, чтобы открыть меню.",
        "main_menu_title": "📋 <b>Главное меню</b>\n\nВыберите раздел:",
        "btn_control": "🎛 Управление",
        "btn_status": "📊 Статус",
        "btn_rooms": "🏠 Комнаты",
        "btn_scenes": "🎬 Сцены",
        "btn_settings": "⚙️ Настройки",
        "btn_help": "❓ Помощь",
        "btn_back": "◀️ Назад",
        "btn_main_menu": "🏠 Главное меню",
        "control_title": "🎛 <b>Управление устройствами</b>\n\nВыберите действие:",
        "btn_on": "✅ Включить",
        "btn_off": "❌ Выключить",
        "btn_toggle": "🔄 Переключить",
        "status_title": "📊 <b>Статус устройств</b>\n\nЧто показать?",
        "btn_all_devices": "📋 Все устройства",
        "btn_lights": "💡 Свет",
        "btn_switches": "🔌 Розетки",
        "btn_climate": "🌡 Климат",
        "btn_fans": "💨 Вентиляторы",
        "rooms_title": "🏠 <b>Комнаты</b>\n\nВыберите комнату:",
        "scenes_title": "🎬 <b>Сцены</b>\n\nВыберите сцену:",
        "settings_title": "⚙️ <b>Настройки</b>\n\nЧто изменить?",
        "btn_lang": "🌐 Язык",
        "btn_ha_status": "🔗 Статус Home Assistant",
        "select_device": "📱 <b>{action}</b>\n\nВыберите устройство:",
        "choose_lang": "🌐 Выберите язык / Choose language:",
        "lang_set": "✅ Язык изменён на русский.",
        "not_found": "❌ Устройство не найдено.",
        "device_not_found": "❌ Устройство «{name}» не найдено.",
        "device_unavailable": "⚠️ Устройство «{name}» сейчас недоступно.",
        "scene_not_found": "❌ Сцена «{name}» не найдена.",
        "empty_list": "📭 Список устройств пуст.",
        "empty_list_short": "📭 Список пуст.",
        "list_truncated": "\n\n… (список обрезан, уточните фильтр)",
        "scene_applied": "🎬 Сцена «{name}» активирована.",
        "ha_online": "✅ Home Assistant: онлайн",
        "ha_offline": "❌ Home Assistant: недоступен",
        "turned_on": "✅ <b>{name}</b> включено.",
        "turned_off": "🔌 <b>{name}</b> выключено.",
        "toggled": "🔄 <b>{name}</b> — состояние изменено.",
        "current_state": "ℹ️ <b>{name}</b>\nСостояние: <code>{state}</code>",
        "unknown": "неизвестно",
        "error": "❌ Ошибка: {err}",
        "value_set": "✅ Установлено значение: {value}.",
        "set_usage": "⚠️ Использование: /set <имя> <значение>\nДля света — яркость в % (0–100), для климата — температура (4–40).",
        "set_not_number": "⚠️ Значение должно быть числом, например: /set свет 50",
        "set_temp_range": "⚠️ Температура должна быть в диапазоне 4–40.",
        "set_unsupported": "❌ Для устройства «{name}» установка значений не поддерживается (только свет и климат).",
        "timer_started": "⏳ Таймер запущен для <code>{eid}</code>.\nУстройство выключится через {minutes} мин.",
        "timer_fired": "⏰ Таймер сработал: устройство <code>{eid}</code> выключено через {minutes} мин.",
        "timer_replaced": "♻️ Предыдущий таймер для этого устройства отменён.",
        "timer_restored": "♻️ Восстановлен таймер для <code>{eid}</code> (осталось {minutes} мин).",
        "timer_cancelled": "🚫 Таймер для <code>{eid}</code> отменён.",
        "timers_empty": "⏳ Активных таймеров нет.",
        "timers_title": "⏳ <b>Активные таймеры: {count}</b>\n\nНажмите на таймер, чтобы отменить:",
        "timer_min": "мин",
        "room_not_found": "🔍 В комнате «{room}» устройств не найдено.",
        "room_title": "🏠 <b>Комната «{room}»:</b>",
        "all_devices_title": "📋 <b>Все устройства:</b>",
        "devices_of_type_title": "📋 <b>Устройства типа {domain}:</b>",
        "state_label": "Состояние:",
        "attrs_label": "Атрибуты:",
        "state_on": "включено",
        "state_off": "выключено",
        "state_unavailable": "недоступно",
        "state_on_short": "вкл",
        "state_off_short": "выкл",
        "help_text": (
            "📋 <b>Список команд:</b>\n\n"
            "<code>/menu</code> — открыть меню\n"
            "<code>/hide</code> — скрыть меню\n"
            "<code>/lang</code> — сменить язык\n"
            "<code>/on</code> <i>имя</i> — включить\n"
            "<code>/off</code> <i>имя</i> — выключить\n"
            "<code>/toggle</code> <i>имя</i> — переключить\n"
            "<code>/set</code> <i>имя значение</i> — яркость света в % или температура климата\n"
            "<code>/state</code> [<i>имя</i>] — статус (без имени — все устройства)\n"
            "<code>/room</code> <i>комната</i> — устройства в комнате\n"
            "<code>/scene</code> <i>имя</i> — активировать сцену\n"
            "<code>/timer</code> <i>мин имя</i> — таймер выключения\n"
            "<code>/timers</code> — список и отмена таймеров\n"
            "<code>/alloff</code> — выключить весь свет и розетки\n"
            "<code>/status</code> — статус HA\n\n"
            "💡 Просто напишите имя устройства — покажу его статус и кнопки."
        ),
        "menu_hidden": "🙈 Меню скрыто. Используйте /menu, чтобы вернуть.",
        "no_rooms": "🔍 Комнаты не найдены.",
        "no_scenes": "🔍 Сцены не найдены.",
        "cb_expired": "⚠️ Данные кнопки устарели. Отправьте /menu заново.",
        "device_hint": "Найдено устройство. Выберите действие:",
        "search_title": "🔎 <b>Найдено устройств: {count}</b>\n\nВыберите:",
        "search_empty": "🔍 По запросу «{q}» ничего не найдено.",
        "search_more": "\n\n… и ещё {n} — уточните запрос",
        "alloff_confirm": "⚠️ <b>Выключить ВСЁ?</b>\n\nБудут выключены все устройства типов: свет, розетки, вентиляторы, шторы ({count} шт.).",
        "alloff_btn_yes": "✅ Да, выключить всё",
        "alloff_btn_no": "🚫 Отмена",
        "alloff_cancelled": "🚫 Отменено.",
        "alloff_done": "🔌 Выключено устройств: {count}.",
        "alloff_error": "❌ Ошибка при массовом выключении: {err}",
    },
    "en": {
        "welcome": "👋 Hello! I'm your smart home control bot.\n\nSend /menu to open the menu.",
        "main_menu_title": "📋 <b>Main menu</b>\n\nChoose a section:",
        "btn_control": "🎛 Control",
        "btn_status": "📊 Status",
        "btn_rooms": "🏠 Rooms",
        "btn_scenes": "🎬 Scenes",
        "btn_settings": "⚙️ Settings",
        "btn_help": "❓ Help",
        "btn_back": "◀️ Back",
        "btn_main_menu": "🏠 Main menu",
        "control_title": "🎛 <b>Device control</b>\n\nChoose an action:",
        "btn_on": "✅ Turn on",
        "btn_off": "❌ Turn off",
        "btn_toggle": "🔄 Toggle",
        "status_title": "📊 <b>Device status</b>\n\nWhat to show?",
        "btn_all_devices": "📋 All devices",
        "btn_lights": "💡 Lights",
        "btn_switches": "🔌 Switches",
        "btn_climate": "🌡 Climate",
        "btn_fans": "💨 Fans",
        "rooms_title": "🏠 <b>Rooms</b>\n\nChoose a room:",
        "scenes_title": "🎬 <b>Scenes</b>\n\nChoose a scene:",
        "settings_title": "⚙️ <b>Settings</b>\n\nWhat to change?",
        "btn_lang": "🌐 Language",
        "btn_ha_status": "🔗 Home Assistant status",
        "select_device": "📱 <b>{action}</b>\n\nChoose a device:",
        "choose_lang": "🌐 Choose language / Выберите язык:",
        "lang_set": "✅ Language changed to English.",
        "not_found": "❌ Device not found.",
        "device_not_found": "❌ Device «{name}» not found.",
        "device_unavailable": "⚠️ Device «{name}» is currently unavailable.",
        "scene_not_found": "❌ Scene «{name}» not found.",
        "empty_list": "📭 Device list is empty.",
        "empty_list_short": "📭 List is empty.",
        "list_truncated": "\n\n… (list truncated, narrow the filter)",
        "scene_applied": "🎬 Scene «{name}» activated.",
        "ha_online": "✅ Home Assistant: online",
        "ha_offline": "❌ Home Assistant: offline",
        "turned_on": "✅ <b>{name}</b> turned on.",
        "turned_off": "🔌 <b>{name}</b> turned off.",
        "toggled": "🔄 <b>{name}</b> — state changed.",
        "current_state": "ℹ️ <b>{name}</b>\nState: <code>{state}</code>",
        "unknown": "unknown",
        "error": "❌ Error: {err}",
        "value_set": "✅ Value set to: {value}.",
        "set_usage": "⚠️ Usage: /set <name> <value>\nFor lights — brightness in % (0–100), for climate — temperature (4–40).",
        "set_not_number": "⚠️ Value must be a number, e.g.: /set light 50",
        "set_temp_range": "⚠️ Temperature must be between 4 and 40.",
        "set_unsupported": "❌ Setting values is not supported for «{name}» (lights and climate only).",
        "timer_started": "⏳ Timer started for <code>{eid}</code>.\nDevice will turn off in {minutes} min.",
        "timer_fired": "⏰ Timer fired: device <code>{eid}</code> turned off after {minutes} min.",
        "timer_replaced": "♻️ Previous timer for this device was cancelled.",
        "timer_restored": "♻️ Restored timer for <code>{eid}</code> ({minutes} min left).",
        "timer_cancelled": "🚫 Timer for <code>{eid}</code> cancelled.",
        "timers_empty": "⏳ No active timers.",
        "timers_title": "⏳ <b>Active timers: {count}</b>\n\nTap a timer to cancel it:",
        "timer_min": "min",
        "room_not_found": "🔍 No devices found in room «{room}».",
        "room_title": "🏠 <b>Room «{room}»:</b>",
        "all_devices_title": "📋 <b>All devices:</b>",
        "devices_of_type_title": "📋 <b>Devices of type {domain}:</b>",
        "state_label": "State:",
        "attrs_label": "Attributes:",
        "state_on": "on",
        "state_off": "off",
        "state_unavailable": "unavailable",
        "state_on_short": "on",
        "state_off_short": "off",
        "help_text": (
            "📋 <b>Commands list:</b>\n\n"
            "<code>/menu</code> — open menu\n"
            "<code>/hide</code> — hide menu\n"
            "<code>/lang</code> — change language\n"
            "<code>/on</code> <i>name</i> — turn on\n"
            "<code>/off</code> <i>name</i> — turn off\n"
            "<code>/toggle</code> <i>name</i> — toggle\n"
            "<code>/set</code> <i>name value</i> — light brightness in % or climate temperature\n"
            "<code>/state</code> [<i>name</i>] — status (all devices without a name)\n"
            "<code>/room</code> <i>room</i> — devices in room\n"
            "<code>/scene</code> <i>name</i> — activate scene\n"
            "<code>/timer</code> <i>min name</i> — turn-off timer\n"
            "<code>/timers</code> — list and cancel timers\n"
            "<code>/alloff</code> — turn off all lights and switches\n"
            "<code>/status</code> — HA status\n\n"
            "💡 Just type a device name — I'll show its status and buttons."
        ),
        "menu_hidden": "🙈 Menu hidden. Use /menu to show it again.",
        "no_rooms": "🔍 No rooms found.",
        "no_scenes": "🔍 No scenes found.",
        "cb_expired": "⚠️ This button data is stale. Send /menu again.",
        "device_hint": "Device found. Choose an action:",
        "search_title": "🔎 <b>Devices found: {count}</b>\n\nChoose one:",
        "search_empty": "🔍 Nothing found for «{q}».",
        "search_more": "\n\n… and {n} more — narrow your query",
        "alloff_confirm": "⚠️ <b>Turn off EVERYTHING?</b>\n\nAll lights, switches, fans and covers will be turned off ({count} devices).",
        "alloff_btn_yes": "✅ Yes, turn everything off",
        "alloff_btn_no": "🚫 Cancel",
        "alloff_cancelled": "🚫 Cancelled.",
        "alloff_done": "🔌 Devices turned off: {count}.",
        "alloff_error": "❌ Error during mass turn-off: {err}",
    },
}

# Путь к файлам данных
# В Docker: /app/data/
# Локально: рядом со скриптом
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
LANG_FILE = DATA_DIR / "user_langs.json"
TIMERS_FILE = DATA_DIR / "timers.json"
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ru")

# Интервал обновления реестра устройств из HA, секунды (минимум 15)
try:
    REFRESH_INTERVAL = max(15, int(os.environ.get("REFRESH_INTERVAL") or 60))
except ValueError:
    REFRESH_INTERVAL = 60

# Атрибуты, по которым определяем комнату (fallback, если нет area_registry)
ROOM_ATTRS = ("room_name", "area", "area_name", "location")
# Домены, которыми можно управлять кнопками
CONTROLLABLE_DOMAINS = {"light", "switch", "fan", "cover"}
# Домены, выключаемые командой /alloff
ALLOFF_DOMAINS = {"light", "switch", "fan", "cover"}
# Допустимый диапазон температуры для /set (climate)
TEMP_RANGE = (4.0, 40.0)
# Пресеты яркости в карточке света
BRIGHTNESS_PRESETS = (25, 50, 75, 100)


def load_user_langs() -> dict:
    """Загружает выбранные языки пользователей из файла."""
    if LANG_FILE.exists():
        try:
            return json.loads(LANG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Не удалось прочитать %s: %s", LANG_FILE, e)
    return {}


def save_user_langs(langs: dict):
    """Сохраняет выбранные языки пользователей в файл."""
    try:
        LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LANG_FILE.write_text(
            json.dumps(langs, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning("Не удалось записать %s: %s", LANG_FILE, e)


USER_LANGS = load_user_langs()


def get_lang(user_id: Optional[int]) -> str:
    """Возвращает выбранный язык для пользователя."""
    if user_id is None:
        return DEFAULT_LANG
    return USER_LANGS.get(str(user_id), DEFAULT_LANG)


def set_lang(user_id: int, lang: str):
    """Устанавливает язык для пользователя."""
    if lang not in MESSAGES:
        return
    USER_LANGS[str(user_id)] = lang
    save_user_langs(USER_LANGS)


def t(user_id: Optional[int], key: str, **kwargs) -> str:
    """Возвращает локализованную строку."""
    lang = get_lang(user_id)
    text = MESSAGES.get(lang, MESSAGES["ru"]).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def state_localized(user_id: Optional[int], state: str, short: bool = False) -> str:
    """Локализует стандартные состояния HA (on/off/unavailable)."""
    if state == "on":
        return t(user_id, "state_on_short" if short else "state_on")
    if state == "off":
        return t(user_id, "state_off_short" if short else "state_off")
    if state == "unavailable":
        return t(user_id, "state_unavailable")
    return state


# ---------- HA Client ----------

class HAError(Exception):
    """Ошибка при работе с Home Assistant."""
    pass


class HAClient:
    """Асинхронный клиент для работы с Home Assistant REST API."""

    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {token}"}
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=self.timeout,
        )

    async def close(self):
        """Закрывает HTTP-клиент."""
        await self.client.aclose()

    async def get_json(self, path: str, params: Optional[dict] = None):
        """Выполняет GET-запрос и возвращает JSON."""
        r = await self.client.get(path, params=params)
        if r.status_code == 401:
            raise HAError("Invalid HA access token.")
        r.raise_for_status()
        return r.json()

    async def post_json(self, path: str, body: dict):
        """Выполняет POST-запрос и возвращает JSON."""
        r = await self.client.post(path, json=body, timeout=self.timeout)
        if r.status_code == 401:
            raise HAError("Invalid HA access token.")
        r.raise_for_status()
        return r.json()

    async def healthcheck(self) -> bool:
        """Проверяет доступность Home Assistant."""
        try:
            r = await self.client.get("/api/", timeout=self.timeout)
            return r.status_code == 200
        except Exception:
            return False

    async def get_entity(self, entity_id: str) -> dict:
        """Получает состояние одного устройства."""
        return await self.get_json(f"/api/states/{entity_id}")

    async def get_entities(self, domain: Optional[str] = None) -> list:
        """Получает список всех устройств (опционально по домену)."""
        params = {"domain": domain} if domain else {}
        data = await self.get_json("/api/states", params=params)
        return data if isinstance(data, list) else data.get("entities", [])

    async def get_entity_ids_by_domain(self, domain: Optional[str] = None) -> dict:
        """Возвращает словарь {entity_id: entity_data}."""
        entities = await self.get_entities(domain=domain)
        return {e["entity_id"]: e for e in entities if "entity_id" in e}

    async def turn_on(self, entity_id: str, **kwargs):
        """Включает устройство."""
        domain, _, _ = entity_id.rpartition(".")
        return await self.post_json(
            f"/api/services/{domain}/turn_on",
            {"entity_id": entity_id, **kwargs}
        )

    async def turn_off(self, entity_id: str, **kwargs):
        """Выключает устройство."""
        domain, _, _ = entity_id.rpartition(".")
        return await self.post_json(
            f"/api/services/{domain}/turn_off",
            {"entity_id": entity_id, **kwargs}
        )

    async def set_value(self, entity_id: str, value: float):
        """Устанавливает значение.

        - light: value трактуется как яркость в процентах (0–100),
          при value > 100 — как сырое значение 0–255.
        - climate: температура.
        """
        domain, _, _ = entity_id.rpartition(".")
        if domain == "light":
            if value <= 100:
                brightness = round(value * 255 / 100)
            else:
                brightness = round(value)
            brightness = max(0, min(255, int(brightness)))
            return await self.post_json(
                "/api/services/light/turn_on",
                {"entity_id": entity_id, "brightness": brightness},
            )
        if domain == "climate":
            return await self.post_json(
                "/api/services/climate/set_temperature",
                {"entity_id": entity_id, "temperature": value},
            )
        raise HAError(f"Unsupported entity type for set: {domain}")

    async def apply_scene(self, scene_id: str):
        """Активирует сцену."""
        return await self.post_json(
            "/api/services/scene/turn_on",
            {"entity_id": scene_id}
        )


class EntityRegistry:
    """Реестр устройств Home Assistant с алиасами, комнатами и сценами."""

    def __init__(self, ha: HAClient):
        self.ha = ha
        self._entities: dict = {}
        self._aliases: dict = {}
        # area_id -> название комнаты
        self._area_names: dict = {}
        # area_id -> [entity_id]
        self._area_entities: dict = {}
        # Алиасы, встречающиеся у нескольких устройств (исключаем из точного поиска)
        self._ambiguous: set = set()
        # Предупреждение о недоступности реестров пишется один раз
        self._area_warned = False

    async def refresh(self):
        """Обновляет список устройств из Home Assistant."""
        states = await self.ha.get_entity_ids_by_domain()
        self._entities = states

        self._aliases = {}
        self._ambiguous = set()
        alias_dupes = 0
        for eid, data in self._entities.items():
            attrs = data.get("attributes", {})
            fname = attrs.get("friendly_name")
            if fname:
                alias = re.sub(r"[^\w\s-]", "", fname).strip().lower()
                if alias and alias != eid.split(".")[-1].lower():
                    if alias in self._aliases:
                        alias_dupes += 1
                        self._ambiguous.add(alias)
                    else:
                        self._aliases[alias] = eid
        # Неоднозначные алиасы исключаем из точного поиска: иначе /off <имя>
        # выключило бы случайное из одноимённых устройств. Такие устройства
        # по-прежнему находятся подстрочным поиском с выбором кнопками.
        for alias in self._ambiguous:
            self._aliases.pop(alias, None)
        if alias_dupes:
            logger.warning(
                "Дублирующиеся имена устройств: %d — такие имена исключены из точного "
                "поиска, используйте подстрочный (/state <часть имени>)",
                alias_dupes,
            )

        await self._load_area_map()

    async def _load_area_map(self):
        """Загружает соответствие комнат (areas) и устройств из реестров HA.

        Сначала пробует REST-endpoints, при 404/410 (в новых версиях HA
        они удалены) — websocket API. При полной недоступности оставляет
        пустой словарь — комнаты будут искаться по атрибутам (fallback).
        """
        self._area_names = {}
        self._area_entities = {}
        try:
            areas, devices, ent_reg = await self._fetch_registries()
        except Exception as e:
            # Пишем предупреждение один раз, а не при каждом обновлении реестра
            if not self._area_warned:
                logger.warning(
                    "Реестры комнат недоступны (%s: %s) — комнаты будут искаться по атрибутам",
                    type(e).__name__, e
                )
                self._area_warned = True
            return
        self._area_warned = False

        for a in areas:
            aid = a.get("area_id")
            name = a.get("name")
            if aid and name:
                self._area_names[aid] = name

        dev_area = {d.get("id"): d.get("area_id") for d in devices if d.get("id")}
        for e in ent_reg:
            eid = e.get("entity_id")
            aid = e.get("area_id") or dev_area.get(e.get("device_id"))
            if eid and aid:
                self._area_entities.setdefault(aid, []).append(eid)

    async def _fetch_registries(self):
        """Получает area/device/entity registry: REST (старые HA) или websocket (новые)."""
        try:
            return (
                await self.ha.get_json("/api/config/area_registry/list"),
                await self.ha.get_json("/api/config/device_registry/list"),
                await self.ha.get_json("/api/config/entity_registry/list"),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code not in (404, 410):
                raise
        # В новых версиях HA REST-endpoints реестров удалены — используем websocket API
        return await self._fetch_registries_ws()

    async def _fetch_registries_ws(self):
        """Достаёт реестры через websocket API HA (авторизация по токену)."""
        if aiohttp is None:
            raise HAError("aiohttp не установлен — websocket API недоступен")
        ws_url = self.ha.base_url.replace("http://", "ws://", 1)
        ws_url = ws_url.replace("https://", "wss://", 1).rstrip("/") + "/api/websocket"
        timeout = aiohttp.ClientTimeout(total=max(20, self.ha.timeout * 2))

        async def recv(ws):
            return await asyncio.wait_for(ws.receive_json(), timeout=self.ha.timeout)

        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.ws_connect(ws_url) as ws:
                if (await recv(ws)).get("type") != "auth_required":
                    raise HAError("HA websocket: неожиданный ответ при подключении")
                await ws.send_json({"type": "auth", "access_token": self.ha.token})
                if (await recv(ws)).get("type") != "auth_ok":
                    raise HAError("HA websocket: авторизация отклонена (проверьте токен)")

                msg_id = 0

                async def call(msg_type):
                    nonlocal msg_id
                    msg_id += 1
                    await ws.send_json({"id": msg_id, "type": msg_type})
                    while True:
                        resp = await recv(ws)
                        if resp.get("id") != msg_id:
                            continue  # пропускаем незапрошенные события
                        if not resp.get("success"):
                            raise HAError(f"HA websocket {msg_type}: {resp.get('error')}")
                        return resp.get("result", [])

                return (
                    await call("config/area_registry/list"),
                    await call("config/device_registry/list"),
                    await call("config/entity_registry/list"),
                )

    def by_id_or_alias(self, text: str) -> Optional[str]:
        """Ищет устройство по entity_id или алиасу."""
        if not text:
            return None
        s = text.strip()
        if s in self._entities:
            return s
        return self._aliases.get(s.lower())

    def search(self, query: str, limit: int = 20) -> list:
        """Ищет устройства по подстроке в имени или entity_id."""
        q = query.strip().lower()
        if not q:
            return []
        results = []
        for eid, data in self._entities.items():
            fname = data.get("attributes", {}).get("friendly_name", "")
            if q in eid.lower() or q in fname.lower():
                results.append(eid)
        # Точное вхождение в начало имени — вперёд
        results.sort(key=lambda e: (
            0 if self.get_friendly_name(e).lower().startswith(q) else 1,
            self.get_friendly_name(e).lower(),
        ))
        return results[:limit]

    def list_entities(self, domain: Optional[str] = None) -> list:
        """Возвращает список entity_id (опционально по домену)."""
        if not domain:
            return sorted(list(self._entities.keys()))
        return sorted([k for k in self._entities if k.split(".")[0] == domain])

    def get_rooms(self) -> list:
        """Возвращает список комнат: из area_registry + из атрибутов устройств."""
        rooms = set()

        # 1. Комнаты из area_registry, в которых есть устройства
        for aid, eids in self._area_entities.items():
            if any(eid in self._entities for eid in eids):
                name = self._area_names.get(aid)
                if name:
                    rooms.add(name)

        # 2. Fallback: атрибуты устройств
        for data in self._entities.values():
            attrs = data.get("attributes", {})
            for key in ROOM_ATTRS:
                room = attrs.get(key)
                if room is None:
                    continue
                if isinstance(room, list):
                    if room and isinstance(room[0], str) and room[0].strip():
                        rooms.add(room[0].strip())
                        break
                    continue  # пустой атрибут — проверяем следующий ключ
                if isinstance(room, str) and room.strip():
                    rooms.add(room.strip())
                    break
        return sorted(list(rooms))

    def find_room_area_id(self, room_name: str) -> Optional[str]:
        """Ищет area_id по названию комнаты (регистронезависимо)."""
        target = room_name.strip().lower()
        for aid, name in self._area_names.items():
            if name.strip().lower() == target:
                return aid
        # Частичное совпадение
        for aid, name in self._area_names.items():
            if target in name.strip().lower():
                return aid
        return None

    def entities_in_room(self, room_name: str) -> list:
        """Возвращает entity_id устройств в комнате.

        Сначала ищет по area_registry, затем — по атрибутам.
        """
        found: list = []

        # 1. По area_registry
        aid = self.find_room_area_id(room_name)
        if aid:
            found = [e for e in self._area_entities.get(aid, []) if e in self._entities]

        # 2. Fallback / дополнение по атрибутам
        target = room_name.strip().lower()
        for eid, data in self._entities.items():
            if eid in found:
                continue
            attrs = data.get("attributes", {})
            for key in ROOM_ATTRS:
                room = attrs.get(key)
                if room is None:
                    continue
                if isinstance(room, list):
                    room = room[0] if room else None
                if isinstance(room, str) and target in room.lower():
                    found.append(eid)
                    break

        return sorted(found)

    def get_scenes(self) -> list:
        """Возвращает список всех сцен."""
        return sorted([eid for eid in self._entities if eid.startswith("scene.")])

    def get_friendly_name(self, eid: str) -> str:
        """Возвращает человеко-читаемое имя устройства."""
        data = self._entities.get(eid, {})
        return data.get("attributes", {}).get("friendly_name", eid)


# ---------- Главное меню (кнопки внизу чата) ----------

def get_main_keyboard(uid: Optional[int]) -> ReplyKeyboardMarkup:
    """Создаёт клавиатуру главного меню."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(t(uid, "btn_control")), KeyboardButton(t(uid, "btn_status"))],
            [KeyboardButton(t(uid, "btn_rooms")), KeyboardButton(t(uid, "btn_scenes"))],
            [KeyboardButton(t(uid, "btn_settings")), KeyboardButton(t(uid, "btn_help"))],
        ],
        resize_keyboard=True,
    )


# ---------- Bot ----------

class HATelegramBot:
    """Основной класс Telegram-бота для Home Assistant."""

    # Максимальная длина одного сообщения Telegram (с запасом на HTML)
    MAX_MSG = 4000
    # Максимум запросов к /notify в минуту (защита от спама через бота)
    NOTIFY_RATE_LIMIT = 20

    def __init__(self, cfg, allowed_users: Optional[set]):
        self.cfg = cfg
        self.allowed_users = allowed_users  # None = разрешены все
        self.ha = HAClient(cfg.base_url, cfg.ha_token, cfg.timeout)
        self.registry = EntityRegistry(self.ha)
        # Таймеры: {(user_id, entity_id): asyncio.Task}
        self._timers: dict = {}
        # Мета таймеров для сохранения: {(user_id, entity_id): {...}}
        self._timer_meta: dict = {}
        # Чаты авторизованных пользователей (для рассылки уведомлений)
        self._known_chats: set = set()
        # Маппинг коротких токенов callback_data -> полный payload.
        # Нужен, потому что callback_data ограничена 64 байтами,
        # а entity_id / имена комнат могут быть длиннее.
        self._cb_map: dict = {}
        self._cb_seq = 0
        self.app = None
        self._notify_runner = None
        # Времена последних запросов к /notify (sliding window для rate limit)
        self._notify_hits: list = []
        # Фоновая задача обновления реестра (создаётся в post_init)
        self._refresh_task = None

    # ---------- Callback-токены ----------

    def _tok(self, payload: str) -> str:
        """Создаёт короткий токен для payload callback_data."""
        self._cb_seq += 1
        token = f"x{self._cb_seq}"
        self._cb_map[token] = payload
        # Защита от неограниченного роста: вытесняем самые старые токены
        # (dict сохраняет порядок вставки — это FIFO)
        if len(self._cb_map) > 3000:
            for k in list(self._cb_map.keys())[:1000]:
                del self._cb_map[k]
        return token

    def _resolve_tok(self, data: str) -> Optional[str]:
        """Возвращает payload по токену (None, если токен неизвестен)."""
        return self._cb_map.get(data)

    # ---------- Утилиты ----------

    def _check_auth(self, update: Update) -> bool:
        """Проверяет, разрешён ли доступ пользователю, и логирует обращение."""
        user_id = update.effective_user.id if update.effective_user else None
        if self.allowed_users is not None and user_id not in self.allowed_users:
            logger.warning("Отказано в доступе: user_id=%s", user_id)
            return False
        # Запоминаем чат для уведомлений
        if update.effective_chat is not None:
            self._known_chats.add(update.effective_chat.id)
        what = ""
        if update.message and update.message.text:
            what = update.message.text[:80]
        elif update.callback_query and update.callback_query.data:
            what = f"cb:{update.callback_query.data[:40]}"
        logger.info("Запрос user=%s: %s", user_id, what)
        return True

    def _uid(self, update: Update) -> Optional[int]:
        """Возвращает Telegram ID пользователя."""
        return update.effective_user.id if update.effective_user else None

    async def _resolve_or_suggest(self, update: Update, uid: Optional[int],
                                  name: str, action_key: str) -> Optional[str]:
        """Ищет устройство: точное совпадение, затем поиск по подстроке.

        При одном совпадении возвращает entity_id сразу.
        При нескольких — отправляет список кнопок и возвращает None.
        """
        eid = self.registry.by_id_or_alias(name)
        if eid:
            return eid
        matches = self.registry.search(name)
        if len(matches) == 1:
            return matches[0]
        if matches:
            buttons = []
            for m in matches:
                fname = self.registry.get_friendly_name(m)
                buttons.append([InlineKeyboardButton(
                    fname, callback_data=self._tok(f"{action_key}:{m}"),
                )])
            text = t(uid, "search_title", count=len(matches))
            # Показываем, что найдено больше, чем вмещает список кнопок
            total = len(self.registry.search(name, limit=10**6))
            if total > len(matches):
                text += t(uid, "search_more", n=total - len(matches))
            await self._reply_text(
                update,
                text,
                "HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return None
        await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        return None

    async def _reply_text(self, update: Update, text: str, parse_mode: Optional[str] = None, **kwargs):
        """Отправляет сообщение, разбивая длинные тексты и защищаясь от битого HTML."""
        parts = self._split_message(text, self.MAX_MSG)
        result = None
        for i, part in enumerate(parts, 1):
            # Клавиатура — только к последней части, иначе она продублируется
            # на каждой части разбитого сообщения
            part_kwargs = dict(kwargs)
            if i < len(parts):
                part_kwargs.pop("reply_markup", None)
            try:
                result = await update.effective_message.reply_text(
                    part, parse_mode=parse_mode,
                    disable_web_page_preview=True, **part_kwargs,
                )
            except BadRequest as e:
                if parse_mode and ("entities" in str(e) or "parse" in str(e)):
                    # Разорванный HTML — отправляем без форматирования
                    logger.warning("Ошибка парсинга HTML, отправляю plain text: %s", e)
                    result = await update.effective_message.reply_text(
                        re.sub(r"<[^>]+>", "", part),
                        disable_web_page_preview=True, **part_kwargs,
                    )
                else:
                    logger.warning("Ошибка отправки части %d: %s", i, e)
                    return result
            except Exception as e:
                logger.warning("Ошибка отправки части %d: %s", i, e)
                return result
            if i < len(parts):
                await asyncio.sleep(0.4)
        return result

    def _split_message(self, text: str, max_length: int) -> list:
        """Разбивает сообщение на части по строкам (не рвёт HTML-теги внутри строк)."""
        lines = text.split("\n")
        parts = []
        current: list = []
        current_length = 0
        for line in lines:
            line_length = len(line) + 1
            if current_length + line_length > max_length and current:
                parts.append("\n".join(current))
                current = []
                current_length = 0
            current.append(line)
            current_length += line_length
        if current:
            parts.append("\n".join(current))
        # Отдельная слишком длинная строка — жёстко обрезаем до лимита
        # (защита от битого HTML сработает в _reply_text: plain text fallback)
        return [p[:max_length] if len(p) > max_length else p for p in parts] or [""]

    def _truncate_lines(self, uid: Optional[int], title: str, lines: list, limit: int = None) -> str:
        """Собирает список HTML-строк в сообщение, обрезая по границам строк."""
        limit = limit or self.MAX_MSG
        text = title
        for line in lines:
            if len(text) + 1 + len(line) > limit:
                text += t(uid, "list_truncated")
                break
            text += "\n" + line
        return text

    async def _get_state(self, eid: str) -> Optional[dict]:
        """Получает состояние устройства."""
        try:
            return await self.ha.get_entity(eid)
        except Exception as e:
            logger.error("Ошибка получения состояния %s: %s", eid, e)
            return None

    def _device_line(self, uid: Optional[int], eid: str, data: dict) -> str:
        """Формирует HTML-строку состояния устройства."""
        attrs = data.get("attributes", {})
        state = data.get("state")
        state_l = state_localized(uid, state, short=True)
        fname = attrs.get("friendly_name", eid)
        return f"<b>{esc(fname)}</b> — <code>{esc(state_l)}</code>"

    # ---------- Команды ----------
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        await self._reply_text(
            update,
            t(uid, "welcome"),
            reply_markup=get_main_keyboard(uid),
        )

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /menu."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        keyboard = self._main_menu_inline(uid)
        await self._reply_text(
            update,
            t(uid, "main_menu_title"),
            "HTML",
            reply_markup=keyboard,
        )

    async def cmd_hide(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /hide — скрывает кнопки меню."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        await self._reply_text(
            update,
            t(uid, "menu_hidden"),
            reply_markup=ReplyKeyboardRemove(),
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        await self._reply_text(update, t(uid, "help_text"), "HTML")

    async def cmd_lang(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /lang — выбор языка."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
            ]
        ])
        await self._reply_text(update, t(uid, "choose_lang"), reply_markup=keyboard)

    # ---------- Команды управления ----------
    async def cmd_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /on."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, "⚠️ /on <имя>")
        name = " ".join(context.args)
        eid = await self._resolve_or_suggest(update, uid, name, "on")
        if not eid:
            return
        try:
            await self.ha.turn_on(eid)
            fname = self.registry.get_friendly_name(eid)
            await self._reply_text(update, t(uid, "turned_on", name=esc(fname)), "HTML")
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /off."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, "⚠️ /off <имя>")
        name = " ".join(context.args)
        eid = await self._resolve_or_suggest(update, uid, name, "off")
        if not eid:
            return
        try:
            await self.ha.turn_off(eid)
            fname = self.registry.get_friendly_name(eid)
            await self._reply_text(update, t(uid, "turned_off", name=esc(fname)), "HTML")
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /toggle."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, "⚠️ /toggle <имя>")
        name = " ".join(context.args)
        eid = await self._resolve_or_suggest(update, uid, name, "tg")
        if not eid:
            return
        try:
            s = await self._get_state(eid)
            if s and s.get("state") == "unavailable":
                fname = self.registry.get_friendly_name(eid)
                return await self._reply_text(
                    update, t(uid, "device_unavailable", name=esc(fname))
                )
            if s and s.get("state") == "off":
                await self.ha.turn_on(eid)
            else:
                await self.ha.turn_off(eid)
            fname = self.registry.get_friendly_name(eid)
            await self._reply_text(update, t(uid, "toggled", name=esc(fname)), "HTML")
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /set — яркость света (%) или температура климата."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if len(context.args) < 2:
            return await self._reply_text(update, t(uid, "set_usage"))
        raw_value = context.args[-1].rstrip("%").replace(",", ".")
        try:
            value = float(raw_value)
        except ValueError:
            return await self._reply_text(update, t(uid, "set_not_number"))
        name = " ".join(context.args[:-1])
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            matches = self.registry.search(name)
            if len(matches) == 1:
                eid = matches[0]
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        domain = eid.split(".")[0]
        if domain not in ("light", "climate"):
            return await self._reply_text(update, t(uid, "set_unsupported", name=esc(name)))
        if domain == "climate" and not (TEMP_RANGE[0] <= value <= TEMP_RANGE[1]):
            return await self._reply_text(update, t(uid, "set_temp_range"))
        try:
            await self.ha.set_value(eid, value)
            shown = f"{value:g}%" if domain == "light" else f"{value:g}°"
            await self._reply_text(update, t(uid, "value_set", value=esc(shown)))
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /state. Без аргументов — живые данные из HA."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if context.args:
            return await self._state_one(update, uid, " ".join(context.args))
        # Все устройства — запрашиваем свежие состояния, а не кеш
        try:
            entities = await self.ha.get_entity_ids_by_domain()
        except Exception as e:
            return await self._reply_text(update, t(uid, "error", err=esc(str(e))))
        if not entities:
            return await self._reply_text(update, t(uid, "empty_list"))
        lines = [self._device_line(uid, eid, data) for eid, data in entities.items()]
        text = self._truncate_lines(uid, t(uid, "all_devices_title"), lines)
        await self._reply_text(update, text, "HTML")

    async def _state_one(self, update: Update, uid: Optional[int], name: str):
        """Показывает подробный статус одного устройства."""
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        s = await self._get_state(eid)
        if not s:
            return await self._reply_text(update, t(uid, "not_found"))
        a = s.get("attributes", {})
        state = s.get("state")
        state_l = state_localized(uid, state)
        out = t(uid, "current_state", name=esc(a.get("friendly_name", eid)), state=esc(state_l))
        if a:
            attrs_json = json.dumps(a, ensure_ascii=False, indent=1)
            out += f"\n{t(uid, 'attrs_label')}\n<code>{esc(attrs_json)}</code>"
        await self._reply_text(update, out, "HTML")

    async def cmd_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /room."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, "⚠️ /room <комната>")
        room_name = " ".join(context.args)
        await self._show_room(update, uid, room_name)

    async def cmd_scene(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /scene."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, "⚠️ /scene <имя>")
        name = " ".join(context.args)
        eid = self.registry.by_id_or_alias(name)
        if not eid or not eid.startswith("scene."):
            matches = [m for m in self.registry.search(name)
                       if m.startswith("scene.")]
            if len(matches) == 1:
                eid = matches[0]
            else:
                eid = None
        if not eid:
            return await self._reply_text(update, t(uid, "scene_not_found", name=esc(name)))
        try:
            await self.ha.apply_scene(eid)
            fname = self.registry.get_friendly_name(eid)
            await self._reply_text(update, t(uid, "scene_applied", name=esc(fname)), "HTML")
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        ok = await self.ha.healthcheck()
        await self._reply_text(update, t(uid, "ha_online") if ok else t(uid, "ha_offline"))

    async def cmd_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /timer — таймер выключения."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if len(context.args) < 2:
            return await self._reply_text(update, "⚠️ /timer <мин> <имя>")
        try:
            minutes = int(context.args[0])
            if minutes <= 0 or minutes > 24 * 60:
                raise ValueError
        except ValueError:
            return await self._reply_text(update, "⚠️ Время должно быть числом от 1 до 1440")
        name = " ".join(context.args[1:])
        eid = await self._resolve_or_suggest(update, uid, name, "off")
        if not eid:
            return

        chat_id = update.effective_chat.id if update.effective_chat else None
        text = await self._start_timer(uid, chat_id, eid, minutes)
        await self._reply_text(update, text, "HTML")

    async def cmd_timers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /timers — список активных таймеров с отменой."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        rows = []
        now = time.time()
        for (tuid, eid), meta in sorted(
            self._timer_meta.items(), key=lambda kv: kv[1]["fire_at"]
        ):
            if tuid != uid:
                continue
            left = max(1, round((meta["fire_at"] - now) / 60))
            fname = self.registry.get_friendly_name(eid)
            rows.append((eid, fname, left))
        if not rows:
            return await self._reply_text(update, t(uid, "timers_empty"))
        buttons = []
        for eid, fname, left in rows:
            buttons.append([InlineKeyboardButton(
                f"❌ {fname} — {left} {t(uid, 'timer_min')}",
                callback_data=self._tok(f"tmrc:{eid}"),
            )])
        await self._reply_text(
            update,
            t(uid, "timers_title", count=len(rows)),
            "HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    def _cancel_timer(self, uid: Optional[int], eid: str) -> bool:
        """Отменяет таймер пользователя для устройства. True, если был отменён."""
        key = (uid, eid)
        task = self._timers.get(key)
        if task is not None and not task.done():
            task.cancel()
            self._timers.pop(key, None)
            self._timer_meta.pop(key, None)
            self.save_timers(verbose=False)
            return True
        if key in self._timers or key in self._timer_meta:
            self._timers.pop(key, None)
            self._timer_meta.pop(key, None)
            self.save_timers(verbose=False)
        return False

    async def _start_timer(self, uid: Optional[int], chat_id: Optional[int],
                           eid: str, minutes: int, remaining: Optional[float] = None) -> str:
        """Запускает (или восстанавливает) таймер выключения. Возвращает текст для пользователя."""
        key = (uid, eid)
        # Отменяем предыдущий таймер для этой пары пользователь+устройство
        old = self._timers.get(key)
        replaced = False
        if old is not None and not old.done():
            old.cancel()
            replaced = True

        sleep_seconds = remaining if remaining is not None else minutes * 60
        fire_at = time.time() + sleep_seconds
        self._timer_meta[key] = {
            "chat_id": chat_id,
            "minutes": minutes,
            "fire_at": fire_at,
        }

        async def turn_off_later():
            try:
                await asyncio.sleep(max(0, fire_at - time.time()))
                await self.ha.turn_off(eid)
                if chat_id is not None:
                    try:
                        await self.app.bot.send_message(
                            chat_id,
                            t(uid, "timer_fired", eid=esc(eid), minutes=minutes),
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.warning("Не удалось отправить уведомление о таймере: %s", e)
            except asyncio.CancelledError:
                pass
            finally:
                if self._timers.get(key) is current_task:
                    self._timers.pop(key, None)
                    self._timer_meta.pop(key, None)
                    self.save_timers(verbose=False)

        current_task = asyncio.create_task(turn_off_later())
        self._timers[key] = current_task
        self.save_timers(verbose=False)

        if remaining is not None:
            left = max(1, round(remaining / 60))
            return t(uid, "timer_restored", eid=esc(eid), minutes=left)
        text = t(uid, "timer_started", eid=esc(eid), minutes=minutes)
        if replaced:
            text += "\n" + t(uid, "timer_replaced")
        return text

    # ---------- /alloff ----------
    async def cmd_alloff(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /alloff — запрашивает подтверждение."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        count = sum(
            1 for eid in self.registry.list_entities()
            if eid.split(".")[0] in ALLOFF_DOMAINS
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(uid, "alloff_btn_yes"), callback_data=self._tok("alloff:yes"))],
            [InlineKeyboardButton(t(uid, "alloff_btn_no"), callback_data=self._tok("alloff:no"))],
        ])
        await self._reply_text(
            update,
            t(uid, "alloff_confirm", count=count),
            "HTML",
            reply_markup=keyboard,
        )

    async def _alloff_execute(self, query, uid: Optional[int]):
        """Выполняет массовое выключение."""
        try:
            targets = [
                eid for eid in self.registry.list_entities()
                if eid.split(".")[0] in ALLOFF_DOMAINS
            ]
            results = await asyncio.gather(
                *(self.ha.turn_off(eid) for eid in targets),
                return_exceptions=True,
            )
            failed = sum(1 for r in results if isinstance(r, Exception))
            if failed:
                logger.warning("alloff: не выключено %d из %d", failed, len(targets))
            await self._edit_msg(
                query,
                t(uid, "alloff_done", count=len(targets) - failed),
                "HTML",
                InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        except Exception as e:
            await self._edit_msg(query, t(uid, "alloff_error", err=esc(str(e))))

    # ---------- Inline-меню ----------
    def _main_menu_inline(self, uid: Optional[int]) -> InlineKeyboardMarkup:
        """Создаёт inline-клавиатуру главного меню."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(t(uid, "btn_control"), callback_data="menu_control"),
                InlineKeyboardButton(t(uid, "btn_status"), callback_data="menu_status"),
            ],
            [
                InlineKeyboardButton(t(uid, "btn_rooms"), callback_data="menu_rooms"),
                InlineKeyboardButton(t(uid, "btn_scenes"), callback_data="menu_scenes"),
            ],
            [
                InlineKeyboardButton(t(uid, "btn_settings"), callback_data="menu_settings"),
                InlineKeyboardButton(t(uid, "btn_help"), callback_data="menu_help"),
            ],
        ])

    def _back_to_main_button(self, uid: Optional[int]) -> list:
        """Возвращает кнопку возврата в главное меню."""
        return [InlineKeyboardButton(t(uid, "btn_main_menu"), callback_data="menu_main")]

    async def _show_control_menu(self, update_or_query, uid: Optional[int]):
        """Показывает меню управления устройствами."""
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(t(uid, "btn_on"), callback_data="ctrl_on"),
                InlineKeyboardButton(t(uid, "btn_off"), callback_data="ctrl_off"),
            ],
            [InlineKeyboardButton(t(uid, "btn_toggle"), callback_data="ctrl_toggle")],
            self._back_to_main_button(uid),
        ])
        await self._send_or_edit(update_or_query, t(uid, "control_title"), "HTML", keyboard)

    async def _show_status_menu(self, update_or_query, uid: Optional[int]):
        """Показывает меню статуса устройств."""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(uid, "btn_all_devices"), callback_data="stat_all")],
            [
                InlineKeyboardButton(t(uid, "btn_lights"), callback_data="stat_light"),
                InlineKeyboardButton(t(uid, "btn_switches"), callback_data="stat_switch"),
            ],
            [
                InlineKeyboardButton(t(uid, "btn_climate"), callback_data="stat_climate"),
                InlineKeyboardButton(t(uid, "btn_fans"), callback_data="stat_fan"),
            ],
            self._back_to_main_button(uid),
        ])
        await self._send_or_edit(update_or_query, t(uid, "status_title"), "HTML", keyboard)

    async def _show_rooms_menu(self, update_or_query, uid: Optional[int]):
        """Показывает список комнат."""
        rooms = self.registry.get_rooms()
        if not rooms:
            await self._send_or_edit(
                update_or_query,
                t(uid, "no_rooms"),
                reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
            return
        buttons = []
        for room in rooms:
            cb_data = self._tok(f"room:{room}")
            buttons.append([InlineKeyboardButton(f"🏠 {room}", callback_data=cb_data)])
        buttons.append(self._back_to_main_button(uid))
        await self._send_or_edit(
            update_or_query,
            t(uid, "rooms_title"),
            "HTML",
            InlineKeyboardMarkup(buttons),
        )

    async def _show_scenes_menu(self, update_or_query, uid: Optional[int]):
        """Показывает список сцен."""
        scenes = self.registry.get_scenes()
        if not scenes:
            await self._send_or_edit(
                update_or_query,
                t(uid, "no_scenes"),
                reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
            return
        buttons = []
        for scene_id in scenes:
            fname = self.registry.get_friendly_name(scene_id)
            cb_data = self._tok(f"scene:{scene_id}")
            buttons.append([InlineKeyboardButton(f"🎬 {fname}", callback_data=cb_data)])
        buttons.append(self._back_to_main_button(uid))
        await self._send_or_edit(
            update_or_query,
            t(uid, "scenes_title"),
            "HTML",
            InlineKeyboardMarkup(buttons),
        )

    async def _show_settings_menu(self, update_or_query, uid: Optional[int]):
        """Показывает меню настроек."""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(uid, "btn_lang"), callback_data="set_lang")],
            [InlineKeyboardButton(t(uid, "btn_ha_status"), callback_data="set_hastatus")],
            self._back_to_main_button(uid),
        ])
        await self._send_or_edit(update_or_query, t(uid, "settings_title"), "HTML", keyboard)

    async def _show_device_list(
        self,
        update_or_query,
        uid: Optional[int],
        action: str,
        action_key: str,
        domain: Optional[str] = None,
    ):
        """Показывает список устройств для управления."""
        entities = self.registry.list_entities(domain)
        if not entities:
            await self._send_or_edit(
                update_or_query,
                t(uid, "empty_list_short"),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_control")],
                ]),
            )
            return
        controllable = [
            e for e in entities
            if e.split(".")[0] in CONTROLLABLE_DOMAINS
        ]
        if not controllable:
            controllable = entities
        buttons = []
        for eid in controllable:
            fname = self.registry.get_friendly_name(eid)
            cb_data = self._tok(f"{action_key}:{eid}")
            buttons.append([InlineKeyboardButton(fname, callback_data=cb_data)])
        buttons.append([InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_control")])
        text = t(uid, "select_device", action=action)
        await self._send_or_edit(update_or_query, text, "HTML", InlineKeyboardMarkup(buttons))

    async def _show_room(self, update_or_query, uid: Optional[int], room_name: str):
        """Показывает устройства в комнате (area_registry + fallback по атрибутам)."""
        eids = self.registry.entities_in_room(room_name)
        lines = []
        buttons = []
        for eid in eids:
            data = self.registry._entities.get(eid, {})
            lines.append(self._device_line(uid, eid, data))
            if eid.split(".")[0] in CONTROLLABLE_DOMAINS:
                fname = self.registry.get_friendly_name(eid)
                buttons.append([
                    InlineKeyboardButton(f"✅ {fname}", callback_data=self._tok(f"on:{eid}")),
                    InlineKeyboardButton(f"❌ {fname}", callback_data=self._tok(f"off:{eid}")),
                ])
        if not lines:
            text = t(uid, "room_not_found", room=esc(room_name))
            kb = InlineKeyboardMarkup([self._back_to_main_button(uid)])
        else:
            text = self._truncate_lines(uid, t(uid, "room_title", room=esc(room_name)), lines)
            buttons.append(self._back_to_main_button(uid))
            kb = InlineKeyboardMarkup(buttons)
        await self._send_or_edit(update_or_query, text, "HTML", kb)

    async def _edit_msg(self, query, text: str, parse_mode: Optional[str] = None, reply_markup=None):
        """Редактирует сообщение, глуша ожидаемые ошибки Telegram."""
        try:
            await query.edit_message_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except BadRequest as e:
            msg = str(e).lower()
            if "not modified" in msg:
                return  # текст не изменился (повторное нажатие) — не ошибка
            if parse_mode and ("entities" in msg or "parse" in msg):
                try:
                    await query.edit_message_text(
                        re.sub(r"<[^>]+>", "", text),
                        reply_markup=reply_markup,
                        disable_web_page_preview=True,
                    )
                except BadRequest as e2:
                    if "not modified" not in str(e2).lower():
                        logger.warning("Ошибка редактирования (plain): %s", e2)
                except Exception as e2:
                    logger.warning("Ошибка редактирования (plain): %s", e2)
            else:
                logger.warning("Ошибка редактирования: %s", e)
        except Exception as e:
            logger.warning("Ошибка редактирования: %s", e)

    async def _send_or_edit(self, update_or_query, text: str, parse_mode: Optional[str] = None, reply_markup=None):
        """Универсальный метод: редактирует или отправляет сообщение."""
        if hasattr(update_or_query, "data"):
            await self._edit_msg(update_or_query, text, parse_mode, reply_markup)
        else:
            update = update_or_query
            await self._reply_text(
                update, text, parse_mode, reply_markup=reply_markup,
            )

    # ---------- Callback handler ----------
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает нажатия на inline-кнопки."""
        query = update.callback_query
        await query.answer()
        if not self._check_auth(update):
            return
        uid = query.from_user.id
        data = query.data or ""

        # Разрешаем короткие токены в полные payload
        payload = self._resolve_tok(data) if data.startswith("x") else None
        if data.startswith("x") and payload is None:
            await self._edit_msg(query, t(uid, "cb_expired"))
            return
        if payload:
            data = payload

        # Смена языка
        if data.startswith("lang_"):
            lang = data.split("_", 1)[1]
            if lang in MESSAGES:
                set_lang(uid, lang)
                await self._edit_msg(query, t(uid, "lang_set"))
                await query.message.reply_text(
                    t(uid, "main_menu_title"),
                    parse_mode="HTML",
                    reply_markup=self._main_menu_inline(uid),
                )
            return

        # Навигация по меню
        if data == "menu_main":
            await self._edit_msg(
                query,
                t(uid, "main_menu_title"),
                "HTML",
                self._main_menu_inline(uid),
            )
        elif data == "menu_control":
            await self._show_control_menu(query, uid)
        elif data == "menu_status":
            await self._show_status_menu(query, uid)
        elif data == "menu_rooms":
            await self._show_rooms_menu(query, uid)
        elif data == "menu_scenes":
            await self._show_scenes_menu(query, uid)
        elif data == "menu_settings":
            await self._show_settings_menu(query, uid)
        elif data == "menu_help":
            await self._edit_msg(
                query,
                t(uid, "help_text"),
                "HTML",
                InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        elif data == "ctrl_on":
            await self._show_device_list(query, uid, t(uid, "btn_on"), "on")
        elif data == "ctrl_off":
            await self._show_device_list(query, uid, t(uid, "btn_off"), "off")
        elif data == "ctrl_toggle":
            await self._show_device_list(query, uid, t(uid, "btn_toggle"), "tg")
        elif data == "stat_all":
            await self._show_status_list(query, uid, None)
        elif data.startswith("stat_"):
            domain = data.split("_", 1)[1]
            await self._show_status_list(query, uid, domain)
        elif data == "set_lang":
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                    InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
                ],
                [InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_settings")],
            ])
            await self._edit_msg(query, t(uid, "choose_lang"), reply_markup=keyboard)
        elif data == "set_hastatus":
            ok = await self.ha.healthcheck()
            text = t(uid, "ha_online") if ok else t(uid, "ha_offline")
            await self._edit_msg(
                query,
                text,
                reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        elif ":" in data:
            action, _, arg = data.partition(":")
            if action in ("on", "off", "tg"):
                await self._apply_device_action(query, uid, action, arg)
            elif action == "set":
                await self._apply_set_action(query, uid, arg)
            elif action == "tmrc":
                if self._cancel_timer(uid, arg):
                    await self._edit_msg(
                        query,
                        t(uid, "timer_cancelled", eid=esc(arg)), "HTML",
                    )
                else:
                    await self._edit_msg(query, t(uid, "cb_expired"))
            elif action == "room":
                await self._show_room(query, uid, arg)
            elif action == "scene":
                await self._apply_scene(query, uid, arg)
            elif action == "card":
                await self._device_card(query, uid, arg)
            elif action == "alloff":
                if arg == "yes":
                    await self._alloff_execute(query, uid)
                else:
                    await self._edit_msg(query, t(uid, "alloff_cancelled"))
            else:
                logger.warning("Неизвестный callback: %s", data)

    async def _apply_device_action(self, query, uid: Optional[int], action: str, eid: str):
        """Включает/выключает/переключает устройство по inline-кнопке."""
        try:
            if action == "on":
                await self.ha.turn_on(eid)
                key = "turned_on"
            elif action == "off":
                await self.ha.turn_off(eid)
                key = "turned_off"
            else:  # tg
                s = await self._get_state(eid)
                if s and s.get("state") == "unavailable":
                    fname = self.registry.get_friendly_name(eid)
                    return await self._edit_msg(
                        query, t(uid, "device_unavailable", name=esc(fname))
                    )
                if s and s.get("state") == "off":
                    await self.ha.turn_on(eid)
                else:
                    await self.ha.turn_off(eid)
                key = "toggled"
            fname = self.registry.get_friendly_name(eid)
            await self._edit_msg(
                query,
                t(uid, key, name=esc(fname)),
                "HTML",
                InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        except Exception as e:
            await self._edit_msg(query, t(uid, "error", err=esc(str(e))))

    async def _apply_set_action(self, query, uid: Optional[int], arg: str):
        """Устанавливает яркость/температуру по inline-кнопке (payload: <eid>:<значение>)."""
        eid, _, raw = arg.rpartition(":")
        try:
            value = float(raw)
        except ValueError:
            return await self._edit_msg(query, t(uid, "error", err="bad value"))
        try:
            await self.ha.set_value(eid, value)
            shown = f"{value:g}%" if eid.startswith("light.") else f"{value:g}°"
            await self._edit_msg(
                query,
                t(uid, "value_set", value=esc(shown)),
                "HTML",
                InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        except Exception as e:
            await self._edit_msg(query, t(uid, "error", err=esc(str(e))))

    async def _apply_scene(self, query, uid: Optional[int], scene_id: str):
        """Активирует сцену по inline-кнопке."""
        try:
            await self.ha.apply_scene(scene_id)
            fname = self.registry.get_friendly_name(scene_id)
            await self._edit_msg(
                query,
                t(uid, "scene_applied", name=esc(fname)),
                "HTML",
                InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        except Exception as e:
            await self._edit_msg(query, t(uid, "error", err=esc(str(e))))

    async def _show_status_list(self, query, uid: Optional[int], domain: Optional[str]):
        """Показывает список устройств с их состояниями (обрезка по строкам)."""
        entities = self.registry.list_entities(domain)
        if not entities:
            await self._edit_msg(
                query,
                t(uid, "empty_list_short"),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_status")],
                ]),
            )
            return
        lines = []
        for eid in entities:
            data = self.registry._entities.get(eid, {})
            lines.append(self._device_line(uid, eid, data))
        title_key = "all_devices_title" if domain is None else "devices_of_type_title"
        title = t(uid, title_key, domain=esc(domain)) if domain else t(uid, title_key)
        text = self._truncate_lines(uid, title, lines)
        await self._edit_msg(
            query,
            text,
            "HTML",
            InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_status")],
            ]),
        )

    # ---------- Обработка текстовых кнопок меню ----------
    async def on_menu_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текстовые сообщения (кнопки меню, поиск устройств)."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        text = update.message.text
        ru_map = MESSAGES["ru"]
        en_map = MESSAGES["en"]

        if text in (ru_map["btn_control"], en_map["btn_control"]):
            await self._show_control_menu(update, uid)
        elif text in (ru_map["btn_status"], en_map["btn_status"]):
            await self._show_status_menu(update, uid)
        elif text in (ru_map["btn_rooms"], en_map["btn_rooms"]):
            await self._show_rooms_menu(update, uid)
        elif text in (ru_map["btn_scenes"], en_map["btn_scenes"]):
            await self._show_scenes_menu(update, uid)
        elif text in (ru_map["btn_settings"], en_map["btn_settings"]):
            await self._show_settings_menu(update, uid)
        elif text in (ru_map["btn_help"], en_map["btn_help"]):
            await self._reply_text(update, t(uid, "help_text"), "HTML")
        else:
            # Поиск устройства: точное совпадение → карточка,
            # иначе подстрочный поиск → список кнопок
            eid = self.registry.by_id_or_alias(text)
            if eid:
                await self._device_card(update, uid, eid)
                return
            matches = self.registry.search(text)
            if not matches:
                return await self._reply_text(update, t(uid, "search_empty", q=esc(text)))
            if len(matches) == 1:
                return await self._device_card(update, uid, matches[0])
            buttons = []
            for m in matches:
                fname = self.registry.get_friendly_name(m)
                buttons.append([InlineKeyboardButton(fname, callback_data=self._tok(f"card:{m}"))])
            msg_text = t(uid, "search_title", count=len(matches))
            total = len(self.registry.search(text, limit=10**6))
            if total > len(matches):
                msg_text += t(uid, "search_more", n=total - len(matches))
            await self._reply_text(
                update,
                msg_text,
                "HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    async def _device_card(self, update_or_query, uid: Optional[int], eid: str):
        """Показывает карточку устройства: состояние + кнопки действий."""
        s = await self._get_state(eid)
        if not s:
            if hasattr(update_or_query, "data"):
                await self._edit_msg(update_or_query, t(uid, "not_found"))
            else:
                await self._reply_text(update_or_query, t(uid, "not_found"))
            return
        a = s.get("attributes", {})
        state = s.get("state")
        state_l = state_localized(uid, state)
        fname = a.get("friendly_name", eid)
        out = t(uid, "current_state", name=esc(fname), state=esc(state_l))

        domain = eid.split(".")[0]
        kb = None
        if domain in CONTROLLABLE_DOMAINS:
            rows = [[
                InlineKeyboardButton(t(uid, "btn_on"), callback_data=self._tok(f"on:{eid}")),
                InlineKeyboardButton(t(uid, "btn_off"), callback_data=self._tok(f"off:{eid}")),
                InlineKeyboardButton(t(uid, "btn_toggle"), callback_data=self._tok(f"tg:{eid}")),
            ]]
            if domain == "light":
                rows.append([
                    InlineKeyboardButton(
                        f"{p}%", callback_data=self._tok(f"set:{eid}:{p}"),
                    ) for p in BRIGHTNESS_PRESETS
                ])
            kb = InlineKeyboardMarkup(rows)
        elif domain == "scene":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "btn_on"), callback_data=self._tok(f"scene:{eid}"))]
            ])
        await self._send_or_edit(update_or_query, out, "HTML", kb)

    # ---------- Уведомления из HA ----------
    def notify_targets(self) -> list:
        """Возвращает список chat_id для рассылки уведомлений."""
        if self._known_chats:
            return sorted(self._known_chats)
        if self.allowed_users:
            logger.warning(
                "Нет известных чатов — fallback на ALLOWED_USER_IDS; "
                "для групповых чатов user_id != chat_id, уведомления могут не дойти"
            )
            return sorted(self.allowed_users)
        return []

    async def _handle_notify(self, request):
        """HTTP-обработчик POST /notify — принимает уведомления из HA."""
        now = time.time()
        self._notify_hits = [h for h in self._notify_hits if now - h < 60]
        if len(self._notify_hits) >= self.NOTIFY_RATE_LIMIT:
            return web.json_response({"ok": False, "error": "rate limit"}, status=429)
        self._notify_hits.append(now)
        if self.cfg.notify_token:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self.cfg.notify_token}":
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        text = body.get("text")
        if not text or not isinstance(text, str):
            return web.json_response({"ok": False, "error": "text required"}, status=400)
        parse_mode = body.get("parse_mode") if body.get("parse_mode") in ("HTML", "MarkdownV2") else None

        targets = body.get("chat_ids")
        if not isinstance(targets, list) or not targets:
            targets = self.notify_targets()
        if not targets:
            return web.json_response({"ok": False, "error": "no known chats"}, status=404)

        sent, failed = 0, 0
        for cid in targets:
            try:
                await self.app.bot.send_message(cid, text, parse_mode=parse_mode)
                sent += 1
            except Exception as e:
                logger.warning("Не удалось отправить уведомление в %s: %s", cid, e)
                failed += 1
        return web.json_response({"ok": True, "sent": sent, "failed": failed})

    async def start_notify_server(self):
        """Запускает HTTP-приёмник уведомлений (если настроен NOTIFY_PORT).

        Занятый/недоступный порт не роняет бота — приёмник просто отключается,
        управление устройствами продолжает работать.
        """
        if not self.cfg.notify_port:
            return
        if web is None:
            logger.error("aiohttp не установлен — приёмник уведомлений недоступен. "
                         "Установите: pip install aiohttp")
            return
        app_web = web.Application()
        app_web.router.add_post("/notify", self._handle_notify)
        self._notify_runner = web.AppRunner(app_web)
        await self._notify_runner.setup()
        site = web.TCPSite(self._notify_runner, self.cfg.notify_host, self.cfg.notify_port)
        try:
            await site.start()
        except OSError as e:
            logger.error("Приёмник уведомлений не запущен (%s) — бот работает без него", e)
            await self._notify_runner.cleanup()
            self._notify_runner = None
            return
        logger.info("Приёмник уведомлений: http://%s:%s/notify",
                    self.cfg.notify_host, self.cfg.notify_port)

    async def stop_notify_server(self):
        """Останавливает HTTP-приёмник уведомлений."""
        if self._notify_runner is not None:
            await self._notify_runner.cleanup()
            self._notify_runner = None

    # ---------- Сохранение/восстановление таймеров ----------
    def save_timers(self, verbose: bool = True):
        """Сохраняет активные таймеры в файл (при изменениях и при shutdown)."""
        data = []
        now = time.time()
        for (uid, eid), meta in self._timer_meta.items():
            remaining = meta["fire_at"] - now
            if remaining <= 0:
                continue
            data.append({
                "uid": uid,
                "chat_id": meta.get("chat_id"),
                "eid": eid,
                "minutes": meta["minutes"],
                "fire_at": meta["fire_at"],
            })
        try:
            TIMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TIMERS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if verbose:
                logger.info("Сохранено таймеров: %d", len(data))
        except Exception as e:
            logger.warning("Не удалось сохранить таймеры: %s", e)

    async def restore_timers(self):
        """Восстанавливает таймеры из файла (вызывается при старте)."""
        if not TIMERS_FILE.exists():
            return
        try:
            data = json.loads(TIMERS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Не удалось прочитать %s: %s", TIMERS_FILE, e)
            return
        now = time.time()
        restored = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            eid = item.get("eid")
            fire_at = item.get("fire_at")
            if not eid or not isinstance(fire_at, (int, float)):
                logger.warning("Пропускаю повреждённую запись таймера: %r", item)
                continue
            remaining = fire_at - now
            if remaining <= 0:
                continue
            await self._start_timer(
                item.get("uid"), item.get("chat_id"),
                eid, item.get("minutes") or 0, remaining=remaining,
            )
            restored += 1
        try:
            TIMERS_FILE.unlink()
        except Exception:
            pass
        if restored:
            logger.info("Восстановлено таймеров: %d", restored)


# ---------- Main ----------

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


def parse_allowed_users() -> Optional[set]:
    """Разбирает ALLOWED_USER_IDS (список через запятую) или ALLOWED_USER_ID (один)."""
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
    return None  # доступ открыт всем — НЕ рекомендуется


def main():
    """Точка входа: настройка и запуск бота."""
    try:
        ha_timeout = int(os.environ.get("HA_TIMEOUT") or 15)
    except ValueError:
        logger.warning("Неверный HA_TIMEOUT=%r, использую 15", os.environ.get("HA_TIMEOUT"))
        ha_timeout = 15
    cfg = Config(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        base_url=os.environ.get("HA_BASE_URL", "http://localhost:8123"),
        ha_token=os.environ.get("HA_ACCESS_TOKEN", ""),
        allowed_users=parse_allowed_users(),
        timeout=ha_timeout,
        notify_host=os.environ.get("NOTIFY_HOST", "0.0.0.0"),
        notify_port=int(os.environ.get("NOTIFY_PORT") or 0),
        notify_token=os.environ.get("NOTIFY_TOKEN") or None,
    )
    if not cfg.token or not cfg.ha_token:
        raise SystemExit("Не заданы TELEGRAM_BOT_TOKEN и HA_ACCESS_TOKEN в файле .env")
    if cfg.allowed_users is None:
        logger.warning("ALLOWED_USER_IDS не задан — доступ к боту разрешён ВСЕМ!")
    if cfg.notify_port and not cfg.notify_token:
        logger.warning("NOTIFY_TOKEN не задан — приёмник уведомлений доступен без авторизации!")

    bot = HATelegramBot(cfg, cfg.allowed_users)
    logger.info("HA Telegram Bot v%s, интервал обновления реестра: %d с",
                BOT_VERSION, REFRESH_INTERVAL)

    async def post_init(application: Application):
        bot.app = application
        logger.info("Бот запущен, загружаю список устройств...")
        try:
            await bot.registry.refresh()
            logger.info("Загружено устройств: %d", len(bot.registry._entities))
        except Exception as e:
            logger.error("Ошибка загрузки: %s", e)

        await bot.restore_timers()
        await bot.start_notify_server()

        async def refresher():
            while True:
                await asyncio.sleep(REFRESH_INTERVAL)
                try:
                    await bot.registry.refresh()
                except Exception as e:
                    logger.error("Ошибка обновления: %s", e)

        # Через asyncio, а не Application.create_task: post_init выполняется
        # до старта application, и PTB предупреждает, что такая задача не
        # отслеживается. Храним ссылку и отменяем вручную при остановке.
        bot._refresh_task = asyncio.get_running_loop().create_task(
            refresher(), name="entity_refresh"
        )

    async def post_shutdown(application: Application):
        logger.info("Остановка бота...")
        if bot._refresh_task is not None:
            bot._refresh_task.cancel()
        bot.save_timers()
        for task in bot._timers.values():
            task.cancel()
        await bot.stop_notify_server()
        await bot.ha.close()

    app = (
        ApplicationBuilder()
        .token(cfg.token)
        .job_queue(None)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("menu", bot.cmd_menu))
    app.add_handler(CommandHandler("hide", bot.cmd_hide))
    app.add_handler(CommandHandler("help", bot.cmd_help))
    app.add_handler(CommandHandler("lang", bot.cmd_lang))
    app.add_handler(CommandHandler("on", bot.cmd_on))
    app.add_handler(CommandHandler("off", bot.cmd_off))
    app.add_handler(CommandHandler("toggle", bot.cmd_toggle))
    app.add_handler(CommandHandler("set", bot.cmd_set))
    app.add_handler(CommandHandler("state", bot.cmd_state))
    app.add_handler(CommandHandler("room", bot.cmd_room))
    app.add_handler(CommandHandler("scene", bot.cmd_scene))
    app.add_handler(CommandHandler("status", bot.cmd_status))
    app.add_handler(CommandHandler("timer", bot.cmd_timer))
    app.add_handler(CommandHandler("timers", bot.cmd_timers))
    app.add_handler(CommandHandler("alloff", bot.cmd_alloff))
    app.add_handler(CallbackQueryHandler(bot.callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_menu_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

"""
Telegram-бот для Home Assistant с интерактивным меню и локализацией.
Поддержка Docker: данные сохраняются в /app/data (или DATA_DIR).

Исправления (см. CHANGELOG в README):
- Реализована команда /set (яркость света в %, температура climate)
- Таймеры: несколько на пользователя, корректная отмена при повторном запуске
- Комнаты через area_registry/device_registry/entity_registry (с fallback на атрибуты)
- Callback-данные больше не обрезаются (маппинг через короткие токены)
- Безопасное обрезание HTML-списков (по строкам, без разрыва тегов)
- Текстовый ввод показывает статус + кнопки вместо опасного "выключить по умолчанию"
- /state без аргументов показывает живые данные из HA, а не кеш
"""

import asyncio
import html
import json
import logging
import os
import re
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
        "set_usage": "⚠️ Использование: /set <имя> <значение>\nДля света — яркость в % (0–100), для климата — температура.",
        "set_not_number": "⚠️ Значение должно быть числом, например: /set свет 50",
        "set_unsupported": "❌ Для устройства «{name}» установка значений не поддерживается (только свет и климат).",
        "timer_started": "⏳ Таймер запущен для <code>{eid}</code>.\nУстройство выключится через {minutes} мин.",
        "timer_fired": "⏰ Таймер сработал: устройство <code>{eid}</code> выключено через {minutes} мин.",
        "timer_replaced": "♻️ Предыдущий таймер для этого устройства отменён.",
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
            "<code>/state</code> [<i>имя</i>] — статус\n"
            "<code>/room</code> <i>комната</i> — устройства в комнате\n"
            "<code>/scene</code> <i>имя</i> — активировать сцену\n"
            "<code>/timer</code> <i>мин имя</i> — таймер выключения\n"
            "<code>/status</code> — статус HA"
        ),
        "menu_hidden": "🙈 Меню скрыто. Используйте /menu, чтобы вернуть.",
        "no_rooms": "🔍 Комнаты не найдены.",
        "no_scenes": "🔍 Сцены не найдены.",
        "cb_expired": "⚠️ Данные кнопки устарели. Отправьте /menu заново.",
        "device_hint": "Найдено устройство. Выберите действие:",
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
        "set_usage": "⚠️ Usage: /set <name> <value>\nFor lights — brightness in % (0–100), for climate — temperature.",
        "set_not_number": "⚠️ Value must be a number, e.g.: /set light 50",
        "set_unsupported": "❌ Setting values is not supported for «{name}» (lights and climate only).",
        "timer_started": "⏳ Timer started for <code>{eid}</code>.\nDevice will turn off in {minutes} min.",
        "timer_fired": "⏰ Timer fired: device <code>{eid}</code> turned off after {minutes} min.",
        "timer_replaced": "♻️ Previous timer for this device was cancelled.",
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
            "<code>/state</code> [<i>name</i>] — status\n"
            "<code>/room</code> <i>room</i> — devices in room\n"
            "<code>/scene</code> <i>name</i> — activate scene\n"
            "<code>/timer</code> <i>min name</i> — turn-off timer\n"
            "<code>/status</code> — HA status"
        ),
        "menu_hidden": "🙈 Menu hidden. Use /menu to show it again.",
        "no_rooms": "🔍 No rooms found.",
        "no_scenes": "🔍 No scenes not found.",
        "cb_expired": "⚠️ This button data is stale. Send /menu again.",
        "device_hint": "Device found. Choose an action:",
    },
}

# Путь к файлу с языками пользователей
# В Docker: /app/data/user_langs.json
# Локально: ./user_langs.json
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
LANG_FILE = DATA_DIR / "user_langs.json"
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ru")

# Атрибуты, по которым определяем комнату (fallback, если нет area_registry)
ROOM_ATTRS = ("room_name", "area", "area_name", "location")
# Домены, которыми можно управлять кнопками
CONTROLLABLE_DOMAINS = {"light", "switch", "fan", "cover"}


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

    async def refresh(self):
        """Обновляет список устройств из Home Assistant."""
        states = await self.ha.get_entity_ids_by_domain()
        self._entities = states

        self._aliases = {}
        for eid, data in self._entities.items():
            attrs = data.get("attributes", {})
            fname = attrs.get("friendly_name")
            if fname:
                alias = re.sub(r"[^\w\s-]", "", fname).strip().lower()
                if alias and alias != eid.split(".")[-1].lower():
                    self._aliases[alias] = eid

        await self._load_area_map()

    async def _load_area_map(self):
        """Загружает соответствие комнат (areas) и устройств из реестров HA.

        Использует area_registry / device_registry / entity_registry.
        При недоступности (старая версия HA, права токена) оставляет
        пустой словарь — комнаты будут искаться по атрибутам (fallback).
        """
        self._area_names = {}
        self._area_entities = {}
        try:
            areas = await self.ha.get_json("/api/config/area_registry/list")
            devices = await self.ha.get_json("/api/config/device_registry/list")
            ent_reg = await self.ha.get_json("/api/config/entity_registry/list")
        except Exception as e:
            logger.warning("area_registry недоступен (%s), комнаты — по атрибутам", e)
            return

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

    def by_id_or_alias(self, text: str) -> Optional[str]:
        """Ищет устройство по entity_id или алиасу."""
        if not text:
            return None
        s = text.strip()
        if s in self._entities:
            return s
        return self._aliases.get(s.lower())

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

    def __init__(self, cfg, allowed_user_id: Optional[int]):
        self.cfg = cfg
        self.allowed_user_id = allowed_user_id
        self.ha = HAClient(cfg.base_url, cfg.ha_token, cfg.timeout)
        self.registry = EntityRegistry(self.ha)
        # Таймеры: {(user_id, entity_id): asyncio.Task}
        self._timers: dict = {}
        # Маппинг коротких токенов callback_data -> полный payload.
        # Нужен, потому что callback_data ограничена 64 байтами,
        # а entity_id / имена комнат могут быть длиннее.
        self._cb_map: dict = {}
        self._cb_seq = 0
        self.app = None

    # ---------- Callback-токены ----------

    def _tok(self, payload: str) -> str:
        """Создаёт короткий токен для payload callback_data."""
        self._cb_seq += 1
        token = f"x{self._cb_seq}"
        self._cb_map[token] = payload
        # Защита от неограниченного роста: вытесняем старые токены
        if len(self._cb_map) > 3000:
            for k in list(self._cb_map.keys())[:1000]:
                del self._cb_map[k]
        return token

    def _resolve_tok(self, data: str) -> Optional[str]:
        """Возвращает payload по токену (None, если токен неизвестен)."""
        return self._cb_map.get(data)

    # ---------- Утилиты ----------

    def _check_auth(self, update: Update) -> bool:
        """Проверяет, разрешён ли доступ пользователю."""
        user_id = update.effective_user.id if update.effective_user else None
        if self.allowed_user_id is not None and user_id != self.allowed_user_id:
            return False
        return True

    def _uid(self, update: Update) -> Optional[int]:
        """Возвращает Telegram ID пользователя."""
        return update.effective_user.id if update.effective_user else None

    async def _reply_text(self, update: Update, text: str, parse_mode: Optional[str] = None, **kwargs):
        """Отправляет сообщение, разбивая длинные тексты и защищаясь от битого HTML."""
        parts = self._split_message(text, self.MAX_MSG)
        result = None
        for i, part in enumerate(parts, 1):
            try:
                result = await update.effective_message.reply_text(
                    part, parse_mode=parse_mode,
                    disable_web_page_preview=True, **kwargs,
                )
            except BadRequest as e:
                if parse_mode and ("entities" in str(e) or "parse" in str(e)):
                    # Разорванный HTML — отправляем без форматирования
                    logger.warning("Ошибка парсинга HTML, отправляю plain text: %s", e)
                    result = await update.effective_message.reply_text(
                        re.sub(r"<[^>]+>", "", part),
                        disable_web_page_preview=True, **kwargs,
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
        # Отдельная слишком длинная строка — жёстко обрезаем
        # (защита сработает в _reply_text: plain text fallback)
        return [p[:max_length + 200] if len(p) > max_length + 500 else p for p in parts] or [""]

    def _truncate_lines(self, uid: Optional[int], title: str, lines: list, limit: int = None) -> str:
        """Собирает список HTML-строк в сообщение, обрезая по границам строк."""
        limit = limit or self.MAX_MSG
        text = title
        used = 0
        for line in lines:
            if len(text) + 1 + len(line) > limit:
                text += t(uid, "list_truncated")
                break
            text += "\n" + line
            used += 1
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
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
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
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
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
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        try:
            s = await self._get_state(eid)
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
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        domain = eid.split(".")[0]
        if domain not in ("light", "climate"):
            return await self._reply_text(update, t(uid, "set_unsupported", name=esc(name)))
        try:
            await self.ha.set_value(eid, value)
            shown = f"{value:g}%" if domain == "light" else f"{value:g}°"
            await self._reply_text(update, t(uid, "value_set", value=esc(shown)))
        except HAError as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))
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
            return await self._reply_text(update, t(uid, "scene_not_found", name=esc(name)))
        try:
            await self.ha.apply_scene(eid)
            fname = self.registry.get_friendly_name(eid)
            await self._reply_text(update, t(uid, "scene_applied", name=esc(fname)), "HTML")
        except HAError as e:
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
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))

        key = (uid, eid)
        # Отменяем предыдущий таймер для этой пары пользователь+устройство
        old = self._timers.get(key)
        replaced = False
        if old is not None and not old.done():
            old.cancel()
            replaced = True

        chat_id = update.effective_chat.id if update.effective_chat else None

        async def turn_off_later():
            try:
                await asyncio.sleep(minutes * 60)
                await self.ha.turn_off(eid)
                if chat_id is not None:
                    try:
                        await context.application.bot.send_message(
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

        current_task = asyncio.create_task(turn_off_later())
        self._timers[key] = current_task

        text = t(uid, "timer_started", eid=esc(eid), minutes=minutes)
        if replaced:
            text += "\n" + t(uid, "timer_replaced")
        await self._reply_text(update, text, "HTML")

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

    async def _send_or_edit(self, update_or_query, text: str, parse_mode: Optional[str] = None, reply_markup=None):
        """Универсальный метод: редактирует или отправляет сообщение."""
        if hasattr(update_or_query, "data"):
            query = update_or_query
            if len(text) > 4096:
                # Слишком длинное для редактирования — отправляем новым сообщением
                await self._reply_text(query, text, parse_mode, reply_markup=reply_markup)
                return
            try:
                await query.edit_message_text(
                    text, parse_mode=parse_mode, reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
            except BadRequest as e:
                if "entities" in str(e) or "parse" in str(e):
                    try:
                        await query.edit_message_text(
                            re.sub(r"<[^>]+>", "", text),
                            reply_markup=reply_markup,
                            disable_web_page_preview=True,
                        )
                    except Exception as e2:
                        logger.warning("Ошибка редактирования (plain): %s", e2)
                else:
                    logger.warning("Ошибка редактирования: %s", e)
            except Exception as e:
                logger.warning("Ошибка редактирования: %s", e)
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
            await query.edit_message_text(t(uid, "cb_expired"))
            return
        if payload:
            data = payload

        # Смена языка
        if data.startswith("lang_"):
            lang = data.split("_", 1)[1]
            if lang in MESSAGES:
                set_lang(uid, lang)
                await query.edit_message_text(t(uid, "lang_set"))
                await query.message.reply_text(
                    t(uid, "main_menu_title"),
                    parse_mode="HTML",
                    reply_markup=self._main_menu_inline(uid),
                )
            return

        # Навигация по меню
        if data == "menu_main":
            await query.edit_message_text(
                t(uid, "main_menu_title"),
                parse_mode="HTML",
                reply_markup=self._main_menu_inline(uid),
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
            await query.edit_message_text(
                t(uid, "help_text"),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
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
            await query.edit_message_text(t(uid, "choose_lang"), reply_markup=keyboard)
        elif data == "set_hastatus":
            ok = await self.ha.healthcheck()
            text = t(uid, "ha_online") if ok else t(uid, "ha_offline")
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        elif ":" in data:
            action, _, arg = data.partition(":")
            if action in ("on", "off", "tg"):
                await self._apply_device_action(query, uid, action, arg)
            elif action == "room":
                await self._show_room(query, uid, arg)
            elif action == "scene":
                await self._apply_scene(query, uid, arg)
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
                if s and s.get("state") == "off":
                    await self.ha.turn_on(eid)
                else:
                    await self.ha.turn_off(eid)
                key = "toggled"
            fname = self.registry.get_friendly_name(eid)
            await query.edit_message_text(
                t(uid, key, name=esc(fname)),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        except Exception as e:
            await query.edit_message_text(t(uid, "error", err=esc(str(e))))

    async def _apply_scene(self, query, uid: Optional[int], scene_id: str):
        """Активирует сцену по inline-кнопке."""
        try:
            await self.ha.apply_scene(scene_id)
            fname = self.registry.get_friendly_name(scene_id)
            await query.edit_message_text(
                t(uid, "scene_applied", name=esc(fname)),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
            )
        except Exception as e:
            await query.edit_message_text(t(uid, "error", err=esc(str(e))))

    async def _show_status_list(self, query, uid: Optional[int], domain: Optional[str]):
        """Показывает список устройств с их состояниями (обрезка по строкам)."""
        entities = self.registry.list_entities(domain)
        if not entities:
            await query.edit_message_text(
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
        if len(text) > 4096:
            await self._reply_text(query, text, "HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_status")],
            ]))
            return
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_status")],
            ]),
        )

    # ---------- Обработка текстовых кнопок меню ----------
    async def on_menu_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает текстовые сообщения (кнопки меню и имена устройств)."""
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
            # Обычное текстовое сообщение — ищем устройство.
            # ВАЖНО: не выполняем действий по умолчанию, показываем статус + кнопки.
            eid = self.registry.by_id_or_alias(text)
            if eid:
                await self._device_card(update, uid, eid)

    async def _device_card(self, update: Update, uid: Optional[int], eid: str):
        """Показывает карточку устройства: состояние + кнопки действий."""
        s = await self._get_state(eid)
        if not s:
            return await self._reply_text(update, t(uid, "not_found"))
        a = s.get("attributes", {})
        state = s.get("state")
        state_l = state_localized(uid, state)
        fname = a.get("friendly_name", eid)
        out = t(uid, "current_state", name=esc(fname), state=esc(state_l))

        domain = eid.split(".")[0]
        kb = None
        if domain in CONTROLLABLE_DOMAINS:
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(t(uid, "btn_on"), callback_data=self._tok(f"on:{eid}")),
                    InlineKeyboardButton(t(uid, "btn_off"), callback_data=self._tok(f"off:{eid}")),
                    InlineKeyboardButton(t(uid, "btn_toggle"), callback_data=self._tok(f"tg:{eid}")),
                ]
            ])
        elif domain == "scene":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "btn_on"), callback_data=self._tok(f"scene:{eid}"))]
            ])
        await self._reply_text(update, out, "HTML", reply_markup=kb)


# ---------- Main ----------

@dataclass
class Config:
    """Конфигурация бота."""
    token: Optional[str] = None
    base_url: str = "http://localhost:8123"
    ha_token: Optional[str] = None
    allowed_user_id: Optional[int] = None
    timeout: int = 15


def main():
    """Точка входа: настройка и запуск бота."""
    cfg = Config(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        base_url=os.environ.get("HA_BASE_URL", "http://localhost:8123"),
        ha_token=os.environ.get("HA_ACCESS_TOKEN", ""),
        allowed_user_id=int(os.environ.get("ALLOWED_USER_ID") or 0) or None,
    )
    if not cfg.token or not cfg.ha_token:
        raise SystemExit("Не заданы TELEGRAM_BOT_TOKEN и HA_ACCESS_TOKEN в файле .env")

    bot = HATelegramBot(cfg, cfg.allowed_user_id)

    async def post_init(application: Application):
        logger.info("Бот запущен, загружаю список устройств...")
        try:
            await bot.registry.refresh()
            logger.info("Загружено устройств: %d", len(bot.registry._entities))
        except Exception as e:
            logger.error("Ошибка загрузки: %s", e)

        async def refresher():
            while True:
                await asyncio.sleep(60)
                try:
                    await bot.registry.refresh()
                except Exception as e:
                    logger.error("Ошибка обновления: %s", e)

        application.create_task(refresher(), name="entity_refresh")

    async def post_shutdown(application: Application):
        logger.info("Остановка бота...")
        for task in bot._timers.values():
            task.cancel()
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
    app.add_handler(CallbackQueryHandler(bot.callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_menu_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

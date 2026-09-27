"""
Telegram-бот для Home Assistant с интерактивным меню.
"""

import asyncio
import html
import json
import logging
import os
import re
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
        "timer_started": "⏳ Таймер запущен для <code>{eid}</code>.\nУстройство выключится через {minutes} мин.",
        "timer_fired": "⏰ Таймер сработал: устройство <code>{eid}</code> выключено через {minutes} мин.",
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
            "<code>/set</code> <i>имя значение</i> — установить значение\n"
            "<code>/state</code> [<i>имя</i>] — статус\n"
            "<code>/room</code> <i>комната</i> — устройства в комнате\n"
            "<code>/scene</code> <i>имя</i> — активировать сцену\n"
            "<code>/timer</code> <i>мин имя</i> — таймер\n"
            "<code>/status</code> — статус HA"
        ),
        "menu_hidden": "🙈 Меню скрыто. Используйте /menu, чтобы вернуть.",
        "no_rooms": "🔍 Комнаты не найдены.",
        "no_scenes": "🔍 Сцены не найдены.",
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
        "timer_started": "⏳ Timer started for <code>{eid}</code>.\nDevice will turn off in {minutes} min.",
        "timer_fired": "⏰ Timer fired: device <code>{eid}</code> turned off after {minutes} min.",
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
            "<code>/set</code> <i>name value</i> — set value\n"
            "<code>/state</code> [<i>name</i>] — status\n"
            "<code>/room</code> <i>room</i> — devices in room\n"
            "<code>/scene</code> <i>name</i> — activate scene\n"
            "<code>/timer</code> <i>min name</i> — timer\n"
            "<code>/status</code> — HA status"
        ),
        "menu_hidden": "🙈 Menu hidden. Use /menu to show it again.",
        "no_rooms": "🔍 No rooms found.",
        "no_scenes": "🔍 No scenes found.",
    },
}

LANG_FILE = Path(__file__).parent / "user_langs.json"
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ru")


def load_user_langs() -> dict:
    if LANG_FILE.exists():
        try:
            return json.loads(LANG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Не удалось прочитать {LANG_FILE}: {e}")
    return {}


def save_user_langs(langs: dict):
    try:
        LANG_FILE.write_text(json.dumps(langs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Не удалось записать {LANG_FILE}: {e}")


USER_LANGS = load_user_langs()


def get_lang(user_id: Optional[int]) -> str:
    if user_id is None:
        return DEFAULT_LANG
    return USER_LANGS.get(str(user_id), DEFAULT_LANG)


def set_lang(user_id: int, lang: str):
    if lang not in MESSAGES:
        return
    USER_LANGS[str(user_id)] = lang
    save_user_langs(USER_LANGS)


def t(user_id: Optional[int], key: str, **kwargs) -> str:
    lang = get_lang(user_id)
    text = MESSAGES.get(lang, MESSAGES["ru"]).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def state_localized(user_id: Optional[int], state: str, short: bool = False) -> str:
    if state == "on":
        return t(user_id, "state_on_short" if short else "state_on")
    if state == "off":
        return t(user_id, "state_off_short" if short else "state_off")
    if state == "unavailable":
        return t(user_id, "state_unavailable")
    return state


# ---------- HA Client ----------

class HAError(Exception):
    pass


class HAClient:
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
        await self.client.aclose()

    async def get_json(self, path: str, params: Optional[dict] = None):
        r = await self.client.get(path, params=params)
        if r.status_code == 401:
            raise HAError("Invalid HA access token.")
        r.raise_for_status()
        return r.json()

    async def post_json(self, path: str, body: dict):
        r = await self.client.post(path, json=body, timeout=self.timeout)
        if r.status_code == 401:
            raise HAError("Invalid HA access token.")
        r.raise_for_status()
        return r.json()

    async def healthcheck(self) -> bool:
        try:
            r = await self.client.get("/api/", timeout=self.timeout)
            return r.status_code == 200
        except Exception:
            return False



    async def get_entity(self, entity_id: str) -> dict:
        return await self.get_json(f"/api/states/{entity_id}")

    async def get_entities(self, domain: Optional[str] = None) -> list:
        params = {"domain": domain} if domain else {}
        data = await self.get_json("/api/states", params=params)
        return data if isinstance(data, list) else data.get("entities", [])

    async def get_entity_ids_by_domain(self, domain: Optional[str] = None) -> dict:
        entities = await self.get_entities(domain=domain)
        return {e["entity_id"]: e for e in entities if "entity_id" in e}

    async def turn_on(self, entity_id: str, **kwargs):
        domain, _, _ = entity_id.rpartition(".")
        return await self.post_json(f"/api/services/{domain}/turn_on", {"entity_id": entity_id, **kwargs})

    async def turn_off(self, entity_id: str, **kwargs):
        domain, _, _ = entity_id.rpartition(".")
        return await self.post_json(f"/api/services/{domain}/turn_off", {"entity_id": entity_id, **kwargs})

    async def set_value(self, entity_id: str, value: float, **kwargs):
        domain, _, _ = entity_id.rpartition(".")
        service_map = {
            "light": ("set_brightness", "brightness"),
            "climate": ("set_temperature", "temperature"),
        }
        if domain not in service_map:
            raise HAError(f"Unsupported entity type for set: {domain}")
        svc, key = service_map[domain]
        return await self.post_json(f"/api/services/{domain}/{svc}", {"entity_id": entity_id, **{key: value}})

    async def apply_scene(self, scene_id: str):
        return await self.post_json("/api/services/scene/turn_on", {"entity_id": scene_id})


class EntityRegistry:
    def __init__(self, ha: HAClient):
        self.ha = ha
        self._entities: dict = {}
        self._aliases: dict = {}
        self._areas: dict = {}  # area_id -> area_name

    async def refresh(self):
        states = await self.ha.get_entity_ids_by_domain()
        self._entities = states
        
        # Создаём алиасы из friendly_name
        for eid, data in self._entities.items():
            attrs = data.get("attributes", {})
            fname = attrs.get("friendly_name")
            if fname:
                alias = re.sub(r"[^\w\s-]", "", fname).strip().lower()
                if alias and alias != eid.split(".")[-1].lower():
                    self._aliases[alias] = eid

    def by_id_or_alias(self, text: str) -> Optional[str]:
        if not text:
            return None
        t = text.strip()
        if t in self._entities:
            return t
        return self._aliases.get(t.lower())

    def list_entities(self, domain: Optional[str] = None) -> list:
        if not domain:
            return sorted(list(self._entities.keys()))
        return sorted([k for k in self._entities if k.split(".")[0] == domain])

    def get_rooms(self) -> list:
        """Получает список комнат из area registry и атрибутов устройств."""
        rooms = set()
        
        # Сначала пробуем получить из _areas (если загружено через WebSocket)
        if hasattr(self, '_areas') and self._areas:
            for area_id, area_name in self._areas.items():
                if area_name and isinstance(area_name, str):
                    rooms.add(area_name)
        
        # Если areas не загружены, пробуем найти в атрибутах устройств
        if not rooms:
            for data in self._entities.values():
                attrs = data.get("attributes", {})
                # Ищем различные возможные атрибуты комнаты
                for key in ["room_name", "area", "area_name", "location"]:
                    room = attrs.get(key)
                    if room:
                        # Проверяем тип - должно быть строкой
                        if isinstance(room, str):
                            rooms.add(room)
                        elif isinstance(room, list) and len(room) > 0:
                            # Если это список, берём первый элемент
                            if isinstance(room[0], str):
                                rooms.add(room[0])
                        break  # Нашли комнату, переходим к следующему устройству
        
        return sorted(list(rooms))

    def get_scenes(self) -> list:
        return sorted([eid for eid in self._entities if eid.startswith("scene.")])

    def get_friendly_name(self, eid: str) -> str:
        data = self._entities.get(eid, {})
        return data.get("attributes", {}).get("friendly_name", eid)


# ---------- Главное меню (кнопки внизу чата) ----------

def get_main_keyboard(uid: Optional[int]) -> ReplyKeyboardMarkup:
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
    def __init__(self, cfg, allowed_user_id: Optional[int]):
        self.cfg = cfg
        self.allowed_user_id = allowed_user_id
        self.ha = HAClient(cfg.base_url, cfg.ha_token, cfg.timeout)
        self.registry = EntityRegistry(self.ha)
        self._timers: dict = {}
        self.app = None

    def _check_auth(self, update: Update) -> bool:
        user_id = update.effective_user.id if update.effective_user else None
        if self.allowed_user_id is not None and user_id != self.allowed_user_id:
            return False
        return True

    def _uid(self, update: Update) -> Optional[int]:
        return update.effective_user.id if update.effective_user else None

    async def _reply_text(self, update: Update, text: str, parse_mode: Optional[str] = None, **kwargs):
        MAX_LENGTH = 4096
        if len(text) <= MAX_LENGTH:
            try:
                return await update.effective_message.reply_text(
                    text, parse_mode=parse_mode, disable_web_page_preview=True, **kwargs
                )
            except Exception as e:
                logger.warning(f"Ошибка отправки: {e}")
                return None

        parts = self._split_message(text, MAX_LENGTH)
        result = None
        for i, part in enumerate(parts, 1):
            try:
                result = await update.effective_message.reply_text(
                    part, parse_mode=parse_mode, disable_web_page_preview=True, **kwargs
                )
                if i < len(parts):
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Ошибка отправки части {i}: {e}")
        return result

    def _split_message(self, text: str, max_length: int) -> list:
        lines = text.split('\n')
        parts = []
        current_part = []
        current_length = 0
        for line in lines:
            line_length = len(line) + 1
            if current_length + line_length > max_length and current_part:
                parts.append('\n'.join(current_part))
                current_part = []
                current_length = 0
            current_part.append(line)
            current_length += line_length
        if current_part:
            parts.append('\n'.join(current_part))
        return parts

    async def _get_state(self, eid: str) -> Optional[dict]:
        try:
            return await self.ha.get_entity(eid)
        except Exception as e:
            logger.error(f"Ошибка получения состояния {eid}: {e}")
            return None

    # ---------- Команды ----------
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        await self._reply_text(
            update,
            t(uid, "welcome"),
            reply_markup=get_main_keyboard(uid),
        )

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        await self._reply_text(
            update,
            t(uid, "menu_hidden"),
            reply_markup=ReplyKeyboardRemove(),
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        await self._reply_text(update, t(uid, "help_text"), "HTML")

    async def cmd_lang(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await self._reply_text(update, t(uid, "turned_on", name=esc(fname)))
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await self._reply_text(update, t(uid, "turned_off", name=esc(fname)))
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await self._reply_text(update, t(uid, "toggled", name=esc(fname)))
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        eid = self.registry.by_id_or_alias(context.args[0]) if context.args else None
        if eid:
            s = await self._get_state(eid)
            if not s:
                return await self._reply_text(update, t(uid, "not_found"))
            a = s.get("attributes", {})
            state = s.get("state")
            state_l = state_localized(uid, state)
            out = t(uid, "current_state", name=esc(a.get('friendly_name', eid)), state=esc(state_l))
            if a:
                attrs_json = json.dumps(a, ensure_ascii=False, indent=1)
                out += f"\n{t(uid, 'attrs_label')}\n<code>{esc(attrs_json)}</code>"
            return await self._reply_text(update, out, "HTML")
        else:
            entities = self.registry._entities
            if not entities:
                return await self._reply_text(update, t(uid, "empty_list"))
            lines = []
            for k, s in entities.items():
                a = s.get("attributes", {})
                state = s.get("state")
                state_l = state_localized(uid, state, short=True)
                lines.append(f"<b>{esc(a.get('friendly_name', k))}</b> — <code>{esc(state_l)}</code>")
            text = t(uid, "all_devices_title") + "\n\n" + "\n".join(lines)
            return await self._reply_text(update, text, "HTML")

    async def cmd_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, "⚠️ /room <комната>")
        room_name = " ".join(context.args)
        await self._show_room(update, uid, room_name)

    async def cmd_scene(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, "⚠️ /scene <имя>")
        name = " ".join(context.args)
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "scene_not_found", name=esc(name)))
        try:
            await self.ha.apply_scene(eid)
            await self._reply_text(update, t(uid, "scene_applied", name=esc(name)))
        except HAError as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        ok = await self.ha.healthcheck()
        await self._reply_text(update, t(uid, "ha_online") if ok else t(uid, "ha_offline"))

    async def cmd_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if len(context.args) < 2:
            return await self._reply_text(update, "⚠️ /timer <мин> <имя>")
        try:
            minutes = int(context.args[0])
        except ValueError:
            return await self._reply_text(update, "⚠️ Время должно быть числом")
        name = " ".join(context.args[1:])
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))

        async def turn_off_later():
            await asyncio.sleep(minutes * 60)
            try:
                await self.ha.turn_off(eid)
                if update.effective_chat:
                    await update.effective_chat.send_message(
                        t(uid, "timer_fired", eid=esc(eid), minutes=minutes),
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.error(f"Ошибка таймера: {e}")

        task = asyncio.create_task(turn_off_later())
        self._timers[uid] = task
        await self._reply_text(update, t(uid, "timer_started", eid=esc(eid), minutes=minutes), "HTML")

    # ---------- Inline-меню ----------
    def _main_menu_inline(self, uid: Optional[int]) -> InlineKeyboardMarkup:
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
        return [InlineKeyboardButton(t(uid, "btn_main_menu"), callback_data="menu_main")]

    async def _show_control_menu(self, update_or_query, uid: Optional[int]):
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(t(uid, "btn_on"), callback_data="ctrl_on"),
                InlineKeyboardButton(t(uid, "btn_off"), callback_data="ctrl_off"),
            ],
            [InlineKeyboardButton(t(uid, "btn_toggle"), callback_data="ctrl_toggle")],
            self._back_to_main_button(uid),
        ])
        text = t(uid, "control_title")
        if isinstance(update_or_query, CallbackQueryHandler):
            pass
        # Универсальный способ — редактирование или отправка
        await self._send_or_edit(update_or_query, text, "HTML", keyboard)

    async def _show_status_menu(self, update_or_query, uid: Optional[int]):
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
            # callback_data ограничен 64 байтами
            cb_data = f"room:{room}"[:64]
            buttons.append([InlineKeyboardButton(f"🏠 {room}", callback_data=cb_data)])
        buttons.append(self._back_to_main_button(uid))
        await self._send_or_edit(update_or_query, t(uid, "rooms_title"), "HTML", InlineKeyboardMarkup(buttons))

    async def _show_scenes_menu(self, update_or_query, uid: Optional[int]):
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
            cb_data = f"sc:{scene_id}"[:64]
            buttons.append([InlineKeyboardButton(f"🎬 {fname}", callback_data=cb_data)])
        buttons.append(self._back_to_main_button(uid))
        await self._send_or_edit(update_or_query, t(uid, "scenes_title"), "HTML", InlineKeyboardMarkup(buttons))

    async def _show_settings_menu(self, update_or_query, uid: Optional[int]):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(uid, "btn_lang"), callback_data="set_lang")],
            [InlineKeyboardButton(t(uid, "btn_ha_status"), callback_data="set_hastatus")],
            self._back_to_main_button(uid),
        ])
        await self._send_or_edit(update_or_query, t(uid, "settings_title"), "HTML", keyboard)

    async def _show_device_list(self, update_or_query, uid: Optional[int], action: str, action_key: str, domain: Optional[str] = None):
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
        # Фильтруем только управляемые устройства
        controllable = [e for e in entities if e.split(".")[0] in {"light", "switch", "fan", "cover"}]
        if not controllable:
            controllable = entities
        buttons = []
        for eid in controllable:
            fname = self.registry.get_friendly_name(eid)
            # cb_data: "on:light.kitchen" или "off:..."
            cb_data = f"{action_key}:{eid}"[:64]
            buttons.append([InlineKeyboardButton(fname, callback_data=cb_data)])
        buttons.append([InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_control")])
        text = t(uid, "select_device", action=action)
        await self._send_or_edit(update_or_query, text, "HTML", InlineKeyboardMarkup(buttons))

    async def _show_room_devices(self, update_or_query, uid: Optional[int], room_name: str):
        await self._show_room(update_or_query, uid, room_name, as_query=True)

    async def _show_room(self, update_or_query, uid: Optional[int], room_name: str, as_query: bool = False):
        entities = self.registry._entities
        lines = []
        buttons = []
        for eid, data in entities.items():
            attrs = data.get("attributes", {})
            room = attrs.get("room_name", "") or attrs.get("area", "")
            if room_name.lower() in room.lower():
                state = data.get("state")
                state_l = state_localized(uid, state, short=True)
                fname = attrs.get("friendly_name", eid)
                lines.append(f"<b>{esc(fname)}</b> — <code>{esc(state_l)}</code>")
                # Кнопки управления для каждого устройства
                if eid.split(".")[0] in {"light", "switch", "fan", "cover"}:
                    buttons.append([
                        InlineKeyboardButton(f"✅ {fname}", callback_data=f"on:{eid}"[:64]),
                        InlineKeyboardButton(f"❌ {fname}", callback_data=f"off:{eid}"[:64]),
                    ])
        if not lines:
            text = t(uid, "room_not_found", room=esc(room_name))
            kb = InlineKeyboardMarkup([self._back_to_main_button(uid)])
        else:
            text = t(uid, "room_title", room=esc(room_name)) + "\n\n" + "\n".join(lines)
            buttons.append(self._back_to_main_button(uid))
            kb = InlineKeyboardMarkup(buttons)
        await self._send_or_edit(update_or_query, text, "HTML", kb)

    async def _send_or_edit(self, update_or_query, text: str, parse_mode: Optional[str] = None, reply_markup=None):
        """Универсальный метод: редактирует сообщение если это callback, иначе отправляет новое."""
        # update_or_query может быть Update или CallbackQuery
        if hasattr(update_or_query, "data"):
            # Это CallbackQuery
            try:
                await update_or_query.edit_message_text(
                    text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=True
                )
            except Exception as e:
                logger.warning(f"Ошибка редактирования: {e}")
        else:
            # Это Update
            update = update_or_query
            try:
                await update.effective_message.reply_text(
                    text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=True
                )
            except Exception as e:
                logger.warning(f"Ошибка отправки: {e}")

    # ---------- Callback handler ----------
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not self._check_auth(update):
            return
        uid = query.from_user.id
        data = query.data or ""

        # Смена языка
        if data.startswith("lang_"):
            lang = data.split("_", 1)[1]
            if lang in MESSAGES:
                set_lang(uid, lang)
                await query.edit_message_text(t(uid, "lang_set"))
                # Обновляем главное меню
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
            await query.edit_message_text(t(uid, "help_text"), parse_mode="HTML", reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]))

        # Подменю управления — выбор действия
        elif data == "ctrl_on":
            await self._show_device_list(query, uid, t(uid, "btn_on"), "on")
        elif data == "ctrl_off":
            await self._show_device_list(query, uid, t(uid, "btn_off"), "off")
        elif data == "ctrl_toggle":
            await self._show_device_list(query, uid, t(uid, "btn_toggle"), "tg")

        # Статус по типу
        elif data == "stat_all":
            await self._show_status_list(query, uid, None)
        elif data.startswith("stat_"):
            domain = data.split("_", 1)[1]
            await self._show_status_list(query, uid, domain)

        # Настройки
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
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]))

        # Действие с устройством: "on:light.kitchen", "off:...", "tg:..."
        elif ":" in data:
            action, _, eid = data.partition(":")
            if action == "on":
                try:
                    await self.ha.turn_on(eid)
                    fname = self.registry.get_friendly_name(eid)
                    await query.edit_message_text(
                        t(uid, "turned_on", name=esc(fname)),
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
                    )
                except Exception as e:
                    await query.edit_message_text(t(uid, "error", err=esc(str(e))))
            elif action == "off":
                try:
                    await self.ha.turn_off(eid)
                    fname = self.registry.get_friendly_name(eid)
                    await query.edit_message_text(
                        t(uid, "turned_off", name=esc(fname)),
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
                    )
                except Exception as e:
                    await query.edit_message_text(t(uid, "error", err=esc(str(e))))
            elif action == "tg":
                try:
                    s = await self._get_state(eid)
                    if s and s.get("state") == "off":
                        await self.ha.turn_on(eid)
                    else:
                        await self.ha.turn_off(eid)
                    fname = self.registry.get_friendly_name(eid)
                    await query.edit_message_text(
                        t(uid, "toggled", name=esc(fname)),
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([self._back_to_main_button(uid)]),
                    )
                except Exception as e:
                    await query.edit_message_text(t(uid, "error", err=esc(str(e))))
            elif data.startswith("room:"):
                room_name = data[5:]
                await self._show_room_devices(query, uid, room_name)
            elif data.startswith("sc:"):
                scene_id = data[3:]
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
            attrs = data.get("attributes", {})
            state = data.get("state")
            state_l = state_localized(uid, state, short=True)
            fname = attrs.get("friendly_name", eid)
            lines.append(f"<b>{esc(fname)}</b> — <code>{esc(state_l)}</code>")
        title_key = "all_devices_title" if domain is None else "devices_of_type_title"
        title = t(uid, title_key, domain=esc(domain)) if domain else t(uid, title_key)
        text = title + "\n\n" + "\n".join(lines)
        # Разбиваем если длинно
        if len(text) > 4000:
            text = text[:4000] + "\n\n..."
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_status")],
            ]),
        )

    # ---------- Обработка текстовых кнопок меню ----------
    async def on_menu_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        text = update.message.text
        lang = get_lang(uid)

        # Сопоставление текста кнопок с действиями
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
            # Обычное текстовое сообщение — ищем устройство
            eid = self.registry.by_id_or_alias(text)
            if eid and eid.endswith((".light", ".switch", ".fan", ".cover", ".plug", ".scene")):
                action = "on" if text.lower().endswith(("on", "вкл", "включить")) else "off"
                try:
                    if action == "on":
                        await self.ha.turn_on(eid)
                        fname = self.registry.get_friendly_name(eid)
                        await self._reply_text(update, t(uid, "turned_on", name=esc(fname)), "HTML")
                    else:
                        await self.ha.turn_off(eid)
                        fname = self.registry.get_friendly_name(eid)
                        await self._reply_text(update, t(uid, "turned_off", name=esc(fname)), "HTML")
                except Exception as e:
                    await self._reply_text(update, t(uid, "error", err=esc(str(e))))


# ---------- Main ----------

def main():
    from dataclasses import dataclass

    @dataclass
    class Config:
        token: Optional[str] = None
        base_url: str = "http://localhost:8123"
        ha_token: Optional[str] = None
        allowed_user_id: Optional[int] = None
        timeout: int = 15

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
            logger.info(f"Загружено устройств: {len(bot.registry._entities)}")
        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")

        async def refresher():
            while True:
                await asyncio.sleep(60)
                try:
                    await bot.registry.refresh()
                except Exception as e:
                    logger.error(f"Ошибка обновления: {e}")

        application.create_task(refresher(), name="entity_refresh")

    async def post_shutdown(application: Application):
        logger.info("Остановка бота...")
        await bot.ha.close()

    app = (
        ApplicationBuilder()
        .token(cfg.token)
        .job_queue(None)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Команды
    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("menu", bot.cmd_menu))
    app.add_handler(CommandHandler("hide", bot.cmd_hide))
    app.add_handler(CommandHandler("help", bot.cmd_help))
    app.add_handler(CommandHandler("lang", bot.cmd_lang))
    app.add_handler(CommandHandler("on", bot.cmd_on))
    app.add_handler(CommandHandler("off", bot.cmd_off))
    app.add_handler(CommandHandler("toggle", bot.cmd_toggle))
    app.add_handler(CommandHandler("state", bot.cmd_state))
    app.add_handler(CommandHandler("room", bot.cmd_room))
    app.add_handler(CommandHandler("scene", bot.cmd_scene))
    app.add_handler(CommandHandler("status", bot.cmd_status))
    app.add_handler(CommandHandler("timer", bot.cmd_timer))

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(bot.callback_handler))

    # Текстовые кнопки меню + обычные сообщения
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_menu_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

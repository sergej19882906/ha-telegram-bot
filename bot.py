"""
Telegram-бот для Home Assistant с поддержкой русского и английского языков.

Команды:
  /start, /help — приветствие и список команд
  /lang — выбор языка интерфейса
  /on <имя>     — включить (свет, розетка, вентилятор)
  /off <имя>    — выключить
  /toggle <имя> — переключить вкл/выкл
  /set <имя> <значение> — установить значение (яркость, температура)
  /state [устройство] — статус устройства (или всех сразу)
  /entities [тип] — список устройств
  /room <комната> — все устройства в комнате
  /scene <имя> — активировать сцену
  /timer <мин> <имя> — таймер выключения устройства
"""

import asyncio
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from pydantic import ValidationError
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
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
    """Экранирует HTML-символы."""
    return html.escape(str(text)) if text is not None else ""


# ---------- Локализация ----------

MESSAGES = {
    "ru": {
        "welcome": "👋 Привет! Я бот для управления вашим умным домом.\n\nОтправьте /help, чтобы увидеть список команд.",
        "help_title": "📋 <b>Список команд:</b>",
        "help_lang": "<code>/lang</code> — выбрать язык / choose language",
        "help_on": "<code>/on</code> <i>имя</i> — включить устройство",
        "help_off": "<code>/off</code> <i>имя</i> — выключить устройство",
        "help_toggle": "<code>/toggle</code> <i>имя</i> — переключить вкл/выкл",
        "help_set": "<code>/set</code> <i>имя значение</i> — установить значение (яркость, температура)",
        "help_state": "<code>/state</code> [<i>устройство</i>] — показать статус",
        "help_entities": "<code>/entities</code> [<i>тип</i>] — список устройств",
        "help_room": "<code>/room</code> <i>комната</i> — все устройства в комнате",
        "help_scene": "<code>/scene</code> <i>имя</i> — активировать сцену",
        "help_timer": "<code>/timer</code> <i>мин имя</i> — таймер выключения",
        "help_status": "<code>/status</code> — состояние Home Assistant",
        "help_hint": "💡 <i>Имя устройства — это его название из Home Assistant (например: «Люстра», «Торшер»).</i>",
        "help_examples": "📝 <i>Примеры:</i>",
        "help_ex1": "• <code>/on Люстра</code>",
        "help_ex2": "• <code>/off Кондиционер</code>",
        "help_ex3": "• <code>/set Люстра 50</code>",
        "help_ex4": "• <code>/room Гостиная</code>",
        "help_ex5": "• <code>/timer 30 Торшер</code>",
        "choose_lang": "🌐 Выберите язык / Choose language:",
        "lang_set": "✅ Язык изменён на русский.",
        "not_found": "❌ Устройство не найдено.",
        "device_not_found": "❌ Устройство «{name}» не найдено.",
        "scene_not_found": "❌ Сцена «{name}» не найдена.",
        "empty_list": "📭 Список устройств пуст. Подождите немного — бот обновляет данные.",
        "empty_list_short": "📭 Список пуст.",
        "usage_room": "⚠️ Использование: /room <название комнаты>",
        "usage_scene": "⚠️ Использование: /scene <название сцены>",
        "usage_timer": "⚠️ Использование: /timer <минуты> <имя устройства>",
        "usage_on": "⚠️ Использование: /on <имя устройства>",
        "usage_off": "⚠️ Использование: /off <имя устройства>",
        "usage_toggle": "⚠️ Использование: /toggle <имя устройства>",
        "usage_set": "⚠️ Использование: /set <имя> <значение>",
        "value_must_be_number": "⚠️ Значение должно быть числом.",
        "time_must_be_minutes": "⚠️ Время должно быть числом (в минутах).",
        "scene_applied": "🎬 Сцена «{name}» активирована.",
        "ha_online": "✅ Home Assistant: онлайн",
        "ha_offline": "❌ Home Assistant: недоступен",
        "turned_on": "✅ Включено.",
        "turned_off": "🔌 Выключено.",
        "current_state": "ℹ️ Текущее состояние: {state}.",
        "unknown": "неизвестно",
        "error": "❌ Ошибка: {err}",
        "done": "✅ Готово.",
        "value_set": "✅ Установлено значение: {value}.",
        "timer_started": "⏳ Таймер запущен для <code>{eid}</code>.\nУстройство выключится через {minutes} мин.",
        "timer_fired": "⏰ Таймер сработал: устройство <code>{eid}</code> выключено через {minutes} мин.",
        "room_not_found": "🔍 В комнате «{room}» устройств не найдено.",
        "room_title": "🏠 <b>Комната «{room}»:</b>",
        "all_devices_title": "📋 <b>Все устройства по типам:</b>",
        "devices_of_type_title": "📋 <b>Устройства типа {domain}:</b>",
        "state_label": "Состояние:",
        "attrs_label": "Атрибуты:",
        "list_truncated": "... список обрезан",
        "state_on": "включено",
        "state_off": "выключено",
        "state_unavailable": "недоступно",
        "state_on_short": "вкл",
        "state_off_short": "выкл",
    },
    "en": {
        "welcome": "👋 Hello! I'm your smart home control bot.\n\nSend /help to see the list of commands.",
        "help_title": "📋 <b>Commands list:</b>",
        "help_lang": "<code>/lang</code> — choose language / выбрать язык",
        "help_on": "<code>/on</code> <i>name</i> — turn on a device",
        "help_off": "<code>/off</code> <i>name</i> — turn off a device",
        "help_toggle": "<code>/toggle</code> <i>name</i> — toggle on/off",
        "help_set": "<code>/set</code> <i>name value</i> — set value (brightness, temperature)",
        "help_state": "<code>/state</code> [<i>device</i>] — show status",
        "help_entities": "<code>/entities</code> [<i>type</i>] — list of devices",
        "help_room": "<code>/room</code> <i>room</i> — all devices in a room",
        "help_scene": "<code>/scene</code> <i>name</i> — activate a scene",
        "help_timer": "<code>/timer</code> <i>min name</i> — turn-off timer",
        "help_status": "<code>/status</code> — Home Assistant status",
        "help_hint": "💡 <i>Device name is its friendly name from Home Assistant (e.g. «Ceiling Light», «AC»).</i>",
        "help_examples": "📝 <i>Examples:</i>",
        "help_ex1": "• <code>/on Ceiling Light</code>",
        "help_ex2": "• <code>/off AC</code>",
        "help_ex3": "• <code>/on Ceiling Light 50</code>",
        "help_ex4": "• <code>/room Living Room</code>",
        "help_ex5": "• <code>/timer 30 Floor Lamp</code>",
        "choose_lang": "🌐 Choose language / Выберите язык:",
        "lang_set": "✅ Language changed to English.",
        "not_found": "❌ Device not found.",
        "device_not_found": "❌ Device «{name}» not found.",
        "scene_not_found": "❌ Scene «{name}» not found.",
        "empty_list": "📭 Device list is empty. Please wait — the bot is updating data.",
        "empty_list_short": "📭 List is empty.",
        "usage_room": "⚠️ Usage: /room <room name>",
        "usage_scene": "⚠️ Usage: /scene <scene name>",
        "usage_timer": "⚠️ Usage: /timer <minutes> <device name>",
        "usage_on": "⚠️ Usage: /on <device name>",
        "usage_off": "⚠️ Usage: /off <device name>",
        "usage_toggle": "⚠️ Usage: /toggle <device name>",
        "usage_set": "⚠️ Usage: /set <name> <value>",
        "value_must_be_number": "⚠️ Value must be a number.",
        "time_must_be_minutes": "⚠️ Time must be a number (in minutes).",
        "scene_applied": "🎬 Scene «{name}» activated.",
        "ha_online": "✅ Home Assistant: online",
        "ha_offline": "❌ Home Assistant: offline",
        "turned_on": "✅ Turned on.",
        "turned_off": "🔌 Turned off.",
        "current_state": "ℹ️ Current state: {state}.",
        "unknown": "unknown",
        "error": "❌ Error: {err}",
        "done": "✅ Done.",
        "value_set": "✅ Value set to: {value}.",
        "timer_started": "⏳ Timer started for <code>{eid}</code>.\nDevice will turn off in {minutes} min.",
        "timer_fired": "⏰ Timer fired: device <code>{eid}</code> turned off after {minutes} min.",
        "room_not_found": "🔍 No devices found in room «{room}».",
        "room_title": "🏠 <b>Room «{room}»:</b>",
        "all_devices_title": "📋 <b>All devices by type:</b>",
        "devices_of_type_title": "📋 <b>Devices of type {domain}:</b>",
        "state_label": "State:",
        "attrs_label": "Attributes:",
        "list_truncated": "... list truncated",
        "state_on": "on",
        "state_off": "off",
        "state_unavailable": "unavailable",
        "state_on_short": "on",
        "state_off_short": "off",
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
    """Локализует стандартные состояния HA."""
    if state == "on":
        return t(user_id, "state_on_short" if short else "state_on")
    if state == "off":
        return t(user_id, "state_off_short" if short else "state_off")
    if state == "unavailable":
        return t(user_id, "state_unavailable")
    return state


# ---------- Настройки ----------

class Config:
    token: Optional[str] = None
    base_url: str = "http://localhost:8123"
    ha_token: Optional[str] = None
    allowed_user_id: Optional[int] = None
    timeout: int = 15

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)

    @property
    def auth(self):
        return {"Authorization": f"Bearer {self.ha_token}"}


# ---------- Клиент Home Assistant ----------

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

    async def get_entities(self, domain: Optional[str] = None, area: Optional[str] = None) -> list:
        params: dict = {}
        if domain:
            params["domain"] = domain
        if area:
            params["area"] = area
        data = await self.get_json("/api/states", params=params)
        if isinstance(data, list):
            return data
        return data.get("entities", [])

    async def get_entity_ids_by_domain(self, domain: Optional[str] = None) -> dict:
        entities = await self.get_entities(domain=domain)
        return {e["entity_id"]: e for e in entities if "entity_id" in e}

    async def turn_on(self, entity_id: str, **kwargs):
        domain, _, device = entity_id.rpartition(".")
        return await self.post_json(f"/api/services/{domain}/turn_on", {"entity_id": entity_id, **kwargs})

    async def turn_off(self, entity_id: str, **kwargs):
        domain, _, device = entity_id.rpartition(".")
        return await self.post_json(f"/api/services/{domain}/turn_off", {"entity_id": entity_id, **kwargs})

    async def set_value(self, entity_id: str, value: float, **kwargs):
        domain, _, device = entity_id.rpartition(".")
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


# ---------- Состояние устройств ----------

class EntityRegistry:
    def __init__(self, ha: HAClient):
        self.ha = ha
        self._entities: dict = {}
        self._aliases: dict = {}

    async def refresh(self):
        states = await self.ha.get_entity_ids_by_domain()
        self._entities = states
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


# ---------- Обработчики Telegram ----------

class HATelegramBot:
    def __init__(self, cfg: Config, allowed_user_id: Optional[int]):
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
        """Отправляет сообщение, автоматически разбивая его на части если оно слишком длинное."""
        MAX_LENGTH = 4096
        
        # Если сообщение короткое, отправляем как есть
        if len(text) <= MAX_LENGTH:
            try:
                return await update.effective_message.reply_text(
                    text, parse_mode=parse_mode, disable_web_page_preview=True, **kwargs
                )
            except Exception as e:
                logger.warning(f"Ошибка отправки сообщения: {e}")
                return None
        
        # Разбиваем длинное сообщение на части
        parts = self._split_message(text, MAX_LENGTH)
        logger.info(f"Сообщение разбито на {len(parts)} частей")
        
        for i, part in enumerate(parts, 1):
            try:
                await update.effective_message.reply_text(
                    part, parse_mode=parse_mode, disable_web_page_preview=True, **kwargs
                )
                # Небольшая задержка между частями, чтобы не спамить API
                if i < len(parts):
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Ошибка отправки части {i}: {e}")
        
        return None

    def _split_message(self, text: str, max_length: int) -> list:
        """Разбивает сообщение на части по строкам, не разрывая HTML-теги."""
        lines = text.split('\n')
        parts = []
        current_part = []
        current_length = 0
        
        for line in lines:
            line_length = len(line) + 1  # +1 для \n
            
            if current_length + line_length > max_length:
                # Текущая часть заполнена, сохраняем её
                if current_part:
                    parts.append('\n'.join(current_part))
                    current_part = []
                    current_length = 0
            
            current_part.append(line)
            current_length += line_length
        
        # Добавляем последнюю часть
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
        await self._reply_text(update, t(self._uid(update), "welcome"))

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        lines = [
            t(uid, "help_title"),
            "",
            t(uid, "help_lang"),
            t(uid, "help_on"),
            t(uid, "help_off"),
            t(uid, "help_toggle"),
            t(uid, "help_set"),
            t(uid, "help_state"),
            t(uid, "help_entities"),
            t(uid, "help_room"),
            t(uid, "help_scene"),
            t(uid, "help_timer"),
            t(uid, "help_status"),
            "",
            t(uid, "help_hint"),
            "",
            t(uid, "help_examples"),
            t(uid, "help_ex1"),
            t(uid, "help_ex2"),
            t(uid, "help_ex3"),
            t(uid, "help_ex4"),
            t(uid, "help_ex5"),
        ]
        await self._reply_text(update, "\n".join(lines), "HTML")

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

    async def callback_lang(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not self._check_auth(update):
            return
        data = query.data or ""
        if data.startswith("lang_"):
            lang = data.split("_", 1)[1]
            if lang in MESSAGES:
                set_lang(query.from_user.id, lang)
                await query.edit_message_text(t(query.from_user.id, "lang_set"))

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
            state_ru = state_localized(uid, state)
            out = f"<b>{esc(a.get('friendly_name', eid))}</b>\n{t(uid, 'state_label')} <code>{esc(state_ru)}</code>"
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
            text = "\n".join(lines)
            return await self._reply_text(update, text, "HTML")

    async def cmd_entities(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        domain = context.args[0] if context.args else None
        ents = self.registry.list_entities(domain)
        if not ents:
            return await self._reply_text(update, t(uid, "empty_list_short"))

        if domain is None:
            grouped: dict = {}
            for e in self.registry._entities:
                d = e.split(".")[0]
                grouped.setdefault(d, []).append(e)
            lines = [t(uid, "all_devices_title"), ""]
            for d, ids in sorted(grouped.items()):
                lines.append(f"\n<b>{esc(d)}</b> ({len(ids)})")
                lines += [f"  <code>{esc(e)}</code>" for e in ids]
        else:
            lines = [t(uid, "devices_of_type_title", domain=esc(domain)), ""]
            lines += [f"<code>{esc(e)}</code>" for e in ents]

        return await self._reply_text(update, "\n".join(lines), "HTML")

    async def cmd_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, t(uid, "usage_room"))
        room_name = " ".join(context.args)
        entities = self.registry._entities
        lines = []
        for eid, data in entities.items():
            attrs = data.get("attributes", {})
            room = attrs.get("room_name", "") or attrs.get("area", "")
            if room_name.lower() in room.lower():
                state = data.get("state")
                state_l = state_localized(uid, state, short=True)
                lines.append(f"<code>{esc(eid)}</code> — {esc(state_l)}")
        if not lines:
            return await self._reply_text(update, t(uid, "room_not_found", room=esc(room_name)))
        return await self._reply_text(
            update,
            t(uid, "room_title", room=esc(room_name)) + "\n\n" + "\n".join(lines),
            "HTML",
        )

    async def cmd_scene(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        name = " ".join(context.args) if context.args else None
        if not name:
            return await self._reply_text(update, t(uid, "usage_scene"))
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "scene_not_found", name=esc(name)))
        try:
            await self.ha.apply_scene(eid)
            return await self._reply_text(update, t(uid, "scene_applied", name=esc(name)))
        except HAError as e:
            return await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        ok = await self.ha.healthcheck()
        return await self._reply_text(update, t(uid, "ha_online") if ok else t(uid, "ha_offline"))

    # ---------- Действия ----------
    async def _do_action(self, update: Update, action: str, eid: str) -> str:
        uid = self._uid(update)
        try:
            if action == "on":
                await self.ha.turn_on(eid)
                return t(uid, "turned_on")
            if action == "off":
                await self.ha.turn_off(eid)
                return t(uid, "turned_off")
            if action == "toggle":
                s = await self._get_state(eid)
                if s and s.get("state") == "off":
                    await self.ha.turn_on(eid)
                    return t(uid, "turned_on")
                elif s and s.get("state") == "on":
                    await self.ha.turn_off(eid)
                    return t(uid, "turned_off")
                else:
                    cur = s.get("state") if s else t(uid, "unknown")
                    return t(uid, "current_state", state=esc(state_localized(uid, cur)))
        except Exception as e:
            return t(uid, "error", err=esc(str(e)))
        return t(uid, "done")

    async def cmd_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, t(uid, "usage_on"))
        name = " ".join(context.args)
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        await self._reply_text(update, await self._do_action(update, "on", eid))

    async def cmd_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, t(uid, "usage_off"))
        name = " ".join(context.args)
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        await self._reply_text(update, await self._do_action(update, "off", eid))

    async def cmd_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, t(uid, "usage_toggle"))
        name = " ".join(context.args)
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        await self._reply_text(update, await self._do_action(update, "toggle", eid))

    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if len(context.args) < 2:
            return await self._reply_text(update, t(uid, "usage_set"))
        name = context.args[0]
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return await self._reply_text(update, t(uid, "device_not_found", name=esc(name)))
        try:
            value = float(context.args[1])
        except ValueError:
            return await self._reply_text(update, t(uid, "value_must_be_number"))
        try:
            await self.ha.set_value(eid, value)
            return await self._reply_text(update, t(uid, "value_set", value=value))
        except Exception as e:
            return await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if len(context.args) < 2:
            return await self._reply_text(update, t(uid, "usage_timer"))
        try:
            minutes = int(context.args[0])
        except ValueError:
            return await self._reply_text(update, t(uid, "time_must_be_minutes"))
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
        return await self._reply_text(
            update,
            t(uid, "timer_started", eid=esc(eid), minutes=minutes),
            "HTML",
        )

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text if update.message else ""
        eid = self.registry.by_id_or_alias(text)
        if eid and eid.endswith((".light", ".switch", ".fan", ".cover", ".plug", ".scene")):
            action = "on" if text.lower().endswith(("on", "вкл", "включить")) else "off"
            await self._reply_text(update, await self._do_action(update, action, eid))

        for uid in list(self._timers):
            tsk = self._timers[uid]
            if tsk.done():
                del self._timers[uid]


# ---------- Запуск ----------

def main():
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
            logger.error(f"Ошибка первоначальной загрузки: {e}")

        async def refresher():
            while True:
                await asyncio.sleep(60)
                try:
                    await bot.registry.refresh()
                except Exception as e:
                    logger.error(f"Ошибка обновления: {e}")

        application.create_task(refresher(), name="entity_refresh")

    async def post_shutdown(application: Application):
        logger.info("Остановка бота, закрываю соединение с HA...")
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
    app.add_handler(CommandHandler("help", bot.cmd_help))
    app.add_handler(CommandHandler("lang", bot.cmd_lang))
    app.add_handler(CommandHandler("state", bot.cmd_state))
    app.add_handler(CommandHandler("entities", bot.cmd_entities))
    app.add_handler(CommandHandler("room", bot.cmd_room))
    app.add_handler(CommandHandler("scene", bot.cmd_scene))
    app.add_handler(CommandHandler("status", bot.cmd_status))
    app.add_handler(CommandHandler("on", bot.cmd_on))
    app.add_handler(CommandHandler("off", bot.cmd_off))
    app.add_handler(CommandHandler("toggle", bot.cmd_toggle))
    app.add_handler(CommandHandler("set", bot.cmd_set))
    app.add_handler(CommandHandler("timer", bot.cmd_timer))
    app.add_handler(CallbackQueryHandler(bot.callback_lang, pattern=r"^lang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
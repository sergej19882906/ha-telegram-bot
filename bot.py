"""
Telegram bot for Home Assistant.

Commands:
  /start, /help — intro
  /on <alias>     — turn on (light, switch, fan, plug)
  /off <alias>    — turn off
  /toggle <alias> — on/off
  /set <alias> <value> — set value (percent, temperature, slider)
  /state [entity] — status of an entity (or all)
  /entities [type] — list of entities (light, switch, climate...)
  /room <room> — all entities in a room
  /scene <name> [on/off] — scene
  /timer <min> <alias> — timer for the device
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from pydantic import ValidationError
from telegram import Update
from telegram.constants import ParseMode
from telegram.constants import ChatAction, ParseMode as PM
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


# ---------- Settings ----------

class Config:
    token: Optional[str] = None
    base_url: str = "https://12123456789"  # placeholder
    ha_token: Optional[str] = None
    allowed_user_id: Optional[int] = None
    timeout: int = 15

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)

    @property
    def auth(self):
        return {"Authorization": f"Bearer {self.ha_token}"}


# ---------- Home Assistant client ----------

class HAError(Exception):
    """Error when communicating with HA."""
    pass

class HAServiceError(HAError):
    pass


class HAClient:
    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=("Bearer", token),
            timeout=self.timeout,
        )

    async def close(self):
        await self.client.aclose()

    async def get_json(self, path: str, params: Optional[dict] = None) -> dict:
        r = await self.client.get(path, params=params)
        if r.status_code == 401:
            raise HAError("Invalid HA access token.")
        r.raise_for_status()
        return r.json()

    async def post_json(self, path: str, body: dict) -> dict:
        r = await self.client.post(path, json=body, timeout=self.timeout)
        if r.status_code == 401:
            raise HAError("Invalid HA access token.")
        r.raise_for_status()
        return r.json()

    # --- basic queries ---
    async def healthcheck(self) -> bool:
        try:
            r = await self.client.get("/api/status/command_line", timeout=self.timeout)
            return r.status_code == 200
        except Exception:
            return False

    async def get_entity(self, entity_id: str) -> dict:
        return await self.get_json(f"/api/states/{entity_id}")

    async def get_entities(self, domain: Optional[str] = None, area: Optional[str] = None) -> list[dict]:
        params: dict = {}
        if domain:
            params["domain"] = domain
        if area:
            params["area"] = area
        return await self.get_json("/api/states", params=params).get("entities", {})

    async def get_entity_ids_by_domain(self, domain: Optional[str] = None) -> dict[str, dict]:
        entities = await self.get_entities(domain=domain)
        return {eid: data for eid, data in entities.items()}

    # --- services ---
    async def turn_on(self, entity_id: str, **kwargs):
        domain, _, device = entity_id.rpartition(".")
        return await self.post_json(f"/api/services/{domain}/turn_on", {"entity_id": entity_id, **kwargs})

    async def turn_off(self, entity_id: str, **kwargs):
        domain, _, device = entity_id.rpartition(".")
        return await self.post_json(f"/api/services/{domain}/turn_off", {"entity_id": entity_id, **kwargs})

    async def set_value(self, entity_id: str, value: float, service="set_level", **kwargs) -> dict:
        domain, _, device = entity_id.rpartition(".")
        # domain-specific services
        services = {
            "light": "set_brightness",
            "switch": None,  # only on/off
            "fan": "set_speed",
            "climate": "set_temperature",
        }
        service_map = {
            "light": ("set_brightness", "brightness"),
            "climate": ("set_temperature", "temperature"),
        }
        if domain not in service_map:
            raise HAError(f"Unsupported entity type for set: {domain}")
        svc, key = service_map[domain]
        return await self.post_json(f"/api/services/{domain}/{svc}", {"entity_id": entity_id, **{key: value}})

    async def apply_scene(self, scene_id: str):
        domain, _, name = scene_id.rpartition(".")
        return await self.post_json(f"/api/services/scene/turn_on", {"entity_id": scene_id})

    async def get_entity_list(self) -> dict[str, dict]:
        return await self.get_entities()


# ---------- Entity state ---

@dataclass(frozen=True)
class Entity:
    entity_id: str
    name: str
    domain: str
    room: str
    is_light: bool

    @classmethod
    def from_state(cls, eid: str, state: dict) -> "Entity":
        domain = eid.rsplit(".", 1)[0]
        attrs = state.get("attributes", {})
        room = attrs.get("room_name") or attrs.get("friendly_name", "")
        return cls(eid, attrs.get("friendly_name", eid), domain, room, domain in {"light", "switch", "fan", "cover", "scene", "plug"})


class EntityRegistry:
    def __init__(self, ha: HAClient):
        self.ha = ha
        self._entities: dict[str, dict] = {}
        self._aliases: dict[str, str] = {}

    async def refresh(self):
        states = await self.ha.get_entity_ids_by_domain()
        self._entities = {eid: data for eid, data in states.items()}
        # auto-aliases from friendly name
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

    def list_entities(self, domain: Optional[str] = None) -> list[str]:
        keys = self._entities if not domain else {k for k in self._entities if k.split(".")[0] == domain}
        return sorted(keys)


# ---------- Telegram handlers ---

class HATelegramBot:
    def __init__(self, cfg: Config, allowed_user_id: int | None):
        self.cfg = cfg
        self.allowed_user_id = allowed_user_id
        self.ha = HAClient(cfg.base_url, cfg.ha_token, cfg.timeout)
        self.registry = EntityRegistry(self.ha)
        self._timers: dict[int, asyncio.Task] = {}
        self.app = None

    # --- permission ---
    def _check_auth(self, update: Update):
        user_id = update.effective_user.id if update.effective_user else None
        if self.allowed_user_id is not None and user_id != self.allowed_user_id:
            return False
        return True

    def _reply_text(self, update: Update, text: str, parse_mode: str | None = None):
        try:
            return update.effective_message.reply_text(text, parse_mode=parse_mode, disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"reply error: {e}")

    async def _get_state(self, eid: str) -> Optional[dict]:
        try:
            return await self.ha.get_entity(eid)
        except Exception as e:
            logger.error(f"get state {eid}: {e}")
            return None

    # ---------- commands ----------
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        await self._reply_text(update, "Hello! I'm your Home Assistant bot.\n"
                                       "Send /help for the list of commands.")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        await self._reply_text(update,
            "Commands:\n"
            "/on <alias> — turn on\n"
            "/off <alias> — turn off\n"
            "/toggle <alias> — toggle\n"
            "/set <alias> <value> — set value (e.g. /set light 80)\n"
            "/state [entity] — status\n"
            "/entities [type] — list (light, switch, climate...)\n"
            "/room <room> — all in a room\n"
            "/scene <name> — scene\n"
            "/timer <min> <alias> — timer for the device\n"
            "/status — HA status\n")

    async def cmd_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        eid = self.registry.by_id_or_alias(context.args[0]) if context.args else None
        if eid:
            s = await self._get_state(eid)
            if not s:
                return self._reply_text(update, "Not found.")
            a = s.get("attributes", {})
            state = s.get("state")
            out = f"**{a.get('friendly_name', eid)}**\nState: `{state}`"
            if a:
                out += f"\nAttrs: {json.dumps(a, indent=1)}"
            return self._reply_text(update, out, ParseMode.HTML)
        else:
            entities = self.registry._entities
            lines = [f"**{a.get('friendly_name', k)}** = `{s.get('state')}`" for k, s in entities.items() for a in [s.get("attributes", {})]]
            return self._reply_text(update, "\n".join(lines)[:3000], ParseMode.HTML)

    async def cmd_entities(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        domain = context.args[0] if context.args else None
        ents = self.registry.list_entities(domain)
        if not ents:
            return self._reply_text(update, "Empty list.")
        lines = ["\n".join(f"`{e}`" for e in ents), ""]
        if domain is None:
            # group by domain
            grouped: dict[str, list] = {}
            for e in self.registry._entities:
                d = e.split(".")[0]
                grouped.setdefault(d, []).append(e)
            lines = [""]
            for d, ids in sorted(grouped.items()):
                lines.append(f"**{d}** ({len(ids)})")
                lines += [f"  {e}" for e in ids]
        return self._reply_text(update, "\n".join(lines), ParseMode.HTML)

    async def cmd_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        if not context.args:
            return self._reply_text(update, "Usage: /room <room name>")
        room_name = context.args[0]
        entities = self.registry._entities
        lines = []
        for eid, data in entities.items():
            attrs = data.get("attributes", {})
            if room_name.lower() in attrs.get("room_name", "").lower():
                lines.append(f"`{eid}` — {data.get('state')}")
        if not lines:
            return self._reply_text(update, f"No entities in the room «{room_name}».")
        return self._reply_text(update, "\n".join(lines), ParseMode.HTML)

    async def cmd_scene(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        name = context.args[0] if context.args else None
        if not name:
            return self._reply_text(update, "Usage: /scene <name>")
        eid = self.registry.by_id_or_alias(name)
        if not eid:
            return self._reply_text(update, f"Scene «{name}» not found.")
        try:
            await self.ha.apply_scene(eid)
            return self._reply_text(update, f"Scene «{name}» applied.")
        except HAError as e:
            return self._reply_text(update, f"Error: {e}")

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        ok = await self.ha.healthcheck()
        return self._reply_text(update, "HA status: online" if ok else "HA status: offline.")

    # ---------- action handlers ----------
    async def _do_action(self, update: Update, action: str, eid: str):
        try:
            if action == "on":
                await self.ha.turn_on(eid)
                return "On."
            if action == "off":
                await self.ha.turn_off(eid)
                return "Off."
            if action == "toggle":
                s = await self._get_state(eid)
                if s and s.get("state") == "off":
                    await self.ha.turn_on(eid)
                    return "On."
                elif s and s.get("state") == "on":
                    await self.ha.turn_off(eid)
                    return "Off."
                else:
                    return f"State: {s.get('state') if s else 'unknown'}."
        except Exception as e:
            return f"Error: {e}"
        return "Done."

    async def cmd_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        if not context.args:
            return self._reply_text(update, "Usage: /on <alias>")
        eid = self.registry.by_id_or_alias(context.args[0])
        if not eid:
            return self._reply_text(update, "Not found.")
        await self._reply_text(update, await self._do_action(update, "on", eid))

    async def cmd_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        if not context.args:
            return self._reply_text(update, "Usage: /off <alias>")
        eid = self.registry.by_id_or_alias(context.args[0])
        if not eid:
            return self._reply_text(update, "Not found.")
        await self._reply_text(update, await self._do_action(update, "off", eid))

    async def cmd_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        if not context.args:
            return self._reply_text(update, "Usage: /toggle <alias>")
        eid = self.registry.by_id_or_alias(context.args[0])
        if not eid:
            return self._reply_text(update, "Not found.")
        await self._reply_text(update, await self._do_action(update, "toggle", eid))

    async def cmd_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        if len(context.args) < 2:
            return self._reply_text(update, "Usage: /set <alias> <value>")
        eid = self.registry.by_id_or_alias(context.args[0])
        if not eid:
            return self._reply_text(update, "Not found.")
        try:
            value = float(context.args[1])
        except ValueError:
            return self._reply_text(update, "Value must be a number.")
        try:
            await self.ha.set_value(eid, value)
            return self._reply_text(update, f"Set: {value}.")
        except Exception as e:
            return self._reply_text(update, f"Error: {e}")

    async def cmd_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._check_auth(update):
            return
        if len(context.args) < 2:
            return self._reply_text(update, "Usage: /timer <min> <alias>")
        try:
            minutes = int(context.args[0])
        except ValueError:
            return self._reply_text(update, "Time must be in minutes.")
        eid = self.registry.by_id_or_alias(context.args[1])
        if not eid:
            return self._reply_text(update, "Not found.")
        async def turn_off_later():
            await self.ha.turn_off(eid)
            if update.effective_chat:
                await update.effective_chat.send_message(f"Device {eid} turned off after {minutes} minutes.")
        task = asyncio.create_task(turn_off_later(), delay=minutes * 60)
        self._timers[update.effective_user.id] = task
        return self._reply_text(update, f"Timer started for {eid}.")

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # free text — look up alias, if found do toggle
        text = update.message.text if update.message else ""
        eid = self.registry.by_id_or_alias(text)
        if eid and eid.endswith((".light", ".switch", ".fan", ".cover", ".plug", ".scene")):
            action = "on" if text.lower().endswith(("on", "in", "open")) else "off"
            await self._reply_text(update, await self._do_action(update, action, eid))
        # timer completion
        for uid in list(self._timers):
            t = self._timers[uid]
            if t.done():
                del self._timers[uid]


# ---------- main ----------

async def main():
    cfg = Config(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        base_url=os.environ.get("HA_BASE_URL", "http://localhost:8123"),
        ha_token=os.environ.get("HA_ACCESS_TOKEN", ""),
        allowed_user_id=int(os.environ.get("ALLOWED_USER_ID") or 0) or None,
    )
    if not cfg.token or not cfg.ha_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN and HA_ACCESS_TOKEN are required.")
    bot = HATelegramBot(cfg, cfg.allowed_user_id)
    app = ApplicationBuilder().token(cfg.token).build()
    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("help", bot.cmd_help))
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_message))

    # refresh entities every 60 sec
    async def refresher():
        await bot.registry.refresh()
        while True:
            await asyncio.sleep(60)
            try:
                await bot.registry.refresh()
            except Exception as e:
                logger.error(f"refresh error: {e}")
    app.add_task(refresher, name="entity_refresh", interval=60)

    try:
        await app.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        await bot.ha.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Класс HATelegramBot: команды, inline-меню, таймеры, приёмник уведомлений."""

import asyncio
import hashlib
import json
import re
import secrets
import time
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .config import (
    ALLOFF_DOMAINS,
    BRIGHTNESS_PRESETS,
    CB_TOKEN_EVICT,
    CB_TOKEN_MAP_MAX,
    CONTROLLABLE_DOMAINS,
    TEMP_RANGE,
    logger,
)
from .ha_client import HAClient
from .messages import MESSAGES, esc, set_lang, state_localized, t
from .registry import EntityRegistry
from .storage import TIMERS_FILE, load_known_chats, save_known_chats

# aiohttp нужен для приёмника уведомлений (NOTIFY_PORT)
try:
    from aiohttp import web
except ImportError:
    web = None


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
    # Сколько ждать колбэк от HA в /testnotify <rest_command>, секунды
    TESTNOTIFY_TIMEOUT = 15

    def __init__(self, cfg, allowed_users: Optional[set]):
        self.cfg = cfg
        self.allowed_users = allowed_users  # None = разрешены все
        self.ha = HAClient(cfg.base_url, cfg.ha_token, cfg.timeout)
        self.registry = EntityRegistry(self.ha)
        # Таймеры: {(user_id, entity_id): asyncio.Task}
        self._timers: dict = {}
        # Мета таймеров для сохранения: {(user_id, entity_id): {...}}
        self._timer_meta: dict = {}
        # Чаты пользователей, писавших боту (для рассылки уведомлений);
        # персистятся — уведомления доходят сразу после перезапуска
        self._known_chats: set = load_known_chats()
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
        # Фоновая задача сторожа уведомлений (создаётся в post_init)
        self._watchdog_task = None
        # Ожидания колбэков от HA для полного круга /testnotify <rest_command>:
        # marker -> asyncio.Future. Словарь, а не один слот, чтобы одновременные
        # проверки разных пользователей не перезаписывали друг друга
        self._pending_roundtrips: dict = {}

    # ---------- Callback-токены ----------

    def _tok(self, payload: str) -> str:
        """Создаёт короткий токен для payload callback_data."""
        self._cb_seq += 1
        token = f"x{self._cb_seq}"
        self._cb_map[token] = payload
        # Защита от неограниченного роста: вытесняем самые старые токены
        # (dict сохраняет порядок вставки — это FIFO)
        if len(self._cb_map) > CB_TOKEN_MAP_MAX:
            for k in list(self._cb_map.keys())[:CB_TOKEN_EVICT]:
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
        # Запоминаем чат для уведомлений (персистим новые, чтобы уведомления
        # доходили сразу после перезапуска бота)
        if update.effective_chat is not None:
            chat_id = update.effective_chat.id
            if chat_id not in self._known_chats:
                self._known_chats.add(chat_id)
                save_known_chats(self._known_chats)
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
                    continue
            except Exception as e:
                logger.warning("Ошибка отправки части %d: %s", i, e)
                continue
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
        # Отдельная слишком длинная строка — жёстко обрезаем до лимита,
        # стараясь не резать HTML-тег пополам (см. _cut_html_safe).
        # Окончательная защита от битого HTML остаётся в _reply_text:
        # plain text fallback при ошибке парсинга.
        return [self._cut_html_safe(p, max_length) for p in parts] or [""]

    def _cut_html_safe(self, text: str, max_length: int) -> str:
        """Обрезает текст до лимита, не разрывая HTML-тег пополам.

        Приоритет границы разреза: перед обрезанным открытым тегом; иначе —
        сразу после закрывающего тега (если он в разумной части текста);
        иначе — по последнему пробелу перед лимитом; иначе — жёстко по лимиту.
        """
        if len(text) <= max_length:
            return text
        cut = text[:max_length]
        lt, gt = cut.rfind("<"), cut.rfind(">")
        if lt > gt:
            # Обрезка попала внутрь тега — отступаем до его начала
            cut = cut[:lt]
        else:
            idx = cut.rfind(">")
            if idx >= max_length // 2:
                # Граница закрывающего тега недалеко от лимита — режем после неё
                cut = cut[:idx + 1]
            else:
                sp = cut.rfind(" ")
                if sp > 0:
                    cut = cut[:sp]
        return cut.rstrip()

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

    def _lang_keyboard(self, uid: Optional[int], with_back: bool = False) -> InlineKeyboardMarkup:
        """Создаёт inline-клавиатуру выбора языка (опционально с кнопкой «Назад»)."""
        rows = [[
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]]
        if with_back:
            rows.append([InlineKeyboardButton(t(uid, "btn_back"), callback_data="menu_settings")])
        return InlineKeyboardMarkup(rows)

    async def cmd_lang(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /lang — выбор языка."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        await self._reply_text(update, t(uid, "choose_lang"),
                               reply_markup=self._lang_keyboard(uid))

    # ---------- Команды управления ----------
    async def _cmd_switch(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                          action: str):
        """Общая логика /on, /off, /toggle: action — "on" | "off" | "tg"."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, t(uid, f"usage_{'toggle' if action == 'tg' else action}"))
        name = " ".join(context.args)
        eid = await self._resolve_or_suggest(update, uid, name, action)
        if not eid:
            return
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
                    return await self._reply_text(
                        update, t(uid, "device_unavailable", name=esc(fname))
                    )
                if s and s.get("state") == "off":
                    await self.ha.turn_on(eid)
                else:
                    await self.ha.turn_off(eid)
                key = "toggled"
            fname = self.registry.get_friendly_name(eid)
            await self._reply_text(update, t(uid, key, name=esc(fname)), "HTML")
        except Exception as e:
            await self._reply_text(update, t(uid, "error", err=esc(str(e))))

    async def cmd_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /on."""
        await self._cmd_switch(update, context, "on")

    async def cmd_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /off."""
        await self._cmd_switch(update, context, "off")

    async def cmd_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /toggle."""
        await self._cmd_switch(update, context, "tg")

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
            shown = f"{value:g}%" if domain == "light" else f"{value:g}°C"
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
            return await self._reply_text(update, t(uid, "usage_room"))
        room_name = " ".join(context.args)
        await self._show_room(update, uid, room_name)

    async def cmd_scene(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /scene."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if not context.args:
            return await self._reply_text(update, t(uid, "usage_scene"))
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

    async def cmd_testnotify(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /testnotify — проверка цепочки уведомлений.

        Без аргументов идёт через тот же код, что и приёмник /notify:
        те же получатели, та же отправка (нога бот → Telegram).

        С аргументом <имя> выполняет полный круг: вызывает
        rest_command.<имя> в HA, HA должен прислать уведомление обратно
        на /notify бота — по маркеру в тексте бот засекает колбэк.
        """
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        args = context.args if context.args else []
        if len(args) > 1:
            return await self._reply_text(update, t(uid, "testnotify_usage"))
        if args:
            return await self._testnotify_roundtrip(update, uid, args[0])

        class _Req:
            # Бот вызывает собственный приёмник — предъявляем свой же токен,
            # иначе при заданном NOTIFY_TOKEN самопроверка получит 401.
            headers = {"Authorization": f"Bearer {self.cfg.notify_token}"} \
                if self.cfg.notify_token else {}

            async def json(self):
                return {"text": t(uid, "testnotify_text")}

        resp = await self._handle_notify(_Req())
        try:
            body = json.loads(resp.text) if resp.text else {}
        except Exception:
            body = {}
        if resp.status == 200:
            await self._reply_text(
                update, t(uid, "testnotify_sent", count=body.get("sent", 0))
            )
        else:
            err = body.get("error", f"HTTP {resp.status}")
            await self._reply_text(update, t(uid, "testnotify_failed", err=esc(str(err))))

    async def notify_roundtrip(self, service: str) -> dict:
        """Полный круг: бот -> HA (rest_command) -> бот (/notify) -> Telegram.

        Возвращает {"ok": True, "secs": ..., "sent": ...} либо
        {"ok": False, "stage": "ha"|"callback", "error": ...}.
        """
        marker = secrets.token_hex(4)
        text = f"{t(None, 'testnotify_text')} [{marker}]"
        future = asyncio.get_running_loop().create_future()
        self._pending_roundtrips[marker] = future
        start = time.time()
        try:
            try:
                await self.ha.call_service("rest_command", service, {"message": text})
            except Exception as e:
                return {"ok": False, "stage": "ha", "error": str(e)}
            try:
                result = await asyncio.wait_for(future, timeout=self.TESTNOTIFY_TIMEOUT)
            except asyncio.TimeoutError:
                return {"ok": False, "stage": "callback",
                        "error": "timeout", "secs": self.TESTNOTIFY_TIMEOUT}
            return {"ok": True, "secs": time.time() - start,
                    "sent": result.get("sent", 0)}
        finally:
            self._pending_roundtrips.pop(marker, None)

    async def _testnotify_roundtrip(self, update: Update, uid: Optional[int], service: str):
        """Полный круг: бот -> HA (rest_command) -> бот (/notify) -> Telegram."""
        r = await self.notify_roundtrip(service)
        if r["ok"]:
            return await self._reply_text(
                update,
                t(uid, "testnotify_ok", secs=f"{r['secs']:.1f}", count=r["sent"]),
            )
        if r["stage"] == "ha":
            return await self._reply_text(
                update,
                t(uid, "testnotify_ha_error", name=esc(service), err=esc(r["error"])),
            )
        return await self._reply_text(
            update,
            t(uid, "testnotify_timeout", secs=self.TESTNOTIFY_TIMEOUT,
              host=esc(self.cfg.notify_host), port=self.cfg.notify_port),
        )

    async def _watchdog_alert(self, text: str):
        """Разослать алерт сторожа всем целям уведомлений."""
        for cid in self.notify_targets():
            try:
                await self.app.bot.send_message(cid, text, parse_mode="HTML")
            except Exception as e:
                logger.warning("Watchdog: не удалось отправить алерт в %s: %s", cid, e)

    async def _watchdog_once(self, was_ok: bool) -> bool:
        """Одна проверка цепочки уведомлений. Возвращает новое состояние (ok?)."""
        try:
            r = await self.notify_roundtrip(self.cfg.notify_watchdog_command)
        except Exception as e:  # сторож не должен умирать сам
            r = {"ok": False, "stage": "ha", "error": str(e)}
        if r["ok"]:
            logger.info("Watchdog: цепочка уведомлений работает (круг %.1f с)", r["secs"])
            if not was_ok:
                await self._watchdog_alert(t(None, "watchdog_recovered"))
            return True
        logger.warning("Watchdog: цепочка уведомлений сломана (%s): %s",
                       r["stage"], r["error"])
        if was_ok:
            await self._watchdog_alert(t(None, "watchdog_failed", err=esc(r["error"])))
        return False

    async def _notify_watchdog(self):
        """Периодическая проверка цепочки HA -> бот -> Telegram."""
        interval = self.cfg.notify_watchdog_interval
        command = self.cfg.notify_watchdog_command
        if not interval or not command:
            return
        await asyncio.sleep(interval)  # не проверять сразу после старта
        was_ok = True
        while True:
            was_ok = await self._watchdog_once(was_ok)
            await asyncio.sleep(interval)

    async def cmd_timer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /timer — таймер выключения."""
        if not self._check_auth(update):
            return
        uid = self._uid(update)
        if len(context.args) < 2:
            return await self._reply_text(update, t(uid, "usage_timer"))
        try:
            minutes = int(context.args[0])
            if minutes <= 0 or minutes > 24 * 60:
                raise ValueError
        except ValueError:
            return await self._reply_text(update, t(uid, "timer_bad_minutes"))
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
                try:
                    await self.ha.turn_off(eid)
                except Exception as e:
                    # HA недоступен или устройство не выключилось — сообщаем
                    # пользователю, а не молча проваливаемся
                    logger.warning("Таймер: не удалось выключить %s: %s", eid, e)
                    if chat_id is not None:
                        try:
                            await self.app.bot.send_message(
                                chat_id,
                                t(uid, "timer_error", eid=esc(eid), err=esc(str(e))),
                                parse_mode="HTML",
                            )
                        except Exception as e2:
                            logger.warning(
                                "Не удалось отправить сообщение об ошибке таймера: %s", e2)
                    return
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
            data = self.registry.get_cached(eid)
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
            await self._edit_msg(
                query,
                t(uid, "choose_lang"),
                reply_markup=self._lang_keyboard(uid, with_back=True),
            )
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
            shown = f"{value:g}%" if eid.startswith("light.") else f"{value:g}°C"
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
            data = self.registry.get_cached(eid)
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
            expected = f"Bearer {self.cfg.notify_token}"
            # compare_digest против тайминг-атак на токен
            if not secrets.compare_digest(
                    auth.encode("utf-8"), expected.encode("utf-8")):
                # Диагностика рассинхрона токенов без раскрытия их в логе:
                # сравниваем длину и короткий хеш полученного и ожидаемого.
                got = auth[7:] if auth.startswith("Bearer ") else auth
                logger.warning(
                    "/notify: неверный токен (получено: %d симв., sha256 %.8s; "
                    "ожидалось: %d симв., sha256 %.8s)",
                    len(got), hashlib.sha256(got.encode()).hexdigest(),
                    len(self.cfg.notify_token),
                    hashlib.sha256(self.cfg.notify_token.encode()).hexdigest(),
                )
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        text = body.get("text")
        if not text or not isinstance(text, str):
            return web.json_response({"ok": False, "error": "text required"}, status=400)
        logger.info("Уведомление от HA: %s", text[:100])
        parse_mode = body.get("parse_mode") if body.get("parse_mode") in ("HTML", "MarkdownV2") else None

        targets = body.get("chat_ids")
        if not isinstance(targets, list) or not targets:
            targets = self.notify_targets()
        if not targets:
            return web.json_response({"ok": False, "error": "no known chats"}, status=404)

        sent, failed = 0, 0
        # Параллельная отправка: один медленный чат не блокирует остальные
        results = await asyncio.gather(
            *(self.app.bot.send_message(cid, text, parse_mode=parse_mode)
              for cid in targets),
            return_exceptions=True,
        )
        for cid, r in zip(targets, results):
            if isinstance(r, Exception):
                logger.warning("Не удалось отправить уведомление в %s: %s", cid, r)
                failed += 1
            else:
                sent += 1

        # Колбэки для полного круга /testnotify <rest_command>: завершаем
        # все ожидания, чей маркер встретился в тексте (их может быть
        # несколько — от параллельных проверок разных пользователей)
        for marker, future in list(self._pending_roundtrips.items()):
            if not future.done() and marker in text:
                future.set_result({"sent": sent, "failed": failed})

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

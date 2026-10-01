"""Локализация (MESSAGES, t) и HTML-утилита esc."""

import html
from typing import Optional

from .config import DEFAULT_LANG, logger
from .storage import USER_LANGS, save_user_langs


def esc(text) -> str:
    """Экранирует HTML-символы для безопасной отправки в Telegram."""
    return html.escape(str(text)) if text is not None else ""


# ---------- Локализация ----------

MESSAGES = {
    "ru": {
        "usage_on": "⚠️ Использование: /on <имя>",
        "usage_off": "⚠️ Использование: /off <имя>",
        "usage_toggle": "⚠️ Использование: /toggle <имя>",
        "usage_room": "⚠️ Использование: /room <комната>",
        "usage_scene": "⚠️ Использование: /scene <имя>",
        "usage_timer": "⚠️ Использование: /timer <мин> <имя>",
        "timer_bad_minutes": "⚠️ Время должно быть числом от 1 до 1440",
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
        "timer_error": "⚠️ Таймер: не удалось выключить <code>{eid}</code>.\nОшибка: {err}",
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
            "<code>/status</code> — статус HA\n"
            "<code>/testnotify</code> [rest_command] — проверить уведомления (полный круг через HA)\n\n"
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
        "testnotify_text": "🧪 Тестовое уведомление из Home Assistant. Если вы видите это сообщение — цепочка уведомлений работает.",
        "testnotify_sent": "✅ Тестовое уведомление отправлено в {count} чат(ов). Проверьте, что оно пришло.",
        "testnotify_failed": "❌ Не удалось отправить тестовое уведомление: {err}",
        "testnotify_usage": "⚠️ Использование:\n/testnotify — проверка доставки бот → Telegram\n/testnotify <имя> — полный круг через rest_command в HA\n(имя команды из configuration.yaml, например: /testnotify telegram_notify)",
        "testnotify_ha_error": "❌ Не удалось вызвать rest_command.{name} в HA: {err}\nПроверьте имя команды и доступность HA.",
        "testnotify_ok": "✅ Цепочка HA → бот → Telegram работает!\nКруг выполнен за {secs} с. Уведомление доставлено в {count} чат(ов).",
        "testnotify_timeout": "❌ Таймаут ({secs} с): HA вызвал rest_command, но уведомление не дошло до бота.\nПроверьте url в rest_command (http://{host}:{port}/notify), Bearer NOTIFY_TOKEN и сеть HA → сервер бота.",
        "watchdog_failed": "⚠️ <b>Сторож уведомлений</b>: цепочка HA → бот → Telegram сломана.\nОшибка: {err}\nПроверьте rest_command, NOTIFY_PORT/NOTIFY_TOKEN и сеть.",
        "watchdog_recovered": "✅ <b>Сторож уведомлений</b>: цепочка восстановлена, уведомления снова проходят.",
    },
    "en": {
        "usage_on": "⚠️ Usage: /on <name>",
        "usage_off": "⚠️ Usage: /off <name>",
        "usage_toggle": "⚠️ Usage: /toggle <name>",
        "usage_room": "⚠️ Usage: /room <room>",
        "usage_scene": "⚠️ Usage: /scene <name>",
        "usage_timer": "⚠️ Usage: /timer <min> <name>",
        "timer_bad_minutes": "⚠️ Time must be a number from 1 to 1440",
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
        "timer_error": "⚠️ Timer: failed to turn off <code>{eid}</code>.\nError: {err}",
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
            "<code>/status</code> — HA status\n"
            "<code>/testnotify</code> [rest_command] — test notifications (full round-trip via HA)\n\n"
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
        "testnotify_text": "🧪 Test notification from Home Assistant. If you see this message, the notification chain works.",
        "testnotify_sent": "✅ Test notification sent to {count} chat(s). Please confirm it arrived.",
        "testnotify_failed": "❌ Failed to send test notification: {err}",
        "testnotify_usage": "⚠️ Usage:\n/testnotify — check delivery bot → Telegram\n/testnotify <name> — full round-trip via rest_command in HA\n(command name from configuration.yaml, e.g.: /testnotify telegram_notify)",
        "testnotify_ha_error": "❌ Failed to call rest_command.{name} in HA: {err}\nCheck the command name and HA availability.",
        "testnotify_ok": "✅ HA → bot → Telegram chain works!\nRound-trip completed in {secs} s. Notification delivered to {count} chat(s).",
        "testnotify_timeout": "❌ Timeout ({secs} s): HA called rest_command, but the notification never reached the bot.\nCheck the rest_command url (http://{host}:{port}/notify), Bearer NOTIFY_TOKEN and the network HA → bot server.",
        "watchdog_failed": "⚠️ <b>Notification watchdog</b>: the HA → bot → Telegram chain is broken.\nError: {err}\nCheck rest_command, NOTIFY_PORT/NOTIFY_TOKEN and the network.",
        "watchdog_recovered": "✅ <b>Notification watchdog</b>: the chain has recovered, notifications flow again.",
    },
}


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


# Ключи, для которых уже писали предупреждение об отсутствии перевода
_missing_warned: set = set()


def t(user_id: Optional[int], key: str, **kwargs) -> str:
    """Возвращает локализованную строку.

    При отсутствующем ключе fallback на строку DEFAULT_LANG (с предупреждением
    в лог — один раз на ключ); если нет и там — возвращается сам ключ.
    """
    lang = get_lang(user_id)
    text = MESSAGES.get(lang, {}).get(key)
    if text is None:
        ru_text = MESSAGES.get(DEFAULT_LANG, {}).get(key)
        if ru_text is not None:
            if key not in _missing_warned:
                _missing_warned.add(key)
                logger.warning(
                    "Отсутствует перевод ключа %r для языка %r — использую %s",
                    key, lang, DEFAULT_LANG,
                )
            text = ru_text
        else:
            text = key
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

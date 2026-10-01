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

Версия 2.1.3:
- После обнаружения 404 REST-endpoints реестров бот запоминает это
  и дальше ходит на websocket напрямую (без 404-шума в логе каждый цикл)

Версия 2.1.4:
- Сторож уведомлений: периодический контрольный круг HA -> бот -> Telegram
  (NOTIFY_WATCHDOG_INTERVAL / NOTIFY_WATCHDOG_COMMAND), алерты при поломке
  и восстановлении; ядро круга вынесено в notify_roundtrip (используется
  и командой /testnotify)

Версия 2.1.5:
- Исправлена самопроверка /testnotify: при заданном NOTIFY_TOKEN внутренний
  запрос к собственному приёмнику предъявляет токен (был вечный 401)
- Текст ошибок HA (тело ответа) включается в сообщение об ошибке вызова сервиса
- Входящие запросы на /notify логируются; при 401 логируются длина и sha256-
  префикс полученного и ожидаемого токенов (без раскрытия значений)

Версия 3.0.0:
- Модульная структура: логика разделена на пакет hamqttbot/, bot.py —
  тонкая точка входа
- Безопасность по умолчанию: без ALLOWED_USER_IDS бот не стартует,
  открытый доступ — только через ALLOW_ALL_USERS=1
- Повторные попытки идемпотентных вызовов к HA (turn_on/turn_off,
  HA_RETRY_ATTEMPTS); ошибки фонового обновления пишутся один раз;
  ошибка таймера сообщается пользователю в чат
- Уведомления отправляются по чатам параллельно (asyncio.gather);
  одна переиспользуемая aiohttp-сессия для websocket-фолбэка
- Docker: multi-arch образы (linux/amd64 + linux/arm64) через buildx
  (./deploy.sh --docker), версия передаётся build-arg BOT_VERSION,
  зависимости из requirements.lock, healthcheck.py (проверка /notify),
  порт приёмника в compose публикуется только при заданном NOTIFY_PORT
- Мелочи: разбивка сообщений не рвёт HTML, t() падает на ru-строку,
  температура с единицей (°C), secrets.compare_digest для NOTIFY_TOKEN,
  публичный EntityRegistry.count()

Версия 2.1.6:
- Одновременные /testnotify <rest_command> больше не перезаписывают друг друга:
  ожидания колбэков хранятся по маркерам (словарь), а не в одном слоте
- Известные чаты для уведомлений сохраняются в data/known_chats.json —
  уведомления из HA доходят сразу после перезапуска бота
- NOTIFY_PORT читается с защитой от мусорных значений (как другие числовые .env)
- Файлы данных по умолчанию лежат в data/ (раньше — корень проекта);
  legacy-файлы из корня переносятся в data/ автоматически при старте
- Usage-подсказки /on /off /toggle /room /scene /timer локализованы (ru/en)
- Публичный метод EntityRegistry.get_cached() вместо доступа к _entities снаружи

Точка входа: этот файл запускает бота (main). Вся логика — в пакете hamqttbot/:
- hamqttbot/config.py    — логирование, Config, parse_*, общие константы
- hamqttbot/storage.py   — файлы данных в data/ (языки, чаты), миграция legacy
- hamqttbot/messages.py  — локализация MESSAGES (ru/en), t(), esc()
- hamqttbot/ha_client.py — HAClient: REST-вызовы к Home Assistant
- hamqttbot/registry.py  — EntityRegistry: кеш устройств, алиасы, комнаты, сцены
- hamqttbot/bot_core.py  — HATelegramBot: команды, меню, таймеры, уведомления
"""

import asyncio
import os

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

# Имена ниже реэкспортируются для обратной совместимости:
# тесты и сторонний код используют `import bot` и обращаются к bot.Config,
# bot.HATelegramBot, bot.MESSAGES, bot.TIMERS_FILE и т.д.
from hamqttbot import (  # noqa: F401
    BOT_VERSION,
    MESSAGES,
    USER_LANGS,
    REFRESH_INTERVAL,
    TIMERS_FILE,
    WATCHDOG_COMMAND,
    WATCHDOG_INTERVAL,
    Config,
    EntityRegistry,
    HAClient,
    HAError,
    HATelegramBot,
    esc,
    get_lang,
    get_main_keyboard,
    load_known_chats,
    load_user_langs,
    logger,
    migrate_legacy_data_files,
    parse_allowed_users,
    parse_int_env,
    require_allowed_users,
    save_known_chats,
    save_user_langs,
    set_lang,
    state_localized,
    t,
)


# ---------- Main ----------

def main():
    """Точка входа: настройка и запуск бота."""
    migrate_legacy_data_files()
    # USER_LANGS загружается при импорте модуля — после миграции перечитываем
    USER_LANGS.clear()
    USER_LANGS.update(load_user_langs())

    ha_timeout = parse_int_env("HA_TIMEOUT", 15)
    cfg = Config(
        token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        base_url=os.environ.get("HA_BASE_URL", "http://localhost:8123"),
        ha_token=os.environ.get("HA_ACCESS_TOKEN", ""),
        allowed_users=require_allowed_users(),
        timeout=ha_timeout,
        notify_host=os.environ.get("NOTIFY_HOST", "0.0.0.0"),
        notify_port=parse_int_env("NOTIFY_PORT", 0),
        notify_token=os.environ.get("NOTIFY_TOKEN") or None,
        notify_watchdog_interval=WATCHDOG_INTERVAL,
        notify_watchdog_command=WATCHDOG_COMMAND,
    )
    if not cfg.token or not cfg.ha_token:
        raise SystemExit("Не заданы TELEGRAM_BOT_TOKEN и HA_ACCESS_TOKEN в файле .env")
    if cfg.notify_port and not cfg.notify_token:
        logger.warning("NOTIFY_TOKEN не задан — приёмник уведомлений доступен без авторизации!")
    if cfg.notify_watchdog_interval and not cfg.notify_watchdog_command:
        logger.warning("NOTIFY_WATCHDOG_INTERVAL задан без NOTIFY_WATCHDOG_COMMAND — сторож выключен")

    bot = HATelegramBot(cfg, cfg.allowed_users)
    logger.info("HA Telegram Bot v%s, интервал обновления реестра: %d с",
                BOT_VERSION, REFRESH_INTERVAL)

    async def post_init(application: Application):
        bot.app = application
        logger.info("Бот запущен, загружаю список устройств...")
        try:
            await bot.registry.refresh()
            logger.info("Загружено устройств: %d", bot.registry.count())
        except Exception as e:
            logger.error("Ошибка загрузки: %s", e)

        await bot.restore_timers()
        await bot.start_notify_server()

        # Дедуп ошибок фонового обновления: warning один раз, восстановление — info
        refresh_failed = False

        async def refresher():
            nonlocal refresh_failed
            while True:
                await asyncio.sleep(REFRESH_INTERVAL)
                try:
                    await bot.registry.refresh()
                    if refresh_failed:
                        logger.info("Обновление реестра восстановлено")
                        refresh_failed = False
                except Exception as e:
                    if not refresh_failed:
                        logger.warning("Ошибка обновления реестра: %s", e)
                        refresh_failed = True

        # Через asyncio, а не Application.create_task: post_init выполняется
        # до старта application, и PTB предупреждает, что такая задача не
        # отслеживается. Храним ссылку и отменяем вручную при остановке.
        bot._refresh_task = asyncio.get_running_loop().create_task(
            refresher(), name="entity_refresh"
        )
        bot._watchdog_task = asyncio.get_running_loop().create_task(
            bot._notify_watchdog(), name="notify_watchdog"
        )

    async def post_shutdown(application: Application):
        logger.info("Остановка бота...")
        if bot._refresh_task is not None:
            bot._refresh_task.cancel()
        if bot._watchdog_task is not None:
            bot._watchdog_task.cancel()
        bot.save_timers()
        for task in bot._timers.values():
            task.cancel()
        await bot.stop_notify_server()
        await bot.registry.close()
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
    app.add_handler(CommandHandler("testnotify", bot.cmd_testnotify))
    app.add_handler(CommandHandler("timer", bot.cmd_timer))
    app.add_handler(CommandHandler("timers", bot.cmd_timers))
    app.add_handler(CommandHandler("alloff", bot.cmd_alloff))
    app.add_handler(CallbackQueryHandler(bot.callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_menu_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

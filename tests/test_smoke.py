"""Постоянные smoke-тесты для HA Telegram Bot.

Запуск из корня репозитория:
    python -m unittest discover -s tests -v

Только стандартная библиотека (unittest.IsolatedAsyncioTestCase) —
внешних зависимостей для прогона не требуется.
"""
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import unittest

# DATA_DIR читается при импорте bot.py — задаём временную папку заранее
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="ha_bot_test_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402


def make_bot():
    cfg = bot.Config(token="t", base_url="http://127.0.0.1:1", ha_token="t")
    return bot.HATelegramBot(cfg, {1})


class FakeHA:
    """HAClient-подобная заглушка с заданным набором устройств."""

    def __init__(self, entities=None):
        self._entities = entities or {}

    async def get_entity_ids_by_domain(self, domain=None):
        return self._entities

    async def get_json(self, path, params=None):
        raise RuntimeError("registry недоступен")


class TestLocalization(unittest.TestCase):
    def test_lang_parity(self):
        self.assertEqual(set(bot.MESSAGES["ru"]), set(bot.MESSAGES["en"]))

    def test_required_keys(self):
        for lang, msgs in bot.MESSAGES.items():
            for key in ("timer_min", "device_unavailable", "search_more",
                        "timer_cancelled", "alloff_done",
                        "testnotify_text", "testnotify_sent", "testnotify_failed",
                        "testnotify_usage", "testnotify_ok", "testnotify_timeout",
                        "testnotify_ha_error"):
                self.assertIn(key, msgs, f"{key} missing in {lang}")

    def test_fallback_to_key(self):
        self.assertEqual(bot.t(1, "__no_such_key__"), "__no_such_key__")


class TestAliases(unittest.IsolatedAsyncioTestCase):
    async def test_ambiguous_aliases_excluded(self):
        entities = {
            "light.a": {"attributes": {"friendly_name": "Свет"}},
            "light.b": {"attributes": {"friendly_name": "Свет"}},
            "switch.c": {"attributes": {"friendly_name": "Чайник"}},
        }
        reg = bot.EntityRegistry(FakeHA(entities))
        await reg.refresh()
        # Неоднозначный алиас исключён из точного поиска
        self.assertIsNone(reg.by_id_or_alias("Свет"))
        self.assertIsNone(reg.by_id_or_alias("свет"))
        # Однозначный алиас работает
        self.assertEqual(reg.by_id_or_alias("Чайник"), "switch.c")
        # Подстрочный поиск находит оба «Света»
        self.assertEqual(set(reg.search("свет")), {"light.a", "light.b"})


class TestTimers(unittest.IsolatedAsyncioTestCase):
    async def test_restore_skips_corrupted(self):
        b = make_bot()
        now = time.time()
        data = [
            {"uid": 1, "chat_id": 1, "eid": "light.a", "minutes": 5,
             "fire_at": now + 100},
            {"broken": True},
            "not-a-dict",
            {"eid": "light.b", "minutes": 3},  # нет fire_at
            {"uid": 1, "chat_id": 1, "eid": "light.c", "minutes": 10,
             "fire_at": now + 200},
        ]
        bot.TIMERS_FILE.write_text(json.dumps(data), encoding="utf-8")

        await b.restore_timers()
        keys = set(b._timers.keys())
        self.assertEqual(keys, {(1, "light.a"), (1, "light.c")})

        # save_timers не падает и пишет только валидные таймеры
        b.save_timers(verbose=False)
        saved = json.loads(bot.TIMERS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 2)
        for task in b._timers.values():
            task.cancel()

    async def test_cancel_removes_timer(self):
        b = make_bot()
        text = await b._start_timer(1, 1, "light.x", 30)
        self.assertIn("light.x", text)
        self.assertIn((1, "light.x"), b._timers)
        self.assertTrue(b._cancel_timer(1, "light.x"))
        self.assertNotIn((1, "light.x"), b._timers)
        self.assertNotIn((1, "light.x"), b._timer_meta)
        # Повторная отмена — False, без падений
        self.assertFalse(b._cancel_timer(1, "light.x"))


class TestNotifyRateLimit(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_429(self):
        b = make_bot()
        b._notify_hits = [time.time() - i for i in range(bot.HATelegramBot.NOTIFY_RATE_LIMIT)]

        class Req:
            headers = {}

            async def json(self):
                return {"text": "x"}

        resp = await b._handle_notify(Req())
        self.assertEqual(resp.status, 429)


class TestTestNotify(unittest.IsolatedAsyncioTestCase):
    def _make_update(self, replies):
        class Msg:
            text = "/testnotify"

            async def reply_text(self, part, **kw):
                replies.append(part)
                return None

        user = type("U", (), {"id": 1})()
        chat = type("C", (), {"id": 7})()
        msg = Msg()
        return type("Up", (), {
            "effective_user": user, "effective_chat": chat,
            "message": msg, "effective_message": msg, "callback_query": None,
        })()

    def _make_bot_with_app(self, captured):
        b = make_bot()

        class FakeBot:
            async def send_message(self, cid, text, parse_mode=None):
                captured.append((cid, text))

        b.app = type("A", (), {"bot": FakeBot()})()
        b._known_chats = {7}
        return b

    async def test_command_sends_via_notify_path(self):
        captured = []
        b = self._make_bot_with_app(captured)
        await b.cmd_testnotify(self._make_update([]), type("C", (), {"args": []})())
        # Уведомление ушло через путь /notify в известный чат
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], 7)
        self.assertIn("Тестовое уведомление", captured[0][1])

    async def test_roundtrip_success(self):
        captured = []
        b = self._make_bot_with_app(captured)
        replies = []

        async def fake_call_service(domain, service, data):
            self.assertEqual((domain, service), ("rest_command", "telegram_notify"))
            text = data["message"]

            class Req:
                headers = {}

                async def json(self):
                    return {"text": text}

            await asyncio.sleep(0.05)  # эмуляция сетевого пути HA -> бот
            return await b._handle_notify(Req())

        b.ha.call_service = fake_call_service
        await b.cmd_testnotify(
            self._make_update(replies), type("C", (), {"args": ["telegram_notify"]})()
        )
        self.assertTrue(any("Цепочка HA → бот → Telegram работает" in r for r in replies), replies)
        self.assertEqual(len(captured), 1)  # уведомление дошло до чата
        self.assertIsNone(b._pending_roundtrip)

    async def test_roundtrip_timeout(self):
        b = self._make_bot_with_app([])
        b.TESTNOTIFY_TIMEOUT = 0.3

        async def fake_call_service(domain, service, data):
            return None  # HA молчит

        b.ha.call_service = fake_call_service
        replies = []
        await b.cmd_testnotify(
            self._make_update(replies), type("C", (), {"args": ["telegram_notify"]})()
        )
        self.assertTrue(any("Таймаут" in r for r in replies), replies)
        self.assertIsNone(b._pending_roundtrip)

    async def test_roundtrip_ha_error(self):
        b = self._make_bot_with_app([])

        async def fake_call_service(domain, service, data):
            raise bot.HAError("404 Not Found")  # сервиса нет в HA

        b.ha.call_service = fake_call_service
        replies = []
        await b.cmd_testnotify(
            self._make_update(replies), type("C", (), {"args": ["no_such_cmd"]})()
        )
        self.assertTrue(any("rest_command.no_such_cmd" in r for r in replies), replies)
        self.assertIsNone(b._pending_roundtrip)


class TestReplySplit(unittest.IsolatedAsyncioTestCase):
    async def test_keyboard_only_on_last_part(self):
        b = make_bot()
        calls = []

        class UM:
            async def reply_text(self, part, **kw):
                calls.append((part, kw))
                return None

        update = type("U", (), {"effective_message": UM()})()
        long_text = "x" * 3900 + "\n" + "y" * 3900
        await b._reply_text(update, long_text, None, reply_markup="KB")
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0][1].get("reply_markup"))
        self.assertEqual(calls[1][1].get("reply_markup"), "KB")


class TestRegistriesWS(unittest.IsolatedAsyncioTestCase):
    """Эмуляция HA: websocket + REST (параметризуется ответом)."""

    AREAS = [{"area_id": "kitchen", "name": "Кухня"}]
    DEVICES = [{"id": "dev1", "area_id": "kitchen"}]
    ENTITIES = [{"entity_id": "light.k", "device_id": "dev1", "area_id": None}]

    async def asyncSetUp(self):
        import aiohttp
        from aiohttp import web

        self.web = web
        results = {
            "config/area_registry/list": self.AREAS,
            "config/device_registry/list": self.DEVICES,
            "config/entity_registry/list": self.ENTITIES,
        }
        self.rest_hits = 0
        self.rest_status = 200
        self.ws_hits = 0

        async def ws_handler(request):
            self.ws_hits += 1
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"type": "auth_required"})
            assert (await ws.receive_json())["type"] == "auth"
            await ws.send_json({"type": "auth_ok"})
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    req = msg.json()
                    if req.get("type") in results:
                        await ws.send_json({"id": req["id"], "type": "result",
                                            "success": True,
                                            "result": results[req["type"]]})
            return ws

        async def rest_handler(request):
            self.rest_hits += 1
            if self.rest_status == 200:
                name = request.match_info["name"]
                return web.json_response(results[f"config/{name}/list"])
            return web.Response(status=self.rest_status)

        app = web.Application()
        app.router.add_get("/api/websocket", ws_handler)
        app.router.add_get("/api/config/{name}/list", rest_handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"

    async def asyncTearDown(self):
        await self.runner.cleanup()

    async def test_rest_first_when_available(self):
        reg = bot.EntityRegistry(bot.HAClient(self.url, "t", timeout=5))
        areas, devices, ents = await reg._fetch_registries()
        self.assertEqual(areas, self.AREAS)
        self.assertEqual(devices, self.DEVICES)
        self.assertEqual(ents, self.ENTITIES)
        self.assertEqual(self.rest_hits, 3)
        self.assertEqual(self.ws_hits, 0)
        self.assertFalse(reg._rest_registries_gone)
        await reg.ha.close()

    async def test_404_falls_back_to_ws_once(self):
        self.rest_status = 404
        reg = bot.EntityRegistry(bot.HAClient(self.url, "t", timeout=5))

        areas, _, _ = await reg._fetch_registries()
        self.assertEqual(areas, self.AREAS)
        self.assertTrue(reg._rest_registries_gone)

        # Повторные вызовы идут на websocket напрямую, REST не дёргается
        await reg._fetch_registries()
        await reg._fetch_registries()
        self.assertEqual(self.rest_hits, 1)
        self.assertEqual(self.ws_hits, 3)

        await reg._load_area_map()
        self.assertEqual(reg._area_names, {"kitchen": "Кухня"})
        self.assertEqual(reg._area_entities, {"kitchen": ["light.k"]})
        await reg.ha.close()

    async def test_warning_dedupe(self):
        # Сервер, который недоступен полностью: warning один раз на два сбоя
        reg = bot.EntityRegistry(
            bot.HAClient("http://127.0.0.1:1", "t", timeout=2))
        records = []

        class H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = H()
        logging.getLogger("ha-bot").addHandler(h)
        try:
            await reg._load_area_map()
            await reg._load_area_map()
        finally:
            logging.getLogger("ha-bot").removeHandler(h)
        warnings = [m for m in records if "Реестры комнат недоступны" in m]
        self.assertEqual(len(warnings), 1)
        self.assertTrue(reg._area_warned)
        await reg.ha.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

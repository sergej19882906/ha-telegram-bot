"""Тесты для улучшений: безопасность по умолчанию, retry, дедуп, fallback и пр.

Запуск из корня репозитория:
    python -m pytest tests/ -q
"""
import asyncio
import contextlib
import json
import logging
import os
import time
import unittest
from unittest.mock import patch

from tests.test_smoke import make_bot  # noqa: E402  (общий хелпер, DATA_DIR уже задан)
from hamqttbot.config import parse_notify_watchdog_interval  # noqa: E402

import bot  # noqa: E402


@contextlib.contextmanager
def patched_env(**values):
    """Временно меняет переменные окружения; None — удалить переменную."""
    saved = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class FakeRegistry:
    """Заглушка EntityRegistry: одно устройство по любому имени."""

    def __init__(self, eid="light.lamp", fname="Лампа"):
        self._eid = eid
        self._fname = fname

    def by_id_or_alias(self, name):
        return self._eid if name else None

    def search(self, name, limit=20):
        return []

    def get_friendly_name(self, eid):
        return self._fname


def make_update(uid=1, chat_id=7, text="/on лампа"):
    replies = []

    class Msg:
        def __init__(self):
            self.text = text

        async def reply_text(self, part, **kw):
            replies.append(part)
            return None

    msg = Msg()
    update = type("U", (), {
        "effective_user": type("U", (), {"id": uid})(),
        "effective_chat": type("C", (), {"id": chat_id})(),
        "message": msg,
        "effective_message": msg,
        "callback_query": None,
    })()
    return update, replies


class TestParseAllowedUsers:
    def test_list(self):
        with patched_env(ALLOWED_USER_IDS="111, 222", ALLOWED_USER_ID=None,
                         ALLOW_ALL_USERS=None):
            assert bot.parse_allowed_users() == {111, 222}

    def test_legacy_single(self):
        with patched_env(ALLOWED_USER_IDS="", ALLOWED_USER_ID="42"):
            assert bot.parse_allowed_users() == {42}

    def test_invalid_entries_skipped(self):
        with patched_env(ALLOWED_USER_IDS="1,abc, 2", ALLOWED_USER_ID=None):
            assert bot.parse_allowed_users() == {1, 2}

    def test_empty_returns_none(self):
        with patched_env(ALLOWED_USER_IDS="", ALLOWED_USER_ID=""):
            assert bot.parse_allowed_users() is None


class TestRequireAllowedUsers:
    def test_empty_without_allow_all_exits(self):
        with patched_env(ALLOWED_USER_IDS="", ALLOWED_USER_ID=None,
                         ALLOW_ALL_USERS=None):
            try:
                bot.require_allowed_users()
            except SystemExit as e:
                assert "ALLOWED_USER_IDS" in str(e)
            else:
                raise AssertionError("ожидался SystemExit")

    def test_empty_with_allow_all_grants_everyone(self):
        with patched_env(ALLOWED_USER_IDS="", ALLOWED_USER_ID=None,
                         ALLOW_ALL_USERS="1"):
            assert bot.require_allowed_users() is None

    def test_non_empty_list_returned(self):
        with patched_env(ALLOWED_USER_IDS="7,8", ALLOW_ALL_USERS=None):
            assert bot.require_allowed_users() == {7, 8}

    def test_allow_all_does_not_override_list(self):
        with patched_env(ALLOWED_USER_IDS="7", ALLOW_ALL_USERS="1"):
            assert bot.require_allowed_users() == {7}


class TestNotifyConfiguration(unittest.TestCase):
    def test_watchdog_zero_disables_it(self):
        with patch.dict(os.environ, {"NOTIFY_WATCHDOG_INTERVAL": "0"}):
            assert parse_notify_watchdog_interval() == 0

    def test_watchdog_nonzero_interval_has_minimum(self):
        with patch.dict(os.environ, {"NOTIFY_WATCHDOG_INTERVAL": "30"}):
            assert parse_notify_watchdog_interval() == 60
        with patch.dict(os.environ, {"NOTIFY_WATCHDOG_INTERVAL": "120"}):
            assert parse_notify_watchdog_interval() == 120

    def test_invalid_watchdog_interval_defaults_to_disabled(self):
        with patch.dict(os.environ, {"NOTIFY_WATCHDOG_INTERVAL": "invalid"}):
            assert parse_notify_watchdog_interval() == 0

    def test_notify_token_required_when_receiver_enabled(self):
        with self.assertRaisesRegex(SystemExit, "NOTIFY_TOKEN обязателен"):
            bot.validate_notify_config(8099, None)
        with self.assertRaisesRegex(SystemExit, "NOTIFY_TOKEN обязателен"):
            bot.validate_notify_config(8099, "   ")

    def test_receiver_can_be_disabled_without_token(self):
        bot.validate_notify_config(0, None)

    def test_notify_port_range(self):
        bot.validate_notify_config(65535, "secret")
        for port in (-1, 65536):
            with self.subTest(port=port), self.assertRaisesRegex(
                SystemExit, "NOTIFY_PORT"
            ):
                bot.validate_notify_config(port, "secret")


class TestCheckAuth:
    def _upd(self, uid, chat_id=42):
        update, _ = make_update(uid=uid, chat_id=chat_id)
        return update

    def test_member_allowed(self):
        b = make_bot()
        assert b._check_auth(self._upd(1)) is True

    def test_stranger_rejected(self):
        b = make_bot()
        assert b._check_auth(self._upd(999)) is False

    def test_allow_all_accepts_anyone(self):
        cfg = bot.Config(token="t", base_url="http://127.0.0.1:1", ha_token="t")
        b = bot.HATelegramBot(cfg, None)  # None = разрешены все
        assert b._check_auth(self._upd(123456)) is True


class TestCmdSwitch(unittest.IsolatedAsyncioTestCase):
    """cmd_on / cmd_off через моки HAClient: успех и ошибка."""

    def _bot(self):
        b = make_bot()
        b.registry = FakeRegistry()
        return b

    async def test_cmd_on_success(self):
        b = self._bot()
        calls = []

        async def fake_turn_on(eid):
            calls.append(eid)

        b.ha.turn_on = fake_turn_on
        update, replies = make_update(text="/on лампа")
        await b.cmd_on(update, type("C", (), {"args": ["лампа"]})())
        assert calls == ["light.lamp"]
        assert any("включено" in r for r in replies), replies

    async def test_cmd_off_success(self):
        b = self._bot()
        calls = []

        async def fake_turn_off(eid):
            calls.append(eid)

        b.ha.turn_off = fake_turn_off
        update, replies = make_update(text="/off лампа")
        await b.cmd_off(update, type("C", (), {"args": ["лампа"]})())
        assert calls == ["light.lamp"]
        assert any("выключено" in r for r in replies), replies

    async def test_cmd_on_error_reported(self):
        b = self._bot()

        async def fake_turn_on(eid):
            raise bot.HAError("HTTP 500: boom")

        b.ha.turn_on = fake_turn_on
        update, replies = make_update(text="/on лампа")
        await b.cmd_on(update, type("C", (), {"args": ["лампа"]})())
        assert any("Ошибка" in r and "boom" in r for r in replies), replies

    async def test_cmd_off_error_reported(self):
        b = self._bot()

        async def fake_turn_off(eid):
            raise RuntimeError("нет связи")

        b.ha.turn_off = fake_turn_off
        update, replies = make_update(text="/off лампа")
        await b.cmd_off(update, type("C", (), {"args": ["лампа"]})())
        assert any("Ошибка" in r for r in replies), replies

    async def test_usage_without_args(self):
        b = self._bot()
        update, replies = make_update(text="/on")
        await b.cmd_on(update, type("C", (), {"args": []})())
        assert any("Использование" in r for r in replies), replies

    async def test_cmd_toggle_off_turns_on(self):
        b = self._bot()
        calls = []

        async def fake_get_entity(eid):
            return {"state": "off", "attributes": {}}

        async def fake_turn_on(eid):
            calls.append(("on", eid))

        b.ha.get_entity = fake_get_entity
        b.ha.turn_on = fake_turn_on
        update, replies = make_update(text="/toggle лампа")
        await b.cmd_toggle(update, type("C", (), {"args": ["лампа"]})())
        assert calls == [("on", "light.lamp")]
        assert any("состояние изменено" in r for r in replies), replies


class TestSetUnits(unittest.IsolatedAsyncioTestCase):
    async def test_climate_shows_celsius(self):
        b = make_bot()
        b.registry = FakeRegistry(eid="climate.ac", fname="Кондиционер")
        calls = []

        async def fake_set_value(eid, value):
            calls.append((eid, value))

        b.ha.set_value = fake_set_value
        update, replies = make_update(text="/set кондиционер 25")
        await b.cmd_set(update, type("C", (), {"args": ["кондиционер", "25"]})())
        assert calls == [("climate.ac", 25.0)]
        assert any("25°C" in r for r in replies), replies


class TestTFallback:
    def test_fallback_to_ru_with_warning_once(self):
        key = "timer_min"
        saved = bot.MESSAGES["en"].pop(key)
        records = []

        class H(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        h = H()
        logging.getLogger("ha-bot").addHandler(h)
        try:
            bot.set_lang(555001, "en")
            ru_text = bot.MESSAGES["ru"][key]
            assert bot.t(555001, key) == ru_text
            # Повторный вызов — без нового предупреждения
            assert bot.t(555001, key) == ru_text
        finally:
            logging.getLogger("ha-bot").removeHandler(h)
            bot.MESSAGES["en"][key] = saved
            bot.set_lang(555001, "ru")
        warnings = [m for m in records if "timer_min" in m]
        assert len(warnings) == 1, warnings

    def test_unknown_key_returns_key(self):
        # Ключа нет ни в одном языке — возвращается сам ключ
        assert bot.t(555002, "__definitely_no_such_key__") == "__definitely_no_such_key__"


class TestLangStorage:
    def test_set_lang_roundtrip(self):
        bot.set_lang(555003, "en")
        try:
            assert bot.get_lang(555003) == "en"
            # Сохранилось на диск: «новый» процесс прочитает то же значение
            assert bot.load_user_langs()["555003"] == "en"
        finally:
            bot.set_lang(555003, "ru")
        assert bot.get_lang(555003) == "ru"


class TestTimerErrorNotify(unittest.IsolatedAsyncioTestCase):
    async def test_turn_off_failure_notifies_chat(self):
        b = make_bot()
        captured = []

        class FakeBot:
            async def send_message(self, cid, text, parse_mode=None):
                captured.append((cid, text))

        b.app = type("A", (), {"bot": FakeBot()})()

        async def failing_turn_off(eid):
            raise bot.HAError("HTTP 502")

        b.ha.turn_off = failing_turn_off
        await b._start_timer(1, 7, "light.x", 5, remaining=0.05)
        task = b._timers[(1, "light.x")]
        await asyncio.wait_for(task, timeout=5)
        assert len(captured) == 1
        assert captured[0][0] == 7
        assert "light.x" in captured[0][1]


class TestSplitHtmlSafe:
    def test_cut_not_inside_tag(self):
        b = make_bot()
        text = "<code>" + "x" * 5000 + "</code>"
        parts = b._split_message(text, 4000)
        assert len(parts) == 1
        head = parts[0]
        assert len(head) <= 4000
        # Обрезка отступила перед обрезанным закрывающим тегом — в хвосте нет "<"
        assert "<" not in head[len("<code>"):]

    def test_short_text_untouched(self):
        b = make_bot()
        assert b._split_message("<b>привет</b>", 4000) == ["<b>привет</b>"]


class TestReplyTextResilience(unittest.IsolatedAsyncioTestCase):
    async def test_error_in_part_does_not_stop_others(self):
        b = make_bot()
        calls = []

        class UM:
            async def reply_text(self, part, **kw):
                calls.append(part)
                if len(calls) == 1:
                    raise RuntimeError("network")
                return None

        update = type("U", (), {"effective_message": UM()})()
        long_text = "x" * 3900 + "\n" + "y" * 3900
        await b._reply_text(update, long_text, None)
        assert len(calls) == 2


class TestNotifyParallel(unittest.IsolatedAsyncioTestCase):
    async def test_slow_chat_does_not_block_others(self):
        b = make_bot()
        sent = []

        class FakeBot:
            async def send_message(self, cid, text, parse_mode=None):
                if cid == 1:
                    await asyncio.sleep(0.3)  # медленный чат
                elif cid == 2:
                    raise RuntimeError("blocked")  # упавший чат
                sent.append(cid)

        b.app = type("A", (), {"bot": FakeBot()})()
        b._known_chats = {1, 2, 3}

        class Req:
            headers = {}

            async def json(self):
                return {"text": "hi"}

        start = time.time()
        resp = await b._handle_notify(Req())
        elapsed = time.time() - start
        assert resp.status == 200
        # Параллельно: общее время ~0.3 с (медленный чат), а не 0.3+; все 3 обработаны
        assert elapsed < 0.6
        assert sorted(sent) == [1, 3]
        body = json.loads(resp.text)
        assert body["sent"] == 2 and body["failed"] == 1

"""Реестр устройств Home Assistant: кеш, алиасы, комнаты, сцены."""

import asyncio
import re
from typing import Optional

import httpx

from .config import ROOM_ATTRS, logger
from .ha_client import HAClient, HAError

# aiohttp нужен для websocket-запросов к HA
try:
    import aiohttp
except ImportError:
    aiohttp = None


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
        # REST-endpoints реестров удалены (404/410) — дальше сразу websocket
        self._rest_registries_gone = False
        # Переиспользуемая aiohttp-сессия для websocket (создаётся лениво)
        self._ws_session = None

    def __len__(self) -> int:
        return len(self._entities)

    def count(self) -> int:
        """Возвращает число устройств в кеше реестра."""
        return len(self._entities)

    async def close(self):
        """Закрывает переиспользуемые ресурсы (aiohttp-сессию websocket)."""
        if self._ws_session is not None:
            await self._ws_session.close()
            self._ws_session = None

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
        if not self._rest_registries_gone:
            try:
                return (
                    await self.ha.get_json("/api/config/area_registry/list"),
                    await self.ha.get_json("/api/config/device_registry/list"),
                    await self.ha.get_json("/api/config/entity_registry/list"),
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in (404, 410):
                    raise
                # REST-endpoints удалены в новых версиях HA: до конца работы
                # процесса идём сразу на websocket, не дёргая 404 каждый цикл
                self._rest_registries_gone = True
                logger.info("REST-endpoints реестров не найдены (404) — переключаюсь на websocket API")
        return await self._fetch_registries_ws()

    async def _fetch_registries_ws(self):
        """Достаёт реестры через websocket API HA (авторизация по токену)."""
        if aiohttp is None:
            raise HAError("aiohttp не установлен — websocket API недоступен")
        ws_url = self.ha.base_url.replace("http://", "ws://", 1)
        ws_url = ws_url.replace("https://", "wss://", 1).rstrip("/") + "/api/websocket"

        if self._ws_session is None or self._ws_session.closed:
            timeout = aiohttp.ClientTimeout(total=max(20, self.ha.timeout * 2))
            self._ws_session = aiohttp.ClientSession(timeout=timeout)
        sess = self._ws_session

        async def recv(ws):
            return await asyncio.wait_for(ws.receive_json(), timeout=self.ha.timeout)

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

    def get_cached(self, eid: str) -> dict:
        """Возвращает закешированные данные устройства ({} если неизвестно)."""
        return self._entities.get(eid, {})

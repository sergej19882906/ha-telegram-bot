"""Асинхронный клиент REST API Home Assistant."""

import asyncio
from typing import Optional

import httpx

from .config import HA_RETRY_ATTEMPTS, HA_RETRY_BASE_DELAY, logger


class HAError(Exception):
    """Ошибка при работе с Home Assistant."""
    pass


class HAClient:
    """Асинхронный клиент для работы с Home Assistant REST API."""

    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
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
        """Выполняет POST-запрос и возвращает JSON.

        В текст ошибки включает тело ответа HA — там HA пишет причину
        (например, почему упал rest_command).
        """
        r = await self.client.post(path, json=body, timeout=self.timeout)
        if r.status_code == 401:
            raise HAError("Invalid HA access token.")
        if r.status_code >= 400:
            detail = (r.text or "").strip()[:300]
            raise HAError(f"HTTP {r.status_code}: {detail}" if detail
                          else f"HTTP {r.status_code}")
        return r.json()

    async def _post_idempotent(self, path: str, body: dict):
        """POST с повторными попытками (экспоненциальная пауза).

        Только для идемпотентных вызовов: повтор turn_on/turn_off безопасен.
        401 (невалидный токен) повторам не подлежит — сразу прокидываем.
        """
        attempt = 0
        while True:
            try:
                return await self.post_json(path, body)
            except Exception as e:
                # 401 (невалидный токен) повторам не подлежит — сразу прокидываем
                if isinstance(e, HAError) and "Invalid HA access token" in str(e):
                    raise
                attempt += 1
                if attempt > HA_RETRY_ATTEMPTS:
                    raise
                delay = HA_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "HA %s не ответил (%s) — повторная попытка %d/%d через %.1f с",
                    path, e, attempt, HA_RETRY_ATTEMPTS, delay,
                )
                await asyncio.sleep(delay)

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
        """Включает устройство (идемпотентно — с повторными попытками)."""
        domain, _, _ = entity_id.rpartition(".")
        return await self._post_idempotent(
            f"/api/services/{domain}/turn_on",
            {"entity_id": entity_id, **kwargs}
        )

    async def turn_off(self, entity_id: str, **kwargs):
        """Выключает устройство (идемпотентно — с повторными попытками)."""
        domain, _, _ = entity_id.rpartition(".")
        return await self._post_idempotent(
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

    async def call_service(self, domain: str, service: str, data: dict):
        """Вызывает сервис HA (например, rest_command/telegram_notify)."""
        return await self.post_json(f"/api/services/{domain}/{service}", data)

"""Источники котиков: TheCatAPI (основной) и Cataas (резервный)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 9 * 1024 * 1024
USER_AGENT = "kotobot/1.0"


class CatUnavailable(RuntimeError):
    """Не удалось получить котика ни из одного источника."""


@dataclass(frozen=True, slots=True)
class CatImage:
    url: str
    source: str
    key: str
    caption: str | None = None


def _looks_like_image(data: bytes) -> bool:
    if data.startswith(b"\xff\xd8\xff"):  # JPEG
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"):  # PNG
        return True
    if data[:6] in (b"GIF87a", b"GIF89a"):  # GIF
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":  # WEBP
        return True
    return False


def _breed_caption(item: dict) -> str | None:
    breeds = item.get("breeds") or []
    if isinstance(breeds, list) and breeds and isinstance(breeds[0], dict):
        name = breeds[0].get("name")
        if name:
            return str(name)
    return None


class CatService:
    """Ходит в интернет за котиками и умеет переключаться между источниками."""

    def __init__(self, api_key: str = "", timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=5.0),
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ HTTP
    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """GET с одним повтором на сетевые сбои и 429/5xx."""
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await self._client.get(url, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                    await asyncio.sleep(0.8)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.5)
        raise last_error  # type: ignore[misc]

    # -------------------------------------------------------------- Источники
    async def _thecatapi_many(self, limit: int) -> list[CatImage]:
        params = {
            "limit": str(max(1, min(limit, 20))),
            "size": "med",
            "mime_types": "jpg,png",
            "order": "RANDOM",
        }
        headers = {"x-api-key": self._api_key} if self._api_key else None
        response = await self._get(
            "https://api.thecatapi.com/v1/images/search",
            params=params,
            headers=headers,
        )
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ValueError("TheCatAPI вернул пустой список")

        images: list[CatImage] = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            images.append(
                CatImage(
                    url=item["url"],
                    source="thecatapi",
                    key=str(item.get("id") or item["url"]),
                    caption=_breed_caption(item),
                )
            )
        if not images:
            raise ValueError("в ответе TheCatAPI нет картинок")
        return images

    async def _pick_thecatapi(self) -> CatImage:
        return (await self._thecatapi_many(1))[0]

    async def _pick_cataas(self) -> CatImage:
        response = await self._get("https://cataas.com/cat", params={"json": "true"})
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Cataas вернул неожиданный ответ")

        url = str(payload.get("url") or "")
        if url.startswith("/"):
            url = "https://cataas.com" + url
        if not url:
            cat_id = payload.get("id")
            if not cat_id:
                raise ValueError("Cataas не вернул ни url, ни id")
            url = f"https://cataas.com/cat/{cat_id}"

        return CatImage(url=url, source="cataas", key=str(payload.get("id") or url))

    # ------------------------------------------------------------------- API
    async def pick(self) -> CatImage:
        """Вернуть метаданные случайного котика (без скачивания файла)."""
        errors: list[str] = []
        for picker in (self._pick_thecatapi, self._pick_cataas):
            try:
                return await picker()
            except Exception as exc:  # noqa: BLE001 — нужен фолбэк при любом сбое
                errors.append(f"{picker.__name__}: {exc}")
                log.warning("Источник %s не сработал: %s", picker.__name__, exc)
        raise CatUnavailable("; ".join(errors) or "источники недоступны")

    async def pick_many(self, limit: int = 10) -> list[CatImage]:
        """Список котиков для inline-режима. Только TheCatAPI (один запрос)."""
        try:
            return await self._thecatapi_many(limit)
        except Exception as exc:  # noqa: BLE001
            log.warning("TheCatAPI (inline) не сработал: %s", exc)
        return []

    async def download(self, image: CatImage) -> bytes:
        """Скачать картинку и проверить, что это действительно изображение."""
        response = await self._get(image.url)
        data = response.content
        if not data:
            raise ValueError("пустой ответ")
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"файл слишком большой: {len(data)} байт")
        if not _looks_like_image(data):
            content_type = response.headers.get("content-type")
            raise ValueError(f"это не картинка ({content_type})")
        return data

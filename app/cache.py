"""Кэш file_id с датой записи и автоочисткой по TTL."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

SECONDS_PER_DAY = 86_400


class FileIdCache:
    """Хранит соответствие «ключ картинки → file_id» и время записи.

    Формат файла: {"thecatapi:abc": {"id": "file_id", "ts": 1699999999.0}}
    Старый формат ({"key": "file_id"}) читается как запись текущего времени.
    """

    def __init__(self, path: Path, max_entries: int = 2000, ttl_days: int = 30) -> None:
        self._path = path
        self._max_entries = max_entries
        self._ttl_days = max(0, ttl_days)
        self._data: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._dirty = False

    # ------------------------------------------------------------------ файл
    async def load(self) -> None:
        try:
            raw = await asyncio.to_thread(self._path.read_text, "utf-8")
            payload = json.loads(raw)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.warning("Не удалось прочитать кэш %s: %s", self._path, exc)
            return

        if not isinstance(payload, dict):
            log.warning("Кэш %s не словарь, игнорирую", self._path)
            return

        now = time.time()
        restored = 0
        for key, value in payload.items():
            if isinstance(value, dict) and value.get("id"):
                ts_value = value.get("ts")
                self._data[str(key)] = {
                    "id": str(value["id"]),
                    "ts": float(ts_value) if ts_value is not None else now,
                }
                restored += 1
            elif isinstance(value, str):
                self._data[str(key)] = {"id": value, "ts": now}
                restored += 1

        removed = self._prune_locked()
        if removed:
            self._dirty = True
        log.info("Кэш file_id: %d записей, удалено устаревших: %d", restored, removed)

    # ------------------------------------------------------------------- API
    def get(self, key: str) -> str | None:
        entry = self._data.get(key)
        return entry["id"] if entry else None

    async def put(self, key: str, file_id: str) -> None:
        async with self._lock:
            self._data[key] = {"id": file_id, "ts": time.time()}
            self._dirty = True
            overflow = len(self._data) - self._max_entries
            if overflow > 0:
                oldest = sorted(self._data, key=lambda k: self._data[k]["ts"])[:overflow]
                for old_key in oldest:
                    del self._data[old_key]

    async def prune(self, ttl_days: int | None = None) -> int:
        """Удалить записи старше TTL. Возвращает число удалённых."""
        async with self._lock:
            if ttl_days is not None:
                self._ttl_days = max(0, ttl_days)
            removed = self._prune_locked()
            if removed:
                self._dirty = True
            return removed

    def _prune_locked(self) -> int:
        if self._ttl_days <= 0:
            return 0
        cutoff = time.time() - self._ttl_days * SECONDS_PER_DAY
        stale = [key for key, entry in self._data.items() if entry["ts"] < cutoff]
        for key in stale:
            del self._data[key]
        return len(stale)

    async def save(self) -> None:
        if not self._dirty:
            return
        async with self._lock:
            if not self._dirty:
                return
            payload = json.dumps(self._data, ensure_ascii=False)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = self._path.with_suffix(".tmp")
                await asyncio.to_thread(tmp_path.write_text, payload, "utf-8")
                await asyncio.to_thread(tmp_path.replace, self._path)
                self._dirty = False
            except OSError as exc:
                log.warning("Не удалось сохранить кэш %s: %s", self._path, exc)

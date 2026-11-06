"""Список разрешённых чатов: базовый из конфига + добавленные командами."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)


class ChatRegistry:
    """Базовые id берутся из ALLOWED_CHAT_IDS, динамические — из data/allowed_chats.json."""

    def __init__(self, path: Path, initial: Iterable[int] = ()) -> None:
        self._path = path
        self._configured = frozenset(int(chat_id) for chat_id in initial)
        self._dynamic: set[int] = set()
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> frozenset[int]:
        return self._configured

    def allows(self, chat_id: int) -> bool:
        # Пустой список означает режим настройки: разрешено везде.
        if not self._configured and not self._dynamic:
            return True
        return chat_id in self._configured or chat_id in self._dynamic

    def ids(self) -> list[int]:
        return sorted(self._configured | self._dynamic)

    async def load(self) -> None:
        try:
            raw = await asyncio.to_thread(self._path.read_text, "utf-8")
            payload = json.loads(raw)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.warning("Не удалось прочитать список чатов %s: %s", self._path, exc)
            return

        values = payload.get("allowed") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            return

        restored: set[int] = set()
        for value in values:
            try:
                restored.add(int(value))
            except (TypeError, ValueError):
                continue
        self._dynamic = restored
        log.info("Динамический список чатов: %d", len(restored))

    async def add(self, chat_id: int) -> bool:
        async with self._lock:
            if chat_id in self._configured or chat_id in self._dynamic:
                return False
            self._dynamic.add(chat_id)
            await self._save_locked()
            return True

    async def remove(self, chat_id: int) -> bool:
        async with self._lock:
            if chat_id not in self._dynamic:
                return False
            self._dynamic.discard(chat_id)
            await self._save_locked()
            return True

    async def _save_locked(self) -> None:
        payload = json.dumps({"allowed": sorted(self._dynamic)}, ensure_ascii=False)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".tmp")
            await asyncio.to_thread(tmp_path.write_text, payload, "utf-8")
            await asyncio.to_thread(tmp_path.replace, self._path)
        except OSError as exc:
            log.warning("Не удалось сохранить список чатов %s: %s", self._path, exc)

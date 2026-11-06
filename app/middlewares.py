"""Middleware: белый список чатов и антифлуд."""

from __future__ import annotations

import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, Message

from config import Config

log = logging.getLogger(__name__)


def event_chat(event: object) -> Chat | None:
    if isinstance(event, Message):
        return event.chat
    if isinstance(event, CallbackQuery) and event.message is not None:
        return event.message.chat
    return None


class AllowListMiddleware(BaseMiddleware):
    """Пускает команды только из разрешённых чатов (если список задан)."""

    def __init__(self, config: Config) -> None:
        self._allowed = config.allowed_chat_ids

    async def __call__(self, handler, event, data):
        if not self._allowed:
            return await handler(event, data)

        chat = event_chat(event)
        if chat is None:
            return await handler(event, data)

        if chat.id not in self._allowed:
            log.info(
                "Чат не в белом списке: id=%s type=%s title=%r",
                chat.id,
                chat.type,
                chat.title,
            )
            if isinstance(event, CallbackQuery):
                await event.answer("Этот бот работает только в одной группе 🙃")
            return None

        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    """Не чаще одного котика в cooldown секунд на чат."""

    def __init__(self, cooldown_seconds: float) -> None:
        self._cooldown = max(0.0, cooldown_seconds)
        self._last_request: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        if self._cooldown <= 0:
            return await handler(event, data)

        chat = event_chat(event)
        if chat is None:
            return await handler(event, data)

        now = time.monotonic()
        previous = self._last_request.get(chat.id, 0.0)
        if now - previous < self._cooldown:
            if isinstance(event, CallbackQuery):
                await event.answer("Мяу! Секундочку…")
            return None

        self._last_request[chat.id] = now
        return await handler(event, data)

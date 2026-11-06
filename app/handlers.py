"""Обработчики команд, кнопок и inline-режима."""

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultPhoto,
    Message,
    User,
)

from app.cache import FileIdCache
from app.cats import CatService
from config import Config

log = logging.getLogger(__name__)
router = Router(name="kotobot")

MORE_CALLBACK = "more_cat"

HELP_TEXT = (
    "🐱 <b>Котобот</b>\n\n"
    "/cat — прислать случайного котика\n"
    "/help — эта справка\n\n"
    "Под фотографией есть кнопка «Ещё котика» — жмите, если одного мало."
)


def more_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🐱 Ещё котика", callback_data=MORE_CALLBACK)]
        ]
    )


def requester_caption(base: str | None, requester: User | None, mode: str) -> str | None:
    """Подпись «для Имя» — чтобы в группе было видно, кто заказал котика."""
    if requester is None or mode == "off":
        return base

    name = (requester.full_name or requester.first_name or "").strip()
    if not name:
        return base

    safe_name = html.escape(name)
    if mode == "mention":
        who = f'<a href="tg://user?id={requester.id}">{safe_name}</a>'
    else:
        who = f"<b>{safe_name}</b>"

    caption = f"🐱 для {who}"
    return f"{caption} · {base}" if base else caption


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    log.info(
        "start: chat_id=%s type=%s title=%r user_id=%s",
        message.chat.id,
        message.chat.type,
        message.chat.title,
        message.from_user.id if message.from_user else None,
    )
    text = HELP_TEXT
    if message.chat.type == "private":
        text += "\n\nДобавьте меня в группу и напишите там /cat."
    await message.answer(text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.message(Command("cat"))
async def cmd_cat(
    message: Message,
    cats: CatService,
    cache: FileIdCache,
    config: Config,
) -> None:
    log.info(
        "cat: chat_id=%s type=%s title=%r user_id=%s",
        message.chat.id,
        message.chat.type,
        message.chat.title,
        message.from_user.id if message.from_user else None,
    )
    await _send_cat(
        message,
        cats,
        cache,
        config,
        requester=message.from_user,
        as_reply=True,
    )


@router.callback_query(F.data == MORE_CALLBACK)
async def cb_more(
    callback: CallbackQuery,
    cats: CatService,
    cache: FileIdCache,
    config: Config,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await _send_cat(
        callback.message,
        cats,
        cache,
        config,
        requester=callback.from_user,
        as_reply=False,
    )


@router.inline_query()
async def inline_query(query: InlineQuery, cats: CatService, config: Config) -> None:
    if not config.inline_enabled:
        await query.answer([], cache_time=1)
        return

    images = await cats.pick_many(10)
    results = [
        InlineQueryResultPhoto(
            id=f"{image.source}-{image.key}",
            photo_url=image.url,
            thumbnail_url=image.url,
            title="Котик",
            description="Нажмите, чтобы отправить в чат",
            caption=image.caption,
        )
        for image in images
    ]
    await query.answer(results, cache_time=10, is_personal=True)


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    log.error(
        "Ошибка при обработке апдейта %s",
        event.update.update_id,
        exc_info=event.exception,
    )
    return True


async def _deliver(
    message: Message,
    photo,
    caption: str | None,
    as_reply: bool,
) -> Message:
    """Отправить фото; по возможности ответом на сообщение пользователя."""
    kwargs = {
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": more_keyboard(),
    }
    if as_reply:
        try:
            return await message.reply_photo(photo, **kwargs)
        except TelegramBadRequest:
            log.info("Не вышло ответить на сообщение, отправляю обычным")
    return await message.answer_photo(photo, **kwargs)


async def _send_cat(
    message: Message,
    cats: CatService,
    cache: FileIdCache,
    config: Config,
    requester: User | None,
    as_reply: bool,
) -> None:
    """Достать котика и отправить. Две попытки: вдруг первый источник отвалился."""
    last_error: Exception | None = None

    for _ in range(2):
        try:
            image = await cats.pick()
        except Exception as exc:  # noqa: BLE001 — важно ответить пользователю, а не упасть
            last_error = exc
            break

        caption = requester_caption(image.caption, requester, config.requester_mode)
        cache_key = f"{image.source}:{image.key}"

        cached_file_id = cache.get(cache_key)
        if cached_file_id:
            try:
                await _deliver(message, cached_file_id, caption, as_reply)
                return
            except TelegramBadRequest:
                log.info("file_id для %s устарел, отправляю файл заново", cache_key)

        try:
            data = await cats.download(image)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("Не удалось скачать %s: %s", image.url, exc)
            continue

        sent = await _deliver(
            message,
            BufferedInputFile(data, filename="cat.jpg"),
            caption,
            as_reply,
        )
        if sent.photo:
            await cache.put(cache_key, sent.photo[-1].file_id)
            await cache.save()
        return

    log.error("Котика отправить не удалось: %s", last_error)
    await message.answer("Котики сегодня прячутся 😿 Попробуйте ещё раз через минуту.")

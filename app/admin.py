"""Команды владельца: управление списком групп."""

from __future__ import annotations

import html
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.chats import ChatRegistry
from config import Config

log = logging.getLogger(__name__)
router = Router(name="admin")


def _is_owner(message: Message, config: Config) -> bool:
    user = message.from_user
    return bool(user and config.owner_ids and user.id in config.owner_ids)


async def _require_owner(message: Message, config: Config) -> bool:
    if not config.owner_ids:
        await message.answer(
            "Владелец не настроен: добавьте <code>OWNER_IDS</code> в bot.env "
            "(свой id можно узнать командой /whoami).",
            parse_mode="HTML",
        )
        return False
    if not _is_owner(message, config):
        await message.answer("⛔ Эта команда только для владельца бота.")
        return False
    return True


@router.message(Command("allow"))
async def cmd_allow(message: Message, config: Config, chats: ChatRegistry) -> None:
    if message.chat.type == "private":
        await message.answer("Добавьте бота в группу и отправьте /allow там.")
        return
    if not await _require_owner(message, config):
        return

    added = await chats.add(message.chat.id)
    title = html.escape(message.chat.title or "без названия")
    if added:
        log.info("Чат добавлен владельцем: id=%s title=%r", message.chat.id, message.chat.title)
        await message.answer(f"✅ Группа «{title}» добавлена в список.")
    else:
        await message.answer(f"Группа «{title}» уже в списке.")


@router.message(Command("deny"))
async def cmd_deny(message: Message, config: Config, chats: ChatRegistry) -> None:
    if message.chat.type == "private":
        await message.answer("Команда работает в группе.")
        return
    if not await _require_owner(message, config):
        return

    title = html.escape(message.chat.title or "без названия")
    if await chats.remove(message.chat.id):
        log.info("Чат убран владельцем: id=%s", message.chat.id)
        await message.answer(f"🗑 Группа «{title}» убрана из списка.")
    elif message.chat.id in chats.configured:
        await message.answer(
            f"Группа «{title}» прописана в <code>bot.env</code> — уберите её id оттуда.",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"Группы «{title}» и так нет в списке.")


@router.message(Command("chats"))
async def cmd_chats(message: Message, config: Config, chats: ChatRegistry) -> None:
    if not await _require_owner(message, config):
        return
    ids = chats.ids()
    if not ids:
        await message.answer("Список пуст — бот работает во всех группах.")
        return
    lines = "\n".join(f"• <code>{chat_id}</code>" for chat_id in ids)
    await message.answer(f"Разрешённые чаты:\n{lines}", parse_mode="HTML")


@router.message(Command("whoami"))
async def cmd_whoami(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else "—"
    await message.answer(
        f"Ваш id: <code>{user_id}</code>\nЧат: <code>{message.chat.id}</code>",
        parse_mode="HTML",
    )

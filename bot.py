"""Точка входа: настройка и запуск long polling."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand

from app.cache import FileIdCache
from app.cats import CatService
from app.handlers import router
from app.middlewares import AllowListMiddleware, ThrottlingMiddleware
from config import Config

log = logging.getLogger("kotobot")


def setup_logging(level: str, log_dir: Path) -> None:
    """Логи и в stdout (docker logs), и в файл с суточной ротацией."""
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Ротация в полночь по местному времени, храним 7 файлов (неделя).
    file_handler = TimedRotatingFileHandler(
        log_dir / "bot.log",
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _daily_cache_cleanup(cache: FileIdCache, ttl_days: int) -> None:
    """Раз в сутки в 04:00 чистим устаревшие записи кэша."""
    while True:
        now = datetime.now()
        target = now.replace(hour=4, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        log.info(
            "Ежедневная чистка кэша запланирована на %s (TTL %d дн.)",
            target.strftime("%Y-%m-%d %H:%M"),
            ttl_days,
        )
        await asyncio.sleep(max(60.0, (target - now).total_seconds()))
        try:
            removed = await cache.prune(ttl_days)
            await cache.save()
            log.info("Чистка кэша выполнена: удалено %d записей", removed)
        except Exception:  # noqa: BLE001 — фоновая задача не должна убивать бота
            log.exception("Ошибка ежедневной чистки кэша")


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="cat", description="Прислать котика"),
        BotCommand(command="help", description="Что умеет бот"),
    ]
    try:
        await bot.set_my_commands(commands)
    except TelegramAPIError as exc:
        log.warning("Не удалось установить список команд: %s", exc)


async def main() -> None:
    config = Config.from_env()
    setup_logging(config.log_level, config.log_dir)

    if config.allow_all_chats:
        log.warning(
            "ALLOWED_CHAT_IDS пуст: бот ответит в любом чате. "
            "Добавьте id группы в .env и перезапустите."
        )
    if not config.thecatapi_key:
        log.warning("THE_CAT_API_KEY не задан: у TheCatAPI будет демо-лимит запросов.")

    bot = Bot(token=config.bot_token, default=DefaultBotProperties())
    dp = Dispatcher()

    cats = CatService(api_key=config.thecatapi_key)
    cache = FileIdCache(
        config.data_dir / "file_ids.json",
        ttl_days=config.cache_ttl_days,
    )
    await cache.load()

    dp["config"] = config
    dp["cats"] = cats
    dp["cache"] = cache

    router.message.middleware(AllowListMiddleware(config))
    router.callback_query.middleware(AllowListMiddleware(config))
    router.message.middleware(ThrottlingMiddleware(config.cooldown_seconds))
    dp.include_router(router)

    # Сбрасываем вебхук и старые апдейты: после рестарта не нужно отвечать на вчерашние /cat.
    await bot.delete_webhook(drop_pending_updates=True)
    await set_commands(bot)

    cleanup_task = asyncio.create_task(_daily_cache_cleanup(cache, config.cache_ttl_days))
    log.info("Котобот запущен, начинаю polling")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        log.info("Останавливаюсь…")
        await cache.save()
        await cats.close()
        await bot.session.close()


def run() -> None:
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    run()

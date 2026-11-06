"""Конфигурация бота: читается из переменных окружения (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# .env — токен (может быть root-only), bot.env — наши настройки поверх.
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "bot.env", override=True)


def _env(*names: str, default: str = "") -> str:
    """Вернуть первое непустое значение из перечисленных переменных."""
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _parse_chat_ids(raw: str) -> frozenset[int]:
    chat_ids: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            chat_ids.add(int(chunk))
        except ValueError:
            raise ValueError(f"ALLOWED_CHAT_IDS: {chunk!r} — это не числовой id") from None
    return frozenset(chat_ids)


def _parse_bool(raw: str, default: bool) -> bool:
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "да"}


def _parse_int(raw: str, default: int) -> int:
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return default


def _parse_choice(raw: str, allowed: set[str], default: str) -> str:
    value = (raw or "").strip().lower()
    return value if value in allowed else default


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    allowed_chat_ids: frozenset[int] = field(default_factory=frozenset)
    thecatapi_key: str = ""
    cooldown_seconds: float = 3.0
    inline_enabled: bool = True
    log_level: str = "INFO"
    data_dir: Path = Path("data")
    cache_ttl_days: int = 30
    requester_mode: str = "name"

    @property
    def allow_all_chats(self) -> bool:
        """True, пока список разрешённых чатов не заполнен."""
        return not self.allowed_chat_ids

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @classmethod
    def from_env(cls) -> "Config":
        token = _env("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "TOKEN", "token")
        if not token:
            raise RuntimeError(
                "Не найден токен бота. Укажите BOT_TOKEN в .env "
                "(например: BOT_TOKEN=123456:ABC-DEF...)"
            )

        try:
            cooldown = float(_env("COOLDOWN_SECONDS", default="3"))
        except ValueError:
            cooldown = 3.0

        return cls(
            bot_token=token,
            allowed_chat_ids=_parse_chat_ids(_env("ALLOWED_CHAT_IDS")),
            thecatapi_key=_env("THE_CAT_API_KEY", "THECATAPI_KEY", "CAT_API_KEY"),
            cooldown_seconds=max(0.0, cooldown),
            inline_enabled=_parse_bool(_env("INLINE_ENABLED", default="1"), True),
            log_level=_env("LOG_LEVEL", default="INFO"),
            data_dir=Path(_env("DATA_DIR", default="data")),
            cache_ttl_days=_parse_int(_env("CACHE_TTL_DAYS", default="30"), 30),
            requester_mode=_parse_choice(
                _env("REQUESTER_MODE", default="name"),
                {"off", "name", "mention"},
                "name",
            ),
        )

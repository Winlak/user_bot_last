"""Configuration settings for the bot."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


def _to_bool(value: str | None, default: bool) -> bool:
    """Return a boolean from an environment value."""

    if value is None:
        return default
    return value.strip().lower() == "true"


def _to_float(value: str | None, default: float | None) -> float | None:
    """Parse an optional float from a string."""

    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _sqlite_path_from_url(url: str | None, fallback: Path) -> Path:
    """Extract the SQLite file path from a URL-like value."""

    if not url:
        return fallback

    # Accept both plain paths and URLs like sqlite+aiosqlite:///db.sqlite3
    if url.startswith("sqlite") and "///" in url:
        return Path(url.split("///", maxsplit=1)[1])

    return Path(url)


@dataclass
class Settings:
    """Bot configuration settings."""

    api_id: int
    api_hash: str

    string_session: str

    source_channel: str
    target_channels: List[str]
    forwarding_enabled: bool
    forwarding_delay_seconds: float
    forwarding_max_messages_per_second: float | None
    forwarding_queue_maxsize: int | None
    data_dir: Path
    db_path: Path
    log_level: str

    def __init__(self):
        """Initialize settings from environment variables."""

        self.api_id = int(os.getenv("TELEGRAM_API_ID", os.getenv("API_ID", "0")))
        self.api_hash = os.getenv("TELEGRAM_API_HASH", os.getenv("API_HASH", ""))
        self.string_session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()


        self.source_channel = os.getenv("SOURCE_CHANNEL", "")
        target_channels_str = os.getenv("TARGET_CHANNELS", "")
        self.target_channels = [
            ch.strip() for ch in target_channels_str.split(",") if ch.strip()
        ]

        self.forwarding_enabled = _to_bool(
            os.getenv("FORWARDING_ENABLED"), True
        )
        self.forwarding_delay_seconds = _to_float(
            os.getenv("FORWARDING_DELAY_SECONDS"), 0.0
        ) or 0.0
        self.forwarding_max_messages_per_second = _to_float(
            os.getenv("FORWARDING_MAX_MESSAGES_PER_SECOND"), None
        )
        queue_maxsize = os.getenv("FORWARDING_QUEUE_MAXSIZE", "")
        self.forwarding_queue_maxsize = int(queue_maxsize) if queue_maxsize else None

        self.data_dir = Path(os.getenv("DATA_DIR", "data"))
        self.db_path = _sqlite_path_from_url(
            os.getenv("DB_URL"), self.data_dir / "db.sqlite3"
        )
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        if not self.api_id or not self.api_hash:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set")
        if not self.string_session:
            raise ValueError("TELEGRAM_STRING_SESSION must be set")
        if not self.source_channel:
            raise ValueError("SOURCE_CHANNEL must be set")
        if not self.target_channels and self.forwarding_enabled:
            raise ValueError("TARGET_CHANNELS must be set when forwarding is enabled")

"""Configuration settings for the bot."""
import os
from pathlib import Path


class Settings:
    """Bot configuration settings."""

    def __init__(self):
        """Initialize settings from environment variables."""
        # Telegram API credentials
        self.api_id = int(os.getenv("API_ID", ""))
        self.api_hash = os.getenv("API_HASH", "")

        # Session name
        self.session_name = os.getenv("SESSION_NAME", "trustat_keyword_forwarder")

        # Channels
        self.source_channel = os.getenv("SOURCE_CHANNEL", "")
        target_channels_str = os.getenv("TARGET_CHANNELS", "")
        self.target_channels = [
            ch.strip() for ch in target_channels_str.split(",") if ch.strip()
        ]

        # Features
        self.forwarding_enabled = os.getenv("FORWARDING_ENABLED", "true").lower() == "true"
        self.case_sensitive = os.getenv("CASE_SENSITIVE", "false").lower() == "true"

        # Files
        self.keywords_file = os.getenv("KEYWORDS_FILE", "../keywords.txt")

        # Validate required settings
        if not self.api_id or not self.api_hash:
            raise ValueError("API_ID and API_HASH must be set")
        if not self.source_channel:
            raise ValueError("SOURCE_CHANNEL must be set")
        if not self.target_channels and self.forwarding_enabled:
            raise ValueError("TARGET_CHANNELS must be set when forwarding is enabled")
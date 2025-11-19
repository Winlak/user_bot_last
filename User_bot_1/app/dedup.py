"""Deduplication store for tracking processed messages."""
import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class DeduplicationStore:
    """Store for tracking processed messages to avoid duplicates."""

    def __init__(self, db_path: str, retention_days: int = 7):
        """
        Initialize deduplication store.

        Args:
            db_path: Path to SQLite database file
            retention_days: Number of days to keep message hashes
        """
        self.db_path = db_path
        self.retention_days = retention_days

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._cleanup_old_entries()

        logger.info("Initialized deduplication store at %s", db_path)

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_hash TEXT PRIMARY KEY,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_processed_at
                ON processed_messages(processed_at)
                """
            )
            conn.commit()

    def _cleanup_old_entries(self):
        """Remove entries older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM processed_messages WHERE processed_at < ?",
                (cutoff_date,),
            )
            deleted_count = cursor.rowcount
            conn.commit()
            if deleted_count > 0:
                logger.info("Cleaned up %s old entries", deleted_count)

    def _hash_message(self, message_text: str) -> str:
        """Create hash of message text."""

        return hashlib.sha256(message_text.encode("utf-8")).hexdigest()

    def is_duplicate(self, message_text: str) -> bool:
        """
        Check if message has been processed before.

        Args:
            message_text: Message text to check

        Returns:
            True if message is a duplicate, False otherwise
        """
        message_hash = self._hash_message(message_text)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_messages WHERE message_hash = ?",
                (message_hash,),
            )
            return cursor.fetchone() is not None

    def add_message(self, message_text: str) -> bool:
        """
        Add message to processed list.

        Args:
            message_text: Message text to add

        Returns:
            True if added successfully, False otherwise
        """
        message_hash = self._hash_message(message_text)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_messages (message_hash) VALUES (?)",
                (message_hash,),
            )
            conn.commit()
            return True

    def get_stats(self) -> dict:
        """Get statistics about stored messages."""

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as total FROM processed_messages"
            )
            total = cursor.fetchone()[0]

            cursor = conn.execute(
                """
                SELECT COUNT(*) as today
                FROM processed_messages
                WHERE DATE(processed_at) = DATE('now')
                """
            )
            today = cursor.fetchone()[0]

            return {
                "total_messages": total,
                "messages_today": today,
                "retention_days": self.retention_days,
            }

    def close(self):
        """Close database connection and cleanup."""

        try:
            self._cleanup_old_entries()
            logger.info("Deduplication store closed")
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Error closing deduplication store: %s", e)

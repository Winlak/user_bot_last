"""Manage channel join requests and pending approvals."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from typing import Optional

from telethon import functions
from telethon.errors.rpcerrorlist import (
    ChannelPrivateError,
    ChannelsTooMuchError,
)

logger = logging.getLogger(__name__)


@dataclass
class PendingSubscription:
    channel_id: Optional[int]
    channel_username: Optional[str]
    message_id: Optional[int]
    link: str
    requested_at: str


@dataclass
class JoinAttempt:
    joined: bool
    pending: bool
    channel_id: Optional[int]
    channel_username: Optional[str]


class SubscriptionTracker:
    """Track channels we requested to join to fetch pending messages."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_subscriptions (
                    channel_id INTEGER PRIMARY KEY,
                    channel_username TEXT,
                    message_id INTEGER,
                    link TEXT,
                    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def add_pending(
        self, channel_id: Optional[int], channel_username: Optional[str], message_id: int, link: str
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_subscriptions
                (channel_id, channel_username, message_id, link)
                VALUES (?, ?, ?, ?)
                """,
                (channel_id, channel_username, message_id, link),
            )
            conn.commit()
            logger.info(
                "Queued join approval for channel %s (message %s)",
                channel_username or channel_id,
                message_id,
            )

    def remove_pending(self, channel_id: Optional[int]) -> None:
        if channel_id is None:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM pending_subscriptions WHERE channel_id = ?", (channel_id,)
            )
            conn.commit()

    def get_oldest_pending(self) -> Optional[PendingSubscription]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT channel_id, channel_username, message_id, link, requested_at
                FROM pending_subscriptions
                ORDER BY requested_at ASC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return None
            return PendingSubscription(*row)

    async def leave_channel(self, client, peer) -> None:
        try:
            await client(functions.channels.LeaveChannelRequest(peer))
            logger.info("Left channel %s to stay under join limits", peer)
        except Exception as exc:  # pragma: no cover - network calls
            logger.error("Failed to leave channel %s: %s", peer, exc)

    async def ensure_membership(
        self, client, peer: str | int, message_id: int, link: str
    ) -> JoinAttempt:
        channel_username = peer if isinstance(peer, str) else None
        channel_id: Optional[int] = None
        try:
            input_entity = await client.get_input_entity(peer)
            channel_id = getattr(input_entity, "channel_id", None)
        except Exception:
            channel_id = None

        try:
            await client(functions.channels.JoinChannelRequest(peer))
            if channel_id:
                self.remove_pending(channel_id)
            return JoinAttempt(True, False, channel_id, channel_username)
        except ChannelsTooMuchError:
            oldest = self.get_oldest_pending()
            if oldest and (oldest.channel_id or oldest.channel_username):
                await self.leave_channel(client, oldest.channel_id or oldest.channel_username)
                self.remove_pending(oldest.channel_id)
                await asyncio.sleep(1)
                try:
                    await client(functions.channels.JoinChannelRequest(peer))
                    if channel_id:
                        self.remove_pending(channel_id)
                    return JoinAttempt(True, False, channel_id, channel_username)
                except Exception as exc:  # pragma: no cover - network calls
                    logger.error("Retry join failed for %s: %s", peer, exc)
            logger.warning(
                "Cannot join %s: reached subscription limit", peer
            )
            return JoinAttempt(False, True, channel_id, channel_username)
        except ChannelPrivateError:
            if channel_id:
                self.add_pending(channel_id, channel_username, message_id, link)
            return JoinAttempt(False, True, channel_id, channel_username)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to join %s: %s", peer, exc)
            return JoinAttempt(False, False, channel_id, channel_username)

    async def leave_after_forward(self, client, message) -> None:
        peer = getattr(message, "peer_id", None)
        if peer is None:
            return
        channel_id = getattr(peer, "channel_id", None)
        username = None
        try:
            entity = await client.get_entity(peer)
            username = getattr(entity, "username", None)
        except Exception:
            entity = peer
        await self.leave_channel(client, entity)
        if channel_id:
            self.remove_pending(channel_id)
        if username:
            logger.info("Finished forwarding; left channel @%s", username)

"""Manage channel join requests and pending approvals."""

from __future__ import annotations

import logging

from telethon import functions
from telethon.errors.rpcerrorlist import (
    ChannelPrivateError,
    ChannelsTooMuchError,
)

from app.dedup import DeduplicationStore

logger = logging.getLogger(__name__)


class SubscriptionTracker:
    """Track channels we requested to join to fetch pending messages."""

    def __init__(self, store: DeduplicationStore, max_joins: int = 450):
        self.store = store
        self.max_joins = max_joins

    async def leave_channel(self, client, peer) -> None:
        try:
            await client(functions.channels.LeaveChannelRequest(peer))
            logger.info("Left channel %s to stay under join limits", peer)
        except Exception as exc:  # pragma: no cover - network calls
            logger.error("Failed to leave channel %s: %s", peer, exc)

    async def leave_after_forward(self, client, channel_link: str) -> None:
        try:
            await self.leave_channel(client, channel_link)
        finally:
            self.store.remove_joined_channel(channel_link)

    async def ensure_membership(
        self, client, channel_link: str, message_link: str
    ) -> str:
        """Attempt to join a channel and return the resulting status string."""

        if self.store.count_joined_channels() >= self.max_joins:
            oldest = self.store.get_oldest_joined_channel()
            if oldest:
                await self.leave_channel(client, oldest["channel_link"])
                self.store.remove_joined_channel(oldest["channel_link"])
            if self.store.count_joined_channels() >= self.max_joins:
                self.store.add_pending_forward(
                    message_link, channel_link, "limit_exceeded", "join limit reached"
                )
                return "limit_exceeded"

        try:
            input_entity = await client.get_input_entity(channel_link)
            channel_id = getattr(input_entity, "channel_id", None)
        except Exception:
            channel_id = None

        try:
            await client(functions.channels.JoinChannelRequest(channel_link))
            self.store.record_joined_channel(channel_link, channel_id)
            self.store.add_pending_forward(
                message_link, channel_link, "waiting_approval"
            )
            return "waiting_approval"
        except ChannelsTooMuchError:
            self.store.add_pending_forward(
                message_link, channel_link, "limit_exceeded", "too many channels"
            )
            logger.warning("Cannot join %s: reached subscription limit", channel_link)
            return "limit_exceeded"
        except ChannelPrivateError as exc:
            self.store.add_pending_forward(
                message_link,
                channel_link,
                "waiting_approval",
                str(exc),
            )
            return "waiting_approval"
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to join %s: %s", channel_link, exc)
            self.store.add_pending_forward(
                message_link, channel_link, "join_failed", str(exc)
            )
            return "join_failed"

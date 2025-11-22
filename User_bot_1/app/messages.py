"""Helpers for working with Telegram messages and links."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from telethon.errors.rpcerrorlist import ChannelInvalidError, ChannelPrivateError
from telethon.tl.types import Message

logger = logging.getLogger(__name__)

TELEGRAM_LINK_RE = re.compile(r"https?://t\.me/(c/)?([\w_]+)/([0-9]+)")


@dataclass
class FetchOutcome:
    """Result of fetching a Telegram message by link."""

    message: Optional[Message]
    leave_after: bool
    pending_peer: str | int | None
    message_id: Optional[int]


def message_identity(message: Message) -> tuple[int | None, int]:
    """Return a hashable identity for a Telethon message."""

    peer = message.peer_id
    if peer is None:
        return (None, message.id)
    channel_id = getattr(peer, "channel_id", None)
    if channel_id is not None:
        return (channel_id, message.id)
    chat_id = getattr(peer, "chat_id", None)
    if chat_id is not None:
        return (chat_id, message.id)
    user_id = getattr(peer, "user_id", None)
    return (user_id, message.id)


def message_identity_string(message: Message) -> str:
    """Return a string identity suitable for deduplication."""

    channel_id, message_id = message_identity(message)
    return f"{channel_id}:{message_id}"


def parse_telegram_link(link: str) -> Optional[Tuple[str | int, int]]:
    """Extract the peer identifier and message id from a Telegram link."""

    match = TELEGRAM_LINK_RE.search(link)
    if not match:
        return None

    is_private = match.group(1) is not None
    peer_part = match.group(2)
    message_id = int(match.group(3))

    if is_private:
        # Private channel links are of the form t.me/c/<channel_id>/<message_id>
        peer = int(f"-100{peer_part}")
    else:
        peer = peer_part

    return peer, message_id


async def fetch_message_by_link(client, link: str):
    """Fetch a Telegram message given its link, handling common channel errors."""

    parsed = parse_telegram_link(link)
    if not parsed:
        logger.warning("Unsupported link format: %s", link)
        return FetchOutcome(None, False, None, None)

    peer, message_id = parsed
    try:
        entity = await client.get_entity(peer)
        message = await client.get_messages(entity, ids=message_id)
        return FetchOutcome(message, False, None, message_id)
    except ChannelPrivateError:
        return FetchOutcome(None, False, peer, message_id)
    except ChannelInvalidError:
        return FetchOutcome(None, False, peer, message_id)
    except Exception as exc:  # pragma: no cover - network calls
        logger.error("Failed to fetch message for %s: %s", link, exc)
        return FetchOutcome(None, False, None, message_id)

"""Main entry point for the Telegram forwarder bot."""
import asyncio
import logging
import re
import signal
import sys

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from app.config import Settings
from app.dedup import DeduplicationStore
from app.queue import ForwardingQueue
from app.subscriptions import SubscriptionTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals."""

    logger.info("Received signal %s, initiating graceful shutdown...", signum)
    shutdown_event.set()


def extract_first_link(text: str) -> str | None:
    """Return the first Telegram link from the given text."""

    if not text:
        return None
    match = re.search(r"https?://t\.me/[^\s]+", text)
    return match.group(0) if match else None


async def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    settings = Settings()
    logging.getLogger().setLevel(settings.log_level.upper())

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("=" * 60)
    logger.info("Bot Configuration:")
    logger.info("  Source Channel: %s", settings.source_channel)
    logger.info("  Target Channels: %s", settings.target_channels)
    logger.info("  Forwarding Enabled: %s", settings.forwarding_enabled)
    logger.info("  Data Directory: %s", settings.data_dir)
    logger.info("  DB Path: %s", settings.db_path)
    logger.info("=" * 60)

    dedup_store = None
    try:
        dedup_store = DeduplicationStore(str(settings.db_path))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to initialise deduplication store: %s", exc)

    subscription_tracker = SubscriptionTracker(str(settings.db_path))

    queue = ForwardingQueue(
        dedup_store=dedup_store,
        subscription_tracker=subscription_tracker,
        delay_seconds=settings.forwarding_delay_seconds,
        max_messages_per_second=settings.forwarding_max_messages_per_second,
        maxsize=settings.forwarding_queue_maxsize,
    )

    client = TelegramClient(
        StringSession(settings.string_session), settings.api_id, settings.api_hash
    )

    @client.on(events.NewMessage(chats=settings.source_channel))
    async def handler(event):
        if shutdown_event.is_set():
            return

        message_text = event.message.message or ""
        link = extract_first_link(message_text)

        if not link:
            logger.debug("No link found in message %s", event.message.id)
            return

        if dedup_store and dedup_store.is_duplicate(link):
            logger.info("Link %s already processed, skipping", link)
            return

        if settings.forwarding_enabled:
            await queue.add_link(client, link, settings.target_channels)
        else:
            logger.info("Dry run: would forward %s", link)

    try:
        await client.start()
        me = await client.get_me()
        logger.info("✅ Successfully logged in as: %s (@%s)", me.first_name, me.username)
        logger.info("Listening to messages from %s...", settings.source_channel)
        await shutdown_event.wait()

    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Error in main loop: %s", exc)
    finally:
        logger.info("Shutting down...")
        await queue.stop()
        if dedup_store:
            dedup_store.close()
        await client.disconnect()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

"""Main entry point for the Telegram keyword forwarder bot."""
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from app.config import Settings
from app.dedup import DeduplicationStore
from app.forwarder import KeywordForwarder
from app.queue import ForwardingQueue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_event = asyncio.Event()


def load_keywords(file_path: str) -> list[str]:
    """Load keywords from file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            keywords = [
                line.strip() for line in f if line.strip() and not line.startswith("#")
            ]
        logger.info(f"Loaded {len(keywords)} keywords: {keywords}")
        return keywords
    except FileNotFoundError:
        logger.error(f"Keywords file not found: {file_path}")
        return []


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def main():
    """Main function."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Load settings
    settings = Settings()

    # Get data directory
    data_dir = Path(os.getenv("DATA_DIR", "."))
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("Bot Configuration:")
    logger.info(f"  Source Channel: {settings.source_channel}")
    logger.info(f"  Target Channels: {settings.target_channels}")
    logger.info(f"  Forwarding Enabled: {settings.forwarding_enabled}")
    logger.info(f"  Keywords File: {settings.keywords_file}")
    logger.info(f"  Case Sensitive: {settings.case_sensitive}")
    logger.info(f"  Data Directory: {data_dir}")
    logger.info("=" * 60)

    # Initialize deduplication store
    db_path = data_dir / "db.sqlite3"
    try:
        dedup_store = DeduplicationStore(str(db_path))
    except Exception as e:
        logger.error(f"Failed to initialise deduplication store: {e}")
        dedup_store = None

    # Load keywords
    keywords = load_keywords(settings.keywords_file)
    if not keywords:
        logger.error("No keywords loaded. Exiting.")
        return

    # Initialize forwarder
    forwarder = KeywordForwarder(
        keywords=keywords,
        case_sensitive=settings.case_sensitive,
        forwarding_enabled=settings.forwarding_enabled,
    )

    if settings.forwarding_enabled:
        logger.info(f"Forwarding is ENABLED to targets: {settings.target_channels}")
    else:
        logger.info("Forwarding is DISABLED (dry-run mode)")

    # Initialize forwarding queue
    queue = ForwardingQueue()

    # Determine session path
    session_file = data_dir / f"{settings.session_name}.session"

    # Check if we have a string session in env
    string_session = os.getenv("STRING_SESSION", "")

    if string_session:
        logger.info("Using STRING_SESSION from environment")
        session = StringSession(string_session)
    elif session_file.exists():
        logger.info(f"Using session file: {session_file}")
        session = str(session_file.with_suffix(""))
    else:
        logger.info(f"Creating new session: {session_file}")
        session = str(session_file.with_suffix(""))

    # Create Telegram client
    client = TelegramClient(session, settings.api_id, settings.api_hash)

    @client.on(events.NewMessage(chats=settings.source_channel))
    async def handler(event):
        """Handle new messages from source channel."""
        if shutdown_event.is_set():
            return

        message_text = event.message.message or ""
        message_id = event.message.id

        # Check for keywords
        if not forwarder.contains_keywords(message_text):
            return

        logger.info(
            f"Message {message_id} matches keywords: {message_text[:100]}..."
        )

        # Check for duplicates
        if dedup_store and dedup_store.is_duplicate(message_text):
            logger.info(f"Message {message_id} is a duplicate, skipping")
            return

        # Add to dedup store
        if dedup_store:
            dedup_store.add_message(message_text)

        # Queue for forwarding
        if settings.forwarding_enabled:
            for target in settings.target_channels:
                await queue.add_to_queue(client, event.message, target)

    try:
        # Start the client
        await client.start()

        # Get and display current user info
        me = await client.get_me()
        logger.info(f"✅ Successfully logged in as: {me.first_name} (@{me.username})")

        # Save string session for future use
        if not string_session:
            new_string_session = client.session.save()
            logger.info("=" * 60)
            logger.info("STRING SESSION (save this to .env):")
            logger.info(new_string_session)
            logger.info("=" * 60)

        logger.info(f"Listening to messages from {settings.source_channel}...")

        # Keep running until shutdown signal
        await shutdown_event.wait()

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.exception(f"Error in main loop: {e}")
    finally:
        logger.info("Shutting down...")
        await queue.stop()
        if dedup_store:
            dedup_store.close()
        await client.disconnect()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
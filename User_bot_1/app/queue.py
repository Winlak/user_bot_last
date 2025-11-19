"""Message forwarding queue with rate limiting."""
import asyncio
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ForwardingQueue:
    """Queue for forwarding messages with rate limiting."""

    def __init__(self, rate_limit_seconds: float = 1.0):
        """
        Initialize forwarding queue.

        Args:
            rate_limit_seconds: Minimum seconds between forwards
        """
        self.rate_limit = rate_limit_seconds
        self.queue = asyncio.Queue()
        self.running = False
        self.worker_task = None
        self.last_forward_time = None

        logger.info(f"Initialized forwarding queue with {rate_limit_seconds}s rate limit")

    async def add_to_queue(self, client: Any, message: Any, target: str):
        """
        Add message to forwarding queue.

        Args:
            client: Telegram client
            message: Message to forward
            target: Target channel
        """
        await self.queue.put((client, message, target))
        logger.info(f"Added message {message.id} to queue for {target}")

        # Start worker if not running
        if not self.running:
            await self.start()

    async def start(self):
        """Start the queue worker."""
        if self.running:
            return

        self.running = True
        self.worker_task = asyncio.create_task(self._worker())
        logger.info("Forwarding queue worker started")

    async def stop(self):
        """Stop the queue worker."""
        self.running = False

        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

        logger.info("Forwarding queue worker stopped")

    async def _worker(self):
        """Worker that processes the forwarding queue."""
        while self.running:
            try:
                # Get next item from queue with timeout
                try:
                    client, message, target = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # Apply rate limiting
                if self.last_forward_time:
                    elapsed = (datetime.now() - self.last_forward_time).total_seconds()
                    if elapsed < self.rate_limit:
                        await asyncio.sleep(self.rate_limit - elapsed)

                # Forward the message
                try:
                    await client.forward_messages(target, message)
                    logger.info(f"✅ Forwarded message {message.id} to {target}")
                    self.last_forward_time = datetime.now()
                except Exception as e:
                    logger.error(f"❌ Failed to forward message {message.id} to {target}: {e}")

                # Mark task as done
                self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in forwarding worker: {e}")
                await asyncio.sleep(1.0)

    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self.queue.qsize()
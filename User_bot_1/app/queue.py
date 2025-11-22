"""Message forwarding queue with rate limiting and deduplication."""
import asyncio
import logging
from datetime import datetime
from typing import Iterable, Optional

from app.messages import fetch_message_by_link, message_identity_string

logger = logging.getLogger(__name__)


class ForwardingQueue:
    """Queue for forwarding messages with rate limiting."""

    def __init__(
        self,
        dedup_store,
        subscription_tracker,
        delay_seconds: float = 0.0,
        max_messages_per_second: Optional[float] = None,
        maxsize: Optional[int] = None,
        pending_retry_seconds: float = 60.0,
    ):
        self.dedup_store = dedup_store
        self.subscription_tracker = subscription_tracker
        self.delay_seconds = max(delay_seconds, 0.0)
        self.min_interval = (
            1.0 / max_messages_per_second if max_messages_per_second else 0.0
        )
        self.queue: asyncio.Queue = (
            asyncio.Queue(maxsize=maxsize) if maxsize else asyncio.Queue()
        )
        self.running = False
        self.worker_task: asyncio.Task | None = None
        self.last_send_time: Optional[datetime] = None
        self.pending_retry_seconds = max(pending_retry_seconds, 5.0)

        logger.info(
            "Initialized forwarding queue: delay=%ss, max_mps=%s, maxsize=%s",
            self.delay_seconds,
            max_messages_per_second,
            maxsize,
        )

    async def add_link(self, client, link: str, targets: Iterable[str]):
        """Add a Telegram link to the forwarding queue."""

        await self.queue.put((client, link, list(targets)))
        logger.info("Queued link %s", link)

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

    async def _respect_rate_limits(self):
        """Sleep to honour the configured rate limits."""

        now = datetime.now()
        if self.last_send_time:
            elapsed = (now - self.last_send_time).total_seconds()
            wait_for = max(0.0, self.min_interval - elapsed)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        self.last_send_time = datetime.now()

    async def _requeue_later(self, client, link: str, targets):
        await asyncio.sleep(self.pending_retry_seconds)
        await self.add_link(client, link, targets)

    async def _worker(self):
        """Worker that processes the forwarding queue."""

        while self.running:
            try:
                client, link, targets = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                outcome = await fetch_message_by_link(client, link)
                if outcome.message is None:
                    if outcome.pending_peer is not None:
                        join_attempt = await self.subscription_tracker.ensure_membership(
                            client, outcome.pending_peer, outcome.message_id or 0, link
                        )
                        if join_attempt.joined:
                            # retry fetch now that we've joined
                            outcome = await fetch_message_by_link(client, link)
                            if outcome.message:
                                outcome.leave_after = True
                        elif join_attempt.pending:
                            logger.info(
                                "Waiting for approval to access %s; will retry", join_attempt.channel_username
                                or join_attempt.channel_id
                            )
                            asyncio.create_task(
                                self._requeue_later(client, link, targets)
                            )
                            continue

                    if outcome.message is None:
                        logger.warning("Message not available for link %s", link)
                        continue

                message = outcome.message
                identity = message_identity_string(message)
                if self.dedup_store and self.dedup_store.is_duplicate(identity):
                    logger.info("Duplicate message %s, skipping", identity)
                    continue

                forward_success = False
                for target in targets:
                    try:
                        await self._respect_rate_limits()
                        await client.forward_messages(target, message)
                        logger.info("Forwarded %s to %s", identity, target)
                        forward_success = True
                    except Exception as exc:  # pragma: no cover - network errors
                        logger.error(
                            "Failed to forward %s to %s: %s", identity, target, exc
                        )

                if forward_success and self.dedup_store:
                    self.dedup_store.add_message(identity)
                    self.dedup_store.add_message(link)

                if forward_success and outcome.leave_after:
                    await self.subscription_tracker.leave_after_forward(client, message)

            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Error in forwarding worker: %s", exc)
            finally:
                self.queue.task_done()

    def get_queue_size(self) -> int:
        """Get current queue size."""

        return self.queue.qsize()

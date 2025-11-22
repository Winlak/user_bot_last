"""Message forwarding queue with rate limiting, retries, and deduplication."""
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

        logger.info(
            "Initialized forwarding queue: delay=%ss, max_mps=%s, maxsize=%s",
            self.delay_seconds,
            max_messages_per_second,
            maxsize,
        )

    async def add_link(
        self,
        client,
        message_link: str,
        targets: Iterable[str],
        channel_link: str | None = None,
    ):
        """Add a Telegram link to the forwarding queue."""

        await self.queue.put((client, message_link, list(targets), channel_link))
        logger.info("Queued link %s", message_link)

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

    async def _forward_message(self, client, message, targets, message_link: str):
        identity = message_identity_string(message)
        if self.dedup_store and self.dedup_store.is_duplicate(identity):
            logger.info("Duplicate message %s, skipping", identity)
            return

        forward_success = False
        for target in targets:
            try:
                await self._respect_rate_limits()
                await client.forward_messages(target, message)
                logger.info("Forwarded %s to %s", identity, target)
                forward_success = True
            except Exception as exc:  # pragma: no cover - network errors
                logger.error("Failed to forward %s to %s: %s", identity, target, exc)

        if forward_success and self.dedup_store:
            self.dedup_store.add_message(identity)
            self.dedup_store.add_message(message_link)

    async def _worker(self):
        """Worker that processes the forwarding queue."""

        while self.running:
            try:
                client, message_link, targets, channel_link = await asyncio.wait_for(
                    self.queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                outcome = await fetch_message_by_link(client, message_link)
                if outcome.message is None:
                    if outcome.needs_join and channel_link:
                        status = await self.subscription_tracker.ensure_membership(
                            client, channel_link, message_link
                        )
                        if status == "waiting_approval":
                            logger.info(
                                "Waiting for channel access to fetch %s; will retry later",
                                message_link,
                            )
                        elif status == "limit_exceeded":
                            logger.warning(
                                "Join limit reached; stored pending task for %s", message_link
                            )
                        else:
                            logger.warning(
                                "Join attempt for %s ended with status %s",
                                message_link,
                                status,
                            )
                    else:
                        logger.warning("Message not available for link %s", message_link)
                    continue

                await self._forward_message(client, outcome.message, targets, message_link)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Error in forwarding worker: %s", exc)
            finally:
                self.queue.task_done()

    def get_queue_size(self) -> int:
        """Get current queue size."""

        return self.queue.qsize()


class PendingForwardWorker:
    """Worker that retries pending forwards after channel approvals."""

    def __init__(
        self,
        client,
        targets: Iterable[str],
        dedup_store,
        subscription_tracker,
        queue: ForwardingQueue,
        retry_interval_seconds: float = 300.0,
        max_attempts: int = 25,
    ):
        self.client = client
        self.targets = list(targets)
        self.dedup_store = dedup_store
        self.subscription_tracker = subscription_tracker
        self.queue = queue
        self.retry_interval_seconds = max(60.0, retry_interval_seconds)
        self.max_attempts = max_attempts
        self.running = False
        self.task: asyncio.Task | None = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._worker())
        logger.info("Pending forward worker started")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Pending forward worker stopped")

    async def _worker(self):
        while self.running:
            try:
                await asyncio.sleep(self.retry_interval_seconds)
                pending_rows = self.dedup_store.get_pending_forwards_for_retry(
                    limit=25, max_attempts=self.max_attempts
                )
                if not pending_rows:
                    continue

                for row in pending_rows:
                    try:
                        outcome = await fetch_message_by_link(
                            self.client, row["message_link"]
                        )
                        attempts = int(row["attempts"]) + 1
                        now = datetime.now()
                        if outcome.message:
                            await self.queue._forward_message(
                                self.client, outcome.message, self.targets, row["message_link"]
                            )
                            await self.subscription_tracker.leave_after_forward(
                                self.client, row["channel_link"]
                            )
                            self.dedup_store.update_pending_forward_status(
                                row["id"], "done", attempts, now
                            )
                            continue

                        if outcome.needs_join:
                            status = "waiting_approval"
                        else:
                            status = "join_failed"
                        if attempts >= self.max_attempts and status == "waiting_approval":
                            status = "join_failed"

                        self.dedup_store.update_pending_forward_status(
                            row["id"], status, attempts, now, str(outcome.access_error)
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.error("Error retrying pending forward %s: %s", row["id"], exc)
                        try:
                            self.dedup_store.update_pending_forward_status(
                                row["id"], "join_failed", row["attempts"] + 1, datetime.now(), str(exc)
                            )
                        except Exception:
                            logger.debug("Failed to update pending status for %s", row["id"])
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Error in pending forward worker: %s", exc)

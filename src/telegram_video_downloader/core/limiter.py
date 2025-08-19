import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from telegram_video_downloader.core.config import settings


class ConcurrencyLimiter:
    """
    Manages concurrency limits for downloads, both globally and per-chat.
    """

    def __init__(self, global_limit: int, per_chat_limit: int):
        self.global_semaphore = asyncio.Semaphore(global_limit)
        self.per_chat_limit = per_chat_limit
        # A dictionary to hold semaphores for each chat
        self.chat_semaphores: Dict[int, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(self.per_chat_limit)
        )

    @asynccontextmanager
    async def limit(self, chat_id: int) -> AsyncGenerator[None, None]:
        """
        An async context manager to enforce concurrency limits.
        """
        chat_semaphore = self.chat_semaphores[chat_id]

        await self.global_semaphore.acquire()
        await chat_semaphore.acquire()
        try:
            yield
        finally:
            chat_semaphore.release()
            self.global_semaphore.release()

            # Optional: Clean up chat semaphores if they are no longer in use
            # to prevent the dictionary from growing indefinitely.
            if chat_semaphore._value == self.per_chat_limit:
                del self.chat_semaphores[chat_id]


# A single instance to be used throughout the application
limiter = ConcurrencyLimiter(
    global_limit=settings.GLOBAL_CONCURRENCY,
    per_chat_limit=settings.PER_CHAT_CONCURRENCY,
)

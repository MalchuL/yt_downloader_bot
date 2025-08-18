import asyncio
import pytest

from src.core import config
from src.core.limiter import ConcurrencyLimiter


@pytest.mark.asyncio
async def test_global_concurrency_limit(monkeypatch):
    """
    Tests that the global semaphore correctly limits concurrent access.
    """
    # Use a small limit for testing
    monkeypatch.setattr(config.settings, "GLOBAL_CONCURRENCY", 2)
    monkeypatch.setattr(config.settings, "PER_CHAT_CONCURRENCY", 5) # Set high to not interfere

    limiter = ConcurrencyLimiter(
        global_limit=config.settings.GLOBAL_CONCURRENCY,
        per_chat_limit=config.settings.PER_CHAT_CONCURRENCY
    )

    concurrent_tasks = 0
    max_concurrent_tasks = 0
    lock = asyncio.Lock()

    async def limited_task(chat_id):
        nonlocal concurrent_tasks, max_concurrent_tasks
        async with limiter.limit(chat_id):
            async with lock:
                concurrent_tasks += 1
                max_concurrent_tasks = max(max_concurrent_tasks, concurrent_tasks)
            await asyncio.sleep(0.01) # Simulate work
            async with lock:
                concurrent_tasks -= 1

    tasks = [asyncio.create_task(limited_task(chat_id=i)) for i in range(5)]
    await asyncio.gather(*tasks)

    assert max_concurrent_tasks == 2


@pytest.mark.asyncio
async def test_per_chat_concurrency_limit(monkeypatch):
    """
    Tests that the per-chat semaphore correctly limits concurrent access for a single chat.
    """
    monkeypatch.setattr(config.settings, "GLOBAL_CONCURRENCY", 5) # Set high to not interfere
    monkeypatch.setattr(config.settings, "PER_CHAT_CONCURRENCY", 2)

    limiter = ConcurrencyLimiter(
        global_limit=config.settings.GLOBAL_CONCURRENCY,
        per_chat_limit=config.settings.PER_CHAT_CONCURRENCY
    )

    concurrent_tasks = 0
    max_concurrent_tasks = 0
    lock = asyncio.Lock()

    test_chat_id = 123

    async def limited_task():
        nonlocal concurrent_tasks, max_concurrent_tasks
        async with limiter.limit(test_chat_id):
            async with lock:
                concurrent_tasks += 1
                max_concurrent_tasks = max(max_concurrent_tasks, concurrent_tasks)
            await asyncio.sleep(0.01)
            async with lock:
                concurrent_tasks -= 1

    tasks = [asyncio.create_task(limited_task()) for _ in range(5)]
    await asyncio.gather(*tasks)

    assert max_concurrent_tasks == 2


@pytest.mark.asyncio
async def test_limiter_cleanup(monkeypatch):
    """
    Tests that the limiter cleans up chat semaphores after they are no longer in use.
    """
    monkeypatch.setattr(config.settings, "GLOBAL_CONCURRENCY", 1)
    monkeypatch.setattr(config.settings, "PER_CHAT_CONCURRENCY", 1)

    limiter = ConcurrencyLimiter(
        global_limit=config.settings.GLOBAL_CONCURRENCY,
        per_chat_limit=config.settings.PER_CHAT_CONCURRENCY
    )

    test_chat_id = 123
    assert test_chat_id not in limiter.chat_semaphores

    async with limiter.limit(test_chat_id):
        assert test_chat_id in limiter.chat_semaphores

    # After the context manager exits, the semaphore should be released and cleaned up
    assert test_chat_id not in limiter.chat_semaphores

import asyncio
import logging

from aiogram import Bot, Dispatcher

from src.bot.handlers import router as bot_router
from src.bot.search_handler import router as search_router
from src.bot.middleware import RequestIdMiddleware
from src.core.config import settings
from src.core.limiter import limiter
from src.core.provider_factory import get_provider
from src.core.request_context import REQUEST_ID_VAR
from src.observers.youtube_search import YouTubeSearch


class RequestIdFilter(logging.Filter):
    """A logging filter to inject the request_id from a context variable."""

    def filter(self, record):
        record.request_id = REQUEST_ID_VAR.get()
        return True


async def main():
    """
    The main entry point for the bot application.
    """
    # Set up logging with request_id
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s",
    )
    # Add our custom filter to all root handlers
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())

    logger = logging.getLogger(__name__)

    # Instantiate the download provider
    try:
        provider = get_provider()
        logger.info("Using download provider: %s", settings.DOWNLOADER_PROVIDER)
    except (ValueError, RuntimeError) as e:
        logger.error("Failed to initialize download provider: %s", e)
        return

    # Initialize bot and dispatcher
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Register middleware for all updates
    dp.update.middleware(RequestIdMiddleware())

    # Instantiate the observer
    observer = YouTubeSearch()

    # Pass the provider, limiter and observer instances to the handlers
    dp["provider"] = provider
    dp["limiter"] = limiter
    dp["observer"] = observer

    # Include the routers
    dp.include_router(bot_router)
    dp.include_router(search_router)

    # Start polling
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
    except Exception as e:
        logging.critical("Bot failed to start: %s", e, exc_info=True)

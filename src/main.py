import asyncio
import logging

from aiogram import Bot, Dispatcher

from src.bot.handlers import router as bot_router
from src.core.config import settings
from src.core.provider_factory import get_provider


async def main():
    """
    The main entry point for the bot application.
    """
    # Set up logging
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Instantiate the download provider
    try:
        provider = get_provider()
        logger.info(f"Using download provider: {settings.DOWNLOADER_PROVIDER}")
    except (ValueError, RuntimeError) as e:
        logger.error(f"Failed to initialize download provider: {e}")
        return

    # Initialize bot and dispatcher
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # Pass the provider instance to the handlers
    dp["provider"] = provider

    # Include the main router
    dp.include_router(bot_router)

    # Start polling
    logger.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
    except Exception as e:
        logging.critical(f"Bot failed to start: {e}", exc_info=True)

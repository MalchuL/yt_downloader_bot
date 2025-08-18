import asyncio
import logging
import os
import re
import time
from typing import List

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards import QualityCallback, create_quality_keyboard
from src.core.config import settings
from src.core.limiter import ConcurrencyLimiter
from src.providers.interface import DownloadProvider, QualityOption

logger = logging.getLogger(__name__)
router = Router()

URL_PATTERN = re.compile(r"https?:\/\/[^\s]+")
MAX_FILESIZE_BYTES = settings.MAX_TELEGRAM_FILESIZE_MB * 1024 * 1024


class DownloadState(StatesGroup):
    choosing_quality = State()
    downloading = State()


@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Welcome! Send me a video link (e.g., from YouTube) and I'll download it for you."
    )


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "Supported sites depend on the configuration.\n"
        "Just send a link. I'll ask for the quality you want.\n"
        f"If you don't choose within {settings.SELECTION_TIMEOUT_SEC} seconds, "
        "I'll automatically start downloading the best available quality."
    )


@router.message(Command("health"))
async def health_handler(message: Message, provider: DownloadProvider):
    """
    Checks the health of the download provider.
    """
    if provider.healthcheck():
        await message.answer(f"Provider '{provider.name}' is healthy.")
    else:
        await message.answer(f"Provider '{provider.name}' is unhealthy.")


from src.bot.search_handler import handle_search
from src.observers.interface import Observer


@router.message(F.text)
async def message_handler(
    message: Message,
    state: FSMContext,
    provider: DownloadProvider,
    bot: Bot,
    limiter: ConcurrencyLimiter,
    observer: Observer,
):
    if limiter.chat_semaphores[message.chat.id].locked():
        await message.reply(
            "You already have an active download in this chat. Please wait for it to complete."
        )
        return

    match = URL_PATTERN.search(message.text)
    if not match:
        await handle_search(message, bot, observer, state)
        return

    url = match.group(0)
    logger.info("Received URL: %s for chat: %d", url, message.chat.id)

    if not provider.supports(url):
        await message.reply("Sorry, this video provider is not supported.")
        return

    try:
        status_msg = await message.reply("Got it. Fetching available qualities...")
        qualities = list(provider.list_qualities(url))
        if not qualities:
            await status_msg.edit_text(
                "Sorry, no downloadable qualities found for this video."
            )
            return

        keyboard = create_quality_keyboard(qualities)
        await status_msg.edit_text(
            "Please choose a quality. The download will start automatically with the "
            f"default choice in {settings.SELECTION_TIMEOUT_SEC} seconds.",
            reply_markup=keyboard,
        )

        await state.set_state(DownloadState.choosing_quality)
        await state.set_data(
            {
                "url": url,
                "qualities": [q.__dict__ for q in qualities],
                "status_message_id": status_msg.id,
            }
        )

        asyncio.create_task(
            selection_timeout(
                message.chat.id, status_msg.id, state, provider, bot, limiter
            )
        )

    except Exception as e:
        logger.error(
            "Error processing URL %s for chat %d: %s",
            url,
            message.chat.id,
            e,
            exc_info=True,
        )
        await message.reply(f"An error occurred: {e}")


@router.callback_query(QualityCallback.filter(), DownloadState.choosing_quality)
async def quality_callback_handler(
    query: CallbackQuery,
    callback_data: QualityCallback,
    state: FSMContext,
    provider: DownloadProvider,
    bot: Bot,
    limiter: ConcurrencyLimiter,
):
    await state.set_state(DownloadState.downloading)

    data = await state.get_data()
    url = data.get("url")
    qualities_data = data.get("qualities", [])
    qualities = [QualityOption(**q) for q in qualities_data]

    selected_index = next(
        (i for i, q in enumerate(qualities) if q.itag == callback_data.itag), -1
    )

    if not url or selected_index == -1:
        await query.message.edit_text(
            "Sorry, something went wrong. Please send the link again."
        )
        await state.clear()
        return

    await query.answer("Selection received!")

    qualities_to_try = qualities[selected_index:]

    await download_and_send_video(
        bot=bot,
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        url=url,
        qualities_to_try=qualities_to_try,
        provider=provider,
        state=state,
        limiter=limiter,
    )


async def selection_timeout(
    chat_id: int,
    message_id: int,
    state: FSMContext,
    provider: DownloadProvider,
    bot: Bot,
    limiter: ConcurrencyLimiter,
):
    await asyncio.sleep(settings.SELECTION_TIMEOUT_SEC)

    if await state.get_state() != DownloadState.choosing_quality:
        return

    logger.info("Selection timed out for chat %d. Proceeding with default.", chat_id)
    await state.set_state(DownloadState.downloading)

    data = await state.get_data()
    url = data.get("url")
    qualities_data = data.get("qualities", [])
    qualities = [QualityOption(**q) for q in qualities_data]

    if not url or not qualities:
        logger.error("Could not find URL or qualities on timeout for chat %d.", chat_id)
        try:
            await bot.edit_message_text(
                "Sorry, something went wrong on timeout. Please try again.",
                chat_id,
                message_id,
            )
        except TelegramBadRequest:
            pass
        return

    await download_and_send_video(
        bot, chat_id, message_id, url, qualities, provider, state, limiter
    )


async def download_and_send_video(
    bot: Bot,
    chat_id: int,
    message_id: int,
    url: str,
    qualities_to_try: List[QualityOption],
    provider: DownloadProvider,
    state: FSMContext,
    limiter: ConcurrencyLimiter,
):
    last_update_time = 0
    downloaded_file_path = None

    async def progress_callback(progress: float, downloaded_bytes: int):
        nonlocal last_update_time
        now = time.time()
        if now - last_update_time < 3:
            return

        try:
            await bot.edit_message_text(
                f"Downloading: {progress:.0%}", chat_id=chat_id, message_id=message_id
            )
            last_update_time = now
        except TelegramBadRequest:
            logger.warning("Failed to update progress message for chat %d.", chat_id)

    async with limiter.limit(chat_id):
        try:
            try:
                await bot.edit_message_text(
                    "Your download is starting...", chat_id=chat_id, message_id=message_id
                )
            except TelegramBadRequest:
                pass  # Race condition with timeout/callback, ignore.

            metadata = provider.get_metadata(url)
            for i, quality in enumerate(qualities_to_try):
                await bot.edit_message_text(
                    f"Starting download for '{quality.label}' quality...",
                    chat_id=chat_id,
                    message_id=message_id,
                )

                downloaded_file_path = await asyncio.to_thread(
                    provider.download,
                    url=url,
                    quality=quality,
                    on_progress=progress_callback,
                )

                file_size = os.path.getsize(downloaded_file_path)
                if file_size > MAX_FILESIZE_BYTES:
                    os.remove(downloaded_file_path)
                    downloaded_file_path = None

                    is_last_quality = i == len(qualities_to_try) - 1
                    if settings.ALLOW_QUALITY_FALLBACK and not is_last_quality:
                        await bot.edit_message_text(
                            f"'{quality.label}' quality is too large ({file_size / 1024**2:.1f}MB). Trying next best...",
                            chat_id=chat_id,
                            message_id=message_id,
                        )
                        await asyncio.sleep(2)
                        continue
                    else:
                        raise IOError(
                            f"'{quality.label}' quality is too large ({file_size / 1024**2:.1f}MB) and no other qualities are available."
                        )

                await bot.edit_message_text(
                    "Download complete. Uploading to Telegram...", chat_id, message_id
                )
                caption = f"{metadata.title}\nQuality: {quality.label}, Provider: {provider.name}"
                with open(downloaded_file_path, "rb") as video_file:
                    await bot.send_video(chat_id, video_file, caption=caption)

                await bot.delete_message(chat_id, message_id)
                return

            await bot.edit_message_text(
                "Could not download the video. All available qualities failed or were too large.",
                chat_id=chat_id,
                message_id=message_id,
            )

        except Exception as e:
            logger.error(
                "Failed during download/upload for chat %d: %s",
                chat_id,
                e,
                exc_info=True,
            )
            try:
                await bot.edit_message_text(
                    f"An error occurred: {e}", chat_id, message_id
                )
            except TelegramBadRequest:
                pass
        finally:
            if downloaded_file_path and os.path.exists(downloaded_file_path):
                os.remove(downloaded_file_path)
                logger.info(
                    "Cleaned up temporary file %s for chat %d",
                    downloaded_file_path,
                    chat_id,
                )
            await state.clear()

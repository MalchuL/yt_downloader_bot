import logging
import uuid
from typing import cast
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InaccessibleMessage
from telegram_video_downloader.searcher.searcher import Searcher, SearchResultItem
from telegram_video_downloader.bot.keyboards import (
    create_video_keyboard,
    create_pagination_keyboard,
    SearchCallback,
)
from telegram_video_downloader.core.config import settings

logger = logging.getLogger(__name__)
router = Router()


class SearchState(StatesGroup):
    searching = State()
    results = State()


def format_single_search_result(item: SearchResultItem, is_expanded: bool) -> str:
    text = f"**{item.video_title}**\n\n"
    text += f"📺 [{item.channel_name}]({item.channel_url}) | {item.channel_subscribers}\n"
    text += f"👀 {item.video_views} | 📅 {item.publication_date} | ⏱️ {item.duration}\n\n"
    if is_expanded:
        text += f"📝 {item.video_description}"
    else:
        text += f"📝 {item.video_description[:100]}..."
    return text


async def handle_search(message: Message, bot: Bot, searcher: Searcher, state: FSMContext) -> None:
    query = message.text
    if not query:
        await message.answer("Please provide a search query.")
        return
    await state.set_state(SearchState.searching)
    await state.set_data({"query": query})

    status_msg = await message.reply(f"Searching for: `{query}`...")

    results = await searcher.search(query, page=1)
    if not results:
        await status_msg.edit_text("No results found.")
        await state.clear()
        return

    try:
        await status_msg.delete()
    except Exception as e:
        logger.warning(f"Failed to delete status message: {e}")

    total_results = len(results)
    total_pages = (total_results + settings.YOUTUBE_SEARCH_RESULTS_LIMIT - 1) // settings.YOUTUBE_SEARCH_RESULTS_LIMIT

    # Create URL mapping
    url_mapping = {}
    for result in results:
        url_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for shorter IDs
        url_mapping[url_id] = result.video_url

    await state.set_state(SearchState.results)
    await state.update_data({
        "results": [r.__dict__ for r in results],
        "page": 1,
        "total_pages": total_pages,
        "url_mapping": url_mapping
    })

    chat_id = message.chat.id
    for i in range(0, len(results), settings.YOUTUBE_SEARCH_RESULTS_LIMIT):
        page_results = results[i:i+settings.YOUTUBE_SEARCH_RESULTS_LIMIT]
        for item in page_results:
            url_id = next(k for k, v in url_mapping.items() if v == item.video_url)
            caption = format_single_search_result(item, is_expanded=False)
            keyboard = create_video_keyboard(url_id, 1, is_expanded=False)
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=item.thumbnail,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.error(f"Failed to send search result: {e}")
                continue

    if total_pages > 1:
        try:
            pagination_keyboard = create_pagination_keyboard(1, total_pages)
            await bot.send_message(
                chat_id=chat_id,
                text="Use the buttons below to navigate pages:",
                reply_markup=pagination_keyboard
            )
        except Exception as e:
            logger.error(f"Failed to send pagination keyboard: {e}")


@router.callback_query(SearchCallback.filter(F.action.in_(["prev", "next"])))
async def pagination_callback_handler(
    query: CallbackQuery, callback_data: SearchCallback, state: FSMContext, searcher: Searcher, bot: Bot
) -> None:
    await query.answer()
    data = await state.get_data()
    search_query = data.get("query")
    if not search_query:
        await query.answer("Search query not found. Please try searching again.")
        return

    page = callback_data.page
    results = await searcher.search(search_query, page=page)
    if not results:
        await query.answer("No results found for this page.")
        return

    total_pages = data.get("total_pages", 1)

    # Create URL mapping for new results
    url_mapping = {}
    for result in results:
        url_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for shorter IDs
        url_mapping[url_id] = result.video_url

    await state.update_data({
        "page": page,
        "results": [r.__dict__ for r in results],
        "url_mapping": url_mapping
    })

    # Clear previous results before sending new ones
    try:
        if query.message and isinstance(query.message, Message):
            await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message: {e}")

    if not query.message or not isinstance(query.message, Message):
        await query.answer("Message not found. Please try searching again.")
        return

    chat_id = query.message.chat.id
    for item in results:
        url_id = next(k for k, v in url_mapping.items() if v == item.video_url)
        caption = format_single_search_result(item, is_expanded=False)
        keyboard = create_video_keyboard(url_id, page, is_expanded=False)
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=item.thumbnail,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send search result: {e}")
            continue

    if total_pages > 1:
        try:
            pagination_keyboard = create_pagination_keyboard(page, total_pages)
            await bot.send_message(
                chat_id=chat_id,
                text="Use the buttons below to navigate pages:",
                reply_markup=pagination_keyboard
            )
        except Exception as e:
            logger.error(f"Failed to send pagination keyboard: {e}")


@router.callback_query(SearchCallback.filter(F.action.in_(["expand", "collapse"])))
async def expand_collapse_callback_handler(
    query: CallbackQuery, callback_data: SearchCallback, state: FSMContext
) -> None:
    await query.answer()
    data = await state.get_data()
    results_data = data.get("results", [])
    results = [SearchResultItem(**r) for r in results_data]
    url_mapping = data.get("url_mapping", {})

    url_id = callback_data.url_id
    video_url = url_mapping.get(url_id)
    if not video_url:
        await query.answer("Sorry, this result is no longer available.")
        return

    target_video = next((r for r in results if r.video_url == video_url), None)
    if not target_video:
        await query.answer("Sorry, this result is no longer available.")
        return

    is_expanded = callback_data.action == "expand"
    caption = format_single_search_result(target_video, is_expanded=is_expanded)
    keyboard = create_video_keyboard(url_id, callback_data.page, is_expanded=is_expanded)

    if not query.message or not isinstance(query.message, Message):
        await query.answer("Message not found. Please try again.")
        return

    try:
        await query.message.edit_caption(caption=caption, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to update message: {e}")
        await query.answer("Failed to update message. Please try again.")


@router.callback_query(SearchCallback.filter(F.action == "download"))
async def download_callback_handler(query: CallbackQuery, callback_data: SearchCallback, state: FSMContext, bot: Bot) -> None:
    await query.answer()
    data = await state.get_data()
    url_mapping = data.get("url_mapping", {})
    
    url_id = callback_data.url_id
    video_url = url_mapping.get(url_id)
    if not video_url:
        await query.answer("Sorry, this video is no longer available.")
        return

    if not query.message or not isinstance(query.message, Message):
        await query.answer("Message not found. Please try again.")
        return
        
    try:
        await bot.send_message(
            chat_id=query.message.chat.id,
            text=f"Please wait while I process your download request for:\n{video_url}"
        )
    except Exception as e:
        logger.error(f"Failed to send download message: {e}")
        await query.answer("Failed to start download. Please try again.")

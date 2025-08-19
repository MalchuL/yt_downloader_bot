import logging
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from telegram_video_downloader.searcher.interface import Searcher, SearchResultItem
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
    await state.set_state(SearchState.searching)
    await state.set_data({"query": query})

    status_msg = await message.reply(f"Searching for: `{query}`...")

    results = await searcher.search(query, page=1)
    if not results:
        await status_msg.edit_text("No results found.")
        await state.clear()
        return

    await status_msg.delete()

    total_results = len(results)
    total_pages = (total_results + settings.YOUTUBE_SEARCH_RESULTS_LIMIT - 1) // settings.YOUTUBE_SEARCH_RESULTS_LIMIT

    await state.set_state(SearchState.results)
    await state.update_data({"results": [r.__dict__ for r in results], "page": 1, "total_pages": total_pages})

    for i in range(0, len(results), settings.YOUTUBE_SEARCH_RESULTS_LIMIT):
        page_results = results[i:i+settings.YOUTUBE_SEARCH_RESULTS_LIMIT]
        for item in page_results:
            caption = format_single_search_result(item, is_expanded=False)
            keyboard = create_video_keyboard(item.video_url, 1, is_expanded=False)
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=item.thumbnail,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    if total_pages > 1:
        pagination_keyboard = create_pagination_keyboard(1, total_pages)
        await message.answer("Use the buttons below to navigate pages:", reply_markup=pagination_keyboard)


@router.callback_query(SearchCallback.filter(F.action.in_(["prev", "next"])))
async def pagination_callback_handler(
    query: CallbackQuery, callback_data: SearchCallback, state: FSMContext, searcher: Searcher, bot: Bot
) -> None:
    await query.answer()
    data = await state.get_data()
    search_query = data.get("query")
    page = callback_data.page

    results = await searcher.search(search_query, page=page)
    total_pages = data.get("total_pages", 1)

    await state.update_data({"page": page, "results": [r.__dict__ for r in results]})

    # Clear previous results before sending new ones
    await query.message.delete()

    for item in results:
        caption = format_single_search_result(item, is_expanded=False)
        keyboard = create_video_keyboard(item.video_url, page, is_expanded=False)
        await bot.send_photo(
            chat_id=query.message.chat.id,
            photo=item.thumbnail,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    if total_pages > 1:
        pagination_keyboard = create_pagination_keyboard(page, total_pages)
        await query.message.answer("Use the buttons below to navigate pages:", reply_markup=pagination_keyboard)


@router.callback_query(SearchCallback.filter(F.action.in_(["expand", "collapse"])))
async def expand_collapse_callback_handler(
    query: CallbackQuery, callback_data: SearchCallback, state: FSMContext
) -> None:
    await query.answer()
    data = await state.get_data()
    results_data = data.get("results", [])
    results = [SearchResultItem(**r) for r in results_data]

    video_url = callback_data.video_url
    target_video = next((r for r in results if r.video_url == video_url), None)

    if not target_video:
        return

    is_expanded = callback_data.action == "expand"
    caption = format_single_search_result(target_video, is_expanded=is_expanded)
    keyboard = create_video_keyboard(video_url, callback_data.page, is_expanded=is_expanded)

    await query.message.edit_caption(caption=caption, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(SearchCallback.filter(F.action == "download"))
async def download_callback_handler(query: CallbackQuery) -> None:
    await query.answer()
    await query.message.answer(f"Please wait while I process your download request for:\n{query.data}")

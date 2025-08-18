from typing import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.providers.interface import QualityOption


class QualityCallback(CallbackData, prefix="quality"):
    """
    Callback data for quality selection buttons.
    'itag' is the provider-specific identifier for the chosen quality.
    """
    itag: str


class SearchCallback(CallbackData, prefix="search"):
    action: str  # "prev", "next", "expand", "collapse", "download"
    page: int
    video_url: str = ""


def create_quality_keyboard(qualities: Iterable[QualityOption]) -> InlineKeyboardMarkup:
    """
    Creates an inline keyboard with buttons for each quality option.
    """
    builder = InlineKeyboardBuilder()
    for quality in qualities:
        label = quality.label
        if quality.is_default:
            label = f"✅ {label} (Default)"

        builder.add(
            InlineKeyboardButton(
                text=label,
                callback_data=QualityCallback(itag=quality.itag).pack(),
            )
        )

    builder.adjust(2)
    return builder.as_markup()


def create_video_keyboard(video_url: str, page: int, is_expanded: bool) -> InlineKeyboardMarkup:
    """
    Creates an inline keyboard for a single video result.
    """
    builder = InlineKeyboardBuilder()
    action = "collapse" if is_expanded else "expand"
    builder.button(
        text="Expand Description" if not is_expanded else "Collapse Description",
        callback_data=SearchCallback(action=action, page=page, video_url=video_url),
    )
    builder.button(
        text="Download",
        callback_data=SearchCallback(action="download", page=page, video_url=video_url),
    )
    builder.adjust(2)
    return builder.as_markup()


def create_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Creates an inline keyboard for pagination.
    """
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.button(
            text="⬅️ Previous",
            callback_data=SearchCallback(action="prev", page=page - 1),
        )
    if page < total_pages:
        builder.button(
            text="Next ➡️",
            callback_data=SearchCallback(action="next", page=page + 1),
        )
    return builder.as_markup()

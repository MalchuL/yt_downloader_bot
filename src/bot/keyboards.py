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

    # Arrange buttons into a neat grid, max 2 per row
    builder.adjust(2)

    return builder.as_markup()

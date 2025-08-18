import pytest
from unittest.mock import AsyncMock, MagicMock

from src.bot.handlers import start_handler, help_handler, health_handler
from src.core.config import settings


@pytest.mark.asyncio
async def test_start_handler():
    """Tests the /start command handler."""
    message = AsyncMock()
    await start_handler(message)
    message.answer.assert_called_once_with(
        "Welcome! Send me a video link (e.g., from YouTube) and I'll download it for you."
    )


@pytest.mark.asyncio
async def test_help_handler():
    """Tests the /help command handler."""
    message = AsyncMock()
    await help_handler(message)
    message.answer.assert_called_once_with(
        "Supported sites depend on the configuration.\n"
        "Just send a link. I'll ask for the quality you want.\n"
        f"If you don't choose within {settings.SELECTION_TIMEOUT_SEC} seconds, "
        "I'll automatically start downloading the best available quality."
    )


@pytest.mark.asyncio
async def test_health_handler_healthy():
    """Tests the /health command handler with a healthy provider."""
    message = AsyncMock()
    provider = MagicMock()
    provider.healthcheck.return_value = True
    provider.name = "healthy_provider"

    await health_handler(message, provider)

    provider.healthcheck.assert_called_once()
    message.answer.assert_called_once_with("Provider 'healthy_provider' is healthy.")


@pytest.mark.asyncio
async def test_health_handler_unhealthy():
    """Tests the /health command handler with an unhealthy provider."""
    message = AsyncMock()
    provider = MagicMock()
    provider.healthcheck.return_value = False
    provider.name = "unhealthy_provider"

    await health_handler(message, provider)

    provider.healthcheck.assert_called_once()
    message.answer.assert_called_once_with("Provider 'unhealthy_provider' is unhealthy.")

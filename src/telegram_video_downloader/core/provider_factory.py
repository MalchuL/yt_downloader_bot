from typing import Type

from telegram_video_downloader.core.config import settings
from telegram_video_downloader.providers.provider import DownloadProvider

# Import all provider modules here so the factory can find them.
# This is a simple approach for auto-discovery.
from telegram_video_downloader.providers import yt_dlp_provider  # noqa: F401
from telegram_video_downloader.providers import pytube_provider  # noqa: F401


def _get_provider_class(provider_name: str) -> Type[DownloadProvider]:
    """
    Find and return the provider class matching the given name.
    """
    for subclass in DownloadProvider.__subclasses__():
        if getattr(subclass, "name", None) == provider_name:
            return subclass
    raise ValueError(f"No provider found with name: '{provider_name}'")


def get_provider() -> DownloadProvider:
    """
    Instantiates and returns the download provider specified in the settings.
    """
    provider_name = settings.DOWNLOADER_PROVIDER
    provider_class = _get_provider_class(provider_name)
    provider_instance = provider_class()

    # Perform a health check on the provider before returning it.
    if not provider_instance.healthcheck():
        raise RuntimeError(
            f"Health check failed for provider: '{provider_name}'"
        )

    return provider_instance

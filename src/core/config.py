import tempfile
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # Core bot settings
    BOT_TOKEN: Optional[str] = None
    DOWNLOADER_PROVIDER: str = "yt_dlp"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Filesystem and download behavior
    DOWNLOAD_TEMP_DIR: str = tempfile.gettempdir()
    SELECTION_TIMEOUT_SEC: int = 30
    ALLOW_QUALITY_FALLBACK: bool = True

    # Concurrency and rate limiting
    GLOBAL_CONCURRENCY: int = 3
    PER_CHAT_CONCURRENCY: int = 1

    # Telegram limits
    MAX_TELEGRAM_FILESIZE_MB: int = 48  # Default to slightly under 50MB for safety

    # Search settings
    YOUTUBE_SEARCH_RESULTS_LIMIT: int = 5

    # Network settings
    HTTP_PROXY: Optional[str] = None
    HTTPS_PROXY: Optional[str] = None

    # Provider-specific settings (example)
    YTDLP_PATH: Optional[str] = "yt-dlp"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Instantiate the settings object to be used throughout the application
settings = Settings()

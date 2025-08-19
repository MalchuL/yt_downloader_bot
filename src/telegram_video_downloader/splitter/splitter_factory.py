from telegram_video_downloader.core.config import settings
from telegram_video_downloader.splitter.ffmpeg_splitter import FFmpegSplitter
from telegram_video_downloader.splitter.splitter import Splitter


def get_splitter() -> Splitter:
    """
    Instantiates and returns the splitter specified in the settings.
    """
    splitter_name = settings.SPLITTER_PROVIDER
    match splitter_name:
        case "ffmpeg":
            return FFmpegSplitter()
        case _:
            raise ValueError(f"Invalid splitter name: {splitter_name}")

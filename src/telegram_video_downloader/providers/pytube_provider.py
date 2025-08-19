import logging
import os
import re
import uuid
from typing import Iterable, Optional

from pytube import YouTube
from pytube.exceptions import PytubeError
from pytube.streams import Stream

from telegram_video_downloader.core.config import settings
from telegram_video_downloader.providers.interface import (
    DownloadProvider,
    ProgressCallback,
    QualityOption,
    VideoMeta,
)

logger = logging.getLogger(__name__)

YOUTUBE_URL_PATTERN = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:m\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=)?(.+)"
)


class PytubeProvider(DownloadProvider):
    """
    A download provider that uses the pytube library, specialized for YouTube.
    This provider is referred to as 'yt_downloader' in the configuration.
    """

    name = "yt_downloader"

    def healthcheck(self) -> bool:
        """Checks if the pytube library can be imported."""
        try:
            import pytube

            logger.info("[%s] Health check passed.", self.name)
            return True
        except ImportError:
            logger.error("[%s] Health check failed: pytube library not found.", self.name)
            return False

    def supports(self, url: str) -> bool:
        """Returns True if the URL is a valid YouTube URL."""
        return bool(YOUTUBE_URL_PATTERN.match(url))

    def get_metadata(self, url: str) -> VideoMeta:
        """Fetches video metadata from YouTube."""
        try:
            yt = YouTube(url)
            return VideoMeta(
                title=yt.title,
                duration_sec=yt.length,
                webpage_url=yt.watch_url,
                author=yt.author,
                thumbnails=[yt.thumbnail_url] if yt.thumbnail_url else [],
            )
        except PytubeError as e:
            logger.error(
                "[%s] Pytube error fetching metadata for %s: %s", self.name, url, e
            )
            raise IOError(
                f"Could not fetch video metadata. The video may be private or unavailable."
            ) from e

    def list_qualities(self, url: str) -> Iterable[QualityOption]:
        """Lists available progressive MP4 qualities for a YouTube video."""
        try:
            yt = YouTube(url)
            # Filter for progressive mp4 streams and order by resolution descending
            streams = (
                yt.streams.filter(progressive=True, file_extension="mp4")
                .order_by("resolution")
                .desc()
            )
        except PytubeError as e:
            logger.error(
                "[%s] Pytube error listing qualities for %s: %s", self.name, url, e
            )
            raise IOError(
                f"Could not fetch video qualities. The video may be private or unavailable."
            ) from e

        qualities = []
        if streams:
            best_stream = streams[0]
            qualities.append(
                QualityOption(
                    itag=str(best_stream.itag),
                    label="Best",
                    height=int(best_stream.resolution[:-1]) if best_stream.resolution else None,
                    is_default=True,
                )
            )

            seen_resolutions = {best_stream.resolution}
            for stream in streams:
                if stream.resolution and stream.resolution not in seen_resolutions:
                    qualities.append(
                        QualityOption(
                            itag=str(stream.itag),
                            label=stream.resolution,
                            height=int(stream.resolution[:-1]) if stream.resolution else None,
                        )
                    )
                    seen_resolutions.add(stream.resolution)

        if not qualities:
            raise RuntimeError(f"[{self.name}] No progressive MP4 streams found for {url}")

        return qualities

    def download(
        self,
        url: str,
        quality: QualityOption,
        on_progress: Optional[ProgressCallback] = None,
        temp_dir: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ) -> str:
        """Downloads the video from YouTube using the specified quality."""
        temp_dir_path = temp_dir or settings.DOWNLOAD_TEMP_DIR
        os.makedirs(temp_dir_path, exist_ok=True)

        try:
            yt = YouTube(url)
            stream = yt.streams.get_by_itag(int(quality.itag))
            if not stream:
                raise IOError(f"Stream with itag '{quality.itag}' not found.")

            total_size = stream.filesize

            def progress_handler(stream: Stream, chunk: bytes, bytes_remaining: int):
                if on_progress and total_size > 0:
                    downloaded_bytes = total_size - bytes_remaining
                    progress_percent = downloaded_bytes / total_size
                    on_progress(progress_percent, downloaded_bytes)

            yt.register_on_progress_callback(progress_handler)

            output_path = stream.download(
                output_path=temp_dir_path, filename_prefix=f"dl_{uuid.uuid4().hex}_"
            )

            yt.register_on_progress_callback(None)  # Unregister callback
            return output_path
        except PytubeError as e:
            logger.error("[%s] Pytube error downloading %s: %s", self.name, url, e)
            raise IOError(f"Failed to download video. Please try again.") from e


    def max_filesize_bytes(self, quality: QualityOption) -> Optional[int]:
        """
        This method cannot be implemented as specified because it requires the video URL
        to fetch format information, which is not provided in the method signature.
        Returning None as per the spec's allowance for an unknown size.
        """
        return None

import logging
import os
import uuid
from typing import Any, Dict, Iterable, Optional

import yt_dlp
from telegram_video_downloader.core.config import settings
from telegram_video_downloader.providers.provider import (
    DownloadProvider,
    ProgressCallback,
    QualityOption,
    VideoMeta,
)
from telegram_video_downloader.providers.utils.youtube_dl_wrapper import YoutubeDLWrapper

logger = logging.getLogger(__name__)


class YtDlpProvider(DownloadProvider):
    """
    A download provider that uses the yt-dlp library to download videos.
    """

    name = "yt_dlp"
    _ydl_opts_base: Dict[str, Any] = {
        "quiet": True,
        "noplaylist": True,
        "cookiefile": settings.YTDLP_COOKIES_FILE,
        "cachedir": settings.YTDLP_SAVE_FOLDER,
    }
    TMP_DIR = settings.DOWNLOAD_TEMP_DIR

    def healthcheck(self) -> bool:
        """Checks if the yt-dlp library is installed and usable."""
        try:
            if not settings.YTDLP_COOKIES_FILE:
                logger.error("[%s] Cookies file not configured", self.name)
                return False
                
            if not os.path.exists(settings.YTDLP_COOKIES_FILE):
                logger.error("[%s] Cookies file not found: %s", self.name, settings.YTDLP_COOKIES_FILE)
                return False
            
            # Test wrapper initialization
            wrapper = YoutubeDLWrapper(
                self._ydl_opts_base,
                temp_dir=self.TMP_DIR
            )
            logger.info("[%s] Health check passed.", self.name)
            return True
        except Exception as e:
            logger.error("[%s] Health check failed: %s", self.name, e)
            return False

    def supports(self, url: str) -> bool:
        """yt-dlp supports a vast range of URLs, so we accept any valid http/https URL."""
        return url.startswith("http://") or url.startswith("https://")

    def _extract_info(self, url: str) -> Dict[str, Any]:
        """Helper to extract video info using yt-dlp."""
        wrapper = YoutubeDLWrapper(
            self._ydl_opts_base,
            temp_dir=self.TMP_DIR
        )
        info = wrapper.extract_info(url, download=False)
        if not isinstance(info, dict):
            raise TypeError(f"Expected dict from extract_info, got {type(info)}")
        return info

    def get_metadata(self, url: str) -> VideoMeta:
        """Fetches video metadata."""
        info = self._extract_info(url)
        return VideoMeta(
            title=info.get("title", "Unknown Title"),
            duration_sec=info.get("duration"),
            webpage_url=info.get("webpage_url", url),
            author=info.get("uploader"),
            thumbnails=[t.get("url") for t in info.get("thumbnails", []) if t.get("url")],
        )

    def list_qualities(self, url: str) -> Iterable[QualityOption]:
        """
        Lists available video and audio qualities.
        For video: prioritizes progressive MP4/WEBM streams
        For audio: provides best quality audio-only options
        """
        logger.info("[%s] Listing qualities for %s", self.name, url)
        logger.info("[%s] Cookies file: %s", self.name, self._ydl_opts_base.get("cookiefile"))
        info = self._extract_info(url)
        logger.debug("[%s] Info: %s", self.name, info)
        formats = info.get("formats", [])

        qualities = []

        # Add audio-only options first
        audio_formats = [
            f for f in formats
            if f.get("vcodec") == "none" 
            and f.get("acodec") != "none"
            and f.get("ext") in ["m4a", "mp3", "opus", "webm"]
        ]
        
        if audio_formats:
            # Sort by quality (bitrate)
            audio_formats.sort(key=lambda f: float(f.get("abr", 0)), reverse=True)
            best_audio = audio_formats[0]
            
            # Add best audio quality option
            qualities.append(
                QualityOption(
                    itag="bestaudio/best",  # Use yt-dlp's format selector
                    label="Best Audio",
                    bitrate_kbps=int(best_audio.get("abr", 0)),
                    is_audio_only=True,
                    is_default=True,  # Make audio the default
                )
            )

            # Add other unique audio qualities
            seen_bitrates = {best_audio.get("abr")}
            for f in audio_formats:
                bitrate = f.get("abr")
                if bitrate and bitrate not in seen_bitrates:
                    qualities.append(
                        QualityOption(
                            itag=f["format_id"],  # Use the actual format ID
                            label=f"Audio {int(bitrate)}kbps",
                            bitrate_kbps=int(bitrate),
                            is_audio_only=True,
                        )
                    )
                    seen_bitrates.add(bitrate)

        # Add video options
        progressive_formats = [
            f
            for f in formats
            if f.get("vcodec") != "none" and f.get("acodec") != "none"
            and f.get("ext") in ["mp4", "webm"]
        ]
        
        if progressive_formats:
            progressive_formats.sort(key=lambda f: (f.get("height", 0), f.get("tbr", 0)), reverse=True)
            best_video = progressive_formats[0]
            
            # Add best video quality option
            qualities.append(
                QualityOption(
                    itag=best_video["format_id"],
                    label="Best Video",
                    height=best_video.get("height"),
                    width=best_video.get("width"),
                    is_default=not audio_formats,  # Default to video only if no audio formats
                )
            )

            # Add other unique video resolutions
            seen_heights = {best_video.get("height")}
            for f in progressive_formats:
                height = f.get("height")
                if height and height not in seen_heights:
                    qualities.append(
                        QualityOption(
                            itag=f["format_id"],
                            label=f"{height}p",
                            height=height,
                            width=f.get("width"),
                        )
                    )
                    seen_heights.add(height)
        elif not qualities:  # No progressive formats and no audio formats
            # Fallback for DASH streams
            qualities.append(
                QualityOption(itag="bestvideo+bestaudio/best", label="Best", is_default=True)
            )

        return qualities

    def download(
        self,
        url: str,
        quality: QualityOption,
        on_progress: Optional[ProgressCallback] = None,
        temp_dir: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ) -> str:
        """Downloads the video or audio to a temporary file and returns the path."""
        temp_dir_path = temp_dir or settings.DOWNLOAD_TEMP_DIR
        os.makedirs(temp_dir_path, exist_ok=True)

        # Choose extension based on format type
        ext = "m4a" if quality.is_audio_only else "mp4"
        output_filename = os.path.join(temp_dir_path, f"dl_{uuid.uuid4().hex}.{ext}")

        progress_hooks = []
        if on_progress:
            def hook(d: Dict[str, Any]) -> None:
                if d["status"] == "downloading":
                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                    if total_bytes:
                        downloaded_bytes = d.get("downloaded_bytes", 0)
                        progress = downloaded_bytes / total_bytes
                        on_progress(progress, downloaded_bytes)

            progress_hooks.append(hook)

        ydl_opts = {
            **self._ydl_opts_base,
            "format": quality.itag,
            "outtmpl": output_filename,
            "progress_hooks": progress_hooks,
        }

        if quality.is_audio_only:
            # Audio-specific options
            ydl_opts.update({
                "format": quality.itag,  # Use the format ID directly
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",  # Using M4A for better Telegram compatibility
                    "preferredquality": "0",  # Best quality
                }],
                "extract_audio": True,
            })
        else:
            # Video-specific options
            ydl_opts["merge_output_format"] = "mp4"

        wrapper = YoutubeDLWrapper(
            ydl_opts,
            temp_dir=self.TMP_DIR
        )
        wrapper.download([url])

        return output_filename

    def max_filesize_bytes(self, quality: QualityOption) -> Optional[int]:
        """
        This method cannot be implemented as specified because it requires the video URL
        to fetch format information, which is not provided in the method signature.
        Returning None as per the spec's allowance for an unknown size.
        """
        return None

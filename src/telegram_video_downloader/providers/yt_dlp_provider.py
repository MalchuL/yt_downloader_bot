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

        # Add video options first
        progressive_formats = [
            f
            for f in formats
            if f.get("vcodec") != "none" and f.get("acodec") != "none"
            and f.get("ext") in ["mp4", "webm"]
        ]

        # Add audio-only options
        audio_formats = [
            f for f in formats
            if f.get("vcodec") == "none" 
            and f.get("acodec") != "none"
            and f.get("ext") in ["mp4", "webm"]  # Keep original container formats
        ]
        
        # Process video formats first
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
                    is_default=True  # Always make best video the default
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
        else:
            # Fallback for DASH streams
            qualities.append(
                QualityOption(itag="bestvideo+bestaudio/best", label="Best", is_default=True)
            )

        # Then process audio formats
        if audio_formats:
            # Group formats by bitrate and choose best format for each bitrate
            audio_by_bitrate: Dict[float, Dict[str, Any]] = {}
            for f in audio_formats:
                bitrate = f.get("abr", 0)
                if not bitrate:
                    continue
                
                # Round bitrate to nearest 32kbps to group similar qualities
                rounded_bitrate = round(float(bitrate) / 32) * 32
                
                # If we haven't seen this bitrate or this format is better, update it
                if rounded_bitrate not in audio_by_bitrate or self._is_better_audio_format(f, audio_by_bitrate[rounded_bitrate]):
                    audio_by_bitrate[rounded_bitrate] = f
            
            # Sort unique formats by bitrate
            unique_audio_formats = sorted(audio_by_bitrate.values(), key=lambda f: float(f.get("abr", 0)), reverse=True)
            
            if unique_audio_formats:
                best_audio = unique_audio_formats[0]
                # Add best audio quality option
                qualities.append(
                    QualityOption(
                        itag="bestaudio/best",  # Use yt-dlp's format selector
                        label="Best Audio",
                        bitrate_kbps=int(best_audio.get("abr", 0)),
                        is_audio_only=True,
                        is_default=False
                    )
                )

                # Add other unique audio qualities
                for f in unique_audio_formats[1:]:  # Skip best quality as it's already added
                    bitrate = int(f.get("abr", 0))
                    acodec = f.get("acodec", "").split(".")[0]  # Remove codec versions
                    qualities.append(
                        QualityOption(
                            itag=f["format_id"],  # Use the actual format ID
                            label=f"Audio {bitrate}kbps ({acodec})",
                            bitrate_kbps=bitrate,
                            is_audio_only=True,
                        )
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

        # For audio-only, we'll keep the original container format
        output_filename = os.path.join(temp_dir_path, f"dl_{uuid.uuid4().hex}.mp4")

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

        if not quality.is_audio_only:
            # Video-specific options
            ydl_opts["merge_output_format"] = "mp4"

        wrapper = YoutubeDLWrapper(
            ydl_opts,
            temp_dir=self.TMP_DIR
        )
        wrapper.download([url])

        return output_filename

    def _is_better_audio_format(self, format1: Dict[str, Any], format2: Dict[str, Any]) -> bool:
        """
        Compare two audio formats to determine which is better quality.
        Prefers formats with higher bitrate, then mp4 over webm.
        """
        # First compare bitrates
        abr1 = float(format1.get("abr", 0))
        abr2 = float(format2.get("abr", 0))
        if abr1 != abr2:
            return abr1 > abr2
            
        # If bitrates are equal, prefer mp4 over webm
        ext1 = format1.get("ext", "")
        ext2 = format2.get("ext", "")
        if ext1 != ext2:
            return bool(ext1 == "mp4")
            
        # If all else is equal, keep the existing one
        return False

    def max_filesize_bytes(self, quality: QualityOption) -> Optional[int]:
        """
        This method cannot be implemented as specified because it requires the video URL
        to fetch format information, which is not provided in the method signature.
        Returning None as per the spec's allowance for an unknown size.
        """
        return None

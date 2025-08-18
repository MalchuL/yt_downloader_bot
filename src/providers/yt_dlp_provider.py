import logging
import os
import uuid
from typing import Any, Dict, Iterable, Optional

import yt_dlp
from src.core.config import settings
from src.providers.interface import (
    DownloadProvider,
    ProgressCallback,
    QualityOption,
    VideoMeta,
)

logger = logging.getLogger(__name__)


class YtDlpProvider(DownloadProvider):
    """
    A download provider that uses the yt-dlp library to download videos.
    """

    name = "yt_dlp"
    _ydl_opts_base: Dict[str, Any] = {"quiet": True, "noplaylist": True}

    def healthcheck(self) -> bool:
        """Checks if the yt-dlp library is installed and usable."""
        try:
            with yt_dlp.YoutubeDL(self._ydl_opts_base) as ydl:
                pass
            logger.info(f"[{self.name}] Health check passed.")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Health check failed: {e}")
            return False

    def supports(self, url: str) -> bool:
        """yt-dlp supports a vast range of URLs, so we accept any valid http/https URL."""
        return url.startswith("http://") or url.startswith("https://")

    def _extract_info(self, url: str) -> Dict[str, Any]:
        """Helper to extract video info using yt-dlp."""
        with yt_dlp.YoutubeDL(self._ydl_opts_base) as ydl:
            return ydl.extract_info(url, download=False)

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
        Lists available video qualities, prioritizing progressive MP4 streams.
        A "Best" option is always provided.
        """
        info = self._extract_info(url)
        formats = info.get("formats", [])

        # Filter for progressive mp4 streams (video+audio)
        progressive_mp4 = [
            f
            for f in formats
            if f.get("vcodec") != "none"
            and f.get("acodec") != "none"
            and f.get("ext") == "mp4"
        ]
        progressive_mp4.sort(key=lambda f: (f.get("height", 0), f.get("tbr", 0)), reverse=True)

        qualities = []
        if progressive_mp4:
            best_format = progressive_mp4[0]
            # Add the "Best" quality option, marked as default
            qualities.append(
                QualityOption(
                    itag=best_format["format_id"],
                    label="Best",
                    height=best_format.get("height"),
                    width=best_format.get("width"),
                    is_default=True,
                )
            )

            # Add other unique resolutions
            seen_heights = {best_format.get("height")}
            for f in progressive_mp4:
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
            # Fallback for streams without progressive MP4 (e.g., DASH)
            # yt-dlp will merge the best available video and audio.
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
        """Downloads the video to a temporary file and returns the path."""
        temp_dir_path = temp_dir or settings.DOWNLOAD_TEMP_DIR
        os.makedirs(temp_dir_path, exist_ok=True)
        output_filename = os.path.join(temp_dir_path, f"dl_{uuid.uuid4().hex}.mp4")

        progress_hooks = []
        if on_progress:

            def hook(d: Dict[str, Any]):
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
            "merge_output_format": "mp4",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return output_filename

    def max_filesize_bytes(self, quality: QualityOption) -> Optional[int]:
        """
        This method cannot be implemented as specified because it requires the video URL
        to fetch format information, which is not provided in the method signature.
        Returning None as per the spec's allowance for an unknown size.
        """
        return None

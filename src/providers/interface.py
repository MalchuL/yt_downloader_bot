from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Iterable, Optional


@dataclass(frozen=True)
class QualityOption:
    """
    Represents a single downloadable quality option for a video.
    """

    itag: str  # provider-specific identifier
    label: str  # e.g., "1080p", "720p", "Best"
    width: Optional[int] = None
    height: Optional[int] = None
    bitrate_kbps: Optional[int] = None
    is_default: bool = False


@dataclass(frozen=True)
class VideoMeta:
    """
    Represents basic metadata about a video.
    """

    title: str
    duration_sec: Optional[int]
    webpage_url: str
    author: Optional[str] = None
    thumbnails: Optional[list[str]] = None


# Callback type for reporting download progress.
# Arguments are: progress percentage (0.0 to 1.0), and total bytes downloaded.
ProgressCallback = Callable[[float, Optional[int]], None]


class DownloadProvider(ABC):
    """
    Abstract base class for a download provider.
    Defines the contract that all providers must adhere to.
    """

    name: str

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Return True if this provider can handle the URL."""
        pass

    @abstractmethod
    def get_metadata(self, url: str) -> VideoMeta:
        """Fetch basic metadata for captions/logging."""
        pass

    @abstractmethod
    def list_qualities(self, url: str) -> Iterable[QualityOption]:
        """Return available qualities ordered best->worst, with exactly one is_default=True."""
        pass

    @abstractmethod
    def download(
        self,
        url: str,
        quality: QualityOption,
        on_progress: Optional[ProgressCallback] = None,
        temp_dir: Optional[str] = None,
        timeout_sec: Optional[int] = None,
    ) -> str:
        """Download to a temp file and return the absolute file path."""
        pass

    @abstractmethod
    def max_filesize_bytes(self, quality: QualityOption) -> Optional[int]:
        """Optional hint; return None if unknown. Used for early limit checks."""
        pass

    @abstractmethod
    def healthcheck(self) -> bool:
        """Return True if provider is ready (e.g., binary present, network OK)."""
        pass

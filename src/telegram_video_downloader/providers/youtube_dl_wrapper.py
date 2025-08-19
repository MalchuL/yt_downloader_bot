import logging
import os
import shutil
from typing import Any, Dict, Optional, Callable

import yt_dlp

logger = logging.getLogger(__name__)


class YoutubeDLWrapper:
    """
    A proxy around yt_dlp.YoutubeDL that handles cookie file management and retries.
    
    This class implements the Proxy pattern to:
    1. Manage cookie file lifecycle (protection proxy)
    2. Add retry logic for operations (virtual proxy)
    3. Provide transparent access to YoutubeDL methods
    
    Usage:
        wrapper = YoutubeDLWrapper(opts)
        # All YoutubeDL methods are available through the proxy
        info = wrapper.extract_info(url, download=False)
        wrapper.download([url])
        # Any other YoutubeDL method can be called directly
        wrapper.any_youtube_dl_method(*args, **kwargs)
    """
    TMP_DIR = "/tmp/yt-dlp-cookies"

    def __init__(
        self,
        opts: Dict[str, Any],
        temp_dir: str = TMP_DIR,
        max_retries: int = 1,
    ):
        """
        Initialize the wrapper with options and temp directory for cookie management.

        Args:
            opts: YoutubeDL options dictionary
            temp_dir: Directory to store temporary cookie files
            max_retries: Maximum number of retries on failure (default: 1)
        """
        self.base_opts = opts.copy()
        self.temp_dir = temp_dir
        self.max_retries = max_retries
        self._cookie_file = opts.get("cookiefile")
        
        # Create temp directory if it doesn't exist
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Initialize with a fresh cookie file copy
        self._temp_cookie_file = self._copy_cookie_file(exists_ok=False)
        self._current_opts = self._prepare_options()


    def _copy_cookie_file(self, exists_ok: bool = True) -> Optional[str]:
        """Copy the cookie file to temp directory and return the new path."""
        
        if not self._cookie_file or not os.path.exists(self._cookie_file):
            logger.warning("No cookie file found at: %s", self._cookie_file)
            return None

        temp_cookie_path = os.path.join(
            self.temp_dir,
            f"cookies_{os.path.basename(self._cookie_file)}"
        )
        if not exists_ok and os.path.exists(temp_cookie_path):
            return temp_cookie_path
        
        try:
            shutil.copy2(self._cookie_file, temp_cookie_path)
            logger.info("Copied cookie file to: %s", temp_cookie_path)
            return temp_cookie_path
        except Exception as e:
            logger.error("Failed to copy cookie file: %s", e)
            return None

    def _prepare_options(self) -> Dict[str, Any]:
        """Prepare options with the current temp cookie file."""
        opts = self.base_opts.copy()
        if self._temp_cookie_file:
            opts["cookiefile"] = self._temp_cookie_file
        return opts

    def _refresh_cookies(self) -> None:
        """Refresh the cookie file by creating a new copy."""
        self._temp_cookie_file = self._copy_cookie_file()
        self._current_opts = self._prepare_options()

    def _execute_with_retry(self, operation: Callable[[], Any]) -> Any:
        """
        Execute an operation with retry logic.
        
        Args:
            operation: A callable that performs the actual YoutubeDL operation
        """
        retries = 0
        last_error = None

        while retries <= self.max_retries:
            try:
                return operation()
            except Exception as e:
                last_error = e
                logger.error(
                    "YoutubeDL operation failed (attempt %d/%d): %s",
                    retries + 1,
                    self.max_retries + 1,
                    e
                )
                
                if retries < self.max_retries:
                    logger.info("Refreshing cookies and retrying...")
                    self._refresh_cookies()
                    retries += 1
                else:
                    break

        raise last_error if last_error else RuntimeError("YoutubeDL operation failed")

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """
        Proxy any unknown attribute access to the YoutubeDL instance.
        
        This implements the proxy pattern by dynamically forwarding method calls
        to the underlying YoutubeDL instance while adding retry logic.
        
        Special handling for extract_info to ensure it returns a Dict[str, Any].
        """
        def method_proxy(*args: Any, **kwargs: Any) -> Any:
            def operation() -> Any:
                with yt_dlp.YoutubeDL(self._current_opts) as ydl:
                    method = getattr(ydl, name)
                    result = method(*args, **kwargs)
                    
                    # Special handling for extract_info to ensure type safety
                    if name == "extract_info" and not isinstance(result, dict):
                        raise TypeError(f"Expected dict from extract_info, got {type(result)}")
                    
                    return result
            return self._execute_with_retry(operation)
        
        return method_proxy

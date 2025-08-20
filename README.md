# Telegram video-downloader bot technical specification

This spec captures what to build, how it should behave, and how you’ll know it’s done. It’s designed for handoff to an outsourced team with minimal back-and-forth.

---

## Goals and scope

- **Primary goal:** A Python Telegram bot that accepts a video URL, lets the user choose quality via inline buttons, waits up to 30 seconds for a choice, then downloads and returns the video to the user.
- **Provider abstraction:** The app must support multiple download providers (e.g., yt_downloader, yt_dlp, custom). The active provider is selected via environment variable. All providers implement the same interface.
- **Supported platforms:** Start with YouTube URLs. The design must allow adding other platforms later via providers.
- **MVP scope:**
  - **Commands:** /start, /help
  - **Input:** Plain text message with a single URL
  - **Quality selection:** Inline keyboard with available resolutions; default kicks in after 30 seconds if not chosen
  - **Output:** The downloaded video file, returned to the same chat
  - **Basic concurrency:** Handle multiple users concurrently
  - **Simple persistence:** In-memory state; file system for temp downloads

---

## Installation
According to `yt-dlp`:
1. Install [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. Login to your YouTube account to use it
3. Open page on youtube and press on extension. Export format must be `Netscape`. Copy or save it
4. Run `cp .env.example .env`
5. inside .env:
   - Set TG Bot token from @BotFather
   - Set Path to cookies file from .3
   

## Run
`uv run src/telegram_video_downloader/main.py`
If when running on getting quality you get error, try to update `yt-dlp` in 
`pyproject.toml` to latest version available https://github.com/yt-dlp/yt-dlp 
and type `uv sync`.

## Functional requirements

- **URL intake:**
  - Validate the message contains a single URL.
  - If invalid/unsupported, reply with a concise error and usage hint.
- **Provider routing:**
  - Read env var (e.g., DOWNLOADER_PROVIDER=yt_dlp) to choose provider at startup.
  - On unsupported URL for active provider, reply with an error suggesting trying later or another provider (configurable message).
- **Quality discovery:**
  - Query provider for available qualities for the URL (e.g., 1080p, 720p, 480p, best, audio+video only).
  - Build inline keyboard with options; include a “Best” default option (clearly marked).
- **Selection and timeout:**
  - Wait for user to tap a quality for up to 30 seconds.
  - If user doesn’t select, proceed with default (configurable; default is “Best”).
  - If user taps after timeout, send a polite note that download started with default, and ignore late selection.
- **Progress feedback:**
  - Send a “Processing…” message upon URL receipt.
  - Update progress during download in-place (edit message) no more often than every 2–3 seconds.
  - On completion, delete progress message (if possible) and send the video with caption.
- **Video delivery:**
  - Send as video with caption including source URL, selected quality, and provider name.
  - If the file is too large for Telegram limits or the provider cannot produce the requested quality, gracefully fall back to the next lower quality (if configured to allow fallback) or return an error.
- **Error handling:**
  - Distinguish user errors (bad URL, unsupported platform) from system errors (provider failure, network).
  - Provide clear, single-message explanations with next steps where applicable.
- **Rate limiting and concurrency:**
  - Per-chat throttle (configurable, e.g., 1 active download per chat).
  - Global concurrency cap (configurable).
- **Cleanup:**
  - Remove temp files after delivery or failure.
  - Cancel and clean up jobs on bot shutdown.

---

## Non-functional requirements

- **Language/runtime:** Python 3.10+.
- **Bot framework:** Use a modern, actively maintained Telegram Bot API library (e.g., aiogram or python-telegram-bot). Choose one and justify in README.
- **Architecture:** Provider-agnostic, dependency-injected provider instance; clear separation of bot handlers, domain logic, and provider adapters.
- **Reliability:** Automatic retry for transient provider/network errors (configurable attempts/backoff).
- **Performance:** Start download within 2 seconds after selection/timeout; support concurrent downloads up to the configured cap.
- **Security:** Validate URLs, block local/loopback addresses, enforce max file size thresholds, sanitize file names, and avoid command injection.
- **Observability:** Structured logs with request IDs; metrics counters for starts/success/fail; timing for provider operations.
- **Configuration:** 100% via env variables with sane defaults; optional .env support in dev.
- **Containerization:** Dockerfile and docker-compose for local/dev; minimal runtime image.

---

## System design

### Components

- **Bot app:**
  - **Handlers:** /start, /help, text URL handler, callback query handler for inline buttons.
  - **State manager:** Tracks per-chat jobs (URL, qualities, selection, timers).
  - **Job runner:** Orchestrates selection timeout, provider download, fallback logic, and Telegram upload.
- **Provider interface:** Abstract base + concrete adapters.
- **Storage:**
  - **Temp dir:** For partial and final files.
  - **Optional cache:** Simple LRU for duplicates within a short window (configurable).
- **Config module:** Loads env vars, validates, exposes typed config.

### Basic flow

1. **User sends URL.**
2. **Provider lists qualities.** Bot replies with inline keyboard.
3. **Start 30s timer.** If user selects, cancel timer; else default quality chosen at 30s.
4. **Download via provider.** Emit progress updates.
5. **Upload to Telegram.** Include caption; handle size/fallback.
6. **Cleanup and finalize.**

---

## Provider interface

Define a strict, minimal interface every provider must implement.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

@dataclass(frozen=True)
class QualityOption:
    itag: str            # provider-specific identifier
    label: str           # e.g., "1080p", "720p", "Best"
    width: Optional[int] = None
    height: Optional[int] = None
    bitrate_kbps: Optional[int] = None
    is_default: bool = False

@dataclass(frozen=True)
class VideoMeta:
    title: str
    duration_sec: Optional[int]
    webpage_url: str
    author: Optional[str] = None
    thumbnails: Optional[list[str]] = None

ProgressCallback = Callable[[float, Optional[int]], None]  # progress in [0,1], bytes_downloaded

class DownloadProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Return True if this provider can handle the URL."""

    @abstractmethod
    def get_metadata(self, url: str) -> VideoMeta:
        """Fetch basic metadata for captions/logging."""

    @abstractmethod
    def list_qualities(self, url: str) -> Iterable[QualityOption]:
        """Return available qualities ordered best->worst, with exactly one is_default=True."""

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

    @abstractmethod
    def max_filesize_bytes(self, quality: QualityOption) -> Optional[int]:
        """Optional hint; return None if unknown. Used for early limit checks."""

    @abstractmethod
    def healthcheck(self) -> bool:
        """Return True if provider is ready (e.g., binary present, network OK)."""
```

- **Provider selection:** Instantiate exactly one provider at startup based on env var. Fail-fast if healthcheck fails.
- **Example adapters to implement:**
  - **yt_downloader provider:** Wraps the existing internal/lib-based downloader.
  - **yt_dlp provider:** Shells out to yt-dlp or uses it as a library, honoring the interface.
- **Quality mapping:** Providers must ensure unique labels and a single default option. If platform lacks multiple qualities, return a single default.

---

## Configuration

- **Core:**
  - **BOT_TOKEN:** Telegram bot token (required)
  - **DOWNLOADER_PROVIDER:** Provider key (e.g., yt_downloader, yt_dlp)
  - **DOWNLOAD_TEMP_DIR:** Temp directory path
  - **SELECTION_TIMEOUT_SEC:** Default 30
  - **ALLOW_QUALITY_FALLBACK:** true/false
  - **GLOBAL_CONCURRENCY:** e.g., 3
  - **PER_CHAT_CONCURRENCY:** e.g., 1
  - **MAX_TELEGRAM_FILESIZE_MB:** Upper bound to avoid attempted uploads beyond bot limit
  - **HTTP_PROXY / HTTPS_PROXY:** Optional, for provider access
  - **LOG_LEVEL:** info/debug/warn
- **Provider-specific (namespaced):**
  - **YTDLP_PATH, YTDLP_ARGS, YTDLP_COOKIES_FILE, YTDLP_RATELIMIT_KBPS**, etc.

---

## Telegram UX details

- **/start:** Short welcome and usage: “Send me a video link. I’ll ask for quality and return the file.”
- **/help:** Supported link types, notes on size limits, and how default selection works after 30 seconds.
- **Inline keyboard:**
  - Up to 6 buttons (wrap into rows), each “<label>”.
  - Include “Best” at top; mark default with “(default)”.
- **Messages:**
  - **On URL receive:** “Got it. Fetching qualities…”
  - **On keyboard:** “Choose quality (30s). If you don’t choose, I’ll start with Best.”
  - **Progress:** “Downloading: 42%”
  - **Success caption:** “Title — 720p via yt_dlp”
  - **Errors:** Clear, one-liner plus “Send another link to try again.”
- **Timeout behavior:** When timer fires, edit the keyboard message to indicate default was selected and proceed.

---

## Error handling, limits, and edge cases

- **File size:** If estimated or actual size exceeds MAX_TELEGRAM_FILESIZE_MB, either:
  - Fall back to next lower quality automatically (if allowed), or
  - Abort with message explaining size limit.
- **Upload failures:** Retry upload up to N times with exponential backoff.
- **Network/provider errors:** Distinguish temporary vs permanent when possible; retry temporary errors.
- **Invalid URLs / unsupported sites:** Immediate, friendly error.
- **Duplicate requests:** If an identical URL and quality is already being processed in the same chat, reference the existing job or queue it.
- **Shutdown:** Graceful stop cancels timers, aborts downloads, and cleans temp files.

---

## Deliverables and acceptance criteria

- **Codebase:**
  - **Python package** with clear module boundaries: bot/, providers/, core/.
  - **Provider interface** as above + at least 2 concrete providers (yt_downloader and yt_dlp).
  - **Tests:** Unit tests for provider interface contract, URL validation, timeout logic, fallback path; integration test for end-to-end happy path (can mock Telegram API).
  - **Tooling:** pyproject.toml, linting (ruff/flake8), formatting (black), type hints (mypy), simple Makefile.
  - **Runtime:** Dockerfile (slim base), docker-compose.yml for local dev.
  - **Docs:** README with setup, env vars, provider selection, limitations; ARCHITECTURE.md with flow diagrams; CHANGELOG.
- **Operational:**
  - **Health endpoint or command:** /health to check provider readiness.
  - **Structured logging:** request_id per job; start/finish/failed with durations.
- **Acceptance tests:**
  - **T1:** User sends valid YouTube URL; sees quality buttons; selects 720p within 30s; receives video.
  - **T2:** User does not select; after 30s, bot downloads default and delivers video.
  - **T3:** Requested quality too large; bot falls back to lower quality and informs user.
  - **T4:** Unsupported URL; bot replies with clear error.
  - **T5:** Concurrent users each get independent progress and results.
  - **T6:** Provider switched via env var without code changes; both providers pass T1–T5.

---

## Project plan and assumptions

- **Estimated timeline:** 2–3 weeks total
  - **Week 1:** Skeleton, provider interface, Telegram handlers, one provider implemented, basic E2E.
  - **Week 2:** Second provider, edge cases, progress updates, tests, Dockerization, docs.
  - **Buffer:** Hardening and review.
- **Assumptions:**
  - You provide the bot token and any required proxies.
  - Legal compliance for downloading content is your responsibility; the bot is for personal use/testing.
  - Telegram file size and API limits vary; configure conservative defaults.
- **Open questions:**
  - Should audio-only downloads be supported?
  - Preferred bot framework (aiogram vs python-telegram-bot)?
  - Any language/localization needs?
  - Should we cache identical downloads across users for a short time?

If you want, I can add a minimal architecture diagram and a sample README outline next.

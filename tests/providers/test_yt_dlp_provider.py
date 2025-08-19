import pytest
from unittest.mock import patch, MagicMock

from telegram_video_downloader.providers.yt_dlp_provider import YtDlpProvider


@pytest.fixture
def provider():
    """Returns an instance of the YtDlpProvider."""
    return YtDlpProvider()


def test_healthcheck_success(provider):
    """Tests that healthcheck returns True when yt-dlp is available."""
    with patch("yt_dlp.YoutubeDL") as mock_ydl:
        assert provider.healthcheck() is True


def test_healthcheck_failure(provider):
    """Tests that healthcheck returns False when yt-dlp raises an error."""
    with patch("yt_dlp.YoutubeDL", side_effect=Exception("Test Error")):
        assert provider.healthcheck() is False


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://vimeo.com/123456", True),
        ("http://www.dailymotion.com/video/x12345", True),
        ("ftp://example.com/video.mp4", False),
        ("just some text", False),
    ],
)
def test_supports_url(provider, url, expected):
    """
    Tests the URL support validation. yt-dlp should support any http/https URL.
    """
    assert provider.supports(url) is expected


@pytest.fixture
def mock_ydl_context():
    """A fixture to mock the yt_dlp.YoutubeDL context manager."""
    with patch("yt_dlp.YoutubeDL") as mock_ydl_class:
        # This mocks the instance returned by `with yt_dlp.YoutubeDL(...) as ydl:`
        mock_instance = mock_ydl_class.return_value.__enter__.return_value
        yield mock_instance


@pytest.fixture
def sample_info_dict():
    """Provides a sample yt-dlp info dictionary."""
    return {
        "title": "Test Title",
        "duration": 123,
        "uploader": "Test Uploader",
        "webpage_url": "https://example.com/watch/test",
        "thumbnails": [{"url": "http://example.com/thumb.jpg"}],
        "formats": [
            {
                "format_id": "22", "height": 720, "width": 1280, "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4", "tbr": 1500
            },
            {
                "format_id": "18", "height": 360, "width": 640, "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4", "tbr": 500
            },
             { # Audio only, should be ignored by list_qualities
                "format_id": "140", "height": None, "vcodec": "none", "acodec": "mp4a", "ext": "m4a"
            },
        ],
    }


def test_get_metadata_success(provider, mock_ydl_context, sample_info_dict):
    """Tests that get_metadata correctly extracts metadata."""
    mock_ydl_context.extract_info.return_value = sample_info_dict
    url = "https://example.com/watch/test"

    metadata = provider.get_metadata(url)

    mock_ydl_context.extract_info.assert_called_once_with(url, download=False)
    assert metadata.title == "Test Title"
    assert metadata.duration_sec == 123
    assert metadata.author == "Test Uploader"
    assert metadata.thumbnails == ["http://example.com/thumb.jpg"]


def test_list_qualities_success(provider, mock_ydl_context, sample_info_dict):
    """Tests that list_qualities correctly parses the formats list."""
    mock_ydl_context.extract_info.return_value = sample_info_dict
    url = "https://example.com/watch/test"

    qualities = list(provider.list_qualities(url))

    assert len(qualities) == 2  # Best (720p) and 360p
    assert qualities[0].label == "Best"
    assert qualities[0].is_default is True
    assert qualities[0].height == 720
    assert qualities[0].itag == "22"

    assert qualities[1].label == "360p"
    assert qualities[1].height == 360


def test_download_success(provider, mock_ydl_context, tmp_path):
    """
    Tests that the download method correctly calls the yt-dlp download method.
    """
    url = "https://example.com/watch/test"
    quality = MagicMock()
    quality.itag = "22"

    # Act
    filepath = provider.download(url, quality, temp_dir=str(tmp_path))

    # Assert
    # Check that ydl.download was called. The first argument is the call list.
    mock_ydl_context.download.assert_called_once_with([url])

    # Check that the output path is inside the temp directory
    assert filepath.startswith(str(tmp_path))

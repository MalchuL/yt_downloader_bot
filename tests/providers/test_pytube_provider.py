import pytest
from unittest.mock import patch, MagicMock

from src.providers.pytube_provider import PytubeProvider, YOUTUBE_URL_PATTERN


@pytest.fixture
def provider():
    """Returns an instance of the PytubeProvider."""
    return PytubeProvider()


def test_healthcheck_success(provider):
    """Tests that healthcheck returns True when pytube can be imported."""
    with patch("pytube.YouTube", MagicMock()):
        assert provider.healthcheck() is True


def test_healthcheck_failure(provider):
    """Tests that healthcheck returns False when pytube cannot be imported."""
    # To simulate an ImportError, we can patch the import machinery.
    # A simpler way for this case is to patch the name 'pytube' in the module's globals.
    with patch.dict("sys.modules", {"pytube": None}):
        assert provider.healthcheck() is False


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://youtu.be/dQw4w9WgXcQ", True),
        ("http://m.youtube.com/watch?v=dQw4w9WgXcQ", True),
        ("https://www.notyoutube.com/watch?v=dQw4w9WgXcQ", False),
        ("https://www.youtube.com/", False), # No video ID
        ("just some text", False),
    ],
)
def test_supports_url(provider, url, expected):
    """Tests the URL support validation for various YouTube and non-YouTube URLs."""
    assert provider.supports(url) is expected


@pytest.fixture
def mock_yt_object():
    """Provides a mock pytube.YouTube object with common attributes."""
    mock = MagicMock()
    mock.title = "Test Title"
    mock.length = 123
    mock.author = "Test Author"
    mock.watch_url = "https://youtube.com/watch?v=test"
    mock.thumbnail_url = "https://example.com/thumb.jpg"
    return mock


def test_get_metadata_success(provider, mock_yt_object):
    """
    Tests that get_metadata successfully extracts information from a mock YouTube object.
    """
    with patch("src.providers.pytube_provider.YouTube", return_value=mock_yt_object) as mock_youtube_class:
        url = "https://www.youtube.com/watch?v=test"
        metadata = provider.get_metadata(url)

        mock_youtube_class.assert_called_once_with(url)
        assert metadata.title == "Test Title"
        assert metadata.duration_sec == 123
        assert metadata.author == "Test Author"
        assert metadata.webpage_url == "https://youtube.com/watch?v=test"
        assert metadata.thumbnails == ["https://example.com/thumb.jpg"]


def test_get_metadata_failure(provider):
    """
    Tests that get_metadata raises an IOError when pytube raises an error.
    """
    from pytube.exceptions import PytubeError

    with patch("src.providers.pytube_provider.YouTube", side_effect=PytubeError) as mock_youtube_class:
        url = "https://www.youtube.com/watch?v=test"
        with pytest.raises(IOError, match="Could not fetch video metadata"):
            provider.get_metadata(url)
        mock_youtube_class.assert_called_once_with(url)


@pytest.fixture
def mock_stream_720p():
    """Provides a mock pytube Stream object for 720p."""
    mock = MagicMock()
    mock.itag = "22"
    mock.resolution = "720p"
    return mock


@pytest.fixture
def mock_stream_360p():
    """Provides a mock pytube Stream object for 360p."""
    mock = MagicMock()
    mock.itag = "18"
    mock.resolution = "360p"
    return mock


def test_list_qualities_success(provider, mock_yt_object, mock_stream_720p, mock_stream_360p):
    """
    Tests that list_qualities correctly processes a list of streams
    and returns QualityOption objects.
    """
    # Mock the chained calls for stream filtering and ordering
    (
        mock_yt_object.streams.filter.return_value.order_by.return_value.desc.return_value
    ) = [mock_stream_720p, mock_stream_360p]

    with patch("src.providers.pytube_provider.YouTube", return_value=mock_yt_object):
        url = "https://www.youtube.com/watch?v=test"
        qualities = list(provider.list_qualities(url))

        assert len(qualities) == 2  # Best (720p) and 360p
        assert qualities[0].label == "Best"
        assert qualities[0].is_default is True
        assert qualities[0].height == 720
        assert qualities[0].itag == "22"

        assert qualities[1].label == "360p"
        assert qualities[1].is_default is False
        assert qualities[1].height == 360
        assert qualities[1].itag == "18"


def test_list_qualities_no_streams(provider, mock_yt_object):
    """
    Tests that list_qualities raises a RuntimeError if no streams are found.
    """
    mock_yt_object.streams.filter.return_value.order_by.return_value.desc.return_value = []

    with patch("src.providers.pytube_provider.YouTube", return_value=mock_yt_object):
        url = "https://www.youtube.com/watch?v=test"
        with pytest.raises(RuntimeError, match="No progressive MP4 streams found"):
            provider.list_qualities(url)


def test_download_success(provider, mock_yt_object, mock_stream_720p, tmp_path):
    """
    Tests the download method for a successful download.
    """
    # Arrange
    url = "https://www.youtube.com/watch?v=test"
    quality = MagicMock()
    quality.itag = "22"

    # The download method should return the path to the downloaded file
    expected_filepath = tmp_path / "video.mp4"
    mock_stream_720p.download.return_value = str(expected_filepath)

    mock_yt_object.streams.get_by_itag.return_value = mock_stream_720p

    with patch("src.providers.pytube_provider.YouTube", return_value=mock_yt_object):
        # Act
        filepath = provider.download(url, quality, temp_dir=str(tmp_path))

        # Assert
        mock_yt_object.streams.get_by_itag.assert_called_once_with(22)
        mock_stream_720p.download.assert_called_once()
        assert filepath == str(expected_filepath)

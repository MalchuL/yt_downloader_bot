import pytest
from unittest.mock import patch

from src.core import config
from src.core.provider_factory import get_provider
from src.providers.interface import DownloadProvider


# Define mock provider classes for isolated testing.
# These classes simulate the behavior of real providers.
class MockGoodProvider(DownloadProvider):
    name = "good_provider"
    def healthcheck(self) -> bool: return True
    def supports(self, url): pass
    def get_metadata(self, url): pass
    def list_qualities(self, url): pass
    def download(self, url, quality, on_progress=None, temp_dir=None, timeout_sec=None): pass
    def max_filesize_bytes(self, quality): pass

class MockBadProvider(DownloadProvider):
    name = "bad_provider"
    def healthcheck(self) -> bool: return False
    def supports(self, url): pass
    def get_metadata(self, url): pass
    def list_qualities(self, url): pass
    def download(self, url, quality, on_progress=None, temp_dir=None, timeout_sec=None): pass
    def max_filesize_bytes(self, quality): pass


@pytest.fixture(autouse=True)
def patch_subclasses():
    """
    Pytest fixture to automatically patch DownloadProvider.__subclasses__ for all tests in this file.
    This ensures that the provider factory only sees our mock providers, isolating the tests.
    """
    with patch.object(DownloadProvider, "__subclasses__", return_value=[MockGoodProvider, MockBadProvider]) as mock:
        yield mock


def test_get_provider_success(monkeypatch):
    """
    Tests that get_provider returns the correct provider instance
    when the configuration points to a valid, healthy provider.
    """
    # We use setattr to modify the already-loaded settings object
    monkeypatch.setattr(config.settings, "DOWNLOADER_PROVIDER", "good_provider")

    provider = get_provider()

    assert isinstance(provider, MockGoodProvider)
    assert provider.name == "good_provider"


def test_get_provider_not_found(monkeypatch):
    """
    Tests that get_provider raises a ValueError if the configured provider
    name does not match any available providers.
    """
    monkeypatch.setattr(config.settings, "DOWNLOADER_PROVIDER", "nonexistent_provider")

    with pytest.raises(ValueError, match="No provider found with name: 'nonexistent_provider'"):
        get_provider()


def test_get_provider_unhealthy(monkeypatch):
    """
    Tests that get_provider raises a RuntimeError if the selected provider
    fails its healthcheck.
    """
    monkeypatch.setattr(config.settings, "DOWNLOADER_PROVIDER", "bad_provider")

    with pytest.raises(RuntimeError, match="Health check failed for provider: 'bad_provider'"):
        get_provider()

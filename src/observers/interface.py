from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SearchResultItem:
    """
    Represents a single search result item.
    """
    thumbnail: str
    channel_name: str
    channel_url: str
    channel_subscribers: str
    publication_date: str
    video_title: str
    video_url: str
    video_views: str
    video_description: str
    duration: str


class Observer(ABC):
    """
    Abstract base class for a search observer.
    """

    @abstractmethod
    async def search(self, query: str, page: int = 1) -> List[SearchResultItem]:
        """
        Search for videos based on a query.

        :param query: The search query.
        :param page: The page number of the search results.
        :return: A list of SearchResultItem objects.
        """
        pass

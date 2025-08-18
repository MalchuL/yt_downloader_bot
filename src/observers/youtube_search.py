import asyncio
from typing import List, Optional

from youtubesearchpython.__future__ import VideosSearch, Channel
from src.core.config import settings
from src.observers.interface import Observer, SearchResultItem


class YouTubeSearch(Observer):
    """
    Observer implementation for searching videos on YouTube.
    """

    async def search(self, query: str, page: int = 1) -> List[SearchResultItem]:
        """
        Search for videos on YouTube.

        :param query: The search query.
        :param page: The page number of the search results.
        :return: A list of SearchResultItem objects.
        """
        search = VideosSearch(query, limit=settings.YOUTUBE_SEARCH_RESULTS_LIMIT)

        for _ in range(page):
            results = await search.next()

        if not results or not results.get("result"):
            return []

        # Concurrently fetch channel information to get subscriber counts
        channel_ids = [
            video["channel"]["id"]
            for video in results["result"]
            if video.get("channel") and video["channel"].get("id")
        ]
        channel_tasks = [self._get_channel_info(channel_id) for channel_id in channel_ids]
        channel_infos = await asyncio.gather(*channel_tasks)

        subscribers_map = {info["id"]: info.get("subscribers", {}).get("simpleText", "N/A") for info in channel_infos if info}

        search_results = []
        for video in results["result"]:
            channel_info = video.get("channel")
            if not channel_info:
                continue

            channel_id = channel_info.get("id")
            subscribers = subscribers_map.get(channel_id, "N/A")

            description_snippet = video.get("descriptionSnippet")
            description = description_snippet[0]["text"] if description_snippet else "No description"

            search_results.append(
                SearchResultItem(
                    thumbnail=video["thumbnails"][0]["url"],
                    channel_name=channel_info["name"],
                    channel_url=channel_info["link"],
                    channel_subscribers=subscribers,
                    publication_date=video.get("publishedTime", "N/A"),
                    video_title=video["title"],
                    video_url=video["link"],
                    video_views=video.get("viewCount", {}).get("text", "N/A"),
                    video_description=description,
                    duration=video.get("duration", "N/A"),
                )
            )

        return search_results

    async def _get_channel_info(self, channel_id: str) -> Optional[dict]:
        """
        Fetches channel information to get the subscriber count.
        """
        try:
            channel = await Channel.get(channel_id)
            return channel
        except Exception:
            return None

import asyncio
import logging
from typing import Any, List, Optional

from youtubesearchpython.__future__ import VideosSearch, Channel
from telegram_video_downloader.core.config import settings
from telegram_video_downloader.searcher.searcher import Searcher, SearchResultItem

logger = logging.getLogger(__name__)


class YouTubeSearch(Searcher):
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

        results = None
        try:
            for _ in range(page):
                try:
                    results = await search.next()
                except Exception as e:
                    logger.error(f"Error during search pagination: {e}")
                    return []

            if not results or not isinstance(results, dict) or not results.get("result"):
                return []
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []

        try:
            # Concurrently fetch channel information to get subscriber counts
            channel_ids = [
                video["channel"]["id"]
                for video in results["result"]
                if video.get("channel") and video["channel"].get("id")
            ]
            channel_tasks = [self._get_channel_info(channel_id) for channel_id in channel_ids]
            channel_infos = await asyncio.gather(*channel_tasks, return_exceptions=True)

            subscribers_map = {}
            for info in channel_infos:
                if isinstance(info, Exception):
                    logger.error(f"Error fetching channel info: {info}")
                    continue
                if info and isinstance(info, dict):
                    subscribers = info.get("subscribers", {})
                    if isinstance(subscribers, dict):
                        subscribers_map[info["id"]] = subscribers.get("simpleText", "N/A")
                    else:
                        subscribers_map[info["id"]] = "N/A"
        except Exception as e:
            logger.error(f"Error processing channel information: {e}")
            subscribers_map = {}

        try:
            search_results = []
            for video in results["result"]:
                try:
                    channel_info = video.get("channel", {})
                    if not channel_info:
                        continue

                    channel_id = channel_info.get("id")
                    subscribers = subscribers_map.get(channel_id, "N/A")

                    description_snippet = video.get("descriptionSnippet", [])
                    description = description_snippet[0].get("text", "No description") if description_snippet else "No description"

                    thumbnails = video.get("thumbnails", [{}])
                    thumbnail_url = thumbnails[0].get("url") if thumbnails else ""

                    search_results.append(
                        SearchResultItem(
                            thumbnail=thumbnail_url,
                            channel_name=channel_info.get("name", "Unknown Channel"),
                            channel_url=channel_info.get("link", ""),
                            channel_subscribers=subscribers,
                            publication_date=video.get("publishedTime", "N/A"),
                            video_title=video.get("title", "Untitled"),
                            video_url=video.get("link", ""),
                            video_views=video.get("viewCount", {}).get("text", "N/A"),
                            video_description=description,
                            duration=video.get("duration", "N/A"),
                        )
                    )
                except Exception as e:
                    logger.error(f"Error processing search result item: {e}")
                    continue

            return search_results
        except Exception as e:
            logger.error(f"Error processing search results: {e}")
            return []

    async def _get_channel_info(self, channel_id: str) -> Optional[dict[str, Any]]:
        """
        Fetches channel information to get the subscriber count.
        """
        try:
            channel = await Channel.get(channel_id)
            if not isinstance(channel, dict):
                return None
            return channel
        except Exception:
            return None

import uuid
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from telegram_video_downloader.core.request_context import REQUEST_ID_VAR


class RequestIdMiddleware(BaseMiddleware):
    """
    Middleware to add a unique request_id to each incoming update for tracing.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Generates a unique ID and sets it in a context variable.
        """
        # Generate a unique ID for the request, taking the first 8 chars for brevity.
        request_id = str(uuid.uuid4())[:8]
        REQUEST_ID_VAR.set(request_id)

        # Pass the request_id to the handler's data dictionary,
        # so it can be accessed directly in handlers if needed (e.g., for FSM storage).
        data["request_id"] = request_id

        return await handler(event, data)

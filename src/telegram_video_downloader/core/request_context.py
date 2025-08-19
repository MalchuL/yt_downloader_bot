from contextvars import ContextVar
from typing import Final

# ContextVar to hold a unique request ID for tracing.
# The default "N/A" is used for logs outside a request-response cycle.
REQUEST_ID_VAR: Final[ContextVar[str]] = ContextVar("request_id", default="N/A")

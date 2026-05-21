"""Langfuse observability configuration. Keys read from .env (optional)."""

import logging
from app.core.config import settings

logger = logging.getLogger("pdf-rag-assistant")
logger.setLevel(logging.INFO)

_langfuse_handler = None
_langfuse_init_failed = False


def get_langfuse_handler():
    """Lazily initialize and return the Langfuse callback handler.

    Returns None if keys not configured or initialization fails.
    Will not retry if initialization already failed once.
    """
    global _langfuse_handler, _langfuse_init_failed

    if _langfuse_init_failed:
        return None

    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None

    if _langfuse_handler is None:
        try:
            from langfuse.callback import CallbackHandler
            _langfuse_handler = CallbackHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            logger.info("Langfuse initialized successfully")
        except Exception as exc:
            logger.warning(f"Langfuse initialization failed (non-critical): {exc}")
            _langfuse_init_failed = True
            return None

    return _langfuse_handler

import os
import threading
from typing import Optional, Any
from langfuse import Langfuse
from app import config

# Global Langfuse client singleton
_langfuse_client = None

def get_langfuse_client() -> Optional[Any]:
    """Returns the global Langfuse client singleton."""
    global _langfuse_client
    if _langfuse_client is None:
        if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
            _langfuse_client = Langfuse(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST
            )
    return _langfuse_client

def flush_langfuse():
    """Flushes the global Langfuse client queue without blocking request paths."""
    lf = get_langfuse_client()
    if lf:
        def _flush():
            try:
                lf.flush()
            except Exception as e:
                print(f"Error flushing Langfuse: {e}")

        threading.Thread(target=_flush, daemon=True).start()

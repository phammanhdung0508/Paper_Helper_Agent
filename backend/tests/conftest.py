import pytest
import os

# Disable Langfuse during tests unless explicitly enabled via environment variable
if os.environ.get("ENABLE_LANGFUSE_TESTS", "").lower() not in ("true", "1", "yes"):
    os.environ["LANGFUSE_PUBLIC_KEY"] = ""
    os.environ["LANGFUSE_SECRET_KEY"] = ""

@pytest.fixture(autouse=True)
def disable_langfuse_during_tests(monkeypatch):
    """
    Automatically disables Langfuse tracing during testing to prevent background 
    upload attempts and connection-refused logs after pytest completes.
    """
    if os.environ.get("ENABLE_LANGFUSE_TESTS", "").lower() not in ("true", "1", "yes"):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
        
        # Force override config values in memory in case they were already loaded
        try:
            from app import config
            monkeypatch.setattr(config, "LANGFUSE_PUBLIC_KEY", "")
            monkeypatch.setattr(config, "LANGFUSE_SECRET_KEY", "")
        except ImportError:
            pass


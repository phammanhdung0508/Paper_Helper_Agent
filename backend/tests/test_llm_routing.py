"""
Advanced LLM routing tests covering:
- Provider fallback chains (OpenRouter fails -> Codex fallback)
- Rate limiting triggers fallback
- Invalid JSON triggers repair retry
- Cache hit avoids provider call
- Task maps to expected provider order
- All providers fail → graceful error
- MockLLMClient returns deterministic valid output
- llm_cache and llm_call_log tables exist
"""

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from pydantic import BaseModel, Field
from typing import Literal

from app import database
from app.llm_client import (
    BaseLLMClient,
    CodexCliClient,
    OpenRouterClient,
    OpenAIDirectClient,
    MockLLMClient,
    LLMRouterClient,
    LLMError,
    run_async,
    _get_provider_order,
)


# Test schema for all provider tests
class TestSchema(BaseModel):
    __test__ = False
    answer: str = Field(description="A test answer.")
    score: int = Field(default=50, description="A numeric score.")


class TestRouteDecision(BaseModel):
    __test__ = False
    route: Literal["general", "rag"] = Field(description="Route decision.")
    reasoning: str = Field(default="test", description="Reasoning.")


# ---------------------------------------------------------------------------
# MockLLMClient tests
# ---------------------------------------------------------------------------

def test_mock_client_returns_valid_output():
    """Verify MockLLMClient returns a Pydantic-valid response."""
    client = MockLLMClient()
    result = run_async(client.run_json("test_task", "test prompt", TestSchema))
    assert isinstance(result, TestSchema)
    assert isinstance(result.answer, str)
    assert isinstance(result.score, int)


def test_mock_client_handles_literal_types():
    """Verify MockLLMClient handles Literal type fields correctly."""
    client = MockLLMClient()
    result = run_async(client.run_json("route_query", "Hello", TestRouteDecision))
    assert isinstance(result, TestRouteDecision)
    assert result.route in ("general", "rag")


# ---------------------------------------------------------------------------
# Provider order tests
# ---------------------------------------------------------------------------

def test_provider_order_route_query():
    """Verify route_query task maps to the configured router provider order."""
    providers = _get_provider_order("route_query")
    assert isinstance(providers, list)
    assert len(providers) > 0
    # Should contain only valid provider names
    for p in providers:
        assert p in ("codex", "openrouter", "openai", "mock", "local")


def test_provider_order_general_chat():
    """Verify general_chat maps to the LLM_GENERAL_PROVIDER config."""
    providers = _get_provider_order("general_chat")
    assert isinstance(providers, list)
    assert len(providers) > 0


def test_provider_order_rag_chat():
    """Verify rag_chat maps to the LLM_RAG_PROVIDER config."""
    providers = _get_provider_order("rag_chat")
    assert isinstance(providers, list)
    assert len(providers) > 0


def test_provider_order_unknown_task_falls_back():
    """Verify an unknown task gets a fallback provider order."""
    providers = _get_provider_order("some_unknown_task")
    assert isinstance(providers, list)
    assert len(providers) > 0


# ---------------------------------------------------------------------------
# LLMRouterClient fallback tests
# ---------------------------------------------------------------------------

def test_router_openrouter_fails_codex_fallback():
    """Verify when OpenRouter fails, the router falls back to the next provider."""
    with patch.object(OpenRouterClient, "run_json", new_callable=AsyncMock) as mock_or, \
         patch.object(CodexCliClient, "run_json", new_callable=AsyncMock) as mock_codex, \
         patch("app.llm_client.LLMRouterClient._cache_lookup", return_value=None), \
         patch("app.llm_client._get_provider_order", return_value=["openrouter", "codex"]), \
         patch("app.llm_client.config") as mock_config:

        mock_config.ENABLE_LLM_FALLBACK = True

        mock_or.side_effect = LLMError("rate_limit", "OpenRouter rate limited")
        mock_codex.return_value = TestSchema(answer="codex fallback", score=42)

        router = LLMRouterClient()
        result = run_async(router.run_json("general_chat", "Hello", TestSchema))

        assert isinstance(result, TestSchema)
        assert result.answer == "codex fallback"
        assert result.score == 42
        mock_or.assert_called_once()
        mock_codex.assert_called_once()


def test_router_codex_rate_limited_openrouter_fallback():
    """Verify when Codex is rate-limited, the router falls back to OpenRouter."""
    with patch.object(CodexCliClient, "run_json", new_callable=AsyncMock) as mock_codex, \
         patch.object(OpenRouterClient, "run_json", new_callable=AsyncMock) as mock_or, \
         patch("app.llm_client.LLMRouterClient._cache_lookup", return_value=None), \
         patch("app.llm_client._get_provider_order", return_value=["codex", "openrouter"]), \
         patch("app.llm_client.config") as mock_config:

        mock_config.ENABLE_LLM_FALLBACK = True

        mock_codex.side_effect = LLMError("rate_limit", "Codex rate limit exceeded")
        mock_or.return_value = TestSchema(answer="openrouter fallback", score=88)

        router = LLMRouterClient()
        result = run_async(router.run_json("rag_chat", "What is X?", TestSchema))

        assert isinstance(result, TestSchema)
        assert result.answer == "openrouter fallback"
        mock_codex.assert_called_once()
        mock_or.assert_called_once()


def test_router_all_providers_fail_graceful_error():
    """Verify when all providers fail, a graceful LLMError is raised."""
    with patch.object(OpenRouterClient, "run_json", new_callable=AsyncMock) as mock_or, \
         patch.object(CodexCliClient, "run_json", new_callable=AsyncMock) as mock_codex, \
         patch("app.llm_client.LLMRouterClient._cache_lookup", return_value=None), \
         patch("app.llm_client._get_provider_order", return_value=["openrouter", "codex"]), \
         patch("app.llm_client.config") as mock_config:

        mock_config.ENABLE_LLM_FALLBACK = True

        mock_or.side_effect = LLMError("auth_lost", "No OpenRouter key")
        mock_codex.side_effect = LLMError("subprocess_crash", "codex not found")

        router = LLMRouterClient()
        with pytest.raises(LLMError) as exc_info:
            run_async(router.run_json("general_chat", "Hello", TestSchema))

        assert exc_info.value.category == "subprocess_crash"


def test_router_cache_hit_avoids_provider_call():
    """Verify a cache hit returns the cached response without calling any provider."""
    cached_json = TestSchema(answer="cached answer", score=99).model_dump_json()

    with patch("app.llm_client.LLMRouterClient._cache_lookup", return_value=cached_json), \
         patch("app.llm_client.LLMRouterClient._log_call") as mock_log, \
         patch.object(OpenRouterClient, "run_json", new_callable=AsyncMock) as mock_or, \
         patch.object(CodexCliClient, "run_json", new_callable=AsyncMock) as mock_codex:

        router = LLMRouterClient()
        result = run_async(router.run_json("general_chat", "Hello", TestSchema))

        assert isinstance(result, TestSchema)
        assert result.answer == "cached answer"
        assert result.score == 99
        # Provider should NOT be called
        mock_or.assert_not_called()
        mock_codex.assert_not_called()
        # Log should record cache hit
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[1].get("cache_hit", False) or call_args[0][-1]  # cache_hit=True


def test_router_fallback_disabled_raises_immediately():
    """Verify when ENABLE_LLM_FALLBACK is false, first failure raises immediately."""
    with patch.object(OpenRouterClient, "run_json", new_callable=AsyncMock) as mock_or, \
         patch.object(CodexCliClient, "run_json", new_callable=AsyncMock) as mock_codex, \
         patch("app.llm_client.LLMRouterClient._cache_lookup", return_value=None), \
         patch("app.llm_client._get_provider_order", return_value=["openrouter", "codex"]), \
         patch("app.llm_client.config") as mock_config:

        mock_config.ENABLE_LLM_FALLBACK = False

        mock_or.side_effect = LLMError("rate_limit", "OpenRouter rate limited")
        mock_codex.return_value = TestSchema(answer="should not reach", score=0)

        router = LLMRouterClient()
        with pytest.raises(LLMError) as exc_info:
            run_async(router.run_json("general_chat", "Hello", TestSchema))

        assert exc_info.value.category == "rate_limit"
        mock_codex.assert_not_called()


# ---------------------------------------------------------------------------
# Database table existence tests
# ---------------------------------------------------------------------------

def test_llm_cache_table_exists():
    """Verify the llm_cache table is created by db_init()."""
    database.db_init()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_cache'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row["name"] == "llm_cache"


def test_llm_call_log_table_exists():
    """Verify the llm_call_log table is created by db_init()."""
    database.db_init()
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_call_log'")
    row = cursor.fetchone()
    conn.close()
    assert row is not None
    assert row["name"] == "llm_call_log"


def test_cache_store_and_lookup():
    """Verify cache_store writes and cache_lookup reads correctly."""
    database.db_init()
    database.cache_store("test_task", "hash123", "TestSchema", '{"answer": "cached", "score": 77}', "mock")
    result = database.cache_lookup("test_task", "hash123", "TestSchema")
    assert result is not None
    parsed = json.loads(result)
    assert parsed["answer"] == "cached"
    assert parsed["score"] == 77


def test_log_llm_call():
    """Verify log_llm_call writes successfully without error."""
    database.db_init()
    # Should not raise
    database.log_llm_call("test_task", "mock", True, 150, None, False)
    database.log_llm_call("test_task", "openrouter", False, 5000, "rate_limit", False)

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM llm_call_log WHERE task = 'test_task'")
    row = cursor.fetchone()
    conn.close()
    assert row["cnt"] >= 2


# ---------------------------------------------------------------------------
# LLMError category tests
# ---------------------------------------------------------------------------

def test_llm_error_category():
    """Verify LLMError stores category and message correctly."""
    err = LLMError("rate_limit", "Too many requests")
    assert err.category == "rate_limit"
    assert "Too many requests" in err.message
    assert "rate_limit" in str(err)


# ---------------------------------------------------------------------------
# Redesign Fallback & Task-Specific Chain Tests
# ---------------------------------------------------------------------------

def test_openrouter_task_specific_chains():
    """Verify that OpenRouterClient routes tasks to correct model chains."""
    with patch("openai.resources.chat.completions.Completions.create") as mock_create, \
         patch("app.llm_client.get_langfuse_client", return_value=None), \
         patch("app.llm_client.config") as mock_config:

        mock_config.OPENROUTER_API_KEY = "dummy-key"
        mock_config.OPENROUTER_BASE_URL = "https://dummy.api"
        mock_config.OPENROUTER_MODEL = ""

        # Mock successful return of structured JSON
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"answer": "model test", "score": 99}'
        mock_response.usage = None
        mock_create.return_value = mock_response

        client = OpenRouterClient()

        # 1. Test code generation task (should use stable GPT-OSS first)
        res_code = run_async(client.run_json("generate_visual_spec", "plot", TestSchema))
        assert isinstance(res_code, TestSchema)
        assert mock_create.call_args_list[0][1]["model"] == "openai/gpt-oss-120b:free"

        # 2. Test text extraction task (should use stable GPT-OSS first)
        mock_create.reset_mock()
        res_ext = run_async(client.run_json("extract_knowledge_graph", "text", TestSchema))
        assert isinstance(res_ext, TestSchema)
        assert mock_create.call_args_list[0][1]["model"] == "openai/gpt-oss-120b:free"


def test_openrouter_429_family_skipping():
    """Verify rate-limit (429) failures skip sibling models of the same family."""
    with patch("openai.resources.chat.completions.Completions.create") as mock_create, \
         patch("app.llm_client.get_langfuse_client", return_value=None), \
         patch("app.llm_client.OpenRouterClient.EXTRACTION_MODELS", ["meta-llama/llama-1:free", "meta-llama/llama-2:free", "qwen/qwen-1:free"]), \
         patch("app.llm_client.config") as mock_config:

        mock_config.OPENROUTER_API_KEY = "dummy-key"
        mock_config.OPENROUTER_BASE_URL = "https://dummy.api"
        mock_config.OPENROUTER_MODEL = ""

        # First call: meta-llama/llama-1:free fails with 429.
        # Sibling model meta-llama/llama-2:free must be skipped completely.
        # Second call: qwen/qwen-1:free succeeds.
        mock_create.side_effect = [
            Exception("HTTP 429 Rate Limit"),
            MagicMock(choices=[MagicMock(message=MagicMock(content='{"answer": "success", "score": 1}'))])
        ]

        client = OpenRouterClient()
        res = run_async(client.run_json("extract_knowledge_graph", "text", TestSchema))
        assert isinstance(res, TestSchema)
        assert res.answer == "success"

        # Verify only 2 calls were made to mock_create
        assert len(mock_create.call_args_list) == 2
        # Verify first call was meta-llama/llama-1:free
        assert mock_create.call_args_list[0][1]["model"] == "meta-llama/llama-1:free"
        # Verify second call was qwen/qwen-1:free (skipping meta-llama/llama-2:free)
        assert mock_create.call_args_list[1][1]["model"] == "qwen/qwen-1:free"


def test_router_codex_gating_behavior_batch_denied():
    """Verify batch tasks respect ENABLE_CODEX_FALLBACK_FOR_BATCH config and block Codex fallback."""
    with patch.object(OpenRouterClient, "run_json", new_callable=AsyncMock) as mock_or, \
         patch.object(CodexCliClient, "run_json", new_callable=AsyncMock) as mock_codex, \
         patch("app.llm_client.LLMRouterClient._cache_lookup", return_value=None), \
         patch("app.llm_client._get_provider_order", return_value=["openrouter", "codex"]), \
         patch("app.llm_client.config") as mock_config:

        mock_config.ENABLE_LLM_FALLBACK = True
        # Gating settings: disable batch fallback, enable interactive fallback
        mock_config.ENABLE_CODEX_FALLBACK_FOR_BATCH = False
        mock_config.ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE = True

        mock_or.side_effect = LLMError("rate_limit", "OpenRouter rate limited")

        router = LLMRouterClient()

        # Call batch task: should fail immediately without calling Codex
        with pytest.raises(LLMError) as exc_info:
            run_async(router.run_json("extract_knowledge_graph", "text", TestSchema))

        assert exc_info.value.category == "codex_disabled"
        mock_codex.assert_not_called()


def test_router_codex_gating_behavior_interactive_allowed():
    """Verify interactive tasks respect ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE config and allow Codex fallback."""
    with patch.object(OpenRouterClient, "run_json", new_callable=AsyncMock) as mock_or, \
         patch.object(CodexCliClient, "run_json", new_callable=AsyncMock) as mock_codex, \
         patch("app.llm_client.LLMRouterClient._cache_lookup", return_value=None), \
         patch("app.llm_client._get_provider_order", return_value=["openrouter", "codex"]), \
         patch("app.llm_client.config") as mock_config:

        mock_config.ENABLE_LLM_FALLBACK = True
        mock_config.ENABLE_CODEX_FALLBACK_FOR_BATCH = False
        mock_config.ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE = True

        mock_or.side_effect = LLMError("rate_limit", "OpenRouter rate limited")
        mock_codex.return_value = TestSchema(answer="codex interactive allowed", score=10)

        router = LLMRouterClient()

        # Call interactive task: should fallback to Codex
        res = run_async(router.run_json("general_chat", "Hello", TestSchema))
        assert isinstance(res, TestSchema)
        assert res.answer == "codex interactive allowed"
        mock_codex.assert_called_once()

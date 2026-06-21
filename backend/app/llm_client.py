"""
LLM Client abstraction layer with multi-provider routing, caching, and fallback.

Architecture:
    BaseLLMClient (abstract)
      → CodexCliClient      (Codex CLI subprocess)
      → GeminiClient         (Google Generative AI SDK)
      → OpenAIDirectClient   (LangChain ChatOpenAI)
      → MockLLMClient        (deterministic test responses)

    LLMRouterClient
      → reads task type
      → checks cache (llm_cache table)
      → chooses provider order from config
      → retries/fallbacks on error
      → logs result (llm_call_log table)
      → validates output
"""

import os
import json
import time
import hashlib
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app import config


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Structured error with a category for routing/fallback decisions."""
    def __init__(self, category: str, message: str):
        self.category = category
        self.message = message
        super().__init__(f"[{category}] {message}")


# Categories that should trigger fallback to the next provider
FALLBACK_CATEGORIES = {
    "rate_limit", "auth_lost", "timeout", "subprocess_crash",
    "empty_output", "invalid_json", "unknown",
}


# ---------------------------------------------------------------------------
# Base client interface
# ---------------------------------------------------------------------------

class BaseLLMClient(ABC):
    """Abstract base class. All providers expose the same interface."""

    provider_name: str = "base"

    @abstractmethod
    async def run_json(
        self, task: str, prompt: str, schema: type[BaseModel]
    ) -> BaseModel:
        """Execute a task/prompt and return a validated Pydantic model."""
        ...


# ---------------------------------------------------------------------------
# Codex CLI client (subprocess)
# ---------------------------------------------------------------------------

class CodexCliClient(BaseLLMClient):
    """Spawns the local Codex CLI as a subprocess."""

    provider_name = "codex"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
    ) -> BaseModel:
        cmd = ["codex", "run", "--task", task, "--prompt", prompt, "--format", "json"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=30.0
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise LLMError(
                    "timeout",
                    "Codex CLI execution timed out after 30 seconds.",
                )

            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()

            if proc.returncode != 0:
                if "rate limit" in stderr_str.lower():
                    raise LLMError("rate_limit", f"Codex CLI rate limit: {stderr_str}")
                elif any(
                    kw in stderr_str.lower()
                    for kw in ["auth", "login", "credentials", "api key"]
                ):
                    raise LLMError("auth_lost", f"Codex CLI auth failure: {stderr_str}")
                else:
                    raise LLMError(
                        "subprocess_crash",
                        f"Codex CLI exited with code {proc.returncode}: {stderr_str}",
                    )

            if not stdout_str:
                raise LLMError("empty_output", "Codex CLI returned empty output.")

            try:
                json_data = json.loads(stdout_str)
            except json.JSONDecodeError as je:
                if not is_retry:
                    repair_prompt = (
                        "The previous output was invalid JSON. "
                        "Please repair and output valid JSON matching the schema.\n\n"
                        f"Original Prompt:\n{prompt}\n\n"
                        f"Invalid Output:\n{stdout_str}"
                    )
                    return await self.run_json(task, repair_prompt, schema, is_retry=True)
                raise LLMError(
                    "invalid_json", f"Failed to parse JSON: {str(je)}"
                )

            try:
                return schema.model_validate(json_data)
            except Exception as ve:
                raise LLMError(
                    "invalid_json", f"Pydantic validation failed: {str(ve)}"
                )

        except (FileNotFoundError, ProcessLookupError):
            raise LLMError(
                "subprocess_crash",
                "'codex' command not found in PATH.",
            )
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(
                "unknown", f"Unexpected Codex CLI error: {str(e)}"
            )


# ---------------------------------------------------------------------------
# Gemini client (Google Generative AI SDK)
# ---------------------------------------------------------------------------

class GeminiClient(BaseLLMClient):
    """Uses the google-generativeai SDK."""

    provider_name = "gemini"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
    ) -> BaseModel:
        if not config.GEMINI_API_KEY:
            raise LLMError("auth_lost", "GEMINI_API_KEY is not configured.")

        try:
            import google.generativeai as genai

            genai.configure(api_key=config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.0-flash")

            # Build the JSON schema instruction from the Pydantic model
            schema_fields = schema.schema()
            schema_instruction = json.dumps(schema_fields, indent=2)

            full_prompt = (
                f"Task: {task}\n\n"
                f"{prompt}\n\n"
                "Return ONLY valid JSON matching this schema:\n"
                f"{schema_instruction}\n\n"
                "Output ONLY the JSON object, no markdown fences, no extra text."
            )

            response = await asyncio.to_thread(
                model.generate_content, full_prompt
            )

            response_text = response.text.strip()

            # Strip markdown fences if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                response_text = "\n".join(lines).strip()

            try:
                json_data = json.loads(response_text)
            except json.JSONDecodeError as je:
                if not is_retry:
                    repair_prompt = (
                        "The previous output was invalid JSON. "
                        "Please repair and output valid JSON matching the schema.\n\n"
                        f"Original Prompt:\n{prompt}\n\n"
                        f"Invalid Output:\n{response_text}"
                    )
                    return await self.run_json(task, repair_prompt, schema, is_retry=True)
                raise LLMError(
                    "invalid_json", f"Gemini JSON parse failed: {str(je)}"
                )

            try:
                return schema.model_validate(json_data)
            except Exception as ve:
                raise LLMError(
                    "invalid_json", f"Gemini Pydantic validation failed: {str(ve)}"
                )

        except LLMError:
            raise
        except ImportError:
            raise LLMError(
                "unknown",
                "google-generativeai package is not installed. Run: pip install google-generativeai",
            )
        except Exception as e:
            err_str = str(e).lower()
            if "rate limit" in err_str or "429" in err_str:
                raise LLMError("rate_limit", f"Gemini rate limit: {str(e)}")
            elif any(kw in err_str for kw in ["api key", "auth", "permission", "403"]):
                raise LLMError("auth_lost", f"Gemini auth failure: {str(e)}")
            else:
                raise LLMError("unknown", f"Gemini API error: {str(e)}")


# ---------------------------------------------------------------------------
# OpenAI Direct client (LangChain ChatOpenAI)
# ---------------------------------------------------------------------------

class OpenAIDirectClient(BaseLLMClient):
    """Uses LangChain's ChatOpenAI with structured output."""

    provider_name = "openai"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
    ) -> BaseModel:
        if not config.OPENAI_API_KEY:
            raise LLMError("auth_lost", "OPENAI_API_KEY is not configured.")

        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=config.OPENAI_API_KEY,
            )
            structured_llm = llm.with_structured_output(schema)
            response = await asyncio.to_thread(
                structured_llm.invoke,
                [
                    SystemMessage(content=f"You are a structured assistant. Task: {task}"),
                    HumanMessage(content=prompt),
                ],
            )
            return response
        except Exception as e:
            err_str = str(e).lower()
            if "rate limit" in err_str:
                raise LLMError("rate_limit", f"OpenAI rate limit: {str(e)}")
            elif any(kw in err_str for kw in ["api key", "auth", "invalid key"]):
                raise LLMError("auth_lost", f"OpenAI auth failure: {str(e)}")
            else:
                raise LLMError("unknown", f"OpenAI API error: {str(e)}")


# ---------------------------------------------------------------------------
# Mock client (deterministic responses for tests & offline mode)
# ---------------------------------------------------------------------------

class MockLLMClient(BaseLLMClient):
    """Returns deterministic Pydantic-valid responses for testing and offline use."""

    provider_name = "mock"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
    ) -> BaseModel:
        # Build a minimal valid instance from the schema's defaults/field info
        fields = schema.model_fields if hasattr(schema, "model_fields") else schema.__fields__
        defaults = {}
        for name, field in fields.items():
            default = field.default
            # Check for PydanticUndefined (no default set)
            has_default = default is not None and not _is_pydantic_undefined(default)
            if has_default:
                defaults[name] = default
            else:
                # Provide sensible type-based defaults
                annotation = field.annotation if hasattr(field, "annotation") else field.outer_type_
                defaults[name] = _default_for_type(annotation, name)

        return schema.model_validate(defaults)


def _is_pydantic_undefined(value) -> bool:
    """Check if a value is PydanticUndefined."""
    return type(value).__name__ == "PydanticUndefinedType" or str(value) == "PydanticUndefined"


def _default_for_type(annotation, field_name: str):
    """Returns a reasonable default value for a given type annotation."""
    import typing
    origin = getattr(annotation, "__origin__", None)

    if annotation == str or annotation is str:
        return f"mock_{field_name}"
    elif annotation == int or annotation is int:
        return 50
    elif annotation == float or annotation is float:
        return 0.5
    elif annotation == bool or annotation is bool:
        return True
    elif origin is list or (hasattr(annotation, "__origin__") and str(origin) == "typing.List"):
        return []
    elif origin is dict:
        return {}
    elif annotation is None or str(annotation) == "NoneType":
        return None

    # Try Literal — return the first allowed value
    args = getattr(annotation, "__args__", None)
    if args:
        for arg in args:
            if isinstance(arg, str):
                return arg
            if isinstance(arg, (int, float)):
                return arg

    return f"mock_{field_name}"


# ---------------------------------------------------------------------------
# Local Rules client (deterministic rule-based routing fallback)
# ---------------------------------------------------------------------------

class LocalRuleClient(BaseLLMClient):
    """Local rule-based router that classifies queries using keywords."""

    provider_name = "local"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
    ) -> BaseModel:
        if task == "route_query":
            # Extract query from prompt
            query = ""
            if "Query to route:" in prompt:
                query = prompt.split("Query to route:")[-1].strip()
            else:
                query = prompt

            # Basic keyword routing matching main.py regex router
            query_lower = query.lower().strip()
            rag_keywords = [
                "policy", "travel", "allowance", "hybrid", "schedule", "equipment", 
                "macbook", "laptop", "refresh", "reimburse", "meals", "office", "work"
            ]
            is_rag = any(kw in query_lower for kw in rag_keywords)
            route_val = "rag" if is_rag else "general"

            try:
                return schema.model_validate({"route": route_val, "reasoning": "Local rule-based routing."})
            except Exception as e:
                raise LLMError("invalid_json", f"Local routing schema mismatch: {e}")
        else:
            raise LLMError("rate_limit", f"Local rule client does not support task '{task}'")


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDER_REGISTRY = {
    "codex": CodexCliClient,
    "gemini": GeminiClient,
    "openai": OpenAIDirectClient,
    "mock": MockLLMClient,
    "local": LocalRuleClient,
}

# Task → config key mapping
_TASK_PROVIDER_MAP = {
    "route_query": "LLM_ROUTER_PROVIDER",
    "general_chat": "LLM_GENERAL_PROVIDER",
    "rag_chat": "LLM_RAG_PROVIDER",
    "extract_knowledge_graph": "LLM_KG_PROVIDER",
    "generate_visual_spec": "LLM_VISUAL_PROVIDER",
    "evaluate_mastery_response": "LLM_EVAL_PROVIDER",
}


def _get_provider_order(task: str) -> List[str]:
    """Returns the ordered list of provider names for a given task."""
    config_key = _TASK_PROVIDER_MAP.get(task, "LLM_GENERAL_PROVIDER")
    raw = getattr(config, config_key, "gemini,codex")
    providers = [p.strip() for p in raw.split(",") if p.strip()]
    # Filter to only providers that exist in the registry
    return [p for p in providers if p in _PROVIDER_REGISTRY]


# ---------------------------------------------------------------------------
# LLM Router Client — orchestrates provider selection, caching, fallback
# ---------------------------------------------------------------------------

class LLMRouterClient(BaseLLMClient):
    """
    Central LLM client that orchestrates:
    1. Cache lookup
    2. Provider selection per task
    3. Fallback on errors
    4. Response caching
    5. Call logging
    """

    provider_name = "router"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
    ) -> BaseModel:
        prompt_hash = hashlib.sha256(
            f"{task}:{prompt}:{schema.__name__}".encode()
        ).hexdigest()[:32]

        # 1. Check cache
        cached = self._cache_lookup(task, prompt_hash, schema.__name__)
        if cached is not None:
            self._log_call(task, "cache", True, 0, None, cache_hit=True)
            try:
                return schema.model_validate(json.loads(cached))
            except Exception:
                pass  # Cache entry invalid, proceed to providers

        # 2. Get provider order for this task
        providers = _get_provider_order(task)
        if not providers:
            providers = ["mock"]  # Ultimate fallback

        # 3. Try each provider in order
        last_error: Optional[LLMError] = None
        for provider_name in providers:
            client_cls = _PROVIDER_REGISTRY.get(provider_name)
            if not client_cls:
                continue

            client = client_cls()
            start_ms = int(time.time() * 1000)

            try:
                result = await client.run_json(task, prompt, schema)
                latency_ms = int(time.time() * 1000) - start_ms

                # Success — cache and log
                self._log_call(task, provider_name, True, latency_ms, None, cache_hit=False)
                result_json = result.model_dump_json() if hasattr(result, "model_dump_json") else json.dumps(result.model_dump() if hasattr(result, "model_dump") else result.dict())
                self._cache_store(task, prompt_hash, schema.__name__, result_json, provider_name)

                return result

            except LLMError as e:
                latency_ms = int(time.time() * 1000) - start_ms
                self._log_call(task, provider_name, False, latency_ms, e.category, cache_hit=False)
                last_error = e
                print(f"LLMRouter: {provider_name} failed for task '{task}': [{e.category}] {e.message}")

                if not config.ENABLE_LLM_FALLBACK:
                    raise
                if e.category not in FALLBACK_CATEGORIES:
                    raise
                continue  # Try next provider

            except Exception as e:
                latency_ms = int(time.time() * 1000) - start_ms
                self._log_call(task, provider_name, False, latency_ms, "unknown", cache_hit=False)
                last_error = LLMError("unknown", str(e))
                print(f"LLMRouter: {provider_name} unexpected error for task '{task}': {e}")

                if not config.ENABLE_LLM_FALLBACK:
                    raise last_error
                continue

        # 4. All providers failed
        if last_error:
            raise last_error
        raise LLMError("unknown", f"No providers available for task '{task}'")

    # --- Cache helpers (delegate to database module) ---

    @staticmethod
    def _cache_lookup(task: str, prompt_hash: str, schema_name: str) -> Optional[str]:
        try:
            from app import database
            return database.cache_lookup(task, prompt_hash, schema_name)
        except Exception:
            return None

    @staticmethod
    def _cache_store(task: str, prompt_hash: str, schema_name: str, response_json: str, provider: str):
        try:
            from app import database
            database.cache_store(task, prompt_hash, schema_name, response_json, provider)
        except Exception as e:
            print(f"LLMRouter: cache_store failed: {e}")

    @staticmethod
    def _log_call(task: str, provider: str, success: bool, latency_ms: int, error_category: Optional[str], cache_hit: bool = False):
        try:
            from app import database
            database.log_llm_call(task, provider, success, latency_ms, error_category, cache_hit)
        except Exception as e:
            print(f"LLMRouter: log_call failed: {e}")


# ---------------------------------------------------------------------------
# Utility: run async coroutine synchronously
# ---------------------------------------------------------------------------

def run_async(coro):
    """Safely runs an async coroutine synchronously even if an event loop is active."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

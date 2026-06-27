"""
LLM Client abstraction layer with multi-provider routing, caching, and fallback.

Architecture:
    BaseLLMClient (abstract)
      → CodexCliClient      (Codex CLI subprocess)
      → OpenRouterClient    (OpenRouter API Client)
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
from typing import Optional, List, Any, Dict
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

import uuid
from app import config
from app.observability import get_langfuse_client, flush_langfuse


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
    "empty_output", "invalid_json", "not_found", "unknown",
}


def _prompt_hash(task: str, prompt: str, schema: type[BaseModel]) -> str:
    return hashlib.sha256(f"{task}:{prompt}:{schema.__name__}".encode()).hexdigest()[:32]


def _debug_log_llm(
    task: str,
    provider: str,
    model: str,
    prompt: str,
    schema: type[BaseModel],
    raw_response: Any = None,
    parsed_response: Any = None,
    success: bool = False,
    error_category: str = None,
    error_message: str = None,
    cache_hit: bool = False,
):
    if not config.ENABLE_LLM_DEBUG_LOG:
        return
    try:
        parsed_text = None
        if parsed_response is not None:
            if hasattr(parsed_response, "model_dump_json"):
                parsed_text = parsed_response.model_dump_json()
            elif hasattr(parsed_response, "dict"):
                parsed_text = json.dumps(parsed_response.dict(), ensure_ascii=False)
            else:
                parsed_text = json.dumps(parsed_response, ensure_ascii=False, default=str)
        from app import database
        database.log_llm_debug(
            task=task,
            provider=provider,
            model=model,
            prompt_hash=_prompt_hash(task, prompt, schema),
            prompt=prompt,
            raw_response=raw_response,
            parsed_response=parsed_text,
            success=success,
            error_category=error_category,
            error_message=error_message,
            cache_hit=cache_hit,
        )
    except Exception as e:
        print(f"LLM debug hook failed: {e}")


# ---------------------------------------------------------------------------
# Base client interface
# ---------------------------------------------------------------------------

class BaseLLMClient(ABC):
    """Abstract base class. All providers expose the same interface."""

    provider_name: str = "base"
    model_name: str = "unknown"

    @abstractmethod
    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
    ) -> BaseModel:
        """Execute a task/prompt and return a validated Pydantic model."""
        ...


# ---------------------------------------------------------------------------
# Codex CLI client (subprocess)
# ---------------------------------------------------------------------------

class CodexCliClient(BaseLLMClient):
    """Spawns the local Codex CLI as a subprocess."""

    provider_name = "codex"
    model_name = "codex-cli"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
    ) -> BaseModel:
        # Initialize manual Langfuse trace generation if credentials exist
        lf_generation = None
        lf = get_langfuse_client()
        if lf:
            if not trace_id:
                trace_id = str(uuid.uuid4())
            try:
                lf_generation = lf.generation(
                    trace_id=trace_id,
                    name=f"codex-{task}",
                    model="codex-cli",
                    input=prompt,
                )
            except Exception as e:
                print(f"Error starting manual Langfuse generation: {e}")

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
                _debug_log_llm(
                    task, self.provider_name, self.model_name, prompt, schema,
                    raw_response=stdout_str, success=False,
                    error_category="invalid_json", error_message=str(je),
                )
                if not is_retry:
                    repair_prompt = (
                        "The previous output was invalid JSON. "
                        "Please repair and output valid JSON matching the schema.\n\n"
                        f"Original Prompt:\n{prompt}\n\n"
                        f"Invalid Output:\n{stdout_str}"
                    )
                    return await self.run_json(task, repair_prompt, schema, is_retry=True, trace_id=trace_id, callbacks=callbacks)
                raise LLMError(
                    "invalid_json", f"Failed to parse JSON: {str(je)}"
                )

            try:
                # Successfully executed
                parsed = schema.model_validate(json_data)
                if lf_generation:
                    try:
                        lf_generation.end(
                            output=stdout_str,
                            metadata={"status": "success"}
                        )
                        flush_langfuse()
                    except Exception:
                        pass
                _debug_log_llm(
                    task, self.provider_name, self.model_name, prompt, schema,
                    raw_response=stdout_str, parsed_response=parsed, success=True,
                )
                return parsed
            except Exception as ve:
                _debug_log_llm(
                    task, self.provider_name, self.model_name, prompt, schema,
                    raw_response=stdout_str, success=False,
                    error_category="invalid_json", error_message=str(ve),
                )
                raise LLMError(
                    "invalid_json", f"Pydantic validation failed: {str(ve)}"
                )

        except (FileNotFoundError, ProcessLookupError) as e:
            if lf_generation:
                try:
                    lf_generation.end(output=str(e), metadata={"status": "failed", "error_category": "subprocess_crash"})
                    flush_langfuse()
                except Exception:
                    pass
            raise LLMError(
                "subprocess_crash",
                "'codex' command not found in PATH.",
            )
        except LLMError as e:
            if lf_generation:
                try:
                    lf_generation.end(output=str(e), metadata={"status": "failed", "error_category": e.category})
                    flush_langfuse()
                except Exception:
                    pass
            raise
        except Exception as e:
            if lf_generation:
                try:
                    lf_generation.end(output=str(e), metadata={"status": "failed", "error_category": "unknown"})
                    flush_langfuse()
                except Exception:
                    pass
            raise LLMError(
                "unknown", f"Unexpected Codex CLI error: {str(e)}"
            )


# ---------------------------------------------------------------------------
# Gemini client removed.


# ---------------------------------------------------------------------------
# OpenAI Direct client (LangChain ChatOpenAI)
# ---------------------------------------------------------------------------

class OpenAIDirectClient(BaseLLMClient):
    """Uses LangChain's ChatOpenAI with structured output."""

    provider_name = "openai"
    model_name = "gpt-4o-mini"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
    ) -> BaseModel:
        if not config.OPENAI_API_KEY:
            raise LLMError("auth_lost", "OPENAI_API_KEY is not configured.")

        # Setup fallback callbacks for direct OpenAI execution if not provided but keys exist
        local_callbacks = callbacks
        if not local_callbacks and config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
            try:
                from langfuse.callback import CallbackHandler
                cb = CallbackHandler(
                    public_key=config.LANGFUSE_PUBLIC_KEY,
                    secret_key=config.LANGFUSE_SECRET_KEY,
                    host=config.LANGFUSE_HOST,
                    trace_id=trace_id or str(uuid.uuid4()),
                    tags=["manual-direct"]
                )
                local_callbacks = [cb]
            except Exception as e:
                print(f"Error initializing fallback Langfuse Callback: {e}")

        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=config.OPENAI_API_KEY,
            )
            structured_llm = llm.with_structured_output(schema)
            
            config_dict = {"callbacks": local_callbacks} if local_callbacks else {}
            
            response = await asyncio.to_thread(
                structured_llm.invoke,
                [
                    SystemMessage(content=f"You are a structured assistant. Task: {task}"),
                    HumanMessage(content=prompt),
                ],
                config_dict
            )
            _debug_log_llm(
                task, self.provider_name, self.model_name, prompt, schema,
                raw_response=response, parsed_response=response, success=True,
            )
            return response
        except Exception as e:
            err_str = str(e).lower()
            if "rate limit" in err_str:
                _debug_log_llm(task, self.provider_name, self.model_name, prompt, schema, success=False, error_category="rate_limit", error_message=str(e))
                raise LLMError("rate_limit", f"OpenAI rate limit: {str(e)}")
            elif any(kw in err_str for kw in ["api key", "auth", "invalid key"]):
                _debug_log_llm(task, self.provider_name, self.model_name, prompt, schema, success=False, error_category="auth_lost", error_message=str(e))
                raise LLMError("auth_lost", f"OpenAI auth failure: {str(e)}")
            else:
                _debug_log_llm(task, self.provider_name, self.model_name, prompt, schema, success=False, error_category="unknown", error_message=str(e))
                raise LLMError("unknown", f"OpenAI API error: {str(e)}")
        finally:
            if local_callbacks:
                for cb in local_callbacks:
                    if hasattr(cb, "langfuse") and hasattr(cb.langfuse, "flush"):
                        try:
                            cb.langfuse.flush()
                        except Exception:
                            pass


# ---------------------------------------------------------------------------
# OpenRouter client (OpenAI-compatible API with free model fallback)
# ---------------------------------------------------------------------------

class OpenRouterClient(BaseLLMClient):
    """Uses OpenRouter API (OpenAI-compatible) with free model fallback chain."""

    provider_name = "openrouter"
    model_name = "openai/gpt-oss-120b:free"

    # Task-specific fallback chains
    CODE_VIS_MODELS = [
        "openai/gpt-oss-120b:free",
        "qwen/qwen3-coder:free",
    ]
    EXTRACTION_MODELS = [
        "openai/gpt-oss-120b:free",
        "qwen/qwen3-coder:free",
    ]

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
    ) -> BaseModel:
        if not config.OPENROUTER_API_KEY:
            raise LLMError("auth_lost", "OPENROUTER_API_KEY is not configured.")

        from openai import OpenAI

        # Build JSON schema instruction from Pydantic model
        schema_fields = schema.schema()
        schema_instruction = json.dumps(schema_fields, indent=2)

        full_prompt = (
            f"Task: {task}\n\n"
            f"{prompt}\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            f"{schema_instruction}\n\n"
            "Output ONLY the JSON object, no markdown fences, no extra text."
        )

        # Select task-specific chain
        if task == "generate_visual_spec":
            models_to_try = list(self.CODE_VIS_MODELS)
        else:
            models_to_try = list(self.EXTRACTION_MODELS)

        # If a custom model is configured, put it first
        custom_model = config.OPENROUTER_MODEL
        if custom_model and custom_model not in models_to_try:
            models_to_try.insert(0, custom_model)

        def get_family_prefix(m_id: str) -> str:
            if "/" in m_id:
                return m_id.split("/")[0]
            return m_id

        failed_families = set()
        last_error = None
        for model_id in models_to_try:
            family = get_family_prefix(model_id)
            if family in failed_families:
                print(f"[OpenRouter] Skipping model '{model_id}' because family '{family}' is rate-limited.")
                continue

            # Initialize manual Langfuse trace generation
            lf_generation = None
            lf = get_langfuse_client()
            if lf:
                if not trace_id:
                    trace_id = str(uuid.uuid4())
                try:
                    lf_generation = lf.generation(
                        trace_id=trace_id,
                        name=f"openrouter-{task}",
                        model=model_id,
                        input=full_prompt,
                    )
                except Exception as e:
                    print(f"Error starting manual Langfuse generation: {e}")

            try:
                client = OpenAI(
                    base_url=config.OPENROUTER_BASE_URL,
                    api_key=config.OPENROUTER_API_KEY,
                    default_headers={
                        "HTTP-Referer": "https://paper-helper-agent.local",
                        "X-Title": "Paper Helper Agent",
                    },
                )

                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model_id,
                    messages=[
                        {"role": "system", "content": f"You are a structured JSON assistant. Task: {task}"},
                        {"role": "user", "content": full_prompt},
                    ],
                    temperature=0,
                    max_tokens=2048,
                )

                response_text = response.choices[0].message.content.strip()
                actual_model = model_id

                # Strip markdown fences if present
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    response_text = "\n".join(lines).strip()

                try:
                    json_data = json.loads(response_text)
                except json.JSONDecodeError as je:
                    _debug_log_llm(
                        task, self.provider_name, actual_model, prompt, schema,
                        raw_response=response_text, success=False,
                        error_category="invalid_json", error_message=str(je),
                    )
                    if lf_generation:
                        try:
                            lf_generation.end(
                                output=response_text,
                                metadata={"status": "failed", "error_category": "invalid_json", "model": actual_model},
                            )
                            flush_langfuse()
                        except Exception:
                            pass
                    last_error = LLMError(
                        "invalid_json", f"OpenRouter ({actual_model}) JSON parse failed: {str(je)}"
                    )
                    continue

                try:
                    parsed = schema.model_validate(json_data)
                    # Log success to Langfuse
                    if lf_generation:
                        try:
                            usage = {}
                            if response.usage:
                                usage = {
                                    "input": response.usage.prompt_tokens,
                                    "output": response.usage.completion_tokens,
                                    "total": response.usage.total_tokens,
                                }
                            lf_generation.end(
                                output=response_text,
                                metadata={
                                    "status": "success",
                                    "provider": "openrouter",
                                    "model": actual_model,
                                },
                                usage=usage,
                            )
                            flush_langfuse()
                        except Exception as e:
                            print(f"Error ending manual Langfuse generation: {e}")
                    _debug_log_llm(
                        task, self.provider_name, actual_model, prompt, schema,
                        raw_response=response_text, parsed_response=parsed, success=True,
                    )
                    self.model_name = actual_model  # Track which model was actually used
                    return parsed
                except Exception as ve:
                    _debug_log_llm(
                        task, self.provider_name, actual_model, prompt, schema,
                        raw_response=response_text, success=False,
                        error_category="invalid_json", error_message=str(ve),
                    )
                    if lf_generation:
                        try:
                            lf_generation.end(
                                output=response_text,
                                metadata={"status": "failed", "error_category": "invalid_json", "model": actual_model},
                            )
                            flush_langfuse()
                        except Exception:
                            pass
                    last_error = LLMError(
                        "invalid_json", f"OpenRouter ({actual_model}) Pydantic validation failed: {str(ve)}"
                    )
                    continue

            except LLMError:
                raise
            except Exception as e:
                err_str = str(e).lower()
                category = "unknown"
                if "rate limit" in err_str or "429" in err_str:
                    category = "rate_limit"
                elif any(kw in err_str for kw in ["api key", "auth", "permission", "403", "401"]):
                    category = "auth_lost"
                elif "timeout" in err_str:
                    category = "timeout"

                if lf_generation:
                    try:
                        lf_generation.end(
                            output=str(e),
                            metadata={"status": "failed", "error_category": category, "model": model_id},
                        )
                        flush_langfuse()
                    except Exception:
                        pass

                print(f"[OpenRouter] Model '{model_id}' failed: [{category}] {e}")
                last_error = LLMError(category, f"OpenRouter ({model_id}): {str(e)}")

                # If rate_limit or timeout, try next model in fallback chain
                if category in ("rate_limit", "timeout"):
                    if category == "rate_limit":
                        failed_families.add(family)
                    continue
                # For auth errors, no point trying other models
                if category == "auth_lost":
                    raise last_error
                # For unknown errors, try next model
                continue

        # All models in fallback chain failed
        if last_error:
            raise last_error
        raise LLMError("unknown", "OpenRouter: all models in fallback chain failed.")


# ---------------------------------------------------------------------------
# Groq client (OpenAI-compatible API with task-specific model fallback)
# ---------------------------------------------------------------------------

class GroqClient(BaseLLMClient):
    """Uses Groq's OpenAI-compatible API with task-specific model chains."""

    provider_name = "groq"
    model_name = "llama-3.1-8b-instant"

    GENERAL_MODELS = [
        "llama-3.1-8b-instant",
        "groq/compound-mini",
    ]
    EXTRACTION_MODELS = [
        "llama-3.1-8b-instant",
        "groq/compound-mini",
    ]
    CODE_VIS_MODELS = [
        "qwen/qwen3-32b",
        "qwen/qwen3.6-27b",
    ]
    EVAL_MODELS = [
        "llama-3.1-8b-instant",
        "groq/compound-mini",
    ]

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
    ) -> BaseModel:
        if not config.GROQ_API_KEY:
            raise LLMError("auth_lost", "GROQ_API_KEY is not configured.")

        from openai import OpenAI

        schema_instruction = json.dumps(schema.schema(), indent=2)
        full_prompt = (
            f"Task: {task}\n\n"
            f"{prompt}\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            f"{schema_instruction}\n\n"
            "Output ONLY the JSON object, no markdown fences, no extra text."
        )

        models_to_try = self._models_for_task(task)
        custom_model = config.GROQ_MODEL
        if custom_model and custom_model not in models_to_try:
            models_to_try.insert(0, custom_model)

        last_error = None
        for model_id in models_to_try:
            lf_generation = None
            lf = get_langfuse_client()
            if lf:
                if not trace_id:
                    trace_id = str(uuid.uuid4())
                try:
                    lf_generation = lf.generation(
                        trace_id=trace_id,
                        name=f"groq-{task}",
                        model=model_id,
                        input=full_prompt,
                    )
                except Exception as e:
                    print(f"Error starting Groq Langfuse generation: {e}")

            try:
                client = OpenAI(base_url=config.GROQ_BASE_URL, api_key=config.GROQ_API_KEY)
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=model_id,
                    messages=[
                        {"role": "system", "content": f"You are a structured JSON assistant. Task: {task}"},
                        {"role": "user", "content": full_prompt},
                    ],
                    temperature=0,
                    max_tokens=2048,
                )

                response_text = response.choices[0].message.content.strip()
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    lines = [line for line in lines if not line.strip().startswith("```")]
                    response_text = "\n".join(lines).strip()
                response_text = _extract_json_object(response_text)

                try:
                    json_data = json.loads(response_text)
                    parsed = schema.model_validate(json_data)
                except Exception as ve:
                    _debug_log_llm(
                        task, self.provider_name, model_id, prompt, schema,
                        raw_response=response_text, success=False,
                        error_category="invalid_json", error_message=str(ve),
                    )
                    if lf_generation:
                        try:
                            lf_generation.end(
                                output=response_text,
                                metadata={"status": "failed", "error_category": "invalid_json", "model": model_id},
                            )
                            flush_langfuse()
                        except Exception:
                            pass
                    last_error = LLMError("invalid_json", f"Groq ({model_id}) JSON validation failed: {ve}")
                    continue

                if lf_generation:
                    try:
                        usage = {}
                        if response.usage:
                            usage = {
                                "input": response.usage.prompt_tokens,
                                "output": response.usage.completion_tokens,
                                "total": response.usage.total_tokens,
                            }
                        lf_generation.end(
                            output=response_text,
                            metadata={"status": "success", "provider": "groq", "model": model_id},
                            usage=usage,
                        )
                        flush_langfuse()
                    except Exception as e:
                        print(f"Error ending Groq Langfuse generation: {e}")
                _debug_log_llm(
                    task, self.provider_name, model_id, prompt, schema,
                    raw_response=response_text, parsed_response=parsed, success=True,
                )
                self.model_name = model_id
                return parsed

            except Exception as e:
                err_str = str(e).lower()
                category = "unknown"
                if "rate limit" in err_str or "429" in err_str:
                    category = "rate_limit"
                elif any(kw in err_str for kw in ["api key", "auth", "permission", "403", "401"]):
                    category = "auth_lost"
                elif "not found" in err_str or "404" in err_str:
                    category = "not_found"
                elif "timeout" in err_str:
                    category = "timeout"

                if lf_generation:
                    try:
                        lf_generation.end(
                            output=str(e),
                            metadata={"status": "failed", "error_category": category, "model": model_id},
                        )
                        flush_langfuse()
                    except Exception:
                        pass

                print(f"[Groq] Model '{model_id}' failed: [{category}] {e}")
                last_error = LLMError(category, f"Groq ({model_id}): {e}")
                if category == "auth_lost":
                    raise last_error
                continue

        if last_error:
            raise last_error
        raise LLMError("unknown", "Groq: all models in fallback chain failed.")

    def _models_for_task(self, task: str) -> List[str]:
        if task == "generate_visual_spec" or task.startswith("generate_viz") or task.startswith("repair_viz"):
            return list(self.CODE_VIS_MODELS)
        if task == "evaluate_mastery_response" or "evaluate" in task:
            return list(self.EVAL_MODELS)
        if task in ("extract_knowledge_graph", "concept_detection") or "extract" in task or "detect" in task:
            return list(self.EXTRACTION_MODELS)
        return list(self.GENERAL_MODELS)


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start:end + 1]


# ---------------------------------------------------------------------------
# Mock client (deterministic responses for tests & offline mode)
# ---------------------------------------------------------------------------

class MockLLMClient(BaseLLMClient):
    """Returns deterministic Pydantic-valid responses for testing and offline use."""

    provider_name = "mock"
    model_name = "mock-offline"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        is_retry: bool = False,
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
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
    model_name = "regex-classifier"

    async def run_json(
        self,
        task: str,
        prompt: str,
        schema: type[BaseModel],
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
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
                "macbook", "laptop", "refresh", "reimburse", "meals", "office", "work",
                "section", "page", "document", "pdf", "file", "author", "paper", "writeup", "text"
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
    "groq": GroqClient,
    "openai": OpenAIDirectClient,
    "openrouter": OpenRouterClient,
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
    raw = getattr(config, config_key, "openrouter,codex")
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
        trace_id: str = "",
        callbacks: Optional[List[Any]] = None,
    ) -> BaseModel:
        prompt_hash = _prompt_hash(task, prompt, schema)

        # 1. Check cache
        cached = self._cache_lookup(task, prompt_hash, schema.__name__)
        if cached is not None:
            self._log_call(task, "cache", True, 0, None, cache_hit=True)
            print(f"[LLM Router] Cache hit for task '{task}'. Skipping provider call.")
            try:
                parsed = schema.model_validate(json.loads(cached))
                _debug_log_llm(
                    task, "cache", "cache", prompt, schema,
                    raw_response=cached, parsed_response=parsed,
                    success=True, cache_hit=True,
                )
                return parsed
            except Exception:
                pass  # Cache entry invalid, proceed to providers

        # 2. Get provider order for this task
        providers = _get_provider_order(task)
        if not providers:
            providers = ["mock"]  # Ultimate fallback

        # 3. Try each provider in order
        last_error: Optional[LLMError] = None
        for provider_name in providers:
            if provider_name == "codex":
                is_batch = (
                    task in ("extract_knowledge_graph", "concept_detection", "generate_visual_spec")
                    or "extract" in task
                    or "detect" in task
                    or "evaluate" in task
                )
                allowed = config.ENABLE_CODEX_FALLBACK_FOR_BATCH if is_batch else config.ENABLE_CODEX_FALLBACK_FOR_INTERACTIVE
                if not allowed:
                    print(f"[LLM Router] Skipping provider 'codex' for task '{task}' because fallback is disabled by config (is_batch={is_batch}).")
                    last_error = LLMError("codex_disabled", f"Codex fallback disabled by config for task '{task}'.")
                    continue

            client_cls = _PROVIDER_REGISTRY.get(provider_name)
            if not client_cls:
                continue

            client = client_cls()
            start_ms = int(time.time() * 1000)

            print(f"[LLM Router] Calling provider '{provider_name}' (model: '{client.model_name}') for task '{task}'...")
            try:
                result = await client.run_json(task, prompt, schema, trace_id=trace_id, callbacks=callbacks)
                latency_ms = int(time.time() * 1000) - start_ms

                print(f"[LLM Router] Provider '{provider_name}' (model: '{client.model_name}') succeeded in {latency_ms}ms.")
                # Success — cache and log
                self._log_call(task, provider_name, True, latency_ms, None, cache_hit=False)
                result_json = result.model_dump_json() if hasattr(result, "model_dump_json") else json.dumps(result.model_dump() if hasattr(result, "model_dump") else result.dict())
                self._cache_store(task, prompt_hash, schema.__name__, result_json, provider_name)

                return result

            except LLMError as e:
                latency_ms = int(time.time() * 1000) - start_ms
                self._log_call(task, provider_name, False, latency_ms, e.category, cache_hit=False)
                last_error = e
                print(f"[LLM Router] Provider '{provider_name}' (model: '{client.model_name}') failed in {latency_ms}ms: [{e.category}] {e.message}")

                if not config.ENABLE_LLM_FALLBACK:
                    raise
                if e.category not in FALLBACK_CATEGORIES:
                    raise
                continue  # Try next provider

            except Exception as e:
                latency_ms = int(time.time() * 1000) - start_ms
                self._log_call(task, provider_name, False, latency_ms, "unknown", cache_hit=False)
                last_error = LLMError("unknown", str(e))
                print(f"[LLM Router] Provider '{provider_name}' (model: '{client.model_name}') failed in {latency_ms}ms: [unknown] {e}")

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

import os
import json
import asyncio
import subprocess
from typing import Optional, Any
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app import config

class LLMError(Exception):
    def __init__(self, category: str, message: str):
        self.category = category
        self.message = message
        super().__init__(f"[{category}] {message}")

class LLMClient:
    async def run_json(self, task: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
        raise NotImplementedError

class CodexCliClient(LLMClient):
    async def run_json(self, task: str, prompt: str, schema: type[BaseModel], is_retry: bool = False) -> BaseModel:
        """
        Executes a task and prompt using the local Codex CLI as a subprocess.
        Validates the output against the specified Pydantic schema.
        Falls back to direct OpenAI API if the CLI is not installed locally.
        """
        # Command definition for the local Codex CLI
        cmd = ["codex", "run", "--task", task, "--prompt", prompt, "--format", "json"]

        try:
            # Spawn Codex CLI subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise LLMError("timeout", "Codex CLI execution timed out after 30 seconds.")

            stdout_str = stdout.decode().strip()
            stderr_str = stderr.decode().strip()

            if proc.returncode != 0:
                # Error classification
                if "rate limit" in stderr_str.lower():
                    raise LLMError("rate_limit", f"Codex CLI rate limit exceeded: {stderr_str}")
                elif any(kw in stderr_str.lower() for kw in ["auth", "login", "credentials", "api key"]):
                    raise LLMError("auth_lost", f"Codex CLI authentication failure: {stderr_str}")
                else:
                    raise LLMError("subprocess_crash", f"Codex CLI subprocess crashed with code {proc.returncode}: {stderr_str}")

            if not stdout_str:
                raise LLMError("empty_output", "Codex CLI returned empty output.")

            try:
                json_data = json.loads(stdout_str)
            except json.JSONDecodeError as je:
                if not is_retry:
                    # Self-repair attempt
                    repair_prompt = (
                        f"The previous output was invalid JSON. Please repair and output valid JSON matching the schema.\n\n"
                        f"Original Prompt:\n{prompt}\n\n"
                        f"Invalid Output:\n{stdout_str}"
                    )
                    return await self.run_json(task, repair_prompt, schema, is_retry=True)
                raise LLMError("invalid_json", f"Failed to parse Codex CLI output as JSON: {str(je)}")

            try:
                return schema.parse_obj(json_data)
            except Exception as ve:
                raise LLMError("invalid_json", f"Pydantic validation failed: {str(ve)}")

        except (FileNotFoundError, ProcessLookupError):
            # Graceful developer fallback if CLI is not present
            print("Warning: 'codex' command not found in PATH. Falling back to OpenAI API directly.")
            return await self._openai_fallback(task, prompt, schema, is_retry)
        except LLMError:
            raise
        except Exception as e:
            raise LLMError("unknown", f"An unexpected error occurred during Codex CLI execution: {str(e)}")

    async def _openai_fallback(self, task: str, prompt: str, schema: type[BaseModel], is_retry: bool = False) -> BaseModel:
        if not config.OPENAI_API_KEY:
            raise LLMError("auth_lost", "OpenAI API Key is not configured in .env.")

        try:
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=config.OPENAI_API_KEY)
            structured_llm = llm.with_structured_output(schema)
            response = await asyncio.to_thread(structured_llm.invoke, [
                SystemMessage(content=f"You are a structured assistant. Task: {task}"),
                HumanMessage(content=prompt)
            ])
            return response
        except Exception as e:
            err_str = str(e).lower()
            if "rate limit" in err_str:
                raise LLMError("rate_limit", f"OpenAI rate limit: {str(e)}")
            elif any(kw in err_str for kw in ["api key", "auth", "invalid key"]):
                raise LLMError("auth_lost", f"OpenAI authentication failed: {str(e)}")
            else:
                raise LLMError("unknown", f"OpenAI API error: {str(e)}")

def run_async(coro):
    """Safely runs an async coroutine synchronously even if an event loop is active."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

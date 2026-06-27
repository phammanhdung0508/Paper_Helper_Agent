#!/usr/bin/env python3
"""Probe configured LLM providers/models with a tiny JSON completion.

Examples:
    python scripts/test_llm_models.py --provider groq
    python scripts/test_llm_models.py --provider openrouter
    python scripts/test_llm_models.py --provider all --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


OPENROUTER_MODELS = [
    "openai/gpt-oss-120b:free",
    "qwen/qwen3-coder:free",
]

OPENAI_MODELS = [
    "gpt-4o-mini",
]

DEFAULT_TIMEOUT = 30.0


@dataclass
class ModelProbe:
    provider: str
    model: str
    status: str
    latency_ms: int | None = None
    detail: str = ""


def classify_http_error(status_code: int, text: str) -> str:
    if status_code == 401:
        return "AUTH_ERROR"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 429:
        return "RATE_LIMIT"
    if 500 <= status_code <= 599:
        return "UPSTREAM_ERROR"
    if "rate" in text.lower() and "limit" in text.lower():
        return "RATE_LIMIT"
    return f"HTTP_{status_code}"


def short_detail(text: str, max_len: int = 160) -> str:
    text = " ".join(text.strip().split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def list_groq_models(api_key: str, base_url: str, timeout: float) -> list[str]:
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        print(f"Groq model discovery failed: {exc}", file=sys.stderr)
        return []

    if response.status_code != 200:
        print(
            f"Groq model discovery failed: {response.status_code} {short_detail(response.text)}",
            file=sys.stderr,
        )
        return []

    data = response.json()
    models = [item.get("id") for item in data.get("data", []) if item.get("id")]
    return sorted(set(models))


def probe_chat_completion(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float,
) -> ModelProbe:
    if not api_key:
        return ModelProbe(provider, model, "NO_API_KEY")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": 'Return exactly this JSON object: {"ok": true}'},
        ],
        "temperature": 0,
        "max_tokens": 32,
    }

    if provider == "openrouter":
        payload["response_format"] = {"type": "json_object"}

    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://paper-helper-agent.local",
                "X-Title": "Paper Helper Agent Model Probe",
            },
            json=payload,
            timeout=timeout,
        )
    except httpx.TimeoutException:
        return ModelProbe(provider, model, "TIMEOUT", int((time.perf_counter() - started) * 1000))
    except httpx.HTTPError as exc:
        return ModelProbe(provider, model, "NETWORK_ERROR", int((time.perf_counter() - started) * 1000), str(exc))

    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        return ModelProbe(
            provider,
            model,
            classify_http_error(response.status_code, response.text),
            latency_ms,
            short_detail(response.text),
        )

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        parsed = json.loads(extract_json_object(strip_code_fence(content)))
    except Exception as exc:
        detail = str(exc)
        if "content" in locals():
            detail = f"{detail}; content={short_detail(content)}"
        return ModelProbe(provider, model, "BAD_JSON", latency_ms, short_detail(detail))

    if parsed.get("ok") is True:
        return ModelProbe(provider, model, "OK", latency_ms)
    return ModelProbe(provider, model, "WRONG_OUTPUT", latency_ms, short_detail(json.dumps(parsed)))


def strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
    return "\n".join(lines).strip()


def extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def print_results(results: list[ModelProbe]) -> None:
    provider_width = max([len("Provider")] + [len(r.provider) for r in results])
    model_width = max([len("Model")] + [len(r.model) for r in results])
    status_width = max([len("Status")] + [len(r.status) for r in results])
    print(
        f"{'Provider':<{provider_width}}  {'Model':<{model_width}}  "
        f"{'Status':<{status_width}}  Latency  Detail"
    )
    print("-" * (provider_width + model_width + status_width + 28))
    for result in results:
        latency = f"{result.latency_ms}ms" if result.latency_ms is not None else "-"
        print(
            f"{result.provider:<{provider_width}}  {result.model:<{model_width}}  "
            f"{result.status:<{status_width}}  {latency:<7}  {result.detail}"
        )


def parse_models_arg(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Test configured LLM models for availability.")
    parser.add_argument("--provider", choices=["all", "groq", "openrouter", "openai"], default="all")
    parser.add_argument("--models", help="Comma-separated model list. Overrides provider defaults/discovery.")
    parser.add_argument("--limit", type=int, default=0, help="Limit discovered models per provider, mainly for Groq.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()

    results: list[ModelProbe] = []
    explicit_models = parse_models_arg(args.models)

    if args.provider in ("all", "groq"):
        groq_key = os.getenv("GROQ_API_KEY", "")
        groq_base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        groq_models = explicit_models or parse_models_arg(os.getenv("GROQ_MODELS"))
        if not groq_models and groq_key:
            groq_models = list_groq_models(groq_key, groq_base, args.timeout)
        if args.limit and groq_models:
            groq_models = groq_models[: args.limit]
        if not groq_models:
            groq_models = [os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")]
        results.extend(probe_chat_completion("groq", groq_base, groq_key, model, args.timeout) for model in groq_models)

    if args.provider in ("all", "openrouter"):
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        openrouter_base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        openrouter_models = explicit_models or parse_models_arg(os.getenv("OPENROUTER_MODELS")) or OPENROUTER_MODELS
        results.extend(
            probe_chat_completion("openrouter", openrouter_base, openrouter_key, model, args.timeout)
            for model in openrouter_models
        )

    if args.provider in ("all", "openai"):
        openai_key = os.getenv("OPENAI_API_KEY", "")
        openai_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        openai_models = explicit_models or parse_models_arg(os.getenv("OPENAI_MODELS")) or OPENAI_MODELS
        results.extend(probe_chat_completion("openai", openai_base, openai_key, model, args.timeout) for model in openai_models)

    print_results(results)
    return 0 if any(result.status == "OK" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

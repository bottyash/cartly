"""
LLM Gateway — OpenRouter, v1.0 Production.

Replaces the local Ollama gateway with OpenRouter's cloud inference.
Uses the OpenAI-compatible SDK with a custom base_url — zero code
changes needed in agents; swap is transparent via env vars.

Env vars:
  OPENROUTER_API_KEY   — required, get at https://openrouter.ai
  OPENROUTER_MODEL     — default: meta-llama/llama-3.2-3b-instruct
  OPENROUTER_BASE_URL  — default: https://openrouter.ai/api/v1
  OPENROUTER_SITE_URL  — sent as HTTP-Referer (for OpenRouter leaderboard)
  OPENROUTER_SITE_NAME — sent as X-Title

Fall-back: if OPENROUTER_API_KEY is unset, raises LLMGatewayError
with a clear message instead of crashing silently.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import openai

# ── Config ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY   = os.getenv("OPENROUTER_API_KEY",   "")
OPENROUTER_MODEL     = os.getenv("OPENROUTER_MODEL",     "meta-llama/llama-3.2-3b-instruct")
OPENROUTER_BASE_URL  = os.getenv("OPENROUTER_BASE_URL",  "https://openrouter.ai/api/v1")
OPENROUTER_SITE_URL  = os.getenv("OPENROUTER_SITE_URL",  "http://localhost:3000")
OPENROUTER_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", "Cartly")

MAX_RETRIES  = 2
RETRY_DELAYS = [1.0, 2.5, 5.0]   # seconds between retries (exponential-ish)
TIMEOUT_S    = 90.0               # per-request timeout

# ── Client factory (lazy, one per process) ────────────────────────────────
_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        if not OPENROUTER_API_KEY:
            raise LLMGatewayError(
                "OPENROUTER_API_KEY is not set. "
                "Add it to .env — get a free key at https://openrouter.ai"
            )
        _client = openai.OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            timeout=TIMEOUT_S,
            default_headers={
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title":      OPENROUTER_SITE_NAME,
            },
        )
    return _client


# ── Errors ────────────────────────────────────────────────────────────────
class LLMGatewayError(Exception):
    """Raised when the gateway fails after all retries."""


# ── JSON extraction ───────────────────────────────────────────────────────
def _extract_json(text: str) -> dict:
    """
    Parse JSON from model response, handling markdown code fences and
    leading/trailing prose that some models add despite JSON mode.
    """
    text = text.strip()
    # Try raw JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Find first { ... } block
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise json.JSONDecodeError("No JSON object found", text, 0)


# ── Public interface ──────────────────────────────────────────────────────
def call_llm(
    system_prompt: str,
    user_prompt: str,
    expect_json: bool = True,
) -> tuple[dict[str, Any] | str, int, float]:
    """
    Call OpenRouter with retry + back-off.

    Returns:
        (parsed_dict, total_tokens, latency_ms)   when expect_json=True
        (raw_string,  total_tokens, latency_ms)   when expect_json=False
    Raises:
        LLMGatewayError: after MAX_RETRIES failures
    """
    client = _get_client()

    # NOTE: llama-3.2-3b-instruct (and most open models on OpenRouter) do NOT
    # support response_format={"type":"json_object"} — it silently returns empty
    # content. We append an explicit JSON instruction to the system prompt instead;
    # _extract_json() handles fences + prose wrapping returned by the model.
    effective_system = (
        system_prompt + "\n\nIMPORTANT: Respond with a single valid JSON object only. No prose, no markdown fences."
        if expect_json else system_prompt
    )

    messages = [
        {"role": "system", "content": effective_system},
        {"role": "user",   "content": user_prompt},
    ]

    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.1,
                max_tokens=1024,
            )
            latency_ms = (time.perf_counter() - t0) * 1000

            content = resp.choices[0].message.content or ""
            usage   = resp.usage
            tokens  = (usage.total_tokens if usage else 0)

            if expect_json:
                return _extract_json(content), tokens, latency_ms
            return content, tokens, latency_ms

        except openai.RateLimitError as exc:
            last_exc = exc
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            time.sleep(delay)

        except openai.APITimeoutError as exc:
            last_exc = exc
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            time.sleep(delay)

        except openai.APIStatusError as exc:
            last_exc = exc
            if exc.status_code and exc.status_code < 500:
                break   # 4xx — no point retrying
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            time.sleep(delay)

        except (json.JSONDecodeError, IndexError) as exc:
            last_exc = exc
            # Retry once — model may have wrapped JSON in prose on first attempt
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            time.sleep(delay)

    raise LLMGatewayError(
        f"OpenRouter call failed after {attempt + 1} attempt(s). "
        f"Model: {OPENROUTER_MODEL}. Last error: {last_exc}"
    ) from last_exc

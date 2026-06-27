"""
llm_client.py
-------------
Minimal stand-in for the LiteLLM gateway described in PDLC Stage 3 (3.4 LLM
Gateway Design): a single point every model call passes through. A full
gateway (provider fallback, rate limiting, retries) is out of scope for a
one-week POC; what's preserved here is the *interface* -- callers never
talk to a provider SDK directly, they call `call_llm()`.

Two modes:
  - LIVE mode: if ANTHROPIC_API_KEY is set in the environment and the
    `anthropic` package is installed, calls the real Anthropic API.
  - MOCK mode: otherwise, returns a deterministic templated response so
    the POC and ticket_demo run end-to-end with zero setup. Mock responses
    are clearly labeled and still reference the real retrieved policy
    context passed in, so the Safety Critic's groundedness check exercises
    real logic even offline.

Set CARTLY_FORCE_MOCK=1 to force mock mode even with a key present
(useful for fast, free demo runs).
"""

import os

_LIVE_MODE = False
_client = None

if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("CARTLY_FORCE_MOCK"):
    try:
        import anthropic
        _client = anthropic.Anthropic()
        _LIVE_MODE = True
    except ImportError:
        _LIVE_MODE = False


def is_live() -> bool:
    return _LIVE_MODE


def call_llm(system: str, prompt: str, model: str = "claude-haiku-4-5-20251001",
             max_tokens: int = 400):
    """Returns (text, tokens_in, tokens_out)."""
    if _LIVE_MODE:
        resp = _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return text, resp.usage.input_tokens, resp.usage.output_tokens

    # ---- MOCK MODE ----
    text = _mock_response(system, prompt)
    tokens_in = max(len(system.split()) + len(prompt.split()), 1)
    tokens_out = max(len(text.split()), 1)
    return text, tokens_in, tokens_out


def _mock_response(system: str, prompt: str) -> str:
    """Deterministic, content-aware mock so offline demo output is still
    coherent and groundable, rather than lorem-ipsum filler."""
    lower_prompt = prompt.lower()

    if "draft a refund approval" in lower_prompt:
        # Extract a policy ID if one was embedded in the prompt context.
        cite = "POL-RETURN-WINDOW"
        if "pol-damaged" in lower_prompt:
            cite = "POL-DAMAGED-DEFECTIVE"
        return (
            "[MOCK] Good news -- your refund has been approved and is being "
            f"processed now. Per our return policy ({cite}), this item qualifies, "
            "and the amount will be credited to your original payment method "
            "within 3-5 business days."
        )

    if "draft a refund decline" in lower_prompt:
        cite = "POL-NON-RETURNABLE"
        if "outside" in lower_prompt or "window" in lower_prompt:
            cite = "POL-RETURN-WINDOW"
        return (
            "[MOCK] I've reviewed your refund request. Unfortunately this item "
            f"isn't eligible under our current policy ({cite}). I'm sorry for the "
            "inconvenience -- if you believe this was a defective or wrong item, "
            "let me know and I can take another look."
        )

    if "classify" in lower_prompt:
        return "refund_request"

    return "[MOCK] Acknowledged."

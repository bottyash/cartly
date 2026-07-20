"""
Policy Knowledge Base — keyword-matched retrieval over policy_chunks.json.

Stands in for a vector store in Sprint 1 (per PDLC: vector store is a Stage-5 component).

Provides:
  policy_retrieval(query, category) -> list[dict]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CHUNKS_PATH = Path(__file__).parent / "policy_chunks.json"

# Load once at import time
with open(_CHUNKS_PATH) as _f:
    _CHUNKS: list[dict[str, Any]] = json.load(_f)

# Keywords that always trigger immediate escalation (kill-switch list)
HARD_TRIGGER_KEYWORDS = [
    "fraud", "lawyer", "legal", "court", "sue", "lawsuit",
    "police", "crime", "chargeback", "consumer court",
]


def policy_retrieval(query: str, category: str | None = None) -> list[dict[str, Any]]:
    """
    Return matching policy chunks for a given query string + optional category.

    Matching strategy:
      1. Keyword overlap scoring (substring match, not word-boundary).
      2. Category-based fallback — if triage provided a category, we inject
         the most relevant policy for that category even if no keywords matched.
      3. Return top-3 by score, deduplicated.

    Never fabricates — returns [] only when genuinely nothing matches.
    """
    query_lower = query.lower()

    # ── Category → policy mapping (deterministic fallback) ───────────────
    CATEGORY_POLICIES = {
        "general_return":         ["POL-004", "POL-010"],
        "damaged_goods":          ["POL-001"],
        "electronics_return":     ["POL-003", "POL-004"],
        "non_delivery":           ["POL-002"],
        "delivery_status":        ["POL-006"],
        "exchange":                ["POL-007"],
        "warranty":               ["POL-008"],
        "cancellation":           ["POL-009"],
        "quality_issue":          ["POL-001", "POL-004"],
        "complaint":              ["POL-004"],
        "other":                  ["POL-004"],
    }

    scored: dict[str, tuple[int, dict[str, Any]]] = {}

    # ── Step 1: Keyword scoring ───────────────────────────────────────────
    for chunk in _CHUNKS:
        if chunk["id"] == "POL-005":  # handled by hard-trigger
            continue
        kw_score = sum(1 for kw in chunk["keywords"] if kw in query_lower)
        if kw_score > 0:
            scored[chunk["id"]] = (kw_score, chunk)

    # ── Step 2: Category fallback ─────────────────────────────────────────
    if category and category in CATEGORY_POLICIES:
        fallback_ids = CATEGORY_POLICIES[category]
        for fid in fallback_ids:
            if fid not in scored:
                chunk = get_chunk_by_id(fid)
                if chunk:
                    scored[fid] = (0, chunk)  # score=0 so keyword matches rank higher

    # ── Step 3: Generic "refund" intent fallback ──────────────────────────
    # If the query contains refund/return/money-back but nothing matched,
    # inject POL-004 (General 30-Day Return Window) as the safe default.
    REFUND_SIGNALS = ["refund", "money back", "reimburs", "return", "give back", "want back"]
    if not scored and any(sig in query_lower for sig in REFUND_SIGNALS):
        chunk = get_chunk_by_id("POL-004")
        if chunk:
            scored["POL-004"] = (1, chunk)
        chunk2 = get_chunk_by_id("POL-010")
        if chunk2:
            scored["POL-010"] = (1, chunk2)

    # ── Step 4: Sort and return top-3 ────────────────────────────────────
    sorted_chunks = sorted(scored.values(), key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in sorted_chunks[:3]]


def check_hard_triggers(text: str) -> list[str]:
    """
    Check whether the ticket text contains any hard-trigger legal/fraud keywords.
    Returns the list of matched keywords (empty if none).
    """
    text_lower = text.lower()
    return [kw for kw in HARD_TRIGGER_KEYWORDS if kw in text_lower]


def get_chunk_by_id(chunk_id: str) -> dict[str, Any] | None:
    """Fetch a specific policy chunk by its ID (used by Safety Critic for re-verification)."""
    for chunk in _CHUNKS:
        if chunk["id"] == chunk_id:
            return chunk
    return None

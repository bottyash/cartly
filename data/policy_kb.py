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
    Return matching policy chunks for a given query string.

    Matching strategy (simple keyword overlap):
      1. Tokenise query into lowercase words.
      2. Score each chunk by how many of its keywords appear in the query.
      3. Return chunks with score > 0, sorted by score descending (top-k=3).

    Returns an empty list when no chunk matches — the calling agent must
    abstain and escalate rather than fabricate a policy claim.
    """
    query_lower = query.lower()
    query_words = set(query_lower.replace(",", " ").replace(".", " ").split())

    scored: list[tuple[int, dict[str, Any]]] = []
    for chunk in _CHUNKS:
        # Skip legal escalation chunk — handled separately by hard-trigger check
        if chunk["id"] == "POL-005":
            continue
        score = sum(1 for kw in chunk["keywords"] if kw in query_lower)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:3]]


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

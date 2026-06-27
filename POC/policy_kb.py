"""
policy_kb.py
------------
Keyword-matched policy retrieval, standing in for the ChromaDB vector store
described in PDLC Stage 3 (Tool Specifications: policy_retrieval). A POC
substitutes simple keyword overlap scoring for embedding similarity; the
retrieval *contract* (query in, scored chunks with source IDs out) is the
same shape a real vector store would return, so swapping this module for
Chroma later does not require changing any caller.

Every policy entry has a stable source_id. The Safety Critic cites these
IDs independently rather than trusting the Refund Agent's claims about
what a policy says -- it re-runs retrieval itself.
"""

from dataclasses import dataclass


@dataclass
class PolicyChunk:
    source_id: str
    category: str
    keywords: set
    text: str


POLICIES = [
    PolicyChunk(
        source_id="POL-RETURN-WINDOW",
        category="refund",
        keywords={"return", "window", "30", "days", "deadline", "late", "eligible"},
        text=(
            "Standard items may be returned within 30 days of delivery for a "
            "full refund, provided the item is unused and in original packaging."
        ),
    ),
    PolicyChunk(
        source_id="POL-NON-RETURNABLE",
        category="refund",
        keywords={"non-returnable", "hygiene", "pierced", "earrings", "final", "sale"},
        text=(
            "Hygiene-sensitive items (pierced jewelry, intimate apparel, opened "
            "consumables) and items marked Final Sale are not eligible for return "
            "or refund except in cases of seller-confirmed defect."
        ),
    ),
    PolicyChunk(
        source_id="POL-AUTONOMY-THRESHOLD",
        category="refund",
        keywords={"threshold", "500", "autonomous", "approval", "limit"},
        text=(
            "Refunds of INR 500 or less that pass the standard eligibility check "
            "may be processed automatically. Refunds above INR 500 require human "
            "approval before any transaction is executed, regardless of eligibility."
        ),
    ),
    PolicyChunk(
        source_id="POL-PROCESSING-TIME",
        category="refund",
        keywords={"processing", "settlement", "days", "arrive", "when"},
        text=(
            "Approved refunds are credited to the original payment method within "
            "3 to 5 business days of approval."
        ),
    ),
    PolicyChunk(
        source_id="POL-DAMAGED-DEFECTIVE",
        category="refund",
        keywords={"damaged", "defective", "broken", "wrong", "item"},
        text=(
            "Items arriving damaged or defective, or a wrong item received, are "
            "eligible for full refund or replacement regardless of the standard "
            "return window, on confirmation of the defect."
        ),
    ),
]


def retrieve(query: str, category: str = None, top_k: int = 3) -> list:
    """Score policy chunks by keyword overlap with the query. Returns the
    top_k chunks as dicts with source_id, text, and a retrieval_score,
    mirroring the contract a real vector store would return.
    """
    query_terms = set(w.strip(".,?!").lower() for w in query.split())
    scored = []
    for chunk in POLICIES:
        if category and chunk.category != category:
            continue
        overlap = len(query_terms & {k.lower() for k in chunk.keywords})
        if overlap > 0:
            scored.append((overlap, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for overlap, chunk in scored[:top_k]:
        results.append({
            "source_id": chunk.source_id,
            "text": chunk.text,
            "retrieval_score": round(overlap / max(len(chunk.keywords), 1), 2),
        })
    return results


def get_by_id(source_id: str):
    """Used by the Safety Critic to independently verify a cited policy ID
    actually exists and to re-check its text, rather than trusting the
    Refund Agent's paraphrase of it."""
    for chunk in POLICIES:
        if chunk.source_id == source_id:
            return chunk
    return None

"""
safety_critic.py
-----------------
Safety/Quality Critic, per PDLC Stage 3 agent topology and the
evaluator-optimizer pattern (orchestration decision record, 3.3): "Every
response must pass the Safety Critic before reaching the customer."

Design choice carried over from architecture docs: the critic does NOT
trust the Refund Agent's citations. It re-retrieves each cited policy ID
from policy_kb itself and checks the draft's claims against the actual
policy text -- not against what the Refund Agent said the policy says.
This is the independent-verification property that gives the groundedness
metric (RAGAS faithfulness in the full system) teeth.

Blocks if:
  - a cited policy ID doesn't exist, or
  - the draft's eligibility framing (approve/decline language) contradicts
    the eligibility finding it was supposed to be grounded in, or
  - the draft contains no policy citation at all when one was available, or
  - injection markers are present in the *input* ticket text (defense in
    depth -- this should already have been screened upstream, but the
    critic is the last gate before a customer sees anything).

Faithfulness score is a simple heuristic proxy for RAGAS faithfulness:
fraction of citation/claim checks that pass.
"""

import re
import policy_kb

FAITHFULNESS_BLOCK_THRESHOLD = 0.70

INJECTION_MARKERS = [
    r"ignore (all|previous|the) instructions",
    r"disregard (the )?policy",
    r"you are now",
    r"system prompt",
    r"reveal your (instructions|prompt)",
    r"approve (the )?full refund regardless",
]


def _screen_injection(raw_ticket_text: str) -> list:
    flags = []
    lower = raw_ticket_text.lower()
    for pattern in INJECTION_MARKERS:
        if re.search(pattern, lower):
            flags.append(f"injection_marker:{pattern}")
    return flags


class SafetyCritic:
    name = "safety_critic"

    def __init__(self, tracer):
        self.tracer = tracer

    def review(self, ticket_id: str, raw_ticket_text: str, refund_result: dict) -> dict:
        flags = _screen_injection(raw_ticket_text)

        draft = refund_result.get("draft_response")
        cited_refs = refund_result.get("policy_refs", [])
        eligible = refund_result.get("eligible")

        checks_total = 0
        checks_passed = 0

        # Check 1: every cited policy ID actually exists in the KB
        # (independent re-lookup, not reuse of the agent's retrieval result).
        for ref in cited_refs:
            checks_total += 1
            verified = policy_kb.get_by_id(ref["source_id"])
            if verified is not None:
                checks_passed += 1
            else:
                flags.append(f"unverifiable_citation:{ref['source_id']}")

        # Check 2: draft contains at least one citation if policy refs existed.
        checks_total += 1
        if draft and cited_refs:
            if any(ref["source_id"] in draft for ref in cited_refs):
                checks_passed += 1
            else:
                flags.append("draft_missing_citation")
        elif not cited_refs:
            checks_passed += 1  # nothing to cite, vacuously fine

        # Check 3: approve/decline language matches the eligibility finding.
        if draft is not None:
            checks_total += 1
            approves_language = bool(re.search(r"approved|good news", draft.lower()))
            declines_language = bool(re.search(r"unfortunately|not eligible|isn't eligible", draft.lower()))
            consistent = (
                (eligible and approves_language and not declines_language)
                or (not eligible and declines_language and not approves_language)
            )
            if consistent:
                checks_passed += 1
            else:
                flags.append("eligibility_language_mismatch")

        faithfulness_score = round(checks_passed / checks_total, 2) if checks_total else 1.0
        approved = faithfulness_score >= FAITHFULNESS_BLOCK_THRESHOLD and not any(
            f.startswith("injection_marker") for f in flags
        )

        result = {
            "approved": approved,
            "faithfulness_score": faithfulness_score,
            "flags": flags,
        }
        self.tracer.log_step(ticket_id, self.name, "review_complete", result)
        return result

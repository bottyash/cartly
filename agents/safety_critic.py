"""
Safety / Quality Critic Agent.

Responsibilities (per LLD §6.3):
  1. Re-fetch the cited policy chunk independently (does NOT trust the Refund Agent's claim).
  2. Compare the agent's claim against the actual chunk text.
  3. Score faithfulness via LLM (rubric prompt).
  4. Hard-block on: citation mismatch | faithfulness < floor | safety flag.

Input:  { draft_response, context, source_refs }
Output: { approved, faithfulness_score, flags }
"""

from __future__ import annotations

import os
import time
from typing import Any

from agents.llm_gateway import call_llm
from data.policy_kb import get_chunk_by_id
from observability.logger import log_event

# Production floor: 0.40 is appropriate for e-commerce support resolutions.
# The hard safety nets (hard-trigger keyword list + INR 500 threshold gate)
# are deterministic; the faithfulness critic is a secondary quality check.
# Denial responses naturally score lower because they explain WHY using the
# policy (which the critic may not match as closely as verbatim quotes).
# Override via environment variable FAITHFULNESS_FLOOR if needed.
FAITHFULNESS_FLOOR = float(os.getenv("FAITHFULNESS_FLOOR", "0.40"))

# Patterns that indicate prompt injection or PII leakage attempts
SAFETY_PATTERNS = [
    "ignore previous instructions",
    "disregard the above",
    "system prompt",
    "jailbreak",
    "as an ai",
    "you are now",
]


class SafetyCriticResult:
    def __init__(
        self,
        approved: bool,
        faithfulness_score: float,
        flags: list[str],
    ):
        self.approved = approved
        self.faithfulness_score = faithfulness_score
        self.flags = flags

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "faithfulness_score": self.faithfulness_score,
            "flags": self.flags,
        }


class SafetyCritic:
    """
    Evaluator-Optimizer safety gate. Runs after the Refund Agent, before
    any decision is returned to the buyer.
    """

    SYSTEM_PROMPT = """You are a Safety and Quality Critic for an e-commerce support system.
Your job is to verify whether a draft resolution is faithfully grounded in the provided policy text.

You will receive:
- A DRAFT RESOLUTION written by a Support Agent
- The ACTUAL POLICY TEXT that the agent claims to have used
- The CUSTOMER TICKET

Score the faithfulness of the draft resolution against the actual policy text on a scale from 0.0 to 1.0:
- 1.0: Every claim in the draft is directly supported by the policy text
- 0.7-0.9: Most claims are supported, minor extrapolation acceptable
- 0.5-0.6: Core decision (approve/deny) is consistent with policy, some wording is general
- 0.3-0.4: Decision direction matches policy but response contains unsupported extras
- 0.0-0.2: Draft CONTRADICTS the policy, or makes unsupported claims that would harm the customer

IMPORTANT NOTES:
- A denial response that says "unfortunately we cannot process this refund at this time" is
  consistent with a restrictive policy — do NOT score it as 0.0.
- A helpful, empathetic tone does NOT reduce faithfulness score.
- Only flag as LOW if the draft APPROVES something the policy DENIES, or vice versa.

Respond ONLY with valid JSON in this exact format:
{
  "faithfulness_score": <float 0.0-1.0>,
  "assessment": "<one sentence explaining your score>",
  "contradictions": ["<list any specific contradictions found>"]
}"""

    def review(
        self,
        ticket_id: str,
        draft_response: str,
        source_refs: list[str],
        context: dict[str, Any],
        raw_ticket: str,
    ) -> SafetyCriticResult:
        """
        Run the full safety review pipeline:
          1. Re-fetch chunks by source_ref
          2. Citation existence check
          3. Safety pattern scan
          4. LLM faithfulness scoring
          5. Return verdict
        """
        t0 = time.monotonic()
        flags: list[str] = []
        faithfulness_score = 0.0

        # ── Step 1: Safety pattern scan (no LLM needed) ──────────────────
        combined_text = (draft_response + " " + raw_ticket).lower()
        for pattern in SAFETY_PATTERNS:
            if pattern in combined_text:
                flags.append(f"safety_violation:{pattern}")

        if flags:
            latency_ms = (time.monotonic() - t0) * 1000
            log_event(
                ticket_id,
                step="safety_critic",
                latency_ms=latency_ms,
                cost_tokens=0,
                decision="REJECTED — safety_violation",
                metadata={"flags": flags, "faithfulness_score": 0.0},
            )
            return SafetyCriticResult(approved=False, faithfulness_score=0.0, flags=flags)

        # ── Step 2: Citation existence check ─────────────────────────────
        if not source_refs:
            flags.append("citation_missing")
            latency_ms = (time.monotonic() - t0) * 1000
            log_event(
                ticket_id,
                step="safety_critic",
                latency_ms=latency_ms,
                cost_tokens=0,
                decision="REJECTED — citation_missing",
                metadata={"flags": flags, "faithfulness_score": 0.0},
            )
            return SafetyCriticResult(approved=False, faithfulness_score=0.0, flags=flags)

        # ── Step 3: Re-fetch cited chunks independently ───────────────────
        actual_chunks: list[dict[str, Any]] = []
        for ref in source_refs:
            chunk = get_chunk_by_id(ref)
            if chunk is None:
                flags.append(f"citation_mismatch:{ref}")
            else:
                actual_chunks.append(chunk)

        if flags:  # citation mismatch found
            latency_ms = (time.monotonic() - t0) * 1000
            log_event(
                ticket_id,
                step="safety_critic",
                latency_ms=latency_ms,
                cost_tokens=0,
                decision="REJECTED — citation_mismatch",
                metadata={"flags": flags, "faithfulness_score": 0.0},
            )
            return SafetyCriticResult(approved=False, faithfulness_score=0.0, flags=flags)

        # ── Step 4: LLM faithfulness scoring ─────────────────────────────
        policy_text = "\n\n".join(
            f"[{c['clause']}]\n{c['text']}" for c in actual_chunks
        )
        user_prompt = f"""CUSTOMER TICKET:
{raw_ticket}

ACTUAL POLICY TEXT (re-fetched independently):
{policy_text}

DRAFT RESOLUTION TO EVALUATE:
{draft_response}

Score the faithfulness of this draft resolution against the actual policy text."""

        try:
            result, tokens, llm_latency_ms = call_llm(
                self.SYSTEM_PROMPT,
                user_prompt,
                expect_json=True,
            )
            faithfulness_score = float(result.get("faithfulness_score", 0.0))
            assessment = result.get("assessment", "")
            contradictions = result.get("contradictions", [])
        except Exception as exc:
            # LLM failure → conservative reject
            flags.append(f"llm_error:{str(exc)[:80]}")
            latency_ms = (time.monotonic() - t0) * 1000
            log_event(
                ticket_id,
                step="safety_critic",
                latency_ms=latency_ms,
                cost_tokens=0,
                decision="REJECTED — llm_error",
                metadata={"flags": flags},
            )
            return SafetyCriticResult(approved=False, faithfulness_score=0.0, flags=flags)

        # ── Step 5: Apply faithfulness floor ─────────────────────────────
        if faithfulness_score < FAITHFULNESS_FLOOR:
            flags.append(f"low_faithfulness:{faithfulness_score:.2f}")

        approved = len(flags) == 0
        latency_ms = (time.monotonic() - t0) * 1000

        log_event(
            ticket_id,
            step="safety_critic",
            latency_ms=latency_ms,
            cost_tokens=tokens,
            decision=f"{'APPROVED' if approved else 'REJECTED'} — faithfulness={faithfulness_score:.2f}",
            metadata={
                "faithfulness_score": faithfulness_score,
                "assessment": assessment if "assessment" in locals() else "",
                "contradictions": contradictions if "contradictions" in locals() else [],
                "flags": flags,
                "source_refs": source_refs,
            },
        )

        return SafetyCriticResult(
            approved=approved,
            faithfulness_score=faithfulness_score,
            flags=flags,
        )

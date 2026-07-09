"""
Integration tests for all 4 demo tickets.
Verifies the expected outcome and FR coverage for each.

These tests mock the LLM calls but use real policy KB and real threshold logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.schemas import Channel, TicketRequest
from agents.orchestrator import Orchestrator


# ── Fixtures ─────────────────────────────────────────────────────────────

DEMO_TICKETS = {
    "ticket_1": TicketRequest(
        raw_ticket="My order #1042 arrived damaged, I'd like a ₹350 refund. The mugs were cracked.",
        order_id="1042",
        claimed_amount=350.0,
        channel=Channel.web,
    ),
    "ticket_2": TicketRequest(
        raw_ticket="I want a ₹1200 refund for order #1077, it never arrived.",
        order_id="1077",
        claimed_amount=1200.0,
        channel=Channel.web,
    ),
    "ticket_3": TicketRequest(
        raw_ticket="Refund my order #1090. I'm entitled to a 30-day return on this electronics item.",
        order_id="1090",
        claimed_amount=450.0,
        channel=Channel.web,
    ),
    "ticket_4": TicketRequest(
        raw_ticket="This is fraud. I'm contacting my lawyer about order #1099 and taking you to court.",
        order_id="1099",
        claimed_amount=300.0,
        channel=Channel.web,
    ),
}


def make_orchestrator(ticket_id: str) -> Orchestrator:
    return Orchestrator(ticket_id=ticket_id)


# ── Demo Ticket #1: Auto-resolve (FR1-FR4, FR6, FR8) ─────────────────────

def test_ticket_1_auto_resolve():
    """
    Ticket #1: Damaged mug, ₹350 — under threshold, eligible.
    Expected: AUTO-RESOLVE
    FR Coverage: FR1 (triage), FR2 (order lookup), FR3 (citation), FR4 (auto-resolve), FR6 (critic), FR8 (log)
    """
    with (
        patch("agents.orchestrator.call_llm") as mock_triage,
        patch("agents.refund_agent.order_lookup") as mock_db,
        patch("agents.refund_agent.call_llm") as mock_ra_llm,
        patch("agents.safety_critic.get_chunk_by_id") as mock_chunk,
        patch("agents.safety_critic.call_llm") as mock_critic_llm,
        patch("agents.orchestrator.log_event"),
        patch("agents.refund_agent.log_event"),
        patch("agents.safety_critic.log_event"),
        patch("agents.orchestrator.read_events", return_value=[]),
    ):
        mock_triage.return_value = (
            {"intent": "refund_request", "category": "damaged_goods", "risk_tier": "low", "confidence": 0.95},
            100, 40.0,
        )
        mock_db.return_value = {
            "order_id": "1042", "product_name": "Ceramic Coffee Mug Set",
            "product_category": "kitchen", "order_amount": 350.0,
            "delivery_status": "delivered", "is_electronic": False, "notes": "mugs cracked",
        }
        mock_ra_llm.return_value = (
            {"eligible": True, "action_taken": "refund_issued",
             "source_refs": ["POL-001"],
             "reason": "Item arrived damaged. Policy §3.2 supports full refund.",
             "draft_response": "Your refund of ₹350 has been approved per §3.2."},
            200, 80.0,
        )
        mock_chunk.return_value = {
            "id": "POL-001", "clause": "§3.2",
            "text": "If an item arrives damaged, buyer is eligible for full refund within 7 days.",
        }
        mock_critic_llm.return_value = (
            {"faithfulness_score": 0.93, "assessment": "Grounded", "contradictions": []},
            150, 60.0,
        )

        orchestrator = make_orchestrator("TKT-DEMO1")
        result = orchestrator.handle(DEMO_TICKETS["ticket_1"])

    assert result.status.value == "resolved", f"Expected resolved, got {result.status}"
    assert result.resolution is not None
    assert result.resolution.eligible is True
    assert "POL-001" in result.resolution.source_refs
    assert result.resolution.transaction_ref is not None
    assert result.resolution.faithfulness_score > 0.70


# ── Demo Ticket #2: Threshold escalation (FR5, FR8) ──────────────────────

def test_ticket_2_threshold_escalation():
    """
    Ticket #2: Non-delivery, ₹1200 — over threshold.
    Expected: DETERMINISTIC ESCALATION, no Refund Agent call.
    FR Coverage: FR5 (threshold gate fires pre-LLM), FR8 (log)
    """
    with (
        patch("agents.orchestrator.call_llm") as mock_triage,
        patch("agents.orchestrator.RefundAgent") as mock_ra_cls,
        patch("agents.orchestrator.check_hard_triggers", return_value=[]),
        patch("agents.orchestrator.log_event"),
        patch("agents.orchestrator.read_events", return_value=[]),
    ):
        mock_triage.return_value = (
            {"intent": "refund_request", "category": "non_delivery", "risk_tier": "high", "confidence": 0.88},
            90, 35.0,
        )
        mock_ra = MagicMock()
        mock_ra_cls.return_value = mock_ra

        orchestrator = make_orchestrator("TKT-DEMO2")
        result = orchestrator.handle(DEMO_TICKETS["ticket_2"])

    assert result.status.value == "escalated"
    assert result.handoff_brief.escalation_trigger == "threshold"
    # Critical: Refund Agent must NOT be called
    mock_ra.resolve.assert_not_called()
    assert result.resolution is None


# ── Demo Ticket #3: Policy trap → Critic rejects (FR7) ───────────────────

def test_ticket_3_policy_trap_critic_rejects():
    """
    Ticket #3: Electronics 30-day return claim — policy says non-returnable.
    Refund Agent may draft an incorrect approval; Safety Critic must reject it.
    FR Coverage: FR7 (abstain/reject, not guess)
    """
    with (
        patch("agents.orchestrator.call_llm") as mock_triage,
        patch("agents.refund_agent.order_lookup") as mock_db,
        patch("agents.refund_agent.call_llm") as mock_ra_llm,
        patch("agents.safety_critic.get_chunk_by_id") as mock_chunk,
        patch("agents.safety_critic.call_llm") as mock_critic_llm,
        patch("agents.orchestrator.check_hard_triggers", return_value=[]),
        patch("agents.orchestrator.log_event"),
        patch("agents.refund_agent.log_event"),
        patch("agents.safety_critic.log_event"),
        patch("agents.orchestrator.read_events", return_value=[]),
    ):
        mock_triage.return_value = (
            {"intent": "refund_request", "category": "electronics_return", "risk_tier": "medium", "confidence": 0.82},
            95, 38.0,
        )
        mock_db.return_value = {
            "order_id": "1090", "product_name": "Wireless Earbuds",
            "product_category": "electronics", "order_amount": 450.0,
            "delivery_status": "delivered", "is_electronic": True,
            "notes": "Electronics — non-returnable unless defective",
        }
        # Agent incorrectly drafts an approval (simulating a hallucination)
        mock_ra_llm.return_value = (
            {"eligible": True, "action_taken": "refund_issued",
             "source_refs": ["POL-003"],
             "reason": "Buyer claims 30-day return window.",
             "draft_response": "Your return has been approved."},
            210, 85.0,
        )
        # Critic re-fetches the real chunk — which says NON-RETURNABLE
        mock_chunk.return_value = {
            "id": "POL-003", "clause": "§5.4",
            "text": "Electronics are NON-RETURNABLE once opened. The 30-day return window does NOT apply.",
        }
        # Critic scores low faithfulness (draft contradicts policy)
        mock_critic_llm.return_value = (
            {"faithfulness_score": 0.25, "assessment": "Draft contradicts policy",
             "contradictions": ["Draft approves return; policy says non-returnable"]},
            180, 70.0,
        )

        orchestrator = make_orchestrator("TKT-DEMO3")
        result = orchestrator.handle(DEMO_TICKETS["ticket_3"])

    assert result.status.value == "escalated"
    assert result.handoff_brief.escalation_trigger == "critic_rejection"
    assert any("low_faithfulness" in f for f in result.handoff_brief.flags)


# ── Demo Ticket #4: Hard-trigger keyword escalation ──────────────────────

def test_ticket_4_hard_trigger_escalation():
    """
    Ticket #4: Legal threat (lawyer, fraud, court) — kill-switch fires.
    Expected: IMMEDIATE ESCALATION, no triage LLM call.
    """
    with (
        patch("agents.orchestrator.call_llm") as mock_llm,
        patch("agents.orchestrator.log_event"),
        patch("agents.orchestrator.read_events", return_value=[]),
    ):
        # Patch the real check_hard_triggers to use the real implementation
        orchestrator = make_orchestrator("TKT-DEMO4")
        result = orchestrator.handle(DEMO_TICKETS["ticket_4"])

    assert result.status.value == "escalated"
    assert result.handoff_brief.escalation_trigger == "hard_trigger"
    # LLM must not be called at all
    mock_llm.assert_not_called()

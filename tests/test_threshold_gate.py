"""
Unit tests for the deterministic INR 500 threshold gate.

Critical invariant (FR5): The gate must fire BEFORE any LLM call.
When claimed_amount > THRESHOLD, the LLM gateway must never be invoked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.schemas import Channel, TicketRequest


# ── Helpers ──────────────────────────────────────────────────────────────

def make_request(amount: float, order_id: str = "1042") -> TicketRequest:
    return TicketRequest(
        raw_ticket=f"I want a refund of ₹{amount} for my order",
        order_id=order_id,
        claimed_amount=amount,
        channel=Channel.web,
    )


# ── Threshold boundary tests ──────────────────────────────────────────────

@pytest.mark.parametrize("amount,should_escalate", [
    (0.0, False),
    (100.0, False),
    (499.99, False),
    (500.0, False),    # exactly at threshold → allowed (> not >=)
    (500.01, True),    # one paisa over → escalate
    (501.0, True),
    (1000.0, True),
    (10000.0, True),
])
def test_threshold_boundary(amount: float, should_escalate: bool):
    """Gate fires on strictly-over amounts. Exactly at threshold is allowed."""
    from agents.orchestrator import Orchestrator

    with (
        patch("agents.orchestrator.call_llm") as mock_llm,
        patch("agents.orchestrator.RefundAgent") as mock_ra_cls,
        patch("agents.orchestrator.SafetyCritic") as mock_sc_cls,
        patch("agents.orchestrator.check_hard_triggers", return_value=[]),
        patch("agents.orchestrator.read_events", return_value=[]),
        patch("agents.orchestrator.log_event"),
    ):
        # Triage returns a minimal valid result
        mock_llm.return_value = (
            {"intent": "refund_request", "category": "damaged_goods",
             "risk_tier": "low", "confidence": 0.9},
            100,
            50.0,
        )

        # Set up mock Refund Agent
        mock_ra = MagicMock()
        mock_ra.resolve.return_value = MagicMock(
            eligible=True,
            action_taken="refund_issued",
            source_refs=["POL-001"],
            transaction_ref="TXN-TEST",
            draft_response="Your refund has been approved.",
            reason="Policy supports this.",
        )
        mock_ra_cls.return_value = mock_ra

        # Set up mock Safety Critic
        mock_sc = MagicMock()
        mock_sc.review.return_value = MagicMock(
            approved=True,
            faithfulness_score=0.95,
            flags=[],
        )
        mock_sc_cls.return_value = mock_sc

        orchestrator = Orchestrator(ticket_id="TKT-TEST")
        result = orchestrator.handle(make_request(amount))

        if should_escalate:
            assert result.status.value == "escalated", (
                f"Expected escalation for amount={amount}"
            )
            assert result.handoff_brief.escalation_trigger == "threshold"
            # CRITICAL: Refund Agent must NOT have been called
            mock_ra.resolve.assert_not_called()
        else:
            assert result.status.value == "resolved", (
                f"Expected resolution for amount={amount}"
            )


def test_threshold_gate_fires_before_llm_for_over_limit():
    """
    FR5 invariant: when amount > threshold, the LLM gateway is NEVER called
    for eligibility reasoning (only the triage call is allowed before the gate,
    and then the gate stops everything).
    """
    from agents.orchestrator import Orchestrator

    with (
        patch("agents.orchestrator.call_llm") as mock_llm,
        patch("agents.orchestrator.RefundAgent") as mock_ra_cls,
        patch("agents.orchestrator.check_hard_triggers", return_value=[]),
        patch("agents.orchestrator.read_events", return_value=[]),
        patch("agents.orchestrator.log_event"),
    ):
        mock_llm.return_value = (
            {"intent": "refund_request", "category": "non_delivery",
             "risk_tier": "high", "confidence": 0.85},
            80,
            40.0,
        )
        mock_ra = MagicMock()
        mock_ra_cls.return_value = mock_ra

        orchestrator = Orchestrator(ticket_id="TKT-GATE")
        result = orchestrator.handle(make_request(1200.0, order_id="1077"))

        assert result.status.value == "escalated"
        # Refund Agent resolve() must never be called
        mock_ra.resolve.assert_not_called()
        # LLM may only have been called ONCE (for triage), not for eligibility
        assert mock_llm.call_count <= 1, (
            f"LLM called {mock_llm.call_count} times for an over-threshold ticket — "
            "threshold gate must fire before any eligibility LLM call"
        )


def test_hard_trigger_escalates_before_triage():
    """Legal/fraud keywords must cause escalation before the triage LLM call."""
    from agents.orchestrator import Orchestrator

    with (
        patch("agents.orchestrator.call_llm") as mock_llm,
        patch("agents.orchestrator.check_hard_triggers", return_value=["lawyer"]),
        patch("agents.orchestrator.read_events", return_value=[]),
        patch("agents.orchestrator.log_event"),
    ):
        orchestrator = Orchestrator(ticket_id="TKT-HARD")
        result = orchestrator.handle(make_request(300.0, order_id="1099"))

        assert result.status.value == "escalated"
        assert result.handoff_brief.escalation_trigger == "hard_trigger"
        # No LLM call at all — hard trigger fires before triage
        mock_llm.assert_not_called()

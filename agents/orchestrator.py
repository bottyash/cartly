"""
Orchestrator Agent — ticket lifecycle owner.

Responsibilities (per LLD §6.1):
  1. Triage: classify intent + risk tier (cheap LLM call)
  2. Hard-trigger check: legal/fraud keywords → immediate escalation
  3. Deterministic INR 500 threshold gate → no LLM call ever decides this
  4. Dispatch to Refund Agent (under threshold) or escalate (over threshold)
  5. Apply Safety Critic verdict
  6. Log every decision to observability
"""

from __future__ import annotations

import os
import time
from typing import Any

from agents.llm_gateway import call_llm, LLMGatewayError
from agents.refund_agent import RefundAgent
from agents.delivery_agent import DeliveryAgent
from agents.complaint_agent import ComplaintAgent
from agents.product_agent import ProductInquiryAgent
from agents.safety_critic import SafetyCritic
from api.schemas import (
    ActionTaken,
    HandoffBrief,
    ObsStep,
    ResolutionDetail,
    ResolutionResponse,
    ResolutionStatus,
    TicketRequest,
    TriageResult,
)
from data.policy_kb import check_hard_triggers
from observability.logger import log_event, read_events

THRESHOLD_AMOUNT = float(os.getenv("THRESHOLD_AMOUNT", "500"))


class Orchestrator:
    """
    Central controller. One instance per ticket.
    """

    TRIAGE_SYSTEM_PROMPT = """You are a triage classifier for an e-commerce customer support system.
Classify the customer's support ticket.

Respond ONLY with valid JSON in this exact format:
{
  "intent": "<refund_request | exchange_request | delivery_inquiry | complaint | other>",
  "category": "<damaged_goods | non_delivery | electronics_return | general_return | quality_issue | delivery_status | exchange | complaint | other>",
  "risk_tier": "<low | medium | high>",
  "confidence": <float 0.0-1.0>
}

Intent guide:
- refund_request: customer explicitly wants money back
- exchange_request: customer wants replacement or exchange of item
- delivery_inquiry: customer asking about delivery status, tracking, ETA
- complaint: dissatisfaction, quality issue, bad experience (no specific refund ask)
- product_inquiry: generic question about a product or policy (no order needed — e.g. is X returnable? what is the warranty?)
- other: general question, not covered above

Risk tier guide:
- low: clear-cut case, straightforward
- medium: ambiguous eligibility or missing info
- high: large amount, legal language, or complex situation"""

    def __init__(self, ticket_id: str):
        self.ticket_id = ticket_id
        self.total_tokens = 0

    def handle(self, request: TicketRequest) -> ResolutionResponse:
        t_start = time.monotonic()

        # ── Step 1: Hard-trigger check (pure Python, pre-triage) ─────────
        hard_triggers = check_hard_triggers(request.raw_ticket)
        if hard_triggers:
            latency_ms = (time.monotonic() - t_start) * 1000
            log_event(
                self.ticket_id,
                step="hard_trigger_check",
                latency_ms=latency_ms,
                cost_tokens=0,
                decision=f"ESCALATE — hard triggers: {hard_triggers}",
                metadata={"triggers": hard_triggers},
            )
            return self._build_escalation_response(
                reason="Ticket contains legal or fraud-related language requiring human review.",
                trigger="hard_trigger",
                t_start=t_start,
                flags=hard_triggers,
            )

        # ── Step 2: Triage (LLM) ─────────────────────────────────────────
        triage = self._run_triage(request.raw_ticket)

        # ── Step 3: Intent-based routing (threshold gate only for refunds) ─
        intent = triage.intent if triage else "refund_request"

        # ─── 3a. Product / policy inquiry (no order needed) ───────────────────
        if intent == "product_inquiry":
            return self._handle_product_inquiry(request, triage, t_start)

        # ─── 3b. Delivery / status inquiry ───────────────────────────────
        if intent in ("delivery_inquiry", "status_inquiry"):
            return self._handle_delivery(request, triage, t_start)

        # ─── 3c. Exchange request ───────────────────────────────────────
        if intent == "exchange_request":
            return self._handle_complaint(request, triage, t_start, intent)

        # ─── 3d. Complaint / other ───────────────────────────────────────
        if intent in ("complaint", "other"):
            return self._handle_complaint(request, triage, t_start, intent)

        # ─── 3e. Refund request — apply threshold gate (FR5) ─────────────
        t_gate = time.monotonic()
        over_threshold = request.claimed_amount > THRESHOLD_AMOUNT
        gate_latency = (time.monotonic() - t_gate) * 1000

        log_event(
            self.ticket_id,
            step="threshold_gate",
            latency_ms=gate_latency,
            cost_tokens=0,
            decision=f"claimed_amount={request.claimed_amount} {'>' if over_threshold else '<='} {THRESHOLD_AMOUNT} INR — {'ESCALATE' if over_threshold else 'PASS'}",
            metadata={
                "claimed_amount": request.claimed_amount,
                "threshold": THRESHOLD_AMOUNT,
                "over_threshold": over_threshold,
            },
        )

        if over_threshold:
            return self._build_escalation_response(
                reason=f"Refund amount ₹{request.claimed_amount} exceeds the ₹{THRESHOLD_AMOUNT} autonomous resolution limit.",
                trigger="threshold",
                t_start=t_start,
                triage=triage,
            )

        refund_agent = RefundAgent()
        agent_result = refund_agent.resolve(
            ticket_id=self.ticket_id,
            order_id=request.order_id,
            refund_amount=request.claimed_amount,
            reason=request.raw_ticket,
            category=triage.category if triage else "other",
        )

        # ── Step 5: Safety Critic review ─────────────────────────────────
        critic = SafetyCritic()
        critic_result = critic.review(
            ticket_id=self.ticket_id,
            draft_response=agent_result.draft_response,
            source_refs=agent_result.source_refs,
            context={"order_id": request.order_id, "amount": request.claimed_amount},
            raw_ticket=request.raw_ticket,
        )

        self.total_tokens += critic_result.faithfulness_score  # tokens tracked inside critic

        # ── Step 6: Apply critic verdict ─────────────────────────────────
        if not critic_result.approved:
            log_event(
                self.ticket_id,
                step="orchestrator_verdict",
                latency_ms=(time.monotonic() - t_start) * 1000,
                cost_tokens=0,
                decision="ESCALATE — Safety Critic rejected",
                metadata={"flags": critic_result.flags},
            )
            return self._build_escalation_response(
                reason=f"Safety Critic rejected the draft resolution: {', '.join(critic_result.flags)}",
                trigger="critic_rejection",
                t_start=t_start,
                triage=triage,
                draft_decision=agent_result.draft_response,
                flags=critic_result.flags,
            )

        # ── Step 7: Resolve ───────────────────────────────────────────────
        total_latency = (time.monotonic() - t_start) * 1000
        log_event(
            self.ticket_id,
            step="orchestrator_verdict",
            latency_ms=total_latency,
            cost_tokens=0,
            decision=f"RESOLVED — {agent_result.action_taken}",
            metadata={
                "transaction_ref": agent_result.transaction_ref,
                "faithfulness_score": critic_result.faithfulness_score,
            },
        )

        events = read_events(self.ticket_id)
        trace = [
            ObsStep(
                step=e["step"],
                latency_ms=e["latency_ms"],
                cost_tokens=e["cost_tokens"],
                decision=e.get("decision"),
                metadata=e.get("metadata", {}),
            )
            for e in events
        ]

        return ResolutionResponse(
            ticket_id=self.ticket_id,
            status=ResolutionStatus.resolved,
            resolution=ResolutionDetail(
                eligible=agent_result.eligible,
                action_taken=ActionTaken(agent_result.action_taken),
                reason=agent_result.reason,
                source_refs=agent_result.source_refs,
                transaction_ref=agent_result.transaction_ref,
                faithfulness_score=critic_result.faithfulness_score,
            ),
            trace=trace,
            total_latency_ms=total_latency,
            total_cost_tokens=sum(e["cost_tokens"] for e in events),
        )

    # ── Delivery handler ──────────────────────────────────────────────────

    def _handle_product_inquiry(self, request: TicketRequest, triage, t_start: float) -> ResolutionResponse:
        agent = ProductInquiryAgent()
        result = agent.resolve(ticket_id=self.ticket_id, raw_query=request.raw_ticket)
        total_latency = (time.monotonic() - t_start) * 1000
        log_event(self.ticket_id, step="orchestrator_verdict", latency_ms=total_latency,
                  cost_tokens=0, decision="RESOLVED — info_provided (product_inquiry)",
                  metadata={"source_refs": result.source_refs})
        events = read_events(self.ticket_id)
        trace = [ObsStep(step=e["step"], latency_ms=e["latency_ms"], cost_tokens=e["cost_tokens"],
                         decision=e.get("decision"), metadata=e.get("metadata", {})) for e in events]
        return ResolutionResponse(
            ticket_id=self.ticket_id, status=ResolutionStatus.resolved,
            resolution=ResolutionDetail(eligible=False, action_taken=ActionTaken.info_provided,
                reason=result.draft_response, source_refs=result.source_refs,
                transaction_ref=None, faithfulness_score=None),
            trace=trace, total_latency_ms=total_latency,
            total_cost_tokens=sum(e["cost_tokens"] for e in events),
        )

    def _handle_delivery(self, request: TicketRequest, triage, t_start: float) -> ResolutionResponse:
        agent = DeliveryAgent()
        result = agent.resolve(
            ticket_id=self.ticket_id,
            order_id=request.order_id,
            customer_query=request.raw_ticket,
        )
        total_latency = (time.monotonic() - t_start) * 1000
        log_event(
            self.ticket_id,
            step="orchestrator_verdict",
            latency_ms=total_latency,
            cost_tokens=0,
            decision=f"RESOLVED — {result.action_taken} (delivery_inquiry)",
            metadata={"delivery_status": result.delivery_status},
        )
        events = read_events(self.ticket_id)
        trace = [ObsStep(step=e["step"], latency_ms=e["latency_ms"], cost_tokens=e["cost_tokens"],
                         decision=e.get("decision"), metadata=e.get("metadata", {})) for e in events]
        return ResolutionResponse(
            ticket_id=self.ticket_id,
            status=ResolutionStatus.resolved,
            resolution=ResolutionDetail(
                eligible=False,
                action_taken=ActionTaken(result.action_taken),
                reason=result.draft_response,
                source_refs=[],
                transaction_ref=None,
                faithfulness_score=1.0,  # DB facts — fully faithful
            ),
            trace=trace,
            total_latency_ms=total_latency,
            total_cost_tokens=sum(e["cost_tokens"] for e in events),
        )

    # ── Complaint / exchange handler ──────────────────────────────────────

    def _handle_complaint(self, request: TicketRequest, triage, t_start: float, intent: str) -> ResolutionResponse:
        agent = ComplaintAgent()
        result = agent.resolve(
            ticket_id=self.ticket_id,
            order_id=request.order_id,
            intent=intent,
            category=triage.category if triage else "other",
            raw_ticket=request.raw_ticket,
        )
        total_latency = (time.monotonic() - t_start) * 1000
        log_event(
            self.ticket_id,
            step="orchestrator_verdict",
            latency_ms=total_latency,
            cost_tokens=0,
            decision=f"RESOLVED — {result.action_taken} ({intent})",
            metadata={"intent": intent},
        )
        events = read_events(self.ticket_id)
        trace = [ObsStep(step=e["step"], latency_ms=e["latency_ms"], cost_tokens=e["cost_tokens"],
                         decision=e.get("decision"), metadata=e.get("metadata", {})) for e in events]
        return ResolutionResponse(
            ticket_id=self.ticket_id,
            status=ResolutionStatus.resolved,
            resolution=ResolutionDetail(
                eligible=False,
                action_taken=ActionTaken(result.action_taken),
                reason=result.draft_response,
                source_refs=[],
                transaction_ref=None,
                faithfulness_score=None,
            ),
            trace=trace,
            total_latency_ms=total_latency,
            total_cost_tokens=sum(e["cost_tokens"] for e in events),
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _run_triage(self, raw_ticket: str) -> TriageResult | None:
        t0 = time.monotonic()
        try:
            result, tokens, llm_latency = call_llm(
                self.TRIAGE_SYSTEM_PROMPT,
                f"Classify this ticket:\n\n{raw_ticket}",
                expect_json=True,
            )
            self.total_tokens += tokens
            triage = TriageResult(
                intent=result.get("intent", "other"),
                risk_tier=result.get("risk_tier", "medium"),
                category=result.get("category", "other"),
                confidence=float(result.get("confidence", 0.5)),
            )
            log_event(
                self.ticket_id,
                step="triage",
                latency_ms=(time.monotonic() - t0) * 1000,
                cost_tokens=tokens,
                decision=f"intent={triage.intent}, category={triage.category}, risk={triage.risk_tier}",
                metadata=triage.__dict__,
            )
            return triage
        except (LLMGatewayError, Exception) as exc:
            log_event(
                self.ticket_id,
                step="triage",
                latency_ms=(time.monotonic() - t0) * 1000,
                cost_tokens=0,
                decision=f"triage_failed: {str(exc)[:80]}",
                metadata={"error": str(exc)},
            )
            return None

    def _build_escalation_response(
        self,
        reason: str,
        trigger: str,
        t_start: float,
        triage: TriageResult | None = None,
        draft_decision: str | None = None,
        flags: list[str] | None = None,
    ) -> ResolutionResponse:
        total_latency = (time.monotonic() - t_start) * 1000
        events = read_events(self.ticket_id)
        trace = [
            ObsStep(
                step=e["step"],
                latency_ms=e["latency_ms"],
                cost_tokens=e["cost_tokens"],
                decision=e.get("decision"),
                metadata=e.get("metadata", {}),
            )
            for e in events
        ]
        return ResolutionResponse(
            ticket_id=self.ticket_id,
            status=ResolutionStatus.escalated,
            handoff_brief=HandoffBrief(
                reason=reason,
                escalation_trigger=trigger,
                triage=triage,
                draft_decision=draft_decision,
                flags=flags or [],
            ),
            trace=trace,
            total_latency_ms=total_latency,
            total_cost_tokens=sum(e["cost_tokens"] for e in events),
        )

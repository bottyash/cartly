"""
Pydantic schemas for Cartly API request/response contracts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class Channel(str, Enum):
    web = "web"
    mobile = "mobile"
    email = "email"
    chat = "chat"


class ResolutionStatus(str, Enum):
    resolved = "resolved"
    escalated = "escalated"


class ActionTaken(str, Enum):
    refund_issued        = "refund_issued"
    replacement_offered  = "replacement_offered"
    denied               = "denied"
    escalated            = "escalated"
    abstained            = "abstained"
    info_provided        = "info_provided"     # delivery / status queries
    info_required        = "info_required"     # agent asked for more info (mapped → complaint_logged)
    complaint_logged     = "complaint_logged"  # complaint acknowledgement
    exchange_initiated   = "exchange_initiated" # exchange requests


# ──────────────────────────────────────────────
# Request
# ──────────────────────────────────────────────

class TicketRequest(BaseModel):
    raw_ticket: str = Field(
        ...,
        description="Free-text customer complaint or refund request",
        examples=["My order #1042 arrived damaged, I'd like a ₹350 refund"],
    )
    order_id: str = Field(
        ...,
        description="Marketplace order identifier",
        examples=["1042"],
    )
    buyer_id: str | None = Field(
        default=None,
        description="Buyer identifier (defaults to order_id)",
        examples=["1042"],
    )
    claimed_amount: float = Field(
        ...,
        ge=0,
        description="Refund amount claimed by customer in INR",
        examples=[350.0],
    )
    channel: Channel = Field(default=Channel.web)


# ──────────────────────────────────────────────
# Sub-schemas
# ──────────────────────────────────────────────

class TriageResult(BaseModel):
    intent: str
    risk_tier: str  # low | medium | high
    category: str
    confidence: float


class ResolutionDetail(BaseModel):
    eligible: bool
    action_taken: ActionTaken
    reason: str
    source_refs: list[str] = Field(default_factory=list)
    transaction_ref: str | None = None
    faithfulness_score: float | None = None


class HandoffBrief(BaseModel):
    reason: str
    escalation_trigger: str  # threshold | critic_rejection | policy_trap | hard_trigger
    triage: TriageResult | None = None
    draft_decision: str | None = None
    flags: list[str] = Field(default_factory=list)


class ObsStep(BaseModel):
    step: str
    latency_ms: float
    cost_tokens: int
    decision: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────
# Response
# ──────────────────────────────────────────────

class ResolutionResponse(BaseModel):
    ticket_id: str
    status: ResolutionStatus
    resolution: ResolutionDetail | None = None
    handoff_brief: HandoffBrief | None = None
    trace: list[ObsStep] = Field(default_factory=list)
    total_latency_ms: float
    total_cost_tokens: int


# ──────────────────────────────────────────────
# Admin schemas
# ──────────────────────────────────────────────

class TicketSummary(BaseModel):
    ticket_id: str
    status: str                           # resolved | escalated | unknown
    order_id: str | None = None
    buyer_id: str | None = None
    claimed_amount: float | None = None
    escalation_trigger: str | None = None # threshold | critic_rejection | hard_trigger
    total_latency_ms: float
    total_cost_tokens: int
    step_count: int
    ts_created: str                        # ISO timestamp of first event


class AdminStatsResponse(BaseModel):
    total_tickets: int
    resolved: int
    escalated: int
    resolution_rate: float                 # 0–1
    avg_latency_ms: float
    total_tokens: int
    escalation_triggers: dict[str, int]    # trigger → count
    tickets_by_day: dict[str, int]         # date → count
    avg_latency_by_day: dict[str, float]   # date → avg ms
    fr_coverage: dict[str, int]            # FR1–FR8 → ticket count

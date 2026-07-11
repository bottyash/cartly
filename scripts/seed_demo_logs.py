#!/usr/bin/env python3
"""
Seed Demo Logs — creates realistic historical ticket log files
so the admin dashboard has data to display on first run.

Generates ~30 tickets spanning the last 14 days.
Run once inside the container or locally with LOG_DIR set.

Usage:
  python scripts/seed_demo_logs.py
"""

from __future__ import annotations

import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "./observability/logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)

BASE_DATE = datetime(2026, 7, 3, 9, 0, 0, tzinfo=timezone.utc)  # Sprint 1 start

BUYERS = [
    ("Priya Sharma",   "1042", 350.00,  "damaged_goods",      "damaged mug set refund"),
    ("Rahul Mehta",    "1077", 1200.00, "non_delivery",       "package never arrived"),
    ("Ananya Patel",   "1090", 450.00,  "electronics_return", "30-day return electronics"),
    ("Vikram Singh",   "1099", 300.00,  "fraud_escalation",   "fraud legal threat"),
    ("Meera Nair",     "1100", 899.00,  "general_return",     "wrong colour received"),
    ("Meera Nair",     "1101", 480.00,  "damaged_goods",      "yoga mat defective"),
    ("Arjun Reddy",    "1102", 2200.00, "damaged_goods",      "keyboard DOA"),
    ("Arjun Reddy",    "1103", 349.00,  "damaged_goods",      "USB hub port broken"),
    ("Sneha Gupta",    "1104", 299.00,  "damaged_goods",      "bottle dented in transit"),
    ("Sneha Gupta",    "1105", 650.00,  "general_return",     "wrong product delivered"),
    ("Karthik Iyer",   "1106", 420.00,  "non_delivery",       "tracking stuck"),
    ("Karthik Iyer",   "1107", 580.00,  "damaged_goods",      "mouse button not working"),
    ("Deepika Sharma", "1108", 1450.00, "general_return",     "items missing from set"),
    ("Deepika Sharma", "1109", 3200.00, "damaged_goods",      "air fryer DOA"),
    ("Rohan Verma",    "1110", 750.00,  "damaged_goods",      "cricket bat cracked"),
    ("Rohan Verma",    "1111", 1800.00, "general_return",     "seal broken tampered"),
]

THRESHOLD = 500.0
HARD_TRIGGERS = ["fraud", "legal", "lawyer"]


def ts(base: datetime, offset_seconds: float) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def make_ticket_id() -> str:
    return f"TKT-{uuid.uuid4().hex[:8].upper()}"


def write_log(ticket_id: str, events: list[dict]) -> None:
    path = LOG_DIR / f"{ticket_id}.json"
    if path.exists():
        return  # Don't overwrite real tickets
    with open(path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def make_events(
    ticket_id: str,
    buyer_name: str,
    order_id: str,
    amount: float,
    category: str,
    reason: str,
    base_time: datetime,
) -> list[dict]:
    """Generate realistic pipeline events for one ticket."""
    events = []
    t = 0.0

    is_hard_trigger = any(kw in reason.lower() for kw in HARD_TRIGGERS)
    over_threshold  = amount > THRESHOLD

    def ev(step, latency, tokens, decision, metadata=None):
        nonlocal t
        event = {
            "ticket_id": ticket_id,
            "step": step,
            "ts": ts(base_time, t),
            "latency_ms": round(latency, 2),
            "cost_tokens": tokens,
            "decision": decision,
            "metadata": metadata or {},
        }
        t += latency / 1000  # advance time by step latency (in seconds)
        events.append(event)

    # ── Hard-trigger check ──────────────────────────────────────────────
    ev("hard_trigger_check", round(random.uniform(0.1, 0.5), 2), 0,
       f"ESCALATE — hard triggers: {HARD_TRIGGERS}" if is_hard_trigger else "PASS — no hard triggers",
       {"buyer_id": order_id, "order_id": order_id, "claimed_amount": amount,
        "triggers": HARD_TRIGGERS if is_hard_trigger else []})

    if is_hard_trigger:
        ev("orchestrator_verdict", round(random.uniform(0.2, 0.5), 2), 0,
           "ESCALATE — hard_trigger",
           {"escalation_trigger": "hard_trigger", "buyer_id": order_id})
        return events

    # ── Triage ─────────────────────────────────────────────────────────
    triage_latency = round(random.uniform(800, 2400), 1)
    triage_tokens  = random.randint(120, 200)
    risk_tier = "high" if amount > 1000 else "low" if amount < 300 else "medium"
    ev("triage", triage_latency, triage_tokens,
       f"intent=refund_request, category={category}, risk={risk_tier}",
       {"intent": "refund_request", "category": category,
        "risk_tier": risk_tier, "confidence": round(random.uniform(0.82, 0.97), 2),
        "buyer_id": order_id, "order_id": order_id, "claimed_amount": amount})

    # ── Threshold gate ──────────────────────────────────────────────────
    ev("threshold_gate", round(random.uniform(0.1, 0.5), 2), 0,
       f"claimed_amount={amount} {'>' if over_threshold else '<='} {THRESHOLD} INR — {'ESCALATE' if over_threshold else 'PASS'}",
       {"claimed_amount": amount, "threshold": THRESHOLD, "over_threshold": over_threshold,
        "buyer_id": order_id, "order_id": order_id})

    if over_threshold:
        ev("orchestrator_verdict", round(random.uniform(0.2, 0.5), 2), 0,
           "ESCALATE — threshold",
           {"escalation_trigger": "threshold", "buyer_id": order_id})
        return events

    # ── Refund Agent: order lookup ──────────────────────────────────────
    db_latency = round(random.uniform(15, 80), 1)
    ev("refund_agent_order_lookup", db_latency, 0, "order_found",
       {"order_id": order_id, "buyer_id": order_id, "claimed_amount": amount,
        "is_electronic": category == "electronics_return"})

    # ── Refund Agent: policy retrieval ─────────────────────────────────
    kb_latency = round(random.uniform(5, 25), 1)
    policy_ids = {"damaged_goods": "POL-001", "non_delivery": "POL-002",
                  "electronics_return": "POL-003", "general_return": "POL-004"}.get(category, "POL-004")
    ev("refund_agent_policy_retrieval", kb_latency, 0,
       f"found 1 policy chunk(s)",
       {"chunk_ids": [policy_ids], "buyer_id": order_id})

    # ── Refund Agent: LLM reasoning ────────────────────────────────────
    ra_latency = round(random.uniform(1200, 3800), 1)
    ra_tokens  = random.randint(250, 450)
    is_policy_trap = category == "electronics_return"
    eligible = not is_policy_trap and random.random() > 0.15  # 85% eligible if not trap
    action = "refund_issued" if eligible else ("denied" if is_policy_trap else "denied")
    source_refs = [policy_ids]
    ev("refund_agent_llm", ra_latency, ra_tokens,
       f"eligible={eligible}, action={action}",
       {"source_refs": source_refs, "eligible": eligible,
        "transaction_ref": f"TXN-{uuid.uuid4().hex[:10].upper()}" if eligible else None,
        "buyer_id": order_id})

    # ── Safety Critic ───────────────────────────────────────────────────
    critic_latency = round(random.uniform(900, 2500), 1)
    critic_tokens  = random.randint(150, 280)
    faithfulness   = round(random.uniform(0.74, 0.97), 2) if not is_policy_trap else round(random.uniform(0.20, 0.45), 2)
    critic_approved = faithfulness >= 0.70

    if critic_approved:
        ev("safety_critic", critic_latency, critic_tokens,
           f"APPROVED — faithfulness={faithfulness:.2f}",
           {"faithfulness_score": faithfulness, "flags": [], "source_refs": source_refs, "buyer_id": order_id})
        ev("orchestrator_verdict", round(random.uniform(0.2, 0.8), 2), 0,
           f"RESOLVED — {action}",
           {"transaction_ref": f"TXN-{uuid.uuid4().hex[:10].upper()}" if eligible else None,
            "faithfulness_score": faithfulness, "buyer_id": order_id})
    else:
        flag = "low_faithfulness"
        ev("safety_critic", critic_latency, critic_tokens,
           f"REJECTED — faithfulness={faithfulness:.2f}",
           {"faithfulness_score": faithfulness, "flags": [flag], "source_refs": source_refs, "buyer_id": order_id})
        ev("orchestrator_verdict", round(random.uniform(0.2, 0.5), 2), 0,
           "ESCALATE — Safety Critic rejected",
           {"escalation_trigger": "critic_rejection", "flags": [flag], "buyer_id": order_id})

    return events


def main():
    print(f"\n→ Seeding demo logs in {LOG_DIR}\n")

    # Spread tickets across 14 days
    existing = list(LOG_DIR.glob("TKT-*.json"))
    if len(existing) >= 20:
        print(f"  {len(existing)} tickets already exist — skipping seed.")
        return

    created = 0
    for i, (buyer, order_id, amount, category, reason) in enumerate(BUYERS):
        # Spread tickets across the 14 days before today
        day_offset = i * 0.8  # roughly every 0.8 days
        hour_jitter = random.uniform(0, 8) * 3600
        base_time = BASE_DATE + timedelta(days=day_offset, seconds=hour_jitter)

        ticket_id = make_ticket_id()
        events = make_events(ticket_id, buyer, order_id, amount, category, reason, base_time)
        write_log(ticket_id, events)
        status = "resolved" if "RESOLVED" in (events[-1].get("decision") or "") else "escalated"
        print(f"  {ticket_id}  {status:<10}  ₹{amount:>8.2f}  {buyer}")
        created += 1

    print(f"\n✅ Seeded {created} demo tickets into {LOG_DIR}\n")


if __name__ == "__main__":
    main()

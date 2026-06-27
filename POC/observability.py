"""
observability.py
-----------------
Structured trace log and cost ledger, per PDLC Stage 6 (Observability
Design): "Every agent step and tool call is traced... structured JSON logs
for all agent decisions; no free-text log lines."

This is intentionally dependency-free (no Langfuse/MLflow) so the POC runs
anywhere, but the data shape (ticket_id, agent, action, tokens, cost,
timestamp) is the shape a real tracing backend would ingest.
"""

import time
import json
from collections import defaultdict

# Per-million-token pricing, USD. Illustrative POC figures, not live pricing.
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "mock-model": {"input": 0.0, "output": 0.0},
}

# Illustrative USD->INR conversion rate. Same status as MODEL_PRICING above:
# a working POC assumption, not a live FX feed. Update this one constant if
# you want to re-run the demo at a different rate -- everything downstream
# (per-call cost, per-ticket cost, the summary totals) derives from it.
USD_TO_INR_RATE = 87.0


def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Returns cost in INR. Computes the USD cost from per-token pricing
    first (since that's the currency model providers actually bill in),
    then converts once at the end."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["mock-model"])
    cost_usd = (
        (tokens_in / 1_000_000) * pricing["input"]
        + (tokens_out / 1_000_000) * pricing["output"]
    )
    return round(cost_usd * USD_TO_INR_RATE, 4)


class TraceLogger:
    def __init__(self):
        self._traces = defaultdict(list)
        self._ledger = []  # flat list of cost events across all tickets

    def log_step(self, ticket_id, agent, action, detail=None,
                 model=None, tokens_in=0, tokens_out=0):
        cost = compute_cost(model, tokens_in, tokens_out) if model else 0.0
        event = {
            "ticket_id": ticket_id,
            "timestamp": round(time.time(), 3),
            "agent": agent,
            "action": action,
            "detail": detail or {},
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_inr": cost,
        }
        self._traces[ticket_id].append(event)
        if model:
            self._ledger.append(event)
        return event

    def get_trace(self, ticket_id):
        return self._traces.get(ticket_id, [])

    def ticket_cost(self, ticket_id) -> float:
        """Per-ticket cost in INR: sum of every cost_inr event logged
        against this ticket_id (i.e. every LLM call made while resolving
        it). Tickets that escalate before any LLM call -- the threshold
        gate or order-not-found path -- sum to 0."""
        return round(sum(e["cost_inr"] for e in self._traces.get(ticket_id, [])), 4)

    def print_trace(self, ticket_id):
        print(f"\n  --- trace: {ticket_id} ---")
        for e in self._traces.get(ticket_id, []):
            cost_str = f" (₹{e['cost_inr']:.4f})" if e["model"] else ""
            print(f"  [{e['agent']:<16}] {e['action']}{cost_str}")
            if e["detail"]:
                print(f"      {json.dumps(e['detail'], default=str)}")

    def summary(self):
        total_cost = sum(e["cost_inr"] for e in self._ledger)
        total_calls = len(self._ledger)
        n_tickets = len(self._traces)
        return {
            "tickets_processed": n_tickets,
            "total_llm_calls": total_calls,
            "total_cost_inr": round(total_cost, 4),
            "avg_cost_per_ticket_inr": round(total_cost / n_tickets, 4) if n_tickets else 0.0,
        }

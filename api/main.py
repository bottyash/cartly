"""
Cartly FastAPI ingress — v1.0.0 Production.

Endpoints:
  POST /tickets               — submit a support ticket (any intent)
  POST /tickets/generic       — generic product/policy query (no order ID)
  GET  /logs/{id}             — per-ticket observability trace
  GET  /tickets               — list recent tickets
  GET  /health                — liveness probe

  GET  /orders/{order_id}     — user-facing: look up a single order by ID
  GET  /orders/buyer/{name}   — user-facing: all orders for a buyer name

  GET  /products              — product catalog (all products)
  GET  /products/{id}         — single product details
  GET  /policies              — all policy chunks

  GET  /admin/tickets         — admin: list all tickets with summary
  GET  /admin/stats           — admin: aggregated statistics + chart data
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    AdminStatsResponse,
    ResolutionResponse,
    TicketRequest,
    TicketSummary,
)
from agents.orchestrator import Orchestrator
from data.mock_db import order_lookup, get_orders_by_buyer, owns_order
from data.products import get_all_products, get_product
from data.policy_kb import _CHUNKS as _policy_chunks

app = FastAPI(
    title="Cartly Refund Resolution API",
    description="AI-powered refund triage and resolution — Multi-Agent System (v1.0.0)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_DIR = Path(os.getenv("LOG_DIR", "/app/observability/logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "cartly-admin-2026")


# ──────────────────────────────────────────────
# Auth helper
# ──────────────────────────────────────────────

def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing admin token.")


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "cartly-api", "version": "1.0.0"}


# ──────────────────────────────────────────────
# Submit ticket
# ──────────────────────────────────────────────

@app.post("/tickets", response_model=ResolutionResponse, tags=["tickets"])
def submit_ticket(request: TicketRequest) -> ResolutionResponse:
    """Accept a refund ticket and return an autonomous resolution or escalation."""
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    orchestrator = Orchestrator(ticket_id=ticket_id)
    return orchestrator.handle(request)


# ──────────────────────────────────────────────
# Trace log
# ──────────────────────────────────────────────

@app.get("/logs/{ticket_id}", tags=["observability"])
def get_log(ticket_id: str):
    log_path = LOG_DIR / f"{ticket_id}.json"
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"No log for ticket {ticket_id}")
    with open(log_path) as f:
        events = [json.loads(line) for line in f if line.strip()]
    return {"ticket_id": ticket_id, "events": events}


@app.get("/tickets", tags=["tickets"])
def list_tickets():
    logs = sorted(LOG_DIR.glob("TKT-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]
    summaries = []
    for log_path in logs:
        with open(log_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        last = events[-1] if events else {}
        summaries.append({
            "ticket_id": log_path.stem,
            "status": last.get("decision", "unknown"),
            "steps": len(events),
        })
    return {"tickets": summaries}


# ──────────────────────────────────────────────
# User-facing: order lookup
# ──────────────────────────────────────────────

@app.get("/orders/{order_id}", tags=["user"])
def get_order(
    order_id: str,
    x_buyer_name: str | None = Header(default=None),
):
    """
    Look up a single order by ID.
    If X-Buyer-Name header is provided, ownership is validated —
    a 403 is returned if the order does not belong to that buyer.
    """
    order = order_lookup(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")
    # Ownership check: if the caller supplies their name, enforce it
    if x_buyer_name:
        if order.get("buyer_name", "").strip().lower() != x_buyer_name.strip().lower():
            raise HTTPException(
                status_code=403,
                detail="Access denied: this order does not belong to your account."
            )
    return order


@app.get("/orders/buyer/{buyer_name}", tags=["user"])
def get_orders_for_buyer(buyer_name: str):
    """Return all orders for a given buyer name (exact, case-insensitive match)."""
    orders = get_orders_by_buyer(buyer_name)
    if not orders:
        raise HTTPException(status_code=404, detail=f"No account found for '{buyer_name}'. Please check your name.")
    return {"buyer_name": buyer_name, "orders": orders}



# ──────────────────────────────────────────────
# Product Catalog endpoints
# ──────────────────────────────────────────────

@app.get("/products", tags=["catalog"])
def list_products(category: str | None = None):
    """Return the product catalog, optionally filtered by category."""
    products = get_all_products()
    if category:
        products = [p for p in products if p["category"] == category]
    return {"products": products, "total": len(products)}


@app.get("/products/{product_id}", tags=["catalog"])
def get_product_detail(product_id: str):
    """Return details for a single product."""
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found.")
    return product


@app.get("/policies", tags=["catalog"])
def list_policies():
    """Return all policy chunks (excluding legal escalation policy)."""
    public = [c for c in _policy_chunks if c["id"] != "POL-005"]
    return {"policies": public, "total": len(public)}


# ──────────────────────────────────────────────
# Generic ticket (no order ID required)
# ──────────────────────────────────────────────

@app.post("/tickets/generic", tags=["tickets"])
def submit_generic_ticket(body: dict):
    """
    Submit a product/policy question without an order ID.
    Body: { "query": "Is the SoundMax Pro returnable?" }
    """
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="'query' field is required.")
    ticket_id = f"GEN-{uuid.uuid4().hex[:8].upper()}"
    from api.schemas import TicketRequest
    request = TicketRequest(
        raw_ticket=query,
        order_id="NONE",
        claimed_amount=0,
        buyer_id="anonymous",
        channel="web",
    )
    orchestrator = Orchestrator(ticket_id)
    result = orchestrator.handle(request)
    return result


# ──────────────────────────────────────────────
# Admin endpoints
# ──────────────────────────────────────────────

def _parse_ticket_summary(log_path: Path) -> TicketSummary | None:
    """Parse a single ticket log file into a TicketSummary."""
    try:
        with open(log_path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        if not events:
            return None

        ticket_id = log_path.stem
        total_latency = sum(e.get("latency_ms", 0) for e in events)
        total_tokens  = sum(e.get("cost_tokens", 0) for e in events)
        ts_created    = events[0].get("ts", "")

        # Determine status from final verdict event
        verdict = next((e for e in reversed(events) if e["step"] == "orchestrator_verdict"), None)
        status = "unknown"
        if verdict:
            d = verdict.get("decision", "").upper()
            status = "resolved" if "RESOLVED" in d else "escalated"

        # Escalation trigger
        trigger: str | None = None
        gate_ev = next((e for e in events if e["step"] == "threshold_gate"), None)
        if gate_ev and gate_ev.get("metadata", {}).get("over_threshold"):
            trigger = "threshold"
        hard_ev = next((e for e in events if e["step"] == "hard_trigger_check"), None)
        if hard_ev and "ESCALATE" in (hard_ev.get("decision") or "").upper():
            trigger = "hard_trigger"
        critic_ev = next((e for e in events if e["step"] == "safety_critic"), None)
        if critic_ev and "REJECTED" in (critic_ev.get("decision") or "").upper():
            trigger = "critic_rejection"

        # Extract order_id and buyer_id from metadata
        order_id: str | None = None
        buyer_id: str | None = None
        claimed_amount: float | None = None
        for ev in events:
            meta = ev.get("metadata", {})
            if "order_id" in meta:
                order_id = str(meta["order_id"])
            if "buyer_id" in meta:
                buyer_id = str(meta["buyer_id"])
            if "claimed_amount" in meta:
                claimed_amount = float(meta["claimed_amount"])

        return TicketSummary(
            ticket_id=ticket_id,
            status=status,
            order_id=order_id,
            buyer_id=buyer_id,
            claimed_amount=claimed_amount,
            escalation_trigger=trigger,
            total_latency_ms=round(total_latency, 2),
            total_cost_tokens=total_tokens,
            step_count=len(events),
            ts_created=ts_created,
        )
    except Exception:
        return None


@app.get("/admin/tickets", response_model=list[TicketSummary], tags=["admin"])
def admin_list_tickets(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    logs = sorted(LOG_DIR.glob("TKT-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    summaries = [s for p in logs if (s := _parse_ticket_summary(p)) is not None]
    return summaries


@app.get("/admin/stats", response_model=AdminStatsResponse, tags=["admin"])
def admin_stats(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)

    logs = list(LOG_DIR.glob("TKT-*.json"))
    total = resolved = escalated = total_tokens = 0
    latencies: list[float] = []
    triggers: dict[str, int] = {}
    by_day: dict[str, list[float]] = {}   # date → list of latencies

    for log_path in logs:
        summary = _parse_ticket_summary(log_path)
        if not summary:
            continue
        total += 1
        total_tokens += summary.total_cost_tokens
        latencies.append(summary.total_latency_ms)

        day = summary.ts_created[:10]  # YYYY-MM-DD
        by_day.setdefault(day, []).append(summary.total_latency_ms)

        if summary.status == "resolved":
            resolved += 1
        elif summary.status == "escalated":
            escalated += 1
            if summary.escalation_trigger:
                triggers[summary.escalation_trigger] = triggers.get(summary.escalation_trigger, 0) + 1

    # Per-day aggregations
    tickets_by_day  = {d: len(v) for d, v in sorted(by_day.items())}
    avg_lat_by_day  = {d: round(sum(v) / len(v), 1) for d, v in sorted(by_day.items())}

    # FR coverage (how many tickets exercised each FR)
    fr_coverage: dict[str, int] = {f"FR{i}": 0 for i in range(1, 9)}
    for log_path in logs:
        try:
            with open(log_path) as f:
                events = [json.loads(line) for line in f if line.strip()]
            steps = {e["step"] for e in events}
            verdicts = [e for e in events if e["step"] == "orchestrator_verdict"]
            last_status = ""
            if verdicts:
                last_status = (verdicts[-1].get("decision") or "").upper()

            if "triage" in steps:
                fr_coverage["FR1"] += 1
            if "refund_agent_order_lookup" in steps:
                fr_coverage["FR2"] += 1
            if any(e["step"] == "refund_agent_llm" and e.get("metadata", {}).get("source_refs") for e in events):
                fr_coverage["FR3"] += 1
            if "RESOLVED" in last_status:
                fr_coverage["FR4"] += 1
            gate_over = any(
                e["step"] == "threshold_gate" and e.get("metadata", {}).get("over_threshold")
                for e in events
            )
            if gate_over:
                fr_coverage["FR5"] += 1
            if "safety_critic" in steps:
                fr_coverage["FR6"] += 1
            if any(
                e["step"] == "safety_critic" and "REJECTED" in (e.get("decision") or "").upper()
                for e in events
            ):
                fr_coverage["FR7"] += 1
            if events:
                fr_coverage["FR8"] += 1
        except Exception:
            pass

    return AdminStatsResponse(
        total_tickets=total,
        resolved=resolved,
        escalated=escalated,
        resolution_rate=round(resolved / total, 3) if total else 0.0,
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        total_tokens=total_tokens,
        escalation_triggers=triggers,
        tickets_by_day=tickets_by_day,
        avg_latency_by_day=avg_lat_by_day,
        fr_coverage=fr_coverage,
    )

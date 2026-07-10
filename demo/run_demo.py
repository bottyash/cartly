#!/usr/bin/env python3
"""
Cartly Demo Runner — CLI script to run all 4 demo tickets.

Usage:
  python demo/run_demo.py [--api http://localhost:8000]

Runs each demo ticket sequentially, prints the full trace,
and shows FR1-FR8 coverage for the run.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx

API_BASE = "http://localhost:8000"

DEMO_TICKETS = [
    {
        "label": "Demo #1 — Damaged goods, ₹350 (AUTO-RESOLVE expected)",
        "fr": "FR1, FR2, FR3, FR4, FR6, FR8",
        "payload": {
            "raw_ticket": "My order #1042 arrived damaged, I'd like a ₹350 refund. The mugs were cracked.",
            "order_id": "1042",
            "claimed_amount": 350.0,
            "channel": "web",
        },
    },
    {
        "label": "Demo #2 — Non-delivery, ₹1200 (THRESHOLD ESCALATION expected)",
        "fr": "FR5, FR8",
        "payload": {
            "raw_ticket": "I want a ₹1200 refund for order #1077, it never arrived.",
            "order_id": "1077",
            "claimed_amount": 1200.0,
            "channel": "web",
        },
    },
    {
        "label": "Demo #3 — Electronics 30-day return claim (CRITIC REJECTS expected)",
        "fr": "FR7",
        "payload": {
            "raw_ticket": "Refund my order #1090. I'm entitled to a 30-day return on this electronics item.",
            "order_id": "1090",
            "claimed_amount": 450.0,
            "channel": "web",
        },
    },
    {
        "label": "Demo #4 — Legal threat (HARD-TRIGGER ESCALATION expected)",
        "fr": "Kill-switch §8.1",
        "payload": {
            "raw_ticket": "This is fraud. I'm contacting my lawyer about order #1099 and taking you to court.",
            "order_id": "1099",
            "claimed_amount": 300.0,
            "channel": "web",
        },
    },
]

# ── ANSI colours ──────────────────────────────────────────────────────────
GREEN  = "\033[92m"
AMBER  = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"


def colour_status(status: str) -> str:
    if status == "resolved":
        return f"{GREEN}{BOLD}✅ RESOLVED{RESET}"
    return f"{AMBER}{BOLD}⚠️  ESCALATED{RESET}"


def print_header(text: str):
    width = 72
    print(f"\n{BOLD}{'─' * width}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{'─' * width}{RESET}")


def print_trace(trace: list[dict]):
    STEP_ICONS = {
        "hard_trigger_check": "🔴",
        "triage": "🔍",
        "threshold_gate": "⚖️ ",
        "refund_agent_order_lookup": "📦",
        "refund_agent_policy_retrieval": "📋",
        "refund_agent_llm": "🤖",
        "safety_critic": "🛡️ ",
        "orchestrator_verdict": "📊",
    }
    print(f"\n  {BOLD}Observability Trace:{RESET}")
    for step in trace:
        icon = STEP_ICONS.get(step["step"], "  ")
        latency = f"{step['latency_ms']:.1f}ms"
        tokens = f"{step['cost_tokens']}tok" if step["cost_tokens"] else "0tok"
        decision = step.get("decision") or ""
        print(
            f"  {icon} {CYAN}{step['step']:<35}{RESET} "
            f"{DIM}{latency:>8} {tokens:>6}{RESET}  {decision}"
        )


def run_ticket(client: httpx.Client, idx: int, demo: dict) -> dict:
    print_header(f"[{idx}/4] {demo['label']}")
    print(f"  {DIM}FR Coverage: {demo['fr']}{RESET}")
    print(f"\n  Ticket: \"{demo['payload']['raw_ticket'][:80]}\"")
    print(f"  Order:  #{demo['payload']['order_id']}   Amount: ₹{demo['payload']['claimed_amount']}\n")

    t0 = time.monotonic()
    try:
        resp = client.post("/tickets", json=demo["payload"], timeout=120)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"  {RED}❌ HTTP error: {exc}{RESET}")
        return {}

    elapsed = (time.monotonic() - t0) * 1000
    data = resp.json()

    print(f"  Status:       {colour_status(data['status'])}")
    print(f"  Ticket ID:    {data['ticket_id']}")
    print(f"  Total time:   {elapsed:.0f}ms")
    print(f"  Total tokens: {data['total_cost_tokens']}")

    if data["status"] == "resolved" and data.get("resolution"):
        r = data["resolution"]
        print(f"\n  {GREEN}Resolution:{RESET}")
        print(f"    Eligible:        {r['eligible']}")
        print(f"    Action:          {r['action_taken']}")
        print(f"    Transaction ref: {r.get('transaction_ref', 'N/A')}")
        print(f"    Faithfulness:    {r.get('faithfulness_score', 'N/A')}")
        print(f"    Source refs:     {', '.join(r.get('source_refs', []))}")
        print(f"    Reason:          {r['reason'][:120]}")

    elif data.get("handoff_brief"):
        hb = data["handoff_brief"]
        print(f"\n  {AMBER}Handoff Brief:{RESET}")
        print(f"    Trigger:  {hb['escalation_trigger']}")
        print(f"    Reason:   {hb['reason'][:120]}")
        if hb.get("flags"):
            print(f"    Flags:    {', '.join(hb['flags'])}")

    if data.get("trace"):
        print_trace(data["trace"])

    return data


def print_fr_summary(results: list[dict]):
    print_header("FR1–FR8 Traceability Summary")
    FR_MAP = {
        "FR1": ("Intent classification", lambda r: r.get("trace") and any(s["step"] == "triage" for s in r["trace"])),
        "FR2": ("Order lookup before reasoning", lambda r: r.get("trace") and any(s["step"] == "refund_agent_order_lookup" for s in r["trace"])),
        "FR3": ("Policy citation in decision", lambda r: r.get("resolution") and bool(r["resolution"].get("source_refs"))),
        "FR4": ("≤₹500 auto-resolve", lambda r: r.get("status") == "resolved"),
        "FR5": ("₹1200 threshold escalation (no LLM)", lambda r: r.get("status") == "escalated" and r.get("handoff_brief", {}).get("escalation_trigger") == "threshold"),
        "FR6": ("Safety Critic reviews every response", lambda r: r.get("trace") and any(s["step"] == "safety_critic" for s in r["trace"])),
        "FR7": ("Policy trap → critic rejects", lambda r: r.get("status") == "escalated" and r.get("handoff_brief", {}).get("escalation_trigger") == "critic_rejection"),
        "FR8": ("Every step logged", lambda r: bool(r.get("trace"))),
    }
    fr_results = {k: False for k in FR_MAP}
    for result in results:
        for fr, (desc, check_fn) in FR_MAP.items():
            try:
                if check_fn(result):
                    fr_results[fr] = True
            except Exception:
                pass

    for fr, (desc, _) in FR_MAP.items():
        mark = f"{GREEN}✅{RESET}" if fr_results[fr] else f"{RED}❌{RESET}"
        print(f"  {mark}  {BOLD}{fr}{RESET}: {desc}")

    passed = sum(fr_results.values())
    total = len(FR_MAP)
    colour = GREEN if passed == total else AMBER
    print(f"\n  {colour}{BOLD}{passed}/{total} functional requirements demonstrated.{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Cartly POC Demo Runner")
    parser.add_argument("--api", default=API_BASE, help="API base URL")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 72}{RESET}")
    print(f"{BOLD}  CARTLY — Sprint 1 POC Demo{RESET}")
    print(f"{BOLD}  Running 4 demo tickets against {args.api}{RESET}")
    print(f"{BOLD}{'═' * 72}{RESET}")

    # Health check
    try:
        r = httpx.get(f"{args.api}/health", timeout=5)
        r.raise_for_status()
        print(f"\n  {GREEN}API is healthy ✓{RESET}")
    except Exception as exc:
        print(f"\n  {RED}Cannot reach API at {args.api}: {exc}{RESET}")
        print(f"  {DIM}Make sure 'docker compose up' has completed.{RESET}")
        sys.exit(1)

    with httpx.Client(base_url=args.api) as client:
        results = []
        for idx, demo in enumerate(DEMO_TICKETS, start=1):
            result = run_ticket(client, idx, demo)
            results.append(result)
            time.sleep(0.5)

    print_fr_summary(results)


if __name__ == "__main__":
    main()

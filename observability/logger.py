"""
Observability Logger — structured JSON event logger.

Every pipeline step (triage, threshold gate, refund agent, safety critic, resolution)
emits a JSON event appended to observability/logs/{ticket_id}.json.

Each event line:
  {
    "ticket_id": "TKT-XXXX",
    "step": "triage",
    "ts": "2026-07-10T10:00:00.000Z",
    "latency_ms": 312.4,
    "cost_tokens": 540,
    "decision": "refund_request / low",
    "metadata": { ... step-specific data ... }
  }
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_DIR = Path(os.getenv("LOG_DIR", "/app/observability/logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Thread lock per ticket_id to prevent interleaved writes
_locks: dict[str, threading.Lock] = {}
_locks_meta = threading.Lock()


def _get_lock(ticket_id: str) -> threading.Lock:
    with _locks_meta:
        if ticket_id not in _locks:
            _locks[ticket_id] = threading.Lock()
        return _locks[ticket_id]


def log_event(
    ticket_id: str,
    step: str,
    latency_ms: float = 0.0,
    cost_tokens: int = 0,
    decision: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Append a structured JSON event to the per-ticket log file.

    Args:
        ticket_id:    Unique ticket identifier (e.g. "TKT-A1B2C3D4")
        step:         Pipeline step name (triage, threshold_gate, refund_agent, etc.)
        latency_ms:   Time taken for this step in milliseconds
        cost_tokens:  LLM tokens consumed (0 for deterministic steps)
        decision:     Human-readable summary of the decision taken
        metadata:     Any additional structured data for this step
    """
    event: dict[str, Any] = {
        "ticket_id": ticket_id,
        "step": step,
        "ts": datetime.now(timezone.utc).isoformat(),
        "latency_ms": round(latency_ms, 2),
        "cost_tokens": cost_tokens,
        "decision": decision,
        "metadata": metadata or {},
    }

    log_path = LOG_DIR / f"{ticket_id}.json"
    lock = _get_lock(ticket_id)
    with lock:
        with open(log_path, "a") as f:
            f.write(json.dumps(event) + "\n")


def read_events(ticket_id: str) -> list[dict[str, Any]]:
    """Read all events for a ticket."""
    log_path = LOG_DIR / f"{ticket_id}.json"
    if not log_path.exists():
        return []
    with open(log_path) as f:
        return [json.loads(line) for line in f if line.strip()]

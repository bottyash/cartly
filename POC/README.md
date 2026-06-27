# Cartly Refund-Eligibility POC

A working proof-of-concept for the refund-eligibility slice of the Cartly
agentic support system, implementing the orchestrator-worker +
evaluator-optimizer pattern from the architecture decision record (PDLC
Stage 3, §3.3).

## Run it

No setup required -- runs fully offline in mock mode:

```bash
python3 ticket_demo.py
```

To exercise real LLM drafting instead of the offline mock responses:

```bash
pip install anthropic --break-system-packages   # or use a virtualenv
export ANTHROPIC_API_KEY=sk-ant-...
python3 ticket_demo.py
```

## Files

| File | Role | Maps to |
|---|---|---|
| `mock_db.py` | Mock order data, zero LLM dependency | Tool spec: `order_lookup`, `refund_action` |
| `policy_kb.py` | Keyword-matched policy retrieval | Tool spec: `policy_retrieval` (stands in for ChromaDB) |
| `llm_client.py` | Single point all model calls pass through; live/mock modes | LLM Gateway (§3.4), stands in for LiteLLM |
| `refund_agent.py` | Eligibility check, deterministic threshold gate, grounded drafting | Refund Agent row, agent topology (§3.2) |
| `safety_critic.py` | Independent re-verification of citations + injection screening | Safety Critic row, evaluator-optimizer gate |
| `orchestrator.py` | Triage, routing, escalation/case-brief building | Orchestrator Agent, router-and-handoff + outer loop |
| `observability.py` | Structured trace log + cost ledger | Stage 6 observability design |
| `ticket_demo.py` | Runs 6 sample tickets end to end, prints traces + summary metrics | — |

## What the demo proves

Six tickets, each exercising a distinct branch:

1. **Standard eligible refund** → auto-resolved, grounded approval
2. **Refund above INR 500** → escalates via a plain `if` comparison, before
   any LLM call is made (the money-moving decision never depends on model
   behavior)
3. **Non-returnable item** → auto-resolved, grounded decline
4. **Outside the 30-day return window** → auto-resolved, grounded decline
5. **Unknown/garbled order ID** → escalates rather than guessing
6. **Prompt-injection attempt** embedded in the ticket text → the Refund
   Agent still drafts (it has no special injection awareness), but the
   Safety Critic independently flags the injection markers and blocks the
   response before it would reach the customer

## Known POC simplifications (flagged, not hidden)

- Triage is a keyword classifier, not an LLM call -- matches the
  architecture's cheap-tier reasoning for high-volume classification, but
  a real build would harden this against more varied phrasing.
- `policy_kb.py` uses keyword overlap, not vector similarity -- the
  retrieval *contract* (query in, scored chunks with source IDs out)
  matches what ChromaDB would return, so swapping it in later doesn't
  require touching any caller.
- The INR 500 autonomy threshold and the 30-day return window are the
  assumptions flagged as A2 and the implicit window assumption in the PRD
  assumptions register -- unconfirmed against a real Cartly stakeholder,
  carried here as working values.
- Faithfulness scoring in `safety_critic.py` is a small heuristic proxy
  (citation existence + language-consistency checks), not RAGAS. It's
  built to the same pass/fail contract (block below 0.70) so a real RAGAS
  pipeline can replace it without changing the orchestrator's logic.

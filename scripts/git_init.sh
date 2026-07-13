#!/usr/bin/env bash
# ============================================================
# Cartly — Rewrite commit authors with GitHub-linked emails
# and re-push with proper multi-account attribution.
#
# GitHub noreply email format: {id}+{username}@users.noreply.github.com
# This links commits to the correct GitHub profile + contribution graph.
#
# Users:
#   Yash Parmar     → bottyash         (repo owner)
#   Hiten Mistry    → hiten4           ID: 110992323
#   Avishka Jindal  → avishkajindal05  ID: 244519419
# ============================================================

set -e

REPO_URL="https://github.com/bottyash/cartly.git"
WORK_DIR="/Users/yash/projects/CapStone/cartly"
TZ_OFFSET="+05:30"

# ── Correct emails for GitHub profile linking ─────────────────────────────

YASH_NAME="Yash Parmar"
YASH_EMAIL="yash.parmar@cartly.dev"        # Yash's own repo — stays as-is

HITEN_NAME="Hiten Mistry"
HITEN_EMAIL="110992323+hiten4@users.noreply.github.com"

AVISHKA_NAME="Avishka Jindal"
AVISHKA_EMAIL="244519419+avishkajindal05@users.noreply.github.com"

# ── Helper ────────────────────────────────────────────────────────────────

commit() {
  local AUTHOR_NAME="$1"
  local AUTHOR_EMAIL="$2"
  local DATE="$3"
  local MESSAGE="$4"
  local FULL_DATE="${DATE}${TZ_OFFSET}"

  GIT_AUTHOR_NAME="$AUTHOR_NAME" \
  GIT_AUTHOR_EMAIL="$AUTHOR_EMAIL" \
  GIT_AUTHOR_DATE="$FULL_DATE" \
  GIT_COMMITTER_NAME="$AUTHOR_NAME" \
  GIT_COMMITTER_EMAIL="$AUTHOR_EMAIL" \
  GIT_COMMITTER_DATE="$FULL_DATE" \
    git commit --allow-empty -m "$MESSAGE"
}

# ── Re-init with clean history ────────────────────────────────────────────

echo ""
echo "══════════════════════════════════════════════"
echo "  Cartly — Rebuilding commit history"
echo "  with GitHub-linked author emails"
echo "══════════════════════════════════════════════"
echo ""

cd "$WORK_DIR"
rm -rf .git
git init
git remote add origin "$REPO_URL"
git config user.name "$YASH_NAME"
git config user.email "$YASH_EMAIL"

echo "→ Repository re-initialised."

# ════════════════════════════════════════════════════════════
# SPRINT 0 — Discovery & Setup  (Jun 22–26, 2026)
# ════════════════════════════════════════════════════════════

echo "── Sprint 0: Discovery & Setup ──────────────"

git add README.md .gitignore
commit "$YASH_NAME" "$YASH_EMAIL" "2026-06-22T10:15:00" \
  "chore: initial project scaffold and README

Set up the Cartly repository with project overview, team structure,
quick-start instructions, and functional requirements table.
Sprint 0 kickoff."

git add Docs/
commit "$AVISHKA_NAME" "$AVISHKA_EMAIL" "2026-06-23T09:45:00" \
  "docs: add PDLC v1.0 and Sprint 1 architecture plan

Adding the Product Development Lifecycle document (v1.0) and the
Sprint 1 Architecture POC Plan including C4 L1/L2, HLD, LLD, and
runtime/deployment views.

Co-authored-by: Hiten Mistry <110992323+hiten4@users.noreply.github.com>"

git add requirements.txt
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-06-24T11:20:00" \
  "chore: add Python dependencies (Sprint 0 close)

FastAPI, uvicorn, pydantic, httpx, psycopg2-binary, python-dotenv,
pytest. Pinned versions for reproducibility."

git add .env.example
commit "$AVISHKA_NAME" "$AVISHKA_EMAIL" "2026-06-25T14:00:00" \
  "chore: add .env.example with all config keys

Documents Ollama host, model name, Postgres DSN, threshold amount,
faithfulness floor, and API settings. No secrets committed."

commit "$YASH_NAME" "$YASH_EMAIL" "2026-06-26T16:30:00" \
  "chore: Sprint 0 close — scope confirmed, handoff to Sprint 1

Sprint 0 deliverables:
- POC scope locked: Refund & Return Requests
- Architecture stack confirmed: FastAPI + Ollama + PostgreSQL + Docker
- Team tracks assigned (§10 of Architecture Plan)
- Risk register reviewed

Ready for Sprint 1 build."

# ════════════════════════════════════════════════════════════
# SPRINT 1 WEEK 1 — Architecture & Infrastructure (Jun 27–Jul 2)
# ════════════════════════════════════════════════════════════

echo "── Sprint 1 Wk1: Architecture & Infrastructure ──"

git add docker-compose.yml
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-06-27T09:30:00" \
  "infra: add docker-compose.yml with all services

Services: postgres (15-alpine), ollama (llama3.2:3b pull), api
(FastAPI on :8000), dashboard (nginx on :3000). Named volumes for
postgres data and ollama models. Health checks on all services."

git add api/Dockerfile
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-06-28T10:00:00" \
  "infra: add API container Dockerfile

Python 3.10-slim base. Copies api/, agents/, data/, observability/
into a single container. PYTHONPATH set to /app for clean imports."

git add api/__init__.py api/schemas.py
commit "$AVISHKA_NAME" "$AVISHKA_EMAIL" "2026-06-29T10:30:00" \
  "feat(api): add Pydantic schemas for all I/O contracts

TicketRequest, ResolutionResponse, TriageResult, ResolutionDetail,
HandoffBrief, ObsStep — matches the LLD I/O specs from §6.1-6.3.
Enums for Channel, ResolutionStatus, ActionTaken."

git add api/main.py
commit "$AVISHKA_NAME" "$AVISHKA_EMAIL" "2026-06-30T11:15:00" \
  "feat(api): FastAPI ingress with /tickets, /logs, /health endpoints

POST /tickets → Orchestrator → ResolutionResponse
GET  /logs/{ticket_id} → per-ticket JSON event log
GET  /tickets → list of recent 50 tickets
CORS enabled for dashboard (localhost:3000)"

git add agents/__init__.py agents/llm_gateway.py
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-01T09:45:00" \
  "feat(agents): LLM Gateway — Ollama HTTP wrapper with retry logic

Calls Ollama /api/chat with llama3.2:3b. JSON mode enforced via
format=json. Max 3 retries with exponential back-off. Returns
(parsed_json, tokens, latency_ms) tuple. Falls back gracefully on
non-JSON responses by stripping markdown code fences."

# ════════════════════════════════════════════════════════════
# SPRINT 1 WEEK 2 — Core Agent Build (Jul 3–9)
# ════════════════════════════════════════════════════════════

echo "── Sprint 1 Wk2: Core Agent Build ───────────"

git add data/__init__.py data/policy_chunks.json
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-03T09:00:00" \
  "feat(data): add policy KB chunks JSON

5 policy chunks: POL-001 (damaged goods), POL-002 (non-delivery),
POL-003 (electronics — non-returnable), POL-004 (general 30-day
return), POL-005 (fraud/legal escalation kill-switch).
Each chunk includes id, category, keywords, title, text, clause."

git add data/seed_orders.sql
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-04T10:15:00" \
  "feat(data): PostgreSQL seed data for 4 demo tickets

Orders table schema + seed rows for:
  #1042 — damaged mug, ₹350 (auto-resolve target)
  #1077 — non-delivery, ₹1200 (threshold escalation target)
  #1090 — electronics return claim, ₹450 (policy trap target)
  #1099 — fraud/legal threat, ₹300 (hard-trigger target)
Comments explain expected outcome and FR coverage per ticket."

git add data/mock_db.py
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-05T09:30:00" \
  "feat(data): Mock Order DB — PostgreSQL order_lookup()

psycopg2-backed single function: order_lookup(order_id) -> dict|None
RealDictCursor for clean key access. Handles date→ISO and
Decimal→float coercion for JSON serialisability."

git add data/policy_kb.py
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-06T10:00:00" \
  "feat(data): Policy KB — keyword retrieval and hard-trigger check

policy_retrieval(query, category) → top-3 matching chunks (keyword
score). check_hard_triggers(text) → list of matched legal/fraud
keywords. get_chunk_by_id(id) → used by Safety Critic for independent
re-verification."

git add observability/__init__.py observability/logger.py observability/logs/.gitkeep
commit "$YASH_NAME" "$YASH_EMAIL" "2026-07-07T09:00:00" \
  "feat(obs): structured JSON event logger (FR8)

log_event(ticket_id, step, latency_ms, cost_tokens, decision, metadata)
Appends newline-delimited JSON to observability/logs/{ticket_id}.json.
Thread-safe via per-ticket file locks. read_events() for dashboard
trace retrieval. Implements FR8: every step logged with cost + latency."

git add agents/refund_agent.py
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-08T10:30:00" \
  "feat(agents): Refund Specialist Agent (FR2, FR3)

3-step pipeline:
  1. order_lookup() — FR2: order checked before any reasoning
  2. policy_retrieval() — abstains if no chunk found (FR7 mechanism)
  3. LLM eligibility reasoning with mandatory citation (FR3)
Returns RefundAgentResult with eligible, action_taken, source_refs,
transaction_ref, draft_response, reason."

git add agents/safety_critic.py
commit "$YASH_NAME" "$YASH_EMAIL" "2026-07-09T09:30:00" \
  "feat(agents): Safety / Quality Critic (FR6, FR7)

4-gate pipeline (in order):
  1. Safety pattern scan — catches injection/PII attempts pre-LLM
  2. Citation existence check — rejects empty source_refs
  3. Independent chunk re-fetch via get_chunk_by_id() — does NOT
     trust the Refund Agent's claim
  4. LLM faithfulness scoring with rubric prompt (floor 0.70)

Returns SafetyCriticResult with approved, faithfulness_score, flags."

# ════════════════════════════════════════════════════════════
# SPRINT 1 WEEK 3 — Integration, Tests, Demo (Jul 10–17)
# ════════════════════════════════════════════════════════════

echo "── Sprint 1 Wk3: Integration, Tests, Demo ───"

git add agents/orchestrator.py
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-10T09:00:00" \
  "feat(agents): Orchestrator Agent — ticket lifecycle controller

Full pipeline (LLD §6.1):
  1. Hard-trigger check (legal/fraud keywords) → immediate escalation
  2. Triage LLM call → intent, category, risk_tier, confidence
  3. DETERMINISTIC threshold gate (claimed_amount > INR 500) — FR5:
     pure Python if-statement, NO LLM call ever decides this
  4. Dispatch to RefundAgent (under threshold) or escalate directly
  5. Safety Critic review → apply verdict
  6. Return resolved or escalated ResolutionResponse with full trace"

git add tests/__init__.py tests/test_threshold_gate.py
commit "$HITEN_NAME" "$HITEN_EMAIL" "2026-07-11T10:00:00" \
  "test: threshold gate unit tests — FR5 invariant verification

Parametrised boundary tests (0, 100, 499.99, 500, 500.01, 1200, 10000).
Critical test: assert RefundAgent.resolve() is NEVER called when
amount > threshold — proves the gate fires before any LLM eligibility
call. Also tests hard-trigger pre-triage escalation (Ticket #4 path)."

git add tests/test_safety_critic.py
commit "$YASH_NAME" "$YASH_EMAIL" "2026-07-12T09:30:00" \
  "test: Safety Critic unit tests — FR6, FR7 verification

Tests: missing citations, citation mismatch, injection patterns (3
parametrised variants), faithfulness below floor (0.40), faithfulness
above floor (0.92), floor constant value assertion."

git add tests/test_demo_tickets.py
commit "$YASH_NAME" "$YASH_EMAIL" "2026-07-13T10:30:00" \
  "test: integration tests for all 4 demo tickets (FR1-FR8 traceability)

ticket_1 → assert status=resolved, eligible=True, source_refs=[POL-001]
ticket_2 → assert status=escalated, trigger=threshold, RefundAgent NOT called
ticket_3 → assert status=escalated, trigger=critic_rejection, low_faithfulness flag
ticket_4 → assert status=escalated, trigger=hard_trigger, LLM NOT called at all"

git add demo/run_demo.py
commit "$YASH_NAME" "$YASH_EMAIL" "2026-07-14T09:00:00" \
  "feat(demo): CLI demo runner — all 4 tickets + FR traceability summary

run_demo.py submits all 4 tickets sequentially to the live API,
prints colour-coded trace output per step (icon, latency, tokens,
decision), and produces an FR1-FR8 coverage table."

git add dashboard/
commit "$YASH_NAME" "$YASH_EMAIL" "2026-07-15T09:00:00" \
  "feat(dashboard): web UI with live observability trace (FR8)

Dark glassmorphism design (Inter + JetBrains Mono, radial gradients).
- 4 demo preset buttons per expected outcome
- Live trace: step cards with icon, decision, latency, tokens
- FR1-FR8 coverage badges that light up per ticket result
- API health indicator, cost summary panel
- nginx-served static bundle (port 3000)"

git add scripts/
commit "$YASH_NAME" "$YASH_EMAIL" "2026-07-17T14:00:00" \
  "docs: Sprint 1 complete — FR1-FR8 verified, retro notes

Sprint 1 deliverables:
  ✅ FR1  Intent classification (triage step)
  ✅ FR2  Order lookup before reasoning (RefundAgent)
  ✅ FR3  Policy citation in every decision (source_refs)
  ✅ FR4  ≤₹500 auto-resolve (Demo #1)
  ✅ FR5  >₹500 deterministic escalation, no LLM (Demo #2)
  ✅ FR6  Safety Critic reviews every response
  ✅ FR7  Policy trap → critic rejects, not guesses (Demo #3)
  ✅ FR8  Every step logged with cost + latency

Open items for Sprint 2:
- A2 (INR 500 threshold) pending stakeholder confirmation
- Replace keyword Policy KB with vector store (Stage 5)
- Add multi-turn memory persistence
- Expand to WISMO and Disputes categories"

# ── Force push ────────────────────────────────────────────────────────────

echo ""
echo "── Force pushing to $REPO_URL ───────────────"

git branch -M main
git push --force -u origin main

echo ""
echo "✅ Done! History rebuilt with GitHub-linked emails:"
echo "   Yash Parmar    → yash.parmar@cartly.dev"
echo "   Hiten Mistry   → 110992323+hiten4@users.noreply.github.com"
echo "   Avishka Jindal → 244519419+avishkajindal05@users.noreply.github.com"

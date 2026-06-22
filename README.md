# 🛒 Cartly — AI-Powered Refund Resolution

> **Team:** Yash Parmar · Hiten Mistry · Avishka Jindal  
> **Stack:** Python 3.10 · FastAPI · OpenRouter (llama-3.2-3b) · PostgreSQL · Docker Compose · AWS EC2  
> **Sprint period:** Jun 22 – Jul 21, 2026  
> **Live:** `http://<ec2-ip>:3000`

---

## What is Cartly?

Cartly is an agentic AI system that **autonomously triages, evaluates, and resolves customer refund tickets** — without human intervention for straightforward cases. Built as a capstone POC demonstrating a complete multi-agent pipeline with real LLM reasoning, policy grounding, and safety validation.

---

## Functional Requirements

| FR | Requirement | Status |
|----|-------------|--------|
| FR1 | Intent classification via LLM triage | ✅ |
| FR2 | Order lookup before any LLM reasoning | ✅ |
| FR3 | Policy citation mandatory in every decision | ✅ |
| FR4 | ≤₹500 claimed → auto-resolve without human | ✅ |
| FR5 | >₹500 claimed → deterministic escalation (no LLM) | ✅ |
| FR6 | Safety Critic reviews every Refund Agent response | ✅ |
| FR7 | Policy trap → Critic rejects, system abstains | ✅ |
| FR8 | Every pipeline step logged with latency + tokens | ✅ |

---

## Architecture

```
Customer Request
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                    │
│  1. Hard-trigger check (legal/fraud keywords)            │
│  2. Triage LLM → intent + risk_tier + category          │
│  3. Threshold gate: amount > ₹500? → ESCALATE            │  ← deterministic
│  4. Refund Agent: DB lookup → Policy KB → LLM reasoning │
│  5. Safety Critic: re-fetch KB → faithfulness score     │
│  6. Verdict → ResolutionResponse + full trace           │
└──────────────────────────────────────────────────────────┘
         │                           │
    LLM Calls                   Every step
  (OpenRouter)               → TKT-*.json log
```

---

## Quick Start (Local)

```bash
# 1. Clone
git clone https://github.com/bottyash/cartly.git && cd cartly

# 2. Configure
cp .env.example .env
# Edit .env → set OPENROUTER_API_KEY=sk-or-v1-...
# Get a free key at: https://openrouter.ai

# 3. Start
docker compose up --build

# 4. Open
open http://localhost:3000
```

| URL | Description |
|-----|-------------|
| `http://localhost:3000` | Landing page (role selector) |
| `http://localhost:3000/user.html` | Customer portal |
| `http://localhost:3000/admin.html` | Admin dashboard (token: `cartly-admin-2026`) |
| `http://localhost:8000/docs` | FastAPI Swagger UI |

---

## Deploy to AWS EC2

```bash
# Prerequisites: AWS CLI configured, key pair created
export KEY_NAME=cartly-key
bash aws/launch.sh

# Deploy updates
export EC2_HOST=<public-ip>
bash aws/deploy.sh
```

See [`aws/README.md`](aws/README.md) for full guide.

---

## Dashboard

### 👤 Customer Portal (`/user.html`)
1. Enter your **Order ID** (demo: `1042`, `1077`, `1090`, `1099`)
2. Chat with the AI refund agent
3. Get instant decision with expandable pipeline trace

### 🔧 Admin Dashboard (`/admin.html`)
- Token: `cartly-admin-2026`
- 5 KPI cards · 4 Chart.js charts · FR1–FR8 coverage · Ticket table + trace modal

---

## Demo Tickets

| # | Order | Scenario | Amount | Result |
|---|-------|----------|--------|--------|
| 1 | 1042 | Damaged mug set (Priya Sharma) | ₹350 | ✅ Auto-resolved |
| 2 | 1077 | Non-delivery (Rahul Mehta) | ₹1200 | ⚠️ Threshold escalation |
| 3 | 1090 | Electronics return (Ananya Patel) | ₹450 | ⚠️ Critic rejects (policy trap) |
| 4 | 1099 | Legal threat (Vikram Singh) | ₹300 | 🚨 Hard-trigger escalation |

---

## Project Structure

```
cartly/
├── api/                FastAPI ingress (endpoints + schemas)
│   ├── main.py         — POST /tickets, GET /admin/stats, etc.
│   ├── schemas.py      — Pydantic models for all I/O
│   └── Dockerfile      — Production container
├── agents/
│   ├── orchestrator.py — Ticket lifecycle controller
│   ├── refund_agent.py — Refund Specialist (FR2, FR3)
│   ├── safety_critic.py— Safety/Quality Critic (FR6, FR7)
│   └── llm_gateway.py  — OpenRouter client (was Ollama in Sprint 1)
├── data/
│   ├── mock_db.py      — PostgreSQL order lookup
│   ├── policy_kb.py    — Policy retrieval + hard-trigger check
│   └── seed_orders.sql — 20 demo orders across 9 buyers
├── observability/
│   └── logger.py       — Per-ticket JSON event logger (FR8)
├── dashboard/
│   ├── index.html      — Landing page (role selector)
│   ├── user.html/js    — Customer portal
│   ├── admin.html/js   — Admin observability dashboard
│   ├── styles.css      — Shared dark design system
│   └── nginx.conf      — Multi-page routing
├── aws/                AWS deployment scripts
├── .github/workflows/  CI/CD (test → deploy on push to main)
├── scripts/
│   └── seed_demo_logs.py — Historical log generator
├── tests/              Unit + integration + admin API tests
├── docker-compose.yml
├── docker-compose.prod.yml
└── .env.example        — All env vars documented
```

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | ✅ Yes | — | OpenRouter API key |
| `OPENROUTER_MODEL` | No | `meta-llama/llama-3.2-3b-instruct` | LLM model |
| `ADMIN_TOKEN` | No | `cartly-admin-2026` | Admin dashboard token |
| `THRESHOLD_AMOUNT` | No | `500` | Auto-resolve ceiling (INR) |
| `FAITHFULNESS_FLOOR` | No | `0.70` | Critic rejection threshold |

---

## Team & Sprints

| Sprint | Period | Focus | Authors |
|--------|--------|-------|---------|
| Sprint 0 | Jun 22–24 | Discovery, PDLC, scaffolding | Yash, Avishka, Hiten |
| Sprint 1 | Jun 25–Jul 12 | Core agents, API, tests | Hiten, Yash, Avishka |
| Sprint 2 | Jul 13–Jul 17 | Dual dashboard, admin endpoints | Avishka, Yash, Hiten |
| Sprint 3 | Jul 18–Jul 21 | OpenRouter, AWS, CI/CD, submission | All |

```
Yash Parmar    → yash.parmar@cartly.dev
Hiten Mistry   → 110992323+hiten4@users.noreply.github.com
Avishka Jindal → 244519419+avishkajindal05@users.noreply.github.com
```

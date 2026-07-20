# AI-ERP-Finance — The AI Finance Assistant

An AI-powered ERP Accounts & Finance platform designed to be more intelligent,
automated, and user-friendly than SAP Business One. The goal: **users never
manually perform repetitive accounting work** — the AI does bookkeeping, journal
entries, invoice processing, tax, reconciliation, forecasting, and fraud
detection.

> **Status: Phase 1 — Runnable Core.** This is a real, working vertical slice
> with a correct double-entry accounting engine, JWT auth + RBAC, the core
> finance modules (GL, AR, AP, Vendors, Customers, Invoices, Dashboard), and a
> working AI brain that runs **with no external API key** (rule-based fallbacks)
> and upgrades to GPT/Claude when a key is present. Remaining modules
> (Payroll, GST/TDS returns, Inventory, Assets, Procurement, Workflow builder,
> K8s, full test suites) are architected and roadmapped — see
> [docs/ROADMAP.md](docs/ROADMAP.md).

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind, Recharts |
| Backend | FastAPI, Python 3.11+, SQLAlchemy 2.0, Pydantic v2 |
| DB | PostgreSQL (prod) / SQLite (zero-config dev default) |
| Cache/Queue | Redis + Celery (wired in compose; used from Phase 2) |
| Auth | JWT (access/refresh), RBAC; OAuth/Azure AD/MFA in Phase 2 |
| AI | Pluggable provider: OpenAI GPT / Anthropic Claude / rule-based fallback |

## Quick start (zero config — SQLite, no Docker)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed          # creates DB + demo company, users, COA, txns
uvicorn app.main:app --reload   # http://localhost:8000  (docs at /docs)
```

Then the frontend:

```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

Demo login: `cfo@demo.io` / `demo1234` (see all seeded users in the seed output).

## Full stack (Postgres + Redis via Docker)

```bash
cp .env.example .env            # optionally add OPENAI_API_KEY / ANTHROPIC_API_KEY
docker compose up --build
```

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system & module architecture
- [docs/DATABASE.md](docs/DATABASE.md) — schema, ER diagram, posting rules
- [docs/ROLES.md](docs/ROLES.md) — RBAC roles & permission matrix
- [docs/ROADMAP.md](docs/ROADMAP.md) — phased delivery plan for all modules

## What makes this "AI-first"

Every write path can be driven by AI, and the AI never bypasses accounting
integrity — it *proposes* journal entries that the double-entry engine validates
(debits must equal credits) before posting. See `backend/app/ai/` and
`backend/app/services/ledger.py`.

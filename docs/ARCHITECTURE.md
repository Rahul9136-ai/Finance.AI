# System Architecture

## 1. High-level

```
                        ┌───────────────────────────────────────────┐
                        │            Next.js Frontend (SPA/SSR)       │
                        │  Dashboard · GL · AR · AP · AI Assistant    │
                        └───────────────────┬─────────────────────────┘
                                            │ HTTPS / REST (JWT)
                                            ▼
              ┌──────────────────────────────────────────────────────────┐
              │                     FastAPI API Gateway                    │
              │   Auth · RBAC · Validation · Rate limit · Audit middleware │
              └───┬───────────────┬──────────────┬───────────────┬────────┘
                  │               │              │               │
                  ▼               ▼              ▼               ▼
         ┌──────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────┐
         │ Ledger Engine│ │  AR / AP     │ │  Tax      │ │  AI Services │
         │ (double-entry│ │  Invoicing   │ │ GST / TDS │ │ OCR·Chat·    │
         │  posting)    │ │  Payments    │ │           │ │ Fraud·Forecast│
         └──────┬───────┘ └──────┬───────┘ └─────┬─────┘ └──────┬───────┘
                │                │               │              │
                └────────────────┴───────┬───────┴──────────────┘
                                         ▼
                        ┌────────────────────────────────┐
                        │  PostgreSQL (multi-tenant, RLS) │
                        │  Redis (cache)  ·  Celery (jobs) │
                        └────────────────────────────────┘
```

## 2. Design principles

1. **Accounting integrity is non-negotiable.** All financial mutations flow
   through the **Ledger Engine** (`services/ledger.py`). It enforces
   double-entry (Σdebits = Σcredits), immutable posted entries (corrections are
   reversing entries), and period locks. AI *proposes*; the engine *validates*.
2. **Multi-tenant from day one.** Every domain row carries `org_id`. A tenant
   context dependency scopes all queries. Postgres Row-Level Security is the
   Phase-2 hard boundary; the ORM scoping is the Phase-1 boundary.
3. **AI is a pluggable provider, not a hard dependency.** `ai/provider.py`
   selects OpenAI → Anthropic → deterministic rule-based fallback based on
   available keys, so the system is fully functional offline for demos/tests.
4. **Event-driven where it matters.** Domain events (`InvoicePosted`,
   `PaymentReceived`) are emitted for async work (reminders, reconciliation,
   dashboard cache invalidation) — synchronous in Phase 1, Celery in Phase 2.
5. **Everything auditable.** An `AuditLog` middleware records who/what/when for
   every mutating request.

## 3. Backend layering

```
app/
  main.py            # app factory, middleware, router registration
  core/              # config, security (JWT/hashing), deps, RBAC, audit
  db/                # engine, session, base
  models/            # SQLAlchemy ORM (the schema)
  schemas/           # Pydantic request/response contracts
  services/          # business logic (ledger, invoicing, dashboard, tax)
  ai/                # provider abstraction + finance skills
  api/routers/       # thin HTTP handlers -> services
```

Rule: routers do **no** business logic; they authenticate, validate (Pydantic),
call a service, and shape the response. Services own transactions and invariants.

## 4. AI brain

| Skill | Input | Output | Fallback (no key) |
|---|---|---|---|
| Invoice Reader | PDF/text | structured invoice (vendor, lines, tax, total) | regex/heuristic field extraction |
| Finance Chatbot | NL question | answer grounded in live DB metrics | LLM tool-calling over the other 4 skills (falls back to intent-matched metric lookups with no LLM key) |
| Expense Categorizer | description + amount | GL account + confidence | keyword rules learned from history |
| Fraud Detector | transaction | risk score + reasons | deterministic rules (dupes, round-amount, weekend, off-hours) |
| Cashflow Forecast | horizon days | projected balance curve | AR/AP-aging + moving-average model |

The chatbot and forecaster are **grounded** — they read real ledger data via
services, so answers are correct rather than hallucinated.

## 5. Non-functional

- **Performance:** indexed queries, pagination on all list endpoints, Redis
  cache for dashboard aggregates (Phase 2), sub-second p95 target.
- **Security:** bcrypt password hashing, short-lived access + rotating refresh
  tokens, RBAC on every route, audit log, secrets via env only.
- **Observability:** structured JSON logging, `/health` + `/health/ready`,
  request-id propagation; Prometheus metrics in Phase 2.
- **Deployability:** 12-factor config, Docker images per service, compose for
  local, Kubernetes manifests + Helm in Phase 2.

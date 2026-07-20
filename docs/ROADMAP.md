# Delivery Roadmap

The brief describes ~20 ERP modules, ~30 infra deliverables, and dozens of AI
features. This is delivered in phases on top of the Phase 1 core, which is a
real, running vertical slice with a correct accounting engine.

## ✅ Phase 1 — Runnable Core (done)

- Architecture, DB schema + ER, RBAC roles (docs/)
- FastAPI backend, SQLAlchemy models, SQLite/Postgres
- JWT auth (access/refresh) + fine-grained RBAC + audit middleware
- **Double-entry ledger engine** (balanced, immutable, reversible) — unit tested
- Chart of Accounts, Journal, Vendors, Customers
- AR/AP invoicing with **auto-generated journal entries**, payments/settlement
- Dashboard KPIs, AR/AP aging, P&L, balance sheet, revenue series
- AI brain: invoice reader, grounded chatbot, expense categorizer, fraud
  detection, cashflow forecast — **all with no-key rule-based fallbacks**
- Next.js frontend: login, dashboard + charts, GL, invoices, AI assistant,
  dark mode
- Docker Compose (Postgres + Redis + backend + frontend)

## 🔜 Phase 2 — Automation & Tax

- Celery + RabbitMQ/Redis workers; event bus (`InvoicePosted` → reminders,
  reconciliation, cache invalidation)
- GST module: GSTR-1 / GSTR-3B generation, HSN/SAC, e-way bill, validation
- TDS module: auto-deduction, returns, certificates, interest/late fee
- Bank module: statement import (PDF/CSV/Excel), **AI reconciliation** matching
  payments↔invoices, cheque/NEFT/RTGS/UPI tracking
- OAuth / Azure AD / Google login + MFA
- Alembic migrations as the source of truth; Postgres Row-Level Security
- Workflow engine: approval matrix, role-based/conditional approval, escalation

## 🔜 Phase 3 — Operational modules

- Payroll (PF/ESIC/PT/TDS, payslips, payroll journal)
- Inventory (batches/serials/expiry, valuation, ABC, EOQ, demand forecast)
- Fixed Assets (register, depreciation schedules, disposal, QR/barcode)
- Procurement (PR→RFQ→PO→GRN, vendor comparison, budget validation)
- Sales (quote→order→delivery→invoice, commissions, analytics)
- Budgeting & cost accounting (cost/profit centers, variance, scenario planning)

## 🔜 Phase 4 — Scale & platform

- Kubernetes manifests + Helm chart, HPA, PodDisruptionBudgets
- CI/CD (GitHub Actions: lint, test, build, scan, deploy)
- Observability: Prometheus/Grafana, OpenTelemetry tracing, structured logs
- 500+ report catalog + scheduled/emailed reports; Power BI/Tableau connectors
- Reports export (PDF/Excel/CSV), command palette, global semantic search
- Integrations: Tally/SAP/Oracle, Stripe/Razorpay/PayPal, WhatsApp/Slack/Teams
- Multi-tenant SaaS hardening, backup & DR, SOC2/ISO-27001 controls, PWA/offline

## Architectural guarantees preserved across phases

1. All money movement flows through the ledger engine — **no module bypasses
   double-entry**.
2. AI proposes; the engine validates. AI never writes unbalanced entries.
3. Every domain row is `org_id`-scoped for multi-tenancy.
4. Every mutation is audited.

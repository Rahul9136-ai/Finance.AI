# Deployment Guide

Finance.AI is two services: a **Next.js frontend** and a **FastAPI backend**.

- **Frontend → Vercel** (great fit).
- **Backend → a container host** (Railway / Render / Fly.io). It is **not**
  suitable for Vercel serverless: the OCR/PDF stack (`onnxruntime`, `pdfplumber`,
  `pypdfium2`, `rapidocr`) exceeds the serverless size limit, and SQLite is
  ephemeral there — use managed **Postgres** in production.

Deploy the **backend first** (you need its public URL for the frontend).

---

## 1. Backend → Railway (recommended, uses the existing Dockerfile)

1. Create a project at [railway.app](https://railway.app) → **Deploy from GitHub repo**
   → select `Rahul9136-ai/Finance.AI`.
2. In the service settings set **Root Directory** = `backend` (it will detect
   `backend/Dockerfile`).
3. Add a **PostgreSQL** database (Railway → New → Database → PostgreSQL).
4. Set the service **Variables**:
   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `postgresql+psycopg2://…` (from the Railway Postgres "Connect" tab; add the `+psycopg2` driver) |
   | `SECRET_KEY` | any 32+ char random string |
   | `CORS_ORIGINS` | your Vercel URL, e.g. `https://finance-ai.vercel.app` |
   | `OPENAI_API_KEY` *(optional)* | for AI extraction |
   | `ANTHROPIC_API_KEY` *(optional)* | alternative to OpenAI |
   | `AI_PROVIDER` *(optional)* | `openai` or `anthropic` |
5. Deploy. The container **seeds the DB on boot** (idempotent) and serves on
   Railway's `$PORT`. Note the public URL, e.g. `https://finance-ai-backend.up.railway.app`.
6. Sanity check: open `https://<backend-url>/health` → `{"status":"ok"}`.

> Render/Fly.io work the same way — point them at `backend/Dockerfile`, add a
> Postgres addon, set the same env vars.

---

## 2. Frontend → Vercel

1. At [vercel.com](https://vercel.com) → **Add New → Project** → import
   `Rahul9136-ai/Finance.AI`.
2. Set **Root Directory** = `frontend` (Vercel auto-detects Next.js).
3. Add an **Environment Variable**:
   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | the backend URL from step 1, e.g. `https://finance-ai-backend.up.railway.app` |
4. **Deploy.** Vercel builds and gives you `https://<project>.vercel.app`.
5. Go back to the backend and make sure `CORS_ORIGINS` includes this Vercel URL,
   then redeploy the backend.

`frontend/next.config.mjs` rewrites `/api/*` to `NEXT_PUBLIC_API_URL` server-side,
so the browser stays same-origin (no CORS needed for the proxied calls).

### Or deploy the frontend via CLI

```bash
cd frontend
npx vercel login          # authenticate to your account
npx vercel --prod         # set Root Directory / env when prompted
```

---

## 3. First login

Open the Vercel URL and sign in with a seeded demo account:

- `cfo@demo.io` / `demo1234` (full access)

Seeded users: admin / cfo / manager / accountant / auditor (all `demo1234`).

---

## Notes

- **Secrets**: never commit `.env`. Set all keys in the host's dashboard.
- **Persistence**: use Postgres in prod; SQLite is for local dev only.
- **Costs**: Vercel + Railway/Render have free tiers sufficient for a demo.

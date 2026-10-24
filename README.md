# One English — school platform

Web platform (FastAPI + Vue 3) for One English, Shymkent: schedule, attendance, balances, CRM with an Instagram/WhatsApp inbox,
chats, finance, payroll/KPI, tasks, books, coins and shop, training base, complaints, student and parent cabinet.
A Flutter app for iOS/Android comes next and uses the same API (`/api/portal/*`, `/api/chats/*`, `/api/auth/*`).

- `docs/PLAN.md` — stages and architecture; `docs/DECISIONS.md` — client decisions that override the ТЗ.
- `docs/design/` — design system and prototypes (web, mobile, icons).

## Run locally

Requirements: Python 3.13 + [uv](https://docs.astral.sh/uv/), PostgreSQL 16, Redis (optional in dev), Node 22.

```bash
# backend
cd backend
uv venv && uv pip install -r pyproject.toml --extra dev
createdb one_english                                  # user/password from OE_DATABASE_URL
export OE_DATABASE_URL=postgresql+asyncpg://oe:oe@localhost:5432/one_english
alembic upgrade head
python -m app.seed --demo                             # demo school; staff password printed at the end
OE_REQUIRE_STAFF_2FA=false uvicorn app.main:app --reload   # API on :8000, docs at /api/docs
python -m app.jobs loop                               # background jobs (separate process)

# web
cd web && npm install && npm run dev                  # http://localhost:5173, proxies /api to :8000
```

Demo owner: `+77010000001` / `Demo-pass-2026` (only when loaded with `--demo`; never in production).

## Tests

```bash
cd backend && pytest -q          # uses database one_english_test
ruff check app tests
cd web && npm run build          # type check + build
```

## Settings (env, prefix `OE_`)

| Variable | Meaning |
|---|---|
| `OE_ENV` | `dev` / `test` / `production` |
| `OE_DATABASE_URL`, `OE_REDIS_URL` | PostgreSQL and Redis |
| `OE_JWT_SECRET` | long random secret, required in production |
| `OE_REQUIRE_STAFF_2FA` | staff must use 2FA for finance, payroll, roles, security, audit (default on) |
| `OE_META_*` | WhatsApp Cloud API / Instagram tokens and webhook secret; without them messages are only logged |
| `OE_STORAGE_DIR` | where uploaded files are kept |

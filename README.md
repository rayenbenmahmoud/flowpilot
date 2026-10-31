# FlowPilot

**Workflow automation for business operations.** Receive events through a signed webhook, evaluate rules, run actions through reusable API adapters, and monitor every execution, with safe retries and duplicate protection.

Built with Django REST Framework, React + TypeScript, Celery, PostgreSQL and n8n-compatible webhooks.

![Fail, retry, succeed: a failed workflow run is retried and succeeds](docs/screenshots/demo-flow.gif)

![Dashboard](docs/screenshots/dashboard.png)

> **Demo mode is on by default.** Email, n8n and partner APIs are simulated, so everything runs on a laptop with no accounts, API keys or paid services. A banner in the UI shows the mode on every screen.

## 🚀 Live Demo

**Try FlowPilot online:** [rayenbenmahmoud-flowpilot.duckdns.org](https://rayenbenmahmoud-flowpilot.duckdns.org)

Explore the dashboard, run workflow automation scenarios, and test execution monitoring, retries, and duplicate-event protection.

> **Demo mode:** External integrations are simulated. No API keys or external accounts are required.

## Features

- **Workflow engine:** an event triggers rules (all/any conditions) and ordered actions, configured as validated data with a small, code-free template language (`{{ payload.total }}`, `{{ payload.currency | default:EUR }}`).
- **Six templates:** welcome email, new-order notification, n8n order hand-off, low-inventory alert, support-ticket routing by rules, and an automatic error notification whenever any workflow fails.
- **Execution history:** status, start time, duration, input summary, step log and error details, with filtering by workflow, status and date, plus search.
- **Safe retries:** a retry creates a new attempt and never repeats steps that already finished.
- **Duplicate protection:** idempotency keys enforced by a database unique constraint.
- **Secure webhook:** HMAC signature, replay protection, payload validation, size limit and rate limiting.
- **Integration adapters:** email (SMTP), n8n and a generic REST client behind one interface, with timeouts and bounded retries.
- **Honest status:** an integration shows *Connected* only after a live test passes.
- **Guided demo:** nine scenarios, including a bounce, a temporary failure that succeeds on retry, and a duplicate event.
- **Accessible, responsive UI:** keyboard navigable, screen-reader labels, works on mobile.

## Tech stack

| Layer | Technology |
|---|---|
| API | Python 3.12, Django 6, Django REST Framework, drf-spectacular (OpenAPI/Swagger) |
| Background jobs | Celery + Redis (runs inline when no broker is configured) |
| Database | PostgreSQL (SQLite for the zero-setup local run) |
| Frontend | React 19, TypeScript, Vite, React Router |
| Integrations | SMTP email, n8n webhooks, generic REST API |
| Quality | pytest, Vitest, Ruff, ESLint, TypeScript strict mode |
| Packaging | Docker Compose |

## Screenshots

| | |
|---|---|
| ![Workflows](docs/screenshots/workflows.png) **Workflows** | ![Workflow editor](docs/screenshots/workflow-editor.png) **Rules and actions** |
| ![Failed execution](docs/screenshots/execution-failed.png) **A failed run with a clear error and Retry** | ![Retry succeeded](docs/screenshots/retry-success.png) **Attempt 2 succeeded** |
| ![Guided demo](docs/screenshots/guided-demo.png) **Guided demo** | ![Duplicate event](docs/screenshots/duplicate-event.png) **Duplicate event not run twice** |
| ![Outputs](docs/screenshots/outputs-mailbox.png) **Simulated mailbox** | ![Integrations](docs/screenshots/integrations.png) **Integrations (simulated in demo mode)** |
| ![API docs](docs/screenshots/api-docs.png) **OpenAPI / Swagger** | ![Mobile](docs/screenshots/mobile-dashboard.png) **Mobile** |

## Architecture

```mermaid
flowchart TB
    subgraph Sources[Event sources]
      S1[Shop / CRM / n8n]
      S2[Guided demo in UI]
    end
    S1 -- "signed webhook (HMAC, timestamp, Idempotency-Key)" --> WH
    subgraph API[Django REST API]
      WH[Webhook endpoint<br/>rate limit, size, signature,<br/>schema validation]
      DASH[Dashboard API<br/>token auth]
      DISP[dispatch_event<br/>one Execution per workflow<br/>unique idempotency key]
    end
    S2 -- "authenticated" --> DASH --> DISP
    WH --> DISP
    DISP -- "enqueue" --> Q[(Redis / Celery<br/>inline if no broker)]
    Q --> RUN[Runner<br/>conditions, ordered actions,<br/>ActionEffect ledger]
    RUN --> AD[Adapters<br/>Email, n8n, HTTP<br/>timeouts, bounded retries]
    AD -- "demo mode: simulated" --> SIM[(Outbox / notifications / tickets)]
    AD -- "live mode: configured + tested" --> EXT[SMTP, n8n, partner API]
    RUN --> DB[(PostgreSQL / SQLite)]
    RUN -- "on failure: workflow.failed event" --> DISP
    UI[React + TypeScript dashboard] --> DASH
    DB --- DASH
```

More diagrams (execution lifecycle, webhook pipeline) and design notes: [docs/architecture.md](docs/architecture.md).

## Quick start (no Docker, Redis or PostgreSQL)

Requires Python 3.12+ and Node 20+. Uses SQLite and runs background jobs inline.

```bash
git clone https://github.com/rayenbenmahmoud/flowpilot.git && cd flowpilot
cp .env.example .env
# generate a webhook secret and paste it after FLOWPILOT_WEBHOOK_SECRET= in .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Terminal 1: backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 8000
```

**Terminal 2: frontend**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> and sign in with `demo` / `flowpilot-demo` (set by `FLOWPILOT_DEMO_USER_PASSWORD`). Open **Guided demo** in the sidebar. Interactive API docs: <http://localhost:8000/api/docs/>.

## Docker Compose (PostgreSQL + Redis + Celery worker)

```bash
cp .env.example .env     # set FLOWPILOT_WEBHOOK_SECRET and POSTGRES_PASSWORD
docker compose up --build
```

UI at <http://localhost:8080>, API docs at <http://localhost:8080/api/docs/>. Add `--profile n8n` to also start a local n8n.

## Configuration

All settings are environment variables (see `.env.example`, which holds placeholders only).

| Variable | Purpose |
|---|---|
| `FLOWPILOT_DEMO_MODE` | `true` simulates every integration (default). `false` uses real ones when configured |
| `DJANGO_SECRET_KEY` | Required when `DJANGO_DEBUG=false` |
| `FLOWPILOT_WEBHOOK_SECRET` | Signs inbound webhooks. **Webhooks are refused while empty** |
| `FLOWPILOT_WEBHOOK_RATE` | Per-IP limit, default `60/min` |
| `DATABASE_URL` | Empty = SQLite. `postgres://user:pass@host:5432/db` for PostgreSQL |
| `CELERY_BROKER_URL`, `REDIS_URL` | Empty = inline execution and in-process rate-limit cache |
| `FLOWPILOT_MAX_ATTEMPTS` | Max attempts per execution chain (default 3) |
| `FLOWPILOT_ADAPTER_TIMEOUT`, `FLOWPILOT_ADAPTER_MAX_ATTEMPTS` | Timeout and attempts for each external call |
| `FLOWPILOT_N8N_BASE_URL`, `FLOWPILOT_N8N_WEBHOOK_SECRET` | Live n8n (needs your own n8n instance) |
| `FLOWPILOT_EXTERNAL_API_BASE_URL`, `FLOWPILOT_EXTERNAL_API_KEY` | Live partner API |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, ... | Live SMTP (needs your own mail account) |

Integrations that need a separate account: an **SMTP provider**, **n8n** (self-hosted or cloud) and any **partner REST API**. None are required for the demo.

## Sending a signed webhook

```bash
export FLOWPILOT_WEBHOOK_SECRET=<value from .env>
BODY='{"order_id":"ORD-1","total":42,"event_id":"evt-1"}'
TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$FLOWPILOT_WEBHOOK_SECRET" -hex | sed 's/^.* //')
curl -X POST http://localhost:8000/api/v1/webhooks/order.created/ \
  -H "Content-Type: application/json" \
  -H "X-FlowPilot-Timestamp: $TS" -H "X-FlowPilot-Signature: sha256=$SIG" \
  -d "$BODY"
```

Run it again unchanged: the response is `200` with `"duplicate": true` and nothing runs twice. A helper script is also included: `python backend/scripts/send_webhook.py order.created '{"order_id":"A1","total":9}'`.

Accepted events: `customer.registered`, `order.created`, `inventory.updated`, `support.request.created`. Each has a validated schema (see `/api/docs/` and `GET /api/v1/meta/`).

## Tests, lint and type checks

```bash
# backend
cd backend && source .venv/bin/activate
python -m pytest                              # 119 tests
python -m pytest --cov=automation             # with coverage
ruff check . && ruff format --check .
DJANGO_DEBUG=true python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yml

# frontend
cd frontend
npm run lint
npm run typecheck
npm test                                      # 26 tests
npm run build
```

## Project layout

```
backend/
  config/                Django settings, Celery app, URLs
  automation/
    models.py            Workflow, Execution, ExecutionLog, ActionEffect (idempotency ledger), outputs
    engine/              templating, conditions, redaction, validation, actions, runner (dispatch/run/retry)
    integrations/        BaseAdapter + email, n8n, generic HTTP adapters, status registry
    views.py, serializers.py, filters.py, webhook_auth.py, throttles.py
    demo.py              guided scenarios and seed data
    tests/               unit and integration tests
  scripts/send_webhook.py
frontend/src/            React + TypeScript app (pages, components, API client, tests)
docs/                    architecture, reliability, demo mode, troubleshooting, n8n example, screenshots
```

## Documentation

- [Architecture (Mermaid diagrams)](docs/architecture.md)
- [Reliability: idempotency, retries, duplicates](docs/reliability.md)
- [Demo mode and limitations](docs/demo-mode-and-limitations.md)
- [Troubleshooting](docs/troubleshooting.md)
- [n8n setup](docs/n8n/README.md)

## Status

- Covered by automated tests: backend (pytest, 94% line coverage), frontend (Vitest), linting, type checks and OpenAPI validation.
- The backend test suite also passes on PostgreSQL 16, and the stack was run with Redis, a separate Celery worker, gunicorn and nginx (the components used by the Docker Compose setup).
- Demo mode simulates email, n8n and partner APIs. Live mode needs your own credentials and has been tested only against mocked services.
- Seeded history is synthetic demo data.
- Not load-tested. Single-tenant, no role management. See [limitations](docs/demo-mode-and-limitations.md).

## License

[MIT](LICENSE)

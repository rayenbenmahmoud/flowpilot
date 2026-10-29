# Architecture

## System overview

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

## Execution lifecycle

```mermaid
stateDiagram-v2
    [*] --> Queued: event accepted
    Queued --> Running: worker starts (only PENDING can start)
    Running --> Succeeded: all actions done
    Running --> Skipped: conditions not met
    Running --> Failed: action error
    Failed --> Queued: Retry creates attempt N+1 (new row)
    Failed --> [*]: attempt limit reached
    Succeeded --> [*]
    Skipped --> [*]
```

## Webhook request pipeline

```mermaid
sequenceDiagram
    participant C as Caller
    participant W as Webhook view
    participant D as dispatch_event
    participant R as Runner
    C->>W: POST /webhooks/{event}/ + signature
    W->>W: rate limit, size limit
    W->>W: verify timestamp + HMAC
    W->>W: known event? JSON? schema valid? idempotency key?
    W->>D: event, payload, key
    D->>D: existing (workflow, key)? yes: mark duplicate
    D->>R: new Execution queued
    R-->>D: result recorded
    W-->>C: 202 (new) or 200 (duplicate) + execution ids
```

## Key design decisions

- **Rules are data, not code.** Conditions and actions are validated JSON; templates are a tiny `{{ payload.x | default:y }}` language with no expression evaluation.
- **Adapters isolate the outside world.** Every external call goes through `BaseAdapter`: demo/live switch, `ensure_ready()`, hard timeouts, bounded retries, redirects not followed, error messages free of secrets.
- **Secrets and URLs are environment-only.** The UI can change harmless settings (timeouts, from-address) but cannot set URLs or secrets, which removes a server-side request forgery path.
- **Failures are data.** A failed run is recorded with a stable error code, a human message and a retryable hint, then emits `workflow.failed`, which the failure-notification workflow turns into an error notification.
- **One data model for local and production.** SQLite for a zero-setup demo, PostgreSQL via `DATABASE_URL`; inline execution without a broker, Celery with Redis when one is configured.

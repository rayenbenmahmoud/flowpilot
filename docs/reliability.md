# Reliability: duplicates, idempotency and retries

## How duplicate events are handled

Senders (and networks) deliver webhooks more than once. FlowPilot treats the **idempotency key** as the identity of an event.

1. The key comes from the `Idempotency-Key` header or an `event_id` field in the body. Webhooks without one are rejected with `missing_idempotency_key`, because without it a duplicate cannot be told apart from a genuinely new, identical event.
2. For each active workflow that listens to the event, FlowPilot looks for an execution with the same `(workflow, key)`.
3. A database **unique constraint** on `(workflow, idempotency_key)` guarantees that two simultaneous deliveries cannot both create an execution. The loser catches the integrity error and is reported as a duplicate.
4. A duplicate returns HTTP `200` with `"duplicate": true` and the ids of the original executions. Nothing runs again.

The key is scoped per workflow, so one order event can still trigger several different workflows.

Manual test runs accept an optional `Idempotency-Key` header too; the UI sends a fresh one per click so a double-click cannot run twice.

## How retries stay safe

- Only **failed** executions can be retried, only the **latest** attempt (one retry per attempt, enforced by the same unique constraint), only while the workflow is **active**, and only until `FLOWPILOT_MAX_ATTEMPTS`.
- A retry is a **new execution row** (`attempt + 1`, `retry_of` pointing to the failed one), so history is never rewritten.
- Every completed action step is recorded in the `ActionEffect` ledger, keyed by `<first-attempt-id>:<step>:<type>`, in the **same database transaction** as the rows the step produced (email record, notification, ticket assignment). A retry skips steps already in the ledger. Example: step 1 sends the welcome email, step 2 (n8n) is down; after the outage the retry runs step 2 only. This is covered by `test_partial_failure_retry_does_not_repeat_completed_steps`.
- The worker only starts executions that are `PENDING`, so a redelivered Celery task or a double click does nothing.

## What is and is not guaranteed

- **Local effects** (outbox, notifications, assignments) are exactly-once per step.
- **External effects** (a real email, an n8n call) are **at-least-once**. If the process dies after the external system accepted the request but before the ledger entry commits, a retry could repeat that single call. To limit the damage, FlowPilot sends the step key as `Idempotency-Key` (HTTP calls) or `X-FlowPilot-Idempotency-Key` (email header) so receivers can de-duplicate. Make your n8n workflow or partner API honour it for true end-to-end exactly-once.
- An execution stuck in `Running` after a hard worker crash is **not** automatically recovered (see limitations).

## Timeouts and limits

| Setting | Default | Effect |
|---|---|---|
| `FLOWPILOT_ADAPTER_TIMEOUT` | 5 s | Hard timeout per external HTTP call (editable per integration, 1 to 30 s) |
| `FLOWPILOT_ADAPTER_MAX_ATTEMPTS` | 2 | Network errors, timeouts and 5xx are retried with 0.5 s, 1 s, … backoff up to this limit; 4xx are never retried |
| `FLOWPILOT_MAX_ATTEMPTS` | 3 | Attempts per execution chain |
| `FLOWPILOT_WEBHOOK_MAX_BYTES` | 65536 | Webhook body size limit |
| `FLOWPILOT_WEBHOOK_TOLERANCE_SECONDS` | 300 | Allowed clock difference (replay protection) |

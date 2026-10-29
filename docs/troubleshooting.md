# Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `ImproperlyConfigured: Set DJANGO_SECRET_KEY` | `DJANGO_DEBUG` is not `true` and no key is set. For local use set `DJANGO_DEBUG=true` in `.env`, or generate a key. |
| Login page says *Cannot reach the API* | Backend is not running on port 8000. Start `python manage.py runserver 8000`. |
| Webhook returns `503 webhook_not_configured` | `FLOWPILOT_WEBHOOK_SECRET` is empty. Set it and restart the backend. |
| Webhook returns `401 invalid_signature` | Sign the **exact raw body bytes** as `"<timestamp>.<body>"` with HMAC-SHA256 and send `sha256=<hex>`. Re-serialising JSON changes the bytes. |
| `401 stale_timestamp` | Caller clock differs from the server by more than 300 s. Sync the clock. |
| `400 missing_idempotency_key` | Send `Idempotency-Key` or an `event_id` field. |
| `200` with `"duplicate": true` | Working as intended: that key was already processed. Use a new key for a new event. |
| `429` from the webhook | Rate limit (`FLOWPILOT_WEBHOOK_RATE`, default 60/min per IP). Honour `Retry-After`. |
| Executions stay *Queued* | A broker is configured but no worker is running. Start `celery -A config worker -l info`, or clear `CELERY_BROKER_URL` to run inline. |
| Execution *Failed* with `integration_disabled` | The integration is switched off on the Integrations page. |
| Execution *Failed* with `not_configured` | Demo mode is off and a required variable is missing; the message names it. |
| *Missing value for `{{ payload.x }}`* | The event lacks a field the workflow uses. Add `| default:text` for optional fields. |
| Retry button disabled | Hover the message under it: already retried, attempt limit reached, or workflow not active. |
| `Demo tools are only available while FLOWPILOT_DEMO_MODE is on` | Expected when demo mode is off. |
| Swagger page blank | Run `python manage.py collectstatic` (Docker does this at build). Assets are served locally, no CDN needed. |
| Frontend `npm run dev` API errors | Dev server proxies `/api` to `http://localhost:8000`; override with `VITE_BACKEND_URL`. |
| Compose `backend` exits at start | Check `docker compose logs backend`; usually a missing `.env` or Postgres still starting. |
| Port already in use | Change the host port in `docker-compose.yml` or stop the other process. |

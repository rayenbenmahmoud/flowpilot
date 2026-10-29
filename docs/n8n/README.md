# Connecting n8n

FlowPilot talks to n8n in the direction **FlowPilot → n8n** through the `Trigger n8n workflow` action, and n8n can talk back with a signed `POST /api/v1/webhooks/<event>/`.

## FlowPilot → n8n (live mode)

1. Run n8n (`docker compose --profile n8n up n8n`, or your own instance).
2. Import `flowpilot-order-receiver.json`. In n8n create a **Header Auth** credential (name `X-FlowPilot-Secret`, value = a secret you generate) and attach it to the Webhook node. Activate the workflow. (Node versions can differ across n8n releases; adjust if the import warns.)
3. In `.env` set `FLOWPILOT_DEMO_MODE=false`, `FLOWPILOT_N8N_BASE_URL=http://localhost:5678` and `FLOWPILOT_N8N_WEBHOOK_SECRET=<same secret>`.
4. Integrations → n8n → **Test connection** (calls `/healthz`). Enable the *Hand orders to n8n* workflow and send an `order.created` event.

Each call carries `Idempotency-Key` (the step key); let your n8n workflow ignore keys it has seen to get exactly-once behaviour.

## n8n → FlowPilot

Use an n8n **HTTP Request** node: method `POST`, URL `http://<host>:8000/api/v1/webhooks/order.created/`, JSON body, and a **Code** node before it that computes the timestamp and `sha256=` HMAC of `"<timestamp>.<body>"` using the webhook secret (n8n's Crypto node supports HMAC-SHA256). Send `X-FlowPilot-Timestamp`, `X-FlowPilot-Signature` and an `event_id` in the body.

This integration path has been tested against a mocked n8n endpoint only, not a real n8n instance.

#!/usr/bin/env python3
"""Send a correctly signed webhook to a running FlowPilot (standard library only).

    FLOWPILOT_WEBHOOK_SECRET=... python scripts/send_webhook.py order.created '{"order_id":"A1","total":42}'

The secret is read from the environment so it never lands in shell history or process lists.
Use the same event_id twice to see duplicate prevention.
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("FLOWPILOT_URL", "http://localhost:8000")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    event, raw = sys.argv[1], sys.argv[2]
    secret = os.environ.get("FLOWPILOT_WEBHOOK_SECRET")
    if not secret:
        print("Set FLOWPILOT_WEBHOOK_SECRET in the environment.", file=sys.stderr)
        return 2
    payload = json.loads(raw)
    payload.setdefault("event_id", f"cli-{int(time.time() * 1000)}")
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    signature = "sha256=" + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        f"{BASE}/api/v1/webhooks/{event}/",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-FlowPilot-Timestamp": timestamp,
            "X-FlowPilot-Signature": signature,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            print(response.status, response.read().decode())
    except urllib.error.HTTPError as error:
        print(error.code, error.read().decode())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

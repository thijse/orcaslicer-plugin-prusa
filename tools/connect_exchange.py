"""Exchange a Prusa Account authorization code for tokens (verifier from pkce_pending.json)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

CLIENT_ID = "oamhmhZez7opFosnwzElIgE2oGgI2iJORSkw587O"
DATA_DIR = os.path.expandvars(r"%APPDATA%\OrcaSlicer\orca_plugins\plugin_data\prusa")


def main() -> int:
    code = sys.argv[1]
    pending = os.path.join(DATA_DIR, "pkce_pending.json")
    with open(pending, encoding="utf-8") as f:
        verifier = json.load(f)["verifier"]
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": "prusaslicer://login",
            "code_verifier": verifier,
        }
    ).encode()
    req = urllib.request.Request(
        "https://account.prusa3d.com/o/token/",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            # Cloudflare answers 1010 to Python's default User-Agent.
            "User-Agent": "PrusaSlicer/2.9.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read()[:300])
        return 1
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": time.time() + float(data.get("expires_in", 3600)),
        "scope": data.get("scope", ""),
    }
    with open(os.path.join(DATA_DIR, "connect_tokens.json"), "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    os.remove(pending)
    print("ok; expires_in", data.get("expires_in"), "scope", data.get("scope"), "refresh", bool(tokens["refresh_token"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

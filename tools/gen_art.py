"""Generate the Prusa tab's printer illustration with CFI Lab gpt-image-2.

Reads PROXY_BASE_URL, LITELLM_API_KEY and SSL_VERIFY from $GEN_ART_ENV or tools/.env (or the env).
Usage: python tools/gen_art.py OUT.png ["prompt"]
"""

import base64
import os
import sys

import httpx
from openai import OpenAI

ENV = os.environ.get("GEN_ART_ENV", os.path.join(os.path.dirname(__file__), ".env"))

PROMPT = (
    "Clean flat vector-style product illustration of a Prusa XL 3D printer with a five-tool changer: "
    "a large cube-shaped open frame in dark charcoal grey aluminium profiles, five tool heads parked on a "
    "dock along the back of the frame, one tool head on the gantry, a square print bed, spools on the side. "
    "Signature Prusa orange (#FA6831) accents on the tool heads and frame corners. Three-quarter front view, "
    "soft subtle shading, minimal detail, no text, no logos, no people. Isolated on a fully transparent background."
)


def load_env() -> None:
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main() -> None:
    load_env()
    out = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else PROMPT
    verify = os.environ.get("SSL_VERIFY", "True").lower() not in ("false", "0", "no")
    client = OpenAI(base_url=os.environ["PROXY_BASE_URL"].rstrip("/") + "/v1", api_key=os.environ["LITELLM_API_KEY"],
                    http_client=httpx.Client(verify=verify, timeout=300), max_retries=2)
    result = client.images.generate(model="gpt-image-2", prompt=prompt, size="1024x1024", background="transparent",
                                    quality="high")
    with open(out, "wb") as f:
        f.write(base64.b64decode(result.data[0].b64_json))
    print("wrote", out)


if __name__ == "__main__":
    main()

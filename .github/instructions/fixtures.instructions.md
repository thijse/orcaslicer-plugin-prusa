---
description: "Use when adding or changing test fixtures, recorded API responses, capture scripts or README screenshots — anything that could contain real printer or account data."
applyTo: "tests/fixtures/**, tools/capture_*.py, docs/images/**"
---
# Recorded data and screenshots

- Raw captures from a real printer or Connect account go to `tests/fixtures/raw/` only. That folder is gitignored and must stay out of git.
- A committed fixture is an anonymised copy:
  - all-zero UUIDs;
  - `10000-0000000000000000` as the serial;
  - `192.168.1.x` addresses;
  - no names, locations, e-mail, tokens, API keys or Wi-Fi details.
  
  Keep only the fields the test reads.
- README screenshots come from `tools/readme_shots.py`. It masks addresses, IDs and file names and blurs the camera. Check every new image for personal data before committing it.

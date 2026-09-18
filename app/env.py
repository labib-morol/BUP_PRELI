"""Minimal .env loader.

Real environment variables always win, so a platform dashboard (Render, Docker -e,
Hugging Face secrets) overrides the file and nothing here can shadow a deployment
setting. Values are never logged.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path | None = None) -> bool:
    candidate = path or ROOT / ".env"
    if not candidate.is_file():
        return False
    loaded = False
    for raw in candidate.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded = True
    return loaded

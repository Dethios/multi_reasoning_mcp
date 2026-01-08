from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*\S+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)AIza[0-9A-Za-z\-_]{35}"),
]


def redact_secrets(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pat in _SECRET_PATTERNS:
        redacted = pat.sub("[REDACTED]", redacted)
    return redacted


def now_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def safe_slug(text: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-")
    if not cleaned:
        return "run"
    return cleaned[:max_len]


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def render_template(template: str, mapping: dict[str, str]) -> str:
    rendered = template
    for key, value in mapping.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


def compute_confirm_token(patch_text: str) -> str:
    digest = hashlib.sha256(patch_text.encode("utf-8", errors="ignore")).hexdigest()
    return "CONFIRM_" + digest[:8]


def json_response(summary: str, **fields: Any) -> dict[str, Any]:
    payload = {"summary": summary}
    payload.update(fields)
    return payload

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .utils import compute_confirm_token, redact_secrets


def summarize_patch(patch_text: str) -> dict[str, Any]:
    files = []
    deleted = []
    new_files = []
    renamed = []
    current = None
    for raw_line in patch_text.splitlines():
        line = raw_line.lstrip()
        if line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                a_path = parts[2].replace("a/", "", 1)
                b_path = parts[3].replace("b/", "", 1)
                current = b_path
                files.append(b_path)
        elif line.startswith("deleted file mode") and current:
            deleted.append(current)
        elif line.startswith("new file mode") and current:
            new_files.append(current)
        elif line.startswith("rename from "):
            renamed.append(line.replace("rename from ", "", 1).strip())
    total_lines = len(patch_text.splitlines())
    return {
        "files": sorted(set(files)),
        "deleted_files": sorted(set(deleted)),
        "new_files": sorted(set(new_files)),
        "renamed_files": sorted(set(renamed)),
        "total_lines": total_lines,
        "file_count": len(set(files)),
    }


def _risk_reasons(summary: dict[str, Any], safety_level: str) -> list[str]:
    reasons = []
    if summary.get("deleted_files"):
        reasons.append("deletes files")
    if summary.get("renamed_files"):
        reasons.append("renames files")
    if summary.get("file_count", 0) >= 10:
        reasons.append("bulk change (>=10 files)")
    if summary.get("total_lines", 0) >= 2000:
        reasons.append("large patch (>=2000 lines)")
    if safety_level in ("high", "strict"):
        reasons.append("high safety level")
    return reasons


def apply_patch_text(
    patch_text: str,
    root: str = ".",
    safety_level: str = "low",
    confirm_token: str | None = None,
) -> dict[str, Any]:
    if not patch_text.strip():
        return {
            "ok": False,
            "summary": "No patch provided.",
            "details": {},
        }

    summary = summarize_patch(patch_text)
    reasons = _risk_reasons(summary, safety_level)
    if reasons:
        required_token = compute_confirm_token(patch_text)
        if confirm_token != required_token:
            return {
                "ok": False,
                "summary": "Confirmation required before applying patch.",
                "needs_confirmation": True,
                "confirm_token": required_token,
                "reasons": reasons,
                "details": summary,
            }

    root_path = Path(root).resolve()
    patch_path = None
    try:
        fd, path = tempfile.mkstemp(prefix="patch_", suffix=".diff")
        patch_path = path
        Path(path).write_text(patch_text, encoding="utf-8")

        git = shutil.which("git")
        if git:
            proc = subprocess.run(
                [git, "apply", "--whitespace=nowarn", "--unsafe-paths", path],
                cwd=root_path,
                capture_output=True,
                text=True,
            )
        else:
            patch = shutil.which("patch")
            if not patch:
                return {
                    "ok": False,
                    "summary": "Neither git nor patch tool is available.",
                    "details": summary,
                }
            proc = subprocess.run(
                [patch, "-p1", "-i", path],
                cwd=root_path,
                capture_output=True,
                text=True,
            )

        return {
            "ok": proc.returncode == 0,
            "summary": "Patch applied." if proc.returncode == 0 else "Patch failed.",
            "details": summary,
            "stdout": redact_secrets(proc.stdout or ""),
            "stderr": redact_secrets(proc.stderr or ""),
            "returncode": proc.returncode,
        }
    finally:
        if patch_path:
            pass

from __future__ import annotations

from pathlib import Path
from typing import Any

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".orchestrator",
}

EXCLUDE_FILES = {".mcp_index.sqlite3"}
EXCLUDE_SUFFIXES = {".sqlite3"}


def _is_excluded(path: Path) -> bool:
    if path.name in EXCLUDE_FILES:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def detect_stack(root: Path) -> list[str]:
    stack = set()
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        stack.add("python")
    if (root / "package.json").exists():
        stack.add("node")
    if (root / "go.mod").exists():
        stack.add("go")
    if any(root.rglob("*.tex")):
        stack.add("latex")
    if (root / "Cargo.toml").exists():
        stack.add("rust")
    return sorted(stack)


def repo_scan(root: str = ".", max_depth: int = 3, max_files: int = 2000) -> dict[str, Any]:
    root_path = Path(root).resolve()
    files = []
    dirs = []

    for p in root_path.rglob("*"):
        if _is_excluded(p):
            continue
        rel = p.relative_to(root_path)
        depth = len(rel.parts)
        if depth > max_depth:
            continue
        if p.is_dir():
            dirs.append(str(rel))
        elif p.is_file():
            files.append(str(rel))
        if len(files) >= max_files:
            break

    key_files = [
        f for f in files
        if any(f.endswith(s) for s in ["README.md", "pyproject.toml", "requirements.txt", "package.json", "go.mod"]) or "/.vscode/" in f
    ]

    return {
        "root": str(root_path),
        "dirs": sorted(dirs)[:200],
        "files": sorted(files)[:200],
        "key_files": sorted(set(key_files))[:200],
        "stack": detect_stack(root_path),
        "excluded": {
            "dirs": sorted(EXCLUDE_DIRS),
            "files": sorted(EXCLUDE_FILES),
            "suffixes": sorted(EXCLUDE_SUFFIXES),
        },
    }

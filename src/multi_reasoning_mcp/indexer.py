from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .types import IndexBuildResult, SearchHit, SearchResults


DEFAULT_INCLUDE_GLOBS = [
    "**/*.md",
    "**/*.txt",
    "**/*.rst",
    "**/*.py",
    "**/*.js",
    "**/*.ts",
    "**/*.tsx",
    "**/*.json",
    "**/*.yaml",
    "**/*.yml",
    "**/*.toml",
]

DEFAULT_EXCLUDE_DIRS = [
    ".git", ".venv", "venv", "node_modules", "dist", "build", ".mypy_cache", ".pytest_cache", "__pycache__",
]


class RepoIndex:
    """
    Simple local index using SQLite FTS5.
    - Great for repo-wide search without needing an LLM to "remember everything".
    - Fast enough for most repos.
    """

    def __init__(self, db_path: str = ".mcp_index.sqlite3") -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _ensure_schema(self) -> None:
        con = self._connect()
        try:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    mtime REAL NOT NULL,
                    bytes INTEGER NOT NULL
                );
            """)
            # FTS5 content table
            con.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
                    path UNINDEXED,
                    content,
                    tokenize = 'porter'
                );
            """)
            con.commit()
        finally:
            con.close()

    def build(
        self,
        root: str = ".",
        include_globs: list[str] | None = None,
        exclude_dirs: list[str] | None = None,
        max_file_bytes: int = 2_000_000,
        rebuild: bool = False,
    ) -> IndexBuildResult:
        root_path = Path(root).resolve()
        include_globs = include_globs or DEFAULT_INCLUDE_GLOBS
        exclude_dirs = exclude_dirs or DEFAULT_EXCLUDE_DIRS

        con = self._connect()
        indexed, skipped, bytes_indexed = 0, 0, 0

        try:
            if rebuild:
                con.execute("DELETE FROM fts;")
                con.execute("DELETE FROM files;")
                con.commit()

            exclude_set = set(exclude_dirs)

            def is_excluded(p: Path) -> bool:
                return any(part in exclude_set for part in p.parts)

            # Collect candidate files
            candidates: set[Path] = set()
            for g in include_globs:
                for p in root_path.glob(g):
                    if p.is_file() and not is_excluded(p):
                        candidates.add(p)

            for p in sorted(candidates):
                try:
                    stat = p.stat()
                except OSError:
                    skipped += 1
                    continue
                if stat.st_size > max_file_bytes:
                    skipped += 1
                    continue

                rel = str(p.relative_to(root_path))
                mtime = stat.st_mtime
                size = stat.st_size

                row = con.execute("SELECT mtime FROM files WHERE path = ?", (rel,)).fetchone()
                if row is not None and float(row["mtime"]) >= mtime:
                    # up-to-date
                    continue

                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    skipped += 1
                    continue

                # Upsert
                con.execute("INSERT OR REPLACE INTO files(path, mtime, bytes) VALUES(?,?,?)", (rel, mtime, size))
                con.execute("DELETE FROM fts WHERE path = ?", (rel,))
                con.execute("INSERT INTO fts(path, content) VALUES(?,?)", (rel, content))
                indexed += 1
                bytes_indexed += size

            con.commit()
        finally:
            con.close()

        return IndexBuildResult(
            root=str(root_path),
            indexed_files=indexed,
            skipped_files=skipped,
            bytes_indexed=bytes_indexed,
            db_path=self.db_path,
        )

    def search(self, query: str, top_k: int = 10) -> SearchResults:
        con = self._connect()
        try:
            rows = con.execute(
                """
                SELECT path, bm25(fts) AS score,
                       snippet(fts, 1, '[', ']', '…', 12) AS snippet
                FROM fts
                WHERE fts MATCH ?
                ORDER BY score
                LIMIT ?;
                """,
                (query, top_k),
            ).fetchall()

            hits = [
                SearchHit(
                    path=r["path"],
                    score=float(r["score"]),
                    snippet=str(r["snippet"]),
                )
                for r in rows
            ]
            return SearchResults(query=query, hits=hits)
        finally:
            con.close()

"""Durable local ledger. Resource locks span processes; SQLite transactions persist intent."""

from __future__ import annotations

import fcntl
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from .domain import (
    Approval,
    DeskError,
    EvidenceEvent,
    OperationAttempt,
    RecoveryCase,
    WarehouseHoldAttempt,
    now,
)


class Storage:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "ledger.sqlite"
        self.locks = self.directory / "locks"
        self.locks.mkdir(exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                INSERT OR IGNORE INTO schema_migrations VALUES (1, CURRENT_TIMESTAMP);
                CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, order_id TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS cases_order ON cases(order_id);
                CREATE TABLE IF NOT EXISTS evidence (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, case_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, action_id TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(case_id, action_id));
                CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries (event_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, accepted INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS projections (order_id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS warehouse_attempts (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, data TEXT NOT NULL);
                INSERT OR IGNORE INTO schema_migrations VALUES (2, CURRENT_TIMESTAMP);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def order_lock(self, order_id: str) -> Iterator[None]:
        path = self.locks / (hashlib.sha256(order_id.encode()).hexdigest() + ".lock")
        with path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DeskError(
                    "Another operator is working on this order. Refresh to see their result."
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def get_case(self, case_id: str) -> RecoveryCase:
        with self.connect() as conn:
            row = conn.execute("SELECT data FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            raise DeskError("Case not found", 404)
        return RecoveryCase.model_validate_json(row["data"])

    def list_cases(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM cases ORDER BY rowid DESC")]

    def save_case(
        self,
        case: RecoveryCase,
        *,
        message: str | None = None,
        kind: str = "state",
        data: dict[str, Any] | None = None,
    ) -> None:
        case.updated_at = now()
        case.revision += 1
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO cases VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, data=excluded.data",
                (case.id, case.order_id, case.status, case.model_dump_json()),
            )
            if message:
                event = EvidenceEvent(
                    id=str(uuid4()), source="recovery desk", kind=kind, message=message, data=data or {}
                )
                conn.execute(
                    "INSERT INTO evidence(id,case_id,data) VALUES (?,?,?)",
                    (event.id, case.id, event.model_dump_json()),
                )

    def event(
        self, case_id: str, source: str, kind: str, message: str, data: dict[str, Any] | None = None
    ) -> None:
        event = EvidenceEvent(id=str(uuid4()), source=source, kind=kind, message=message, data=data or {})
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO evidence(id,case_id,data) VALUES (?,?,?)",
                (event.id, case_id, event.model_dump_json()),
            )

    def events(self, case_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute("SELECT data FROM evidence WHERE case_id=? ORDER BY seq", (case_id,))
            ]

    def save_attempt(self, attempt: OperationAttempt) -> None:
        attempt.updated_at = now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO attempts VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (attempt.id, attempt.case_id, attempt.action_id, attempt.model_dump_json()),
            )

    def attempts(self, case_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute("SELECT data FROM attempts WHERE case_id=? ORDER BY rowid", (case_id,))
            ]

    def save_hold_attempt(self, attempt: WarehouseHoldAttempt) -> None:
        attempt.updated_at = now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO warehouse_attempts VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (attempt.id, attempt.case_id, attempt.model_dump_json()),
            )

    def hold_attempts(self, case_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                json.loads(row[0])
                for row in conn.execute(
                    "SELECT data FROM warehouse_attempts WHERE case_id=? ORDER BY rowid", (case_id,)
                )
            ]

    def save_approvals(self, approvals: list[Approval]) -> None:
        with self.connect() as conn:
            for approval in approvals:
                conn.execute(
                    "INSERT INTO approvals VALUES (?,?,?)",
                    (approval.id, approval.case_id, approval.model_dump_json()),
                )

    def approvals(self, case_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                json.loads(r[0])
                for r in conn.execute("SELECT data FROM approvals WHERE case_id=? ORDER BY rowid", (case_id,))
            ]

    def ingest(self, event_id: str, order_id: str, version: int, payload: dict[str, Any]) -> str:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM deliveries WHERE event_id=?", (event_id,)).fetchone():
                return "duplicate"
            row = conn.execute("SELECT version FROM projections WHERE order_id=?", (order_id,)).fetchone()
            accepted = row is None or version > row[0]
            conn.execute(
                "INSERT INTO deliveries VALUES (?,?,?,?,?)",
                (event_id, order_id, version, json.dumps(payload), int(accepted)),
            )
            if accepted:
                conn.execute(
                    "INSERT INTO projections VALUES (?,?,?) ON CONFLICT(order_id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
                    (order_id, version, json.dumps(payload)),
                )
        return "accepted" if accepted else "stale"

    def projection(self, order_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT version,payload FROM projections WHERE order_id=?", (order_id,)
            ).fetchone()
        return {"version": row[0], "payload": json.loads(row[1])} if row else None

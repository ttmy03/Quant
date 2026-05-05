from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trading_app.schemas import OrderIntent


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    alpaca_order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    order_type TEXT NOT NULL,
    limit_price REAL,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    raw_response TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    seed INTEGER NOT NULL,
    inputs TEXT NOT NULL,
    metrics TEXT NOT NULL
);
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Storage:
    """Small SQLite gateway for audit, order, and simulation records."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def record_audit(
        self,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        payload_json = json.dumps(payload or {}, sort_keys=True)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_events (created_at, actor, event_type, message, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (created_at, actor, event_type, message, payload_json),
            )
            event_id = cursor.lastrowid
        return {
            "id": event_id,
            "created_at": created_at,
            "actor": actor,
            "event_type": event_type,
            "message": message,
            "payload": payload or {},
        }

    def list_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, actor, event_type, message, payload
                FROM audit_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_row(row, json_fields=("payload",)) for row in rows]

    def record_order(
        self,
        intent: OrderIntent,
        status: str,
        dry_run: bool,
        alpaca_order_id: str | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        raw_json = json.dumps(raw_response or {}, sort_keys=True)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    created_at, alpaca_order_id, symbol, side, qty, order_type,
                    limit_price, status, dry_run, raw_response
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    alpaca_order_id,
                    intent.symbol,
                    intent.side,
                    intent.qty,
                    intent.order_type,
                    intent.limit_price,
                    status,
                    int(dry_run),
                    raw_json,
                ),
            )
            order_id = cursor.lastrowid
        return {
            "id": order_id,
            "created_at": created_at,
            "alpaca_order_id": alpaca_order_id,
            "symbol": intent.symbol,
            "side": intent.side,
            "qty": intent.qty,
            "order_type": intent.order_type,
            "limit_price": intent.limit_price,
            "status": status,
            "dry_run": dry_run,
            "raw_response": raw_response or {},
        }

    def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, alpaca_order_id, symbol, side, qty, order_type,
                       limit_price, status, dry_run, raw_response
                FROM orders
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        decoded = [self._decode_row(row, json_fields=("raw_response",)) for row in rows]
        for row in decoded:
            row["dry_run"] = bool(row["dry_run"])
        return decoded

    def record_simulation(
        self,
        name: str,
        seed: int,
        inputs: dict[str, Any],
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO simulation_results (created_at, name, seed, inputs, metrics)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    name,
                    seed,
                    json.dumps(inputs, sort_keys=True),
                    json.dumps(metrics, sort_keys=True),
                ),
            )
            simulation_id = cursor.lastrowid
        return {
            "id": simulation_id,
            "created_at": created_at,
            "name": name,
            "seed": seed,
            "inputs": inputs,
            "metrics": metrics,
        }

    def list_simulations(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, name, seed, inputs, metrics
                FROM simulation_results
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_row(row, json_fields=("inputs", "metrics")) for row in rows]

    @staticmethod
    def _decode_row(row: sqlite3.Row, json_fields: tuple[str, ...]) -> dict[str, Any]:
        result = dict(row)
        for field in json_fields:
            result[field] = json.loads(result[field])
        return result

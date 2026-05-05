from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trading_app.schemas import OrderIntent, Signal


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
    source TEXT NOT NULL DEFAULT 'manual',
    scheduler_run_id INTEGER,
    raw_response TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trading_control_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    kill_switch_active INTEGER NOT NULL DEFAULT 0,
    paused INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduler_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    paper_trading_only INTEGER NOT NULL,
    symbols TEXT NOT NULL,
    signals_count INTEGER NOT NULL DEFAULT 0,
    orders_count INTEGER NOT NULL DEFAULT 0,
    blocked_reason TEXT,
    no_live_orders_sent INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS scheduler_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    scheduler_run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    order_id INTEGER,
    raw_signal TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    seed INTEGER NOT NULL,
    inputs TEXT NOT NULL,
    metrics TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    inputs TEXT NOT NULL,
    metrics TEXT NOT NULL,
    trades TEXT NOT NULL,
    equity_curve TEXT NOT NULL
);
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Storage:
    """Small SQLite gateway for audit, order, simulation, and backtest records."""

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
            self._ensure_column(connection, "orders", "source", "TEXT NOT NULL DEFAULT 'manual'")
            self._ensure_column(connection, "orders", "scheduler_run_id", "INTEGER")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608 - table names are internal constants
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")  # noqa: S608

    @staticmethod
    def _with_control_flags(state: dict[str, Any]) -> dict[str, Any]:
        state["kill_switch_active"] = bool(state["kill_switch_active"])
        state["paused"] = bool(state["paused"])
        state["can_trade"] = not state["kill_switch_active"] and not state["paused"]
        return state

    def get_trading_control_state(self) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, kill_switch_active, paused, reason, updated_at, updated_by
                FROM trading_control_state
                WHERE id = 1
                """
            ).fetchone()
            if row is None:
                updated_at = utc_now_iso()
                connection.execute(
                    """
                    INSERT INTO trading_control_state (
                        id, kill_switch_active, paused, reason, updated_at, updated_by
                    )
                    VALUES (1, 0, 0, '', ?, 'system')
                    """,
                    (updated_at,),
                )
                row = connection.execute(
                    """
                    SELECT id, kill_switch_active, paused, reason, updated_at, updated_by
                    FROM trading_control_state
                    WHERE id = 1
                    """
                ).fetchone()
        return self._with_control_flags(dict(row))

    def update_trading_control_state(
        self,
        *,
        kill_switch_active: bool | None = None,
        paused: bool | None = None,
        reason: str = "",
        actor: str = "operator",
    ) -> dict[str, Any]:
        current = self.get_trading_control_state()
        next_kill_switch = current["kill_switch_active"] if kill_switch_active is None else kill_switch_active
        next_paused = current["paused"] if paused is None else paused
        updated_at = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE trading_control_state
                SET kill_switch_active = ?, paused = ?, reason = ?, updated_at = ?, updated_by = ?
                WHERE id = 1
                """,
                (int(next_kill_switch), int(next_paused), reason, updated_at, actor),
            )
            row = connection.execute(
                """
                SELECT id, kill_switch_active, paused, reason, updated_at, updated_by
                FROM trading_control_state
                WHERE id = 1
                """
            ).fetchone()
        return self._with_control_flags(dict(row))

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
        source: str = "manual",
        scheduler_run_id: int | None = None,
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        raw_json = json.dumps(raw_response or {}, sort_keys=True)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO orders (
                    created_at, alpaca_order_id, symbol, side, qty, order_type,
                    limit_price, status, dry_run, source, scheduler_run_id, raw_response
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    source,
                    scheduler_run_id,
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
            "source": source,
            "scheduler_run_id": scheduler_run_id,
            "raw_response": raw_response or {},
        }

    def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, alpaca_order_id, symbol, side, qty, order_type,
                       limit_price, status, dry_run, source, scheduler_run_id, raw_response
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

    def start_scheduler_run(
        self,
        *,
        dry_run: bool,
        paper_trading_only: bool,
        symbols: list[str],
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scheduler_runs (
                    created_at, status, dry_run, paper_trading_only, symbols, no_live_orders_sent
                )
                VALUES (?, 'running', ?, ?, ?, 1)
                """,
                (created_at, int(dry_run), int(paper_trading_only), json.dumps(symbols, sort_keys=True)),
            )
            run_id = cursor.lastrowid
        return {
            "id": run_id,
            "created_at": created_at,
            "completed_at": None,
            "status": "running",
            "dry_run": dry_run,
            "paper_trading_only": paper_trading_only,
            "symbols": symbols,
            "signals_count": 0,
            "orders_count": 0,
            "blocked_reason": None,
            "no_live_orders_sent": True,
        }

    def complete_scheduler_run(
        self,
        run_id: int,
        *,
        status: str,
        signals_count: int,
        orders_count: int,
        blocked_reason: str | None = None,
    ) -> dict[str, Any]:
        completed_at = utc_now_iso()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE scheduler_runs
                SET completed_at = ?, status = ?, signals_count = ?, orders_count = ?, blocked_reason = ?,
                    no_live_orders_sent = 1
                WHERE id = ?
                """,
                (completed_at, status, signals_count, orders_count, blocked_reason, run_id),
            )
            row = connection.execute(
                """
                SELECT id, created_at, completed_at, status, dry_run, paper_trading_only, symbols,
                       signals_count, orders_count, blocked_reason, no_live_orders_sent
                FROM scheduler_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        return self._decode_scheduler_run(row)

    def record_scheduler_signal(
        self,
        scheduler_run_id: int,
        signal: Signal,
        *,
        source: str,
        order_id: int | None = None,
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        signal_payload = signal.model_dump()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scheduler_signals (
                    created_at, scheduler_run_id, symbol, action, confidence, reason, source, order_id, raw_signal
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    scheduler_run_id,
                    signal.symbol,
                    signal.action,
                    signal.confidence,
                    signal.reason,
                    source,
                    order_id,
                    json.dumps(signal_payload, sort_keys=True),
                ),
            )
            signal_id = cursor.lastrowid
        return {
            "id": signal_id,
            "created_at": created_at,
            "scheduler_run_id": scheduler_run_id,
            "symbol": signal.symbol,
            "action": signal.action,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "source": source,
            "order_id": order_id,
            "raw_signal": signal_payload,
        }

    def list_scheduler_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, completed_at, status, dry_run, paper_trading_only, symbols,
                       signals_count, orders_count, blocked_reason, no_live_orders_sent
                FROM scheduler_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_scheduler_run(row) for row in rows]

    def list_scheduler_signals(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, scheduler_run_id, symbol, action, confidence, reason, source, order_id, raw_signal
                FROM scheduler_signals
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_row(row, json_fields=("raw_signal",)) for row in rows]

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

    def record_backtest(
        self,
        name: str,
        symbol: str,
        inputs: dict[str, Any],
        metrics: dict[str, Any],
        trades: list[dict[str, Any]],
        equity_curve: list[dict[str, Any]],
    ) -> dict[str, Any]:
        created_at = utc_now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO backtest_results (created_at, name, symbol, inputs, metrics, trades, equity_curve)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    name,
                    symbol,
                    json.dumps(inputs, sort_keys=True),
                    json.dumps(metrics, sort_keys=True),
                    json.dumps(trades, sort_keys=True),
                    json.dumps(equity_curve, sort_keys=True),
                ),
            )
            backtest_id = cursor.lastrowid
        return {
            "id": backtest_id,
            "created_at": created_at,
            "name": name,
            "symbol": symbol,
            "inputs": inputs,
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_curve,
        }

    def list_backtests(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, name, symbol, inputs, metrics, trades, equity_curve
                FROM backtest_results
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            self._decode_row(row, json_fields=("inputs", "metrics", "trades", "equity_curve"))
            for row in rows
        ]

    @staticmethod
    def _decode_row(row: sqlite3.Row, json_fields: tuple[str, ...]) -> dict[str, Any]:
        result = dict(row)
        for field in json_fields:
            result[field] = json.loads(result[field])
        return result

    @staticmethod
    def _decode_scheduler_run(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["dry_run"] = bool(result["dry_run"])
        result["paper_trading_only"] = bool(result["paper_trading_only"])
        result["symbols"] = json.loads(result["symbols"])
        result["no_live_orders_sent"] = bool(result["no_live_orders_sent"])
        return result

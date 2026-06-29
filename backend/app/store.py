from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


DATA_DIR = Path(os.getenv("INDEX_AGENT_DATA_DIR") or os.getenv("OPENUNI_RUNTIME_DIR") or Path(__file__).resolve().parent.parent / "data")
DB_PATH = DATA_DIR / "agent.sqlite"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            value TEXT NOT NULL,
            executed INTEGER NOT NULL DEFAULT 0,
            execution_note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()
    return conn


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value


def _record_fingerprint(payload: Dict[str, Any]) -> str:
    plan = payload.get("plan") or {}
    allocations = plan.get("allocations") or []
    compact_allocations = [
        {
            "asset_key": item.get("asset_key"),
            "target_weight": round(float(item.get("target_weight") or 0), 6),
            "amount": round(float(item.get("amount") or 0), 2),
            "multiplier": round(float(item.get("multiplier") or 0), 4),
        }
        for item in allocations
    ]
    value = {
        "strategy_id": payload.get("strategy_id") or plan.get("strategy_id"),
        "suggested_total_buy": round(float(plan.get("suggested_total_buy") or 0), 2),
        "base_amount": round(float(plan.get("base_amount") or 0), 2),
        "multiplier": round(float(plan.get("multiplier") or 0), 4),
        "average_temperature": round(float(plan.get("average_temperature") or 0), 2),
        "temperature_band": plan.get("temperature_band"),
        "allocations": compact_allocations,
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def get_value(key: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["value"])


def set_value(key: str, value: Any) -> None:
    conn = _connect()
    payload = json.dumps(_to_jsonable(value), ensure_ascii=False)
    conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, payload),
    )
    conn.commit()
    conn.close()


def add_record(record: Any) -> tuple[int, bool]:
    payload = _to_jsonable(record)
    fingerprint = _record_fingerprint(payload)
    conn = _connect()
    rows = conn.execute("SELECT id, value FROM records ORDER BY id DESC").fetchall()
    for row in rows:
        existing = json.loads(row["value"])
        if _record_fingerprint(existing) == fingerprint:
            conn.close()
            return int(row["id"]), True
    cursor = conn.execute(
        "INSERT INTO records (created_at, value, executed, execution_note) VALUES (?, ?, ?, ?)",
        (
            payload["created_at"],
            json.dumps(payload, ensure_ascii=False),
            1 if payload.get("executed") else 0,
            payload.get("execution_note", ""),
        ),
    )
    conn.commit()
    record_id = int(cursor.lastrowid)
    conn.close()
    return record_id, False


def _dedupe_records(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id, value, executed, execution_note FROM records ORDER BY id DESC").fetchall()
    grouped: Dict[str, List[sqlite3.Row]] = {}
    for row in rows:
        value = json.loads(row["value"])
        grouped.setdefault(_record_fingerprint(value), []).append(row)

    changed = False
    for duplicates in grouped.values():
        if len(duplicates) <= 1:
            continue
        keep = duplicates[0]
        keep_id = int(keep["id"])
        executed = any(bool(row["executed"]) for row in duplicates)
        note = next((row["execution_note"] for row in duplicates if row["execution_note"]), "")
        delete_ids = [int(row["id"]) for row in duplicates[1:]]
        conn.execute(
            "UPDATE records SET executed = ?, execution_note = ? WHERE id = ?",
            (1 if executed else 0, note, keep_id),
        )
        conn.executemany("DELETE FROM records WHERE id = ?", [(record_id,) for record_id in delete_ids])
        changed = True
    if changed:
        conn.commit()


def list_records() -> List[Dict[str, Any]]:
    conn = _connect()
    _dedupe_records(conn)
    rows = conn.execute("SELECT id, value, executed, execution_note FROM records ORDER BY id DESC").fetchall()
    conn.close()
    records: List[Dict[str, Any]] = []
    for row in rows:
        value = json.loads(row["value"])
        value["id"] = row["id"]
        value["executed"] = bool(row["executed"])
        value["execution_note"] = row["execution_note"]
        records.append(value)
    return records


def update_record_execution(record_id: int, executed: bool, note: str) -> bool:
    conn = _connect()
    cursor = conn.execute(
        "UPDATE records SET executed = ?, execution_note = ? WHERE id = ?",
        (1 if executed else 0, note, record_id),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed

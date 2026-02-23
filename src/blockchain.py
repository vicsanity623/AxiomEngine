# Axiom - blockchain.py
# Copyright (C) 2026 The Axiom Contributors
#
# Minimal blockchain layer: ordered chain of blocks, each committing a set of fact_ids.
# Chain integrity via previous_block_id; longest chain wins on sync.

import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Any


logger = logging.getLogger(__name__)

GENESIS_BLOCK_ID = "axiom_genesis_v1"
GENESIS_PREVIOUS = ""


def _block_payload(previous_block_id: str, height: int, created_at_utc: str, fact_ids: list[str]) -> bytes:
    """Canonical payload for block hash (deterministic)."""
    return json.dumps(
        {
            "previous": previous_block_id,
            "height": height,
            "created_at_utc": created_at_utc,
            "fact_ids": sorted(fact_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _block_id(previous_block_id: str, height: int, created_at_utc: str, fact_ids: list[str]) -> str:
    return hashlib.sha256(
        _block_payload(previous_block_id, height, created_at_utc, fact_ids)
    ).hexdigest()


def ensure_genesis(conn: sqlite3.Connection) -> None:
    """Insert genesis block if blocks table is empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM blocks LIMIT 1")
    if cursor.fetchone() is not None:
        return
    created = datetime.now(UTC).isoformat()
    cursor.execute(
        """
        INSERT INTO blocks (block_id, previous_block_id, height, created_at_utc, fact_ids)
        VALUES (?, ?, 0, ?, ?)
        """,
        (GENESIS_BLOCK_ID, GENESIS_PREVIOUS, created, json.dumps([])),
    )
    conn.commit()
    logger.debug("[Chain] Genesis block created.")


def get_chain_head(db_path: str | None = None, conn: sqlite3.Connection | None = None) -> tuple[str, int] | None:
    """Returns (block_id, height) of the current chain tip, or None if no chain."""
    own_conn = conn is None
    if db_path is None and conn is None:
        # Fallback if called without context, should be avoided by node.py
        db_path = "axiom_ledger.db" 
        
    conn = conn if conn else sqlite3.connect(db_path)
    try:
        ensure_genesis(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT block_id, height FROM blocks ORDER BY height DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return (row[0], row[1])
    finally:
        if own_conn:
            conn.close()


def create_block(fact_ids: list[str], db_path: str | None = None, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """
    Create a new block extending the current head. fact_ids should be a list of fact_ids
    to commit in this block. Returns the new block dict or None if creation failed.
    """
    own_conn = conn is None
    if db_path is None and conn is None:
        db_path = "axiom_ledger.db"
        
    conn = conn if conn else sqlite3.connect(db_path)
    try:
        ensure_genesis(conn)
        head = get_chain_head(db_path=db_path, conn=conn) # Pass connection context
        if head is None:
            return None
        previous_block_id, height = head
        new_height = height + 1
        created_at_utc = datetime.now(UTC).isoformat()
        fact_ids = list(fact_ids)  # copy
        block_id = _block_id(previous_block_id, new_height, created_at_utc, fact_ids)

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO blocks (block_id, previous_block_id, height, created_at_utc, fact_ids)
            VALUES (?, ?, ?, ?, ?)
            """,
            (block_id, previous_block_id, new_height, created_at_utc, json.dumps(fact_ids)),
        )
        conn.commit()
        return {
            "block_id": block_id,
            "previous_block_id": previous_block_id,
            "height": new_height,
            "created_at_utc": created_at_utc,
            "fact_ids": fact_ids,
        }
    except sqlite3.IntegrityError as e:
        logger.warning(f"[Chain] Block creation failed (race?): {e}")
        return None
    finally:
        if own_conn:
            conn.close()


def validate_block(
    block_id: str,
    previous_block_id: str,
    height: int,
    created_at_utc: str,
    fact_ids: list[str],
    expected_previous: str,
    expected_height: int,
) -> bool:
    """Verify block hash and chain link."""
    computed_id = _block_id(previous_block_id, height, created_at_utc, fact_ids)
    if computed_id != block_id:
        return False
    if previous_block_id != expected_previous or height != expected_height:
        return False
    return True


def append_block(block: dict[str, Any], db_path: str | None = None, conn: sqlite3.Connection | None = None) -> bool:
    """
    Append a validated block to the chain. Caller must ensure it extends current head.
    Returns True if appended, False if invalid or duplicate.
    """
    own_conn = conn is None
    if db_path is None and conn is None:
        db_path = "axiom_ledger.db"
        
    conn = conn if conn else sqlite3.connect(db_path)
    try:
        ensure_genesis(conn)
        head = get_chain_head(db_path=db_path, conn=conn) # Pass connection context
        if head is None:
            return False
        prev_id, prev_height = head
        if block["previous_block_id"] != prev_id or block["height"] != prev_height + 1:
            return False
        if not validate_block(
            block["block_id"],
            block["previous_block_id"],
            block["height"],
            block["created_at_utc"],
            block["fact_ids"],
            prev_id,
            prev_height,
        ):
            return False
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO blocks (block_id, previous_block_id, height, created_at_utc, fact_ids)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                block["block_id"],
                block["previous_block_id"],
                block["height"],
                block["created_at_utc"],
                json.dumps(block["fact_ids"]),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate block_id
    finally:
        if own_conn:
            conn.close()


def get_blocks_after(height: int, db_path: str | None = None, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """Return blocks with height > height, ordered by height ascending."""
    own_conn = conn is None
    if db_path is None and conn is None:
        db_path = "axiom_ledger.db"
        
    conn = conn if conn else sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT block_id, previous_block_id, height, created_at_utc, fact_ids FROM blocks WHERE height > ? ORDER BY height ASC",
            (height,),
        )
        rows = cursor.fetchall()
        return [
            {
                "block_id": r[0],
                "previous_block_id": r[1],
                "height": r[2],
                "created_at_utc": r[3],
                "fact_ids": json.loads(r[4]) if isinstance(r[4], str) else r[4],
            }
            for r in rows
        ]
    finally:
        if own_conn:
            conn.close()


def get_block_by_id(block_id: str, db_path: str | None = None, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Fetch a single block by id."""
    own_conn = conn is None
    if db_path is None and conn is None:
        db_path = "axiom_ledger.db"
        
    conn = conn if conn else sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT block_id, previous_block_id, height, created_at_utc, fact_ids FROM blocks WHERE block_id = ?",
            (block_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "block_id": row[0],
            "previous_block_id": row[1],
            "height": row[2],
            "created_at_utc": row[3],
            "fact_ids": json.loads(row[4]) if isinstance(row[4], str) else row[4],
        }
    finally:
        if own_conn:
            conn.close()
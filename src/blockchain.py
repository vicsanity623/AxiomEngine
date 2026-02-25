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
from typing import Any, Tuple


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


def _normalize_block_from_wire(block: dict[str, Any]) -> dict[str, Any]:
    """Normalize a block received over JSON so hash validation is deterministic."""
    height = block.get("height", 0)
    try:
        height = int(height)
    except (TypeError, ValueError):
        height = 0
    fact_ids = block.get("fact_ids") or []
    if not isinstance(fact_ids, list):
        fact_ids = [str(fact_ids)]
    fact_ids = [str(fid).strip() for fid in fact_ids if fid is not None]
    created = block.get("created_at_utc") or ""
    if created is not None and not isinstance(created, str):
        created = str(created)
    return {
        "block_id": str(block.get("block_id") or ""),
        "previous_block_id": str(block.get("previous_block_id") or ""),
        "height": height,
        "created_at_utc": created,
        "fact_ids": fact_ids,
    }


def ensure_genesis(conn: sqlite3.Connection) -> None:
    """Insert genesis block if blocks table is empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM blocks LIMIT 1")
    if cursor.fetchone() is not None:
        return
    
    # FIX: Use a fixed, known timestamp for the Genesis block so all nodes generate the identical hash.
    CREATED_GENESIS_TIME = "2024-01-01T00:00:00.000000+00:00"
    
    cursor.execute(
        """
        INSERT INTO blocks (block_id, previous_block_id, height, created_at_utc, fact_ids)
        VALUES (?, ?, 0, ?, ?)
        """,
        (GENESIS_BLOCK_ID, GENESIS_PREVIOUS, CREATED_GENESIS_TIME, json.dumps([])),
    )
    conn.commit()
    logger.debug("[Chain] Genesis block created.")


def get_chain_head(db_path: str | None = None, conn: sqlite3.Connection | None = None) -> tuple[str, int] | None:
    """Returns (block_id, height) of the current chain tip, or None if no chain."""
    own_conn = conn is None
    if db_path is None and conn is None:
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
) -> Tuple[bool, str]:
    """Verify block hash and chain link. Returns (ok, reason)."""
    computed_id = _block_id(previous_block_id, height, created_at_utc, fact_ids)
    if computed_id != block_id:
        return False, f"hash mismatch (computed {computed_id[:16]}..., received {block_id[:16]}...)"
    # NOTE: expected_height represents the *expected* height of this block.
    # Callers must pass the height the block SHOULD have (typically previous_height + 1).
    if previous_block_id != expected_previous or height != expected_height:
        return False, "link mismatch (previous or height)"
    return True, ""


def append_block(block: dict[str, Any], db_path: str | None = None, conn: sqlite3.Connection | None = None) -> bool:
    """
    Append a validated block to the chain. Caller must ensure it extends current head.
    Normalizes block from wire (height as int, fact_ids as list of str) so JSON round-trip cannot break hash.
    Returns True if appended, False if invalid or duplicate.
    """
    own_conn = conn is None
    if db_path is None and conn is None:
        db_path = "axiom_ledger.db"

    block = _normalize_block_from_wire(block)

    conn = conn if conn else sqlite3.connect(db_path)
    try:
        ensure_genesis(conn)
        head = get_chain_head(db_path=db_path, conn=conn) # Pass connection context
        if head is None:
            logger.warning("[P2P Chain] Append failed: no local chain head.")
            return False
        prev_id, prev_height = head
        if block["previous_block_id"] != prev_id or block["height"] != prev_height + 1:
            logger.warning(
                "[P2P Chain] Append failed: chain divergence. Peer block expects previous=%s height=%s; "
                "our head is %s height=%s. Chains have diverged (e.g. different DBs or one node created blocks alone).",
                block.get("previous_block_id", "")[:16],
                block.get("height"),
                prev_id[:16] if prev_id else None,
                prev_height,
            )
            return False
        
        # Use the reason string from validate_block for clearer logging in P2P.
        # The expected height for this incoming block is (prev_height + 1).
        ok, reason = validate_block(
            block["block_id"],
            block["previous_block_id"],
            block["height"],
            block["created_at_utc"],
            block["fact_ids"],
            prev_id,
            prev_height + 1,
        )
        if not ok:
            logger.warning("[P2P Chain] Append failed: block validation failed (%s).", reason)
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
        logger.warning("[P2P Chain] Append failed: block already exists (duplicate block_id).")
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


def replace_chain_with_peer_blocks(blocks: list[dict[str, Any]], db_path: str | None = None) -> bool:
    """
    Longest-chain wins: replace our chain (keep genesis) with the peer's blocks.
    Use when we've diverged and the peer has a longer chain. blocks must be ordered by height ascending.
    Returns True if replacement succeeded; all blocks are validated and inserted in one go.
    """
    if not blocks:
        return False
    if db_path is None:
        db_path = "axiom_ledger.db"
    conn = sqlite3.connect(db_path)
    try:
        ensure_genesis(conn)
        cursor = conn.cursor()
        
        # Delete all non-genesis blocks. This must be atomic.
        cursor.execute("DELETE FROM blocks WHERE height > 0")
        
        prev_id = GENESIS_BLOCK_ID
        prev_height = 0
        
        for i, blk_wire in enumerate(blocks):
            blk = _normalize_block_from_wire(blk_wire)
            
            # 1. Check link continuity against the block we just successfully inserted/processed
            if blk["previous_block_id"] != prev_id or blk["height"] != prev_height + 1:
                logger.error(
                    f"[Chain Replace] Integrity break at peer block index {i} (Height {blk.get('height')}). "
                    f"Expected previous ID {prev_id[:16]}... but peer block specifies {blk['previous_block_id'][:16]}..."
                )
                conn.rollback()
                return False
            
            # 2. Validate hash and content integrity against expected link.
            #    The expected height for this block is (prev_height + 1).
            ok, reason = validate_block(
                blk["block_id"],
                blk["previous_block_id"],
                blk["height"],
                blk["created_at_utc"], # *** FIX: Corrected key from 'blk_created_at_utc' back to 'created_at_utc' ***
                blk["fact_ids"],
                prev_id,
                prev_height + 1,
            )
            if not ok:
                logger.error(f"[Chain Replace] Hash/Content validation failed for block {blk['block_id'][:16]}... Reason: {reason}")
                conn.rollback()
                return False
            
            # 3. Insert the block
            cursor.execute(
                """
                INSERT INTO blocks (block_id, previous_block_id, height, created_at_utc, fact_ids)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    blk["block_id"],
                    blk["previous_block_id"],
                    blk["height"],
                    blk["created_at_utc"],
                    json.dumps(blk["fact_ids"]),
                ),
            )
            
            # Update trackers for the next iteration
            prev_id = blk["block_id"]
            prev_height = blk["height"]
            
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[Chain Replace] Unexpected error during chain replacement: {e}")
        conn.rollback()
        return False
    finally:
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
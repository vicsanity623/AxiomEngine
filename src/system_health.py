"""
Axiom - system_health.py

Helpers to compute lightweight snapshots of ledger and blockchain health.
Intended for periodic idle tasks, not heavy analytics.
"""

import sqlite3
from typing import Dict, Any


def compute_health_snapshot(db_path: str) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    snapshot: Dict[str, Any] = {}
    try:
        cur = conn.cursor()

        # Fact counts by status and basic stats.
        cur.execute("SELECT status, COUNT(*) as c FROM facts GROUP BY status")
        status_counts = {row["status"]: row["c"] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) as c FROM facts")
        total_facts = cur.fetchone()["c"]

        cur.execute("SELECT AVG(trust_score) as avg_trust FROM facts")
        avg_trust_row = cur.fetchone()
        avg_trust = avg_trust_row["avg_trust"] if avg_trust_row else None

        cur.execute(
            "SELECT MIN(ingest_timestamp_utc) as oldest, MAX(ingest_timestamp_utc) as newest FROM facts"
        )
        age_row = cur.fetchone()

        # Block / chain stats.
        cur.execute("SELECT COUNT(*) as c FROM blocks")
        total_blocks = cur.fetchone()["c"]

        cur.execute("SELECT MAX(height) as h FROM blocks")
        head_row = cur.fetchone()
        chain_height = head_row["h"] if head_row else None

        snapshot = {
            "total_facts": int(total_facts or 0),
            "status_counts": status_counts,
            "avg_trust_score": float(avg_trust) if avg_trust is not None else None,
            "oldest_fact_ts": age_row["oldest"] if age_row else None,
            "newest_fact_ts": age_row["newest"] if age_row else None,
            "total_blocks": int(total_blocks or 0),
            "chain_height": int(chain_height or 0),
        }
    finally:
        conn.close()

    return snapshot


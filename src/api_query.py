"""Provide functions and utilities for querying the API.

# Copyright (C) 2026 The Axiom Contributors
"""

import logging
import sqlite3
import zlib
from typing import Any

logger = logging.getLogger(__name__)

# DB_NAME removed. We rely on path argument.


def search_ledger_for_api(
    search_term: str,
    include_uncorroborated: bool = False,
    include_disputed: bool = False,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Search the local SQLite ledger for facts containing the search term."""
    conn = None
    if db_path is None:
        db_path = "axiom_ledger.db"  # Fallback default path

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # We must select the content column explicitly in case it's a BLOB
        query = "SELECT fact_id, fact_content, status, trust_score, source_url, ingest_timestamp_utc FROM facts WHERE fact_content LIKE ?"
        params = [f"%{search_term}%"]
        if not include_disputed:
            query += " AND status != 'disputed'"
        if not include_uncorroborated:
            query += " AND status = 'trusted'"

        cursor.execute(query, params)

        results = []
        for row in cursor.fetchall():
            r = dict(row)
            # --- DECOMPRESS THE CONTENT FOR SEARCHING/RETURNING ---
            try:
                r["fact_content"] = zlib.decompress(r["fact_content"]).decode(
                    "utf-8"
                )
                results.append(r)
            except (TypeError, zlib.error):
                logger.warning(
                    f"[API Query] Could not decompress fact {r['fact_id'][:8]}. Skipping or keeping compressed."
                )
                # If decompression fails, we skip it or return the raw blob depending on preference.
                # For API calls, we should probably skip bad data.
                continue

        return results

    except sqlite3.Error as e:
        logger.error(f"[Ledger Query] Database error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def query_lexical_mesh(
    search_term: str, db_path: str | None = None
) -> dict[str, Any] | None:
    """Navigate the synapses of Axiom's brain."""
    conn = None
    if db_path is None:
        db_path = "axiom_ledger.db"

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM lexicon WHERE word = ?",
            (search_term.lower(),),
        )
        atom = cursor.fetchone()

        cursor.execute(
            """
            SELECT word_a, word_b, relation_type, strength
            FROM synapses
            WHERE word_a = ? OR word_b = ?
            ORDER BY strength DESC LIMIT 10
        """,
            (search_term.lower(), search_term.lower()),
        )
        synapses = [dict(row) for row in cursor.fetchall()]

        return {
            "concept": search_term,
            "properties": dict(atom) if atom else None,
            "associations": synapses,
        }
    except Exception as e:
        logger.error(f"[Mesh Query] Brain traversal error: {e}")
        return None
    finally:
        if conn:
            conn.close()

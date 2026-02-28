"""Provide functions and utilities for querying the API.

# Copyright (C) 2026 The Axiom Contributors
"""

from __future__ import annotations

import logging
import sqlite3
import typing
import zlib
from typing import TypedDict

logger = logging.getLogger(__name__)


class FactResult(TypedDict):
    """Represents a row from the 'facts' table."""

    fact_id: str
    fact_content: str
    status: str
    trust_score: int
    source_url: str
    ingest_timestamp_utc: str


class LexiconAtom(TypedDict):
    """Represents a row from the 'lexicon' table."""

    word: str
    pos_tag: str
    occurrence_count: int


class SynapseRelation(TypedDict):
    """Represents a row from the 'synapses' table."""

    word_a: str
    word_b: str
    relation_type: str
    strength: int


class LexicalMeshResult(TypedDict):
    """Represents the structured result of a lexical mesh query."""

    concept: str
    properties: LexiconAtom | None
    associations: list[SynapseRelation]


def search_ledger_for_api(
    search_term: str,
    include_uncorroborated: bool = False,
    include_disputed: bool = False,
    db_path: str = "axiom_ledger.db",
) -> list[FactResult]:
    """Search the local SQLite ledger for facts containing the search term."""
    conn = None

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT fact_id, fact_content, status, trust_score, source_url, ingest_timestamp_utc FROM facts WHERE fact_content LIKE ?"
        params: list[str | int] = [f"%{search_term}%"]
        if not include_disputed:
            query += " AND status != 'disputed'"
        if not include_uncorroborated:
            query += " AND status = 'trusted'"

        cursor.execute(query, params)

        results: list[FactResult] = []
        for row in cursor.fetchall():
            r = dict(row)
            try:
                r["fact_content"] = zlib.decompress(r["fact_content"]).decode(
                    "utf-8"
                )
                results.append(r)  # type: ignore[arg-type]
            except (TypeError, zlib.error):
                logger.warning(
                    f"[API Query] Could not decompress fact {r['fact_id'][:8]}. Skipping or keeping compressed."
                )
                continue

        return results

    except sqlite3.Error as e:
        logger.error(f"[Ledger Query] Database error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def query_lexical_mesh(
    search_term: str, db_path: str = "axiom_ledger.db"
) -> LexicalMeshResult | None:
    """Navigate the synapses of Axiom's brain."""
    conn = None

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT word, pos_tag, occurrence_count FROM lexicon WHERE word = ?",
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

        synapses: list[SynapseRelation] = [
            typing.cast("SynapseRelation", dict(row))
            for row in cursor.fetchall()
        ]

        properties: LexiconAtom | None = (
            typing.cast("LexiconAtom", dict(atom)) if atom else None
        )

        return {
            "concept": search_term,
            "properties": properties,
            "associations": synapses,
        }
    except Exception as e:
        logger.error(f"[Mesh Query] Brain traversal error: {e}")
        return None
    finally:
        if conn:
            conn.close()

"""Tests for the metacognitive engine (integrity check and pruning)."""

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.ledger import DB_NAME as LEDGER_DB_NAME, initialize_database


# Use a test DB path so we don't touch the real ledger
TEST_DB = "test_metacognitive_ledger.db"


@pytest.fixture
def temp_db(tmp_path):
    """Create a real ledger DB in a temp dir and patch metacognitive_engine to use it."""
    db_path = tmp_path / TEST_DB
    # Initialize schema using ledger (it uses its global DB_NAME, so we must patch both)
    with patch("src.ledger.DB_NAME", str(db_path)):
        initialize_database()

    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        # Insert facts that match prune criteria: old + low trust + short/empty ADL
        old_cutoff = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        cursor.execute(
            """
            INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status, adl_summary)
            VALUES (?, ?, ?, ?, ?, 'uncorroborated', ?)
            """,
            (
                "shallow_old_1",
                b"compressed_fact_1",
                "https://example.com/1",
                old_cutoff,
                1,
                "x|y|z",  # ADL length 7 < 10 -> will be pruned
            ),
        )
        cursor.execute(
            """
            INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status, adl_summary)
            VALUES (?, ?, ?, ?, ?, 'uncorroborated', ?)
            """,
            (
                "keep_old_but_strong_adl",
                b"compressed_fact_2",
                "https://example.com/2",
                old_cutoff,
                1,
                "subject|root_verb|ENT1_ENT2_ENT3",  # ADL length >= 10 -> keep
            ),
        )
        # Recent fact: should never be pruned by meta (only by housekeeping elsewhere)
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        cursor.execute(
            """
            INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status, adl_summary)
            VALUES (?, ?, ?, ?, ?, 'uncorroborated', ?)
            """,
            (
                "recent_shallow",
                b"compressed_fact_3",
                "https://example.com/3",
                recent,
                1,
                "",
            ),
        )
        conn.commit()

    yield str(db_path)
    if os.path.exists(db_path):
        os.remove(db_path)


def test_prune_integrity_check_removes_stale_shallow_facts(temp_db):
    """run_metacognitive_cycle() should delete old, low-trust facts with ADL length < 10."""
    import src.metacognitive_engine as meta

    with patch.object(meta, "DB_NAME", temp_db):
        meta.run_metacognitive_cycle()

    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT fact_id FROM facts ORDER BY fact_id")
        remaining = [row[0] for row in cursor.fetchall()]

    # "shallow_old_1" had ADL length 7 -> deleted
    assert "shallow_old_1" not in remaining
    # "keep_old_but_strong_adl" had ADL long enough -> kept
    assert "keep_old_but_strong_adl" in remaining
    # "recent_shallow" is only 1 day old -> not in the 90-day window, kept
    assert "recent_shallow" in remaining


def test_run_metacognitive_cycle_no_crash(temp_db):
    """run_metacognitive_cycle() completes without raising."""
    import src.metacognitive_engine as meta

    with patch.object(meta, "DB_NAME", temp_db):
        meta.run_metacognitive_cycle()  # should not raise

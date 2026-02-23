# tests/test_ledger.py
import os
import sqlite3

import pytest

from src.ledger import initialize_database

DB_NAME = "test_axiom_ledger.db"


# Fixture to set up a clean DB before each test
@pytest.fixture(scope="function")
def db_connection():
    # Ensure we use a temporary database file
    global DB_NAME
    original_db_name = DB_NAME
    DB_NAME = "test_axiom_ledger.db"

    # Setup: Create the database and tables
    initialize_database()

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    yield conn

    # Teardown: Close connection and delete test DB
    conn.close()
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
    DB_NAME = original_db_name  # Restore global state if needed


def test_database_initialization(db_connection):
    """Test that tables exist after initialization."""
    cursor = db_connection.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='facts';",
    )
    assert cursor.fetchone() is not None
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='synapses';",
    )
    assert cursor.fetchone() is not None


def test_simple_insert(db_connection):
    """Test inserting a basic fact (requires ledger.py to have an insert function that works standalone)"""
    # NOTE: You will need to temporarily add a simple, dependency-free insert function
    # to ledger.py to test this fully, as the existing one relies on Crucible/hashlib.
    # For now, we test the structure itself.

    cursor = db_connection.cursor()
    cursor.execute(
        "INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "test_id_1",
            "A test fact.",
            "http://test.com",
            "2025-01-01T00:00:00",
            1,
            "uncorroborated",
        ),
    )
    db_connection.commit()

    cursor.execute("SELECT COUNT(*) FROM facts")
    assert cursor.fetchone()[0] == 1

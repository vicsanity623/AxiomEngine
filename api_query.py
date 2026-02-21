# Axiom - api_query.py
# Copyright (C) 2025 The Axiom Contributors
# --- V3.0: LOCAL LEDGER INTERFACE ---

import sqlite3
import logging

logger = logging.getLogger(__name__)
DB_NAME = "axiom_ledger.db"

def search_ledger_for_api(search_term, include_uncorroborated=False, include_disputed=False):
    """
    Searches the local SQLite ledger for facts containing the search term.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        query = "SELECT * FROM facts WHERE fact_content LIKE ?"
        params = [f'%{search_term}%']
        
        if not include_disputed:
            query += " AND status != 'disputed'"

        if not include_uncorroborated:
            query += " AND status = 'trusted'"

        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        return results

    except sqlite3.Error as e:
        logger.error(f"[Ledger Query] Database error: {e}")
        return []
    finally:
        if conn: conn.close()
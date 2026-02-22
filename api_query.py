# Axiom - api_query.py
# Copyright (C) 2025 The Axiom Contributors

import sqlite3
import logging

logger = logging.getLogger(__name__)
DB_NAME = "axiom_ledger.db"

def search_ledger_for_api(search_term, include_uncorroborated=False, include_disputed=False):
    """Searches the local SQLite ledger for facts containing the search term."""
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        query = "SELECT * FROM facts WHERE fact_content LIKE ?"
        params = [f'%{search_term}%']
        if not include_disputed: query += " AND status != 'disputed'"
        if not include_uncorroborated: query += " AND status = 'trusted'"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"[Ledger Query] Database error: {e}")
        return []
    finally:
        if conn: conn.close()

def query_lexical_mesh(search_term):
    """
    NEW: Navigates the synapses of Axiom's brain.
    Returns what Axiom 'understands' about a concept and its strongest associations.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM lexicon WHERE word = ?", (search_term.lower(),))
        atom = cursor.fetchone()
        
        cursor.execute("""
            SELECT word_a, word_b, relation_type, strength 
            FROM synapses 
            WHERE word_a = ? OR word_b = ? 
            ORDER BY strength DESC LIMIT 10
        """, (search_term.lower(), search_term.lower()))
        synapses = [dict(row) for row in cursor.fetchall()]
        
        return {
            "concept": search_term,
            "properties": dict(atom) if atom else None,
            "associations": synapses
        }
    except Exception as e:
        logger.error(f"[Mesh Query] Brain traversal error: {e}")
        return None
    finally:
        if conn: conn.close()
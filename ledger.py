# Axiom - ledger.py
# Copyright (C) 2026 The Axiom Contributors

import sqlite3
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DB_NAME = "axiom_ledger.db"
REQUIRED_CORROBORATING_DOMAINS = 3

def _domain_from_url(url):
    """Extracts the base domain (e.g., 'bbc.com') to prevent gaming the system with multiple links from one site."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return "unknown"

def initialize_database():
    """
    Creates the 'facts' table and the 'fact_relationships' table if they don't exist.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    logger.info("[Ledger] Initializing and verifying database schema...")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            fact_id TEXT PRIMARY KEY,
            fact_content TEXT NOT NULL,
            source_url TEXT NOT NULL,
            ingest_timestamp_utc TEXT NOT NULL,
            trust_score INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'uncorroborated',
            corroborating_sources TEXT,
            contradicts_fact_id TEXT,
            lexically_processed INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id_1 TEXT NOT NULL,
            fact_id_2 TEXT NOT NULL,
            weight INTEGER NOT NULL,
            UNIQUE(fact_id_1, fact_id_2)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lexicon (
            word TEXT PRIMARY KEY,
            pos_tag TEXT,
            occurrence_count INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS synapses (
            word_a TEXT NOT NULL,
            word_b TEXT NOT NULL,
            relation_type TEXT,
            strength INTEGER DEFAULT 1,
            PRIMARY KEY (word_a, word_b, relation_type)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lexicon_word ON lexicon(word)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_synapse_a ON synapses(word_a)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_synapse_b ON synapses(word_b)")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_facts_processed ON facts(lexically_processed)")

    conn.commit()
    conn.close()
    logger.info("\033[92m[Ledger] Database schema is up-to-date.\033[0m")

def get_all_facts_for_analysis():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM facts")
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"[Ledger] Read Error: {e}")
        return []
    finally:
        conn.close()

def insert_uncorroborated_fact(fact_id, fact_content, source_url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        cursor.execute("""
            INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status)
            VALUES (?, ?, ?, ?, 1, 'uncorroborated')
        """, (fact_id, fact_content, source_url, timestamp))
        conn.commit()
        return {"fact_id": fact_id, "fact_content": fact_content, "source_url": source_url}
    except sqlite3.IntegrityError:
        return None
    except Exception as e:
        logger.error(f"[Ledger] Insert Error: {e}")
        return None
    finally:
        conn.close()

def find_similar_fact_from_different_domain(fact_content, source_domain, all_facts):
    content_start = fact_content[:60].lower()
    source_domain = source_domain.lower()
    for fact in all_facts:
        existing_domain = _domain_from_url(fact['source_url'])
        if source_domain == existing_domain: continue
        if fact['fact_content'].lower().startswith(content_start):
            return fact
    return None

def update_fact_corroboration(fact_id, new_source_url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT source_url, corroborating_sources, trust_score FROM facts WHERE fact_id = ?", (fact_id,))
        row = cursor.fetchone()
        if not row: return
        original_url, existing_sources_str, current_score = row
        domains = {_domain_from_url(original_url)}
        if existing_sources_str:
            for s in existing_sources_str.split(','):
                if s.strip(): domains.add(_domain_from_url(s))
        new_domain = _domain_from_url(new_source_url)
        domains.add(new_domain)
        new_score = len(domains)
        status = 'trusted' if new_score >= REQUIRED_CORROBORATING_DOMAINS else 'uncorroborated'
        new_sources_str = (existing_sources_str + "," + new_source_url) if existing_sources_str else new_source_url
        cursor.execute("UPDATE facts SET trust_score = ?, status = ?, corroborating_sources = ? WHERE fact_id = ?", 
                       (new_score, status, new_sources_str, fact_id))
        conn.commit()
    finally:
        conn.close()

def mark_facts_as_disputed(original_fact_id, new_fact_id, new_fact_content, new_source_url):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        try:
            cursor.execute("""
                INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status, contradicts_fact_id)
                VALUES (?, ?, ?, ?, 1, 'disputed', ?)
            """, (new_fact_id, new_fact_content, new_source_url, timestamp, original_fact_id))
        except sqlite3.IntegrityError:
            cursor.execute("UPDATE facts SET status='disputed', contradicts_fact_id=? WHERE fact_id=?", (original_fact_id, new_fact_id))
        cursor.execute("UPDATE facts SET status='disputed', contradicts_fact_id=? WHERE fact_id=?", (new_fact_id, original_fact_id))
        conn.commit()
    finally:
        conn.close()

def insert_relationship(fact_id_1, fact_id_2, weight):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    id1, id2 = (fact_id_1, fact_id_2) if fact_id_1 < fact_id_2 else (fact_id_2, fact_id_1)
    try:
        cursor.execute("INSERT OR IGNORE INTO fact_relationships (fact_id_1, fact_id_2, weight) VALUES (?, ?, ?)", (id1, id2, weight))
        conn.commit()
    finally:
        conn.close()

def get_unprocessed_facts_for_lexicon():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM facts WHERE lexically_processed = 0 AND status != 'disputed'")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def mark_fact_as_processed(fact_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE facts SET lexically_processed = 1 WHERE fact_id = ?", (fact_id,))
    conn.commit()
    conn.close()

def update_lexical_atom(word, pos):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO lexicon (word, pos_tag, occurrence_count) 
        VALUES (?, ?, 1) 
        ON CONFLICT(word) DO UPDATE SET occurrence_count = occurrence_count + 1
    """, (word.lower(), pos))
    conn.commit()
    conn.close()

def update_synapse(word_a, word_b, relation):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    w1, w2 = (word_a, word_b) if word_a < word_b else (word_b, word_a)
    cursor.execute("""
        INSERT INTO synapses (word_a, word_b, relation_type, strength)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(word_a, word_b, relation_type) DO UPDATE SET strength = strength + 1
    """, (w1.lower(), w2.lower(), relation))
    conn.commit()
    conn.close()
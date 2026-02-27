# Axiom - ledger.py
# Copyright (C) 2026 The Axiom Contributors
# --- V3.5: DYNAMIC DB PATHING ACROSS ALL UTILITIES ---

import logging
import sqlite3
import zlib
from datetime import UTC, datetime
from typing import Any  # Added for type hinting consistency
from urllib.parse import urlparse

# Removed: DB_NAME = "axiom_ledger.db"
from src.config import REQUIRED_CORROBORATING_DOMAINS

logger = logging.getLogger(__name__)

# Define a default path here only if necessary for functions called without arguments,
# but ideally all calls should pass the path.
DEFAULT_DB_PATH = "axiom_ledger.db"


def _domain_from_url(url):
    """Extracts the base domain (e.g., 'bbc.com') to prevent gaming the system with multiple links from one site."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        domain = domain.removeprefix("www.")
        return domain.lower()
    except Exception:
        return "unknown"


def initialize_database(db_path: str = DEFAULT_DB_PATH):
    """Creates the 'facts' table and the 'fact_relationships' table if they don't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    logger.info(
        f"[Ledger] Initializing and verifying database schema at: {db_path}..."
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS facts (
            fact_id TEXT PRIMARY KEY,
            fact_content BLOB NOT NULL,  /* CHANGED to BLOB for ZLIB compressed data */
            source_url TEXT NOT NULL,
            ingest_timestamp_utc TEXT NOT NULL,
            trust_score INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'uncorroborated',
            corroborating_sources TEXT,
            contradicts_fact_id TEXT,
            lexically_processed INTEGER DEFAULT 0,
            adl_summary TEXT DEFAULT '', /* <-- NEW COLUMN FOR AXIOM'S SHORTHAND */
            fragment_state TEXT NOT NULL DEFAULT 'unknown',  /* Heuristic fragment classification */
            fragment_score REAL NOT NULL DEFAULT 0.0,        /* Confidence that this is a fragment */
            fragment_reason TEXT                             /* Human-readable reason for classification */
        )
    """
    )

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blocks (
            block_id TEXT PRIMARY KEY,
            previous_block_id TEXT NOT NULL,
            height INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            fact_ids TEXT NOT NULL
        )
    """)

    # --- Indexes (Correctly placed before commit) ---
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_lexicon_word ON lexicon(word)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_synapse_a ON synapses(word_a)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_synapse_b ON synapses(word_b)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_facts_processed ON facts(lexically_processed)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(height)"
    )

    # Lightweight migration for existing ledgers that predate fragment columns.
    # SQLite lacks IF NOT EXISTS for columns, so we attempt ALTERs defensively.
    try:
        cursor.execute(
            "ALTER TABLE facts ADD COLUMN fragment_state TEXT NOT NULL DEFAULT 'unknown'"
        )
    except Exception:
        pass
    try:
        cursor.execute(
            "ALTER TABLE facts ADD COLUMN fragment_score REAL NOT NULL DEFAULT 0.0"
        )
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE facts ADD COLUMN fragment_reason TEXT")
    except Exception:
        pass

    # Only attempt to create the fragment_state index after we are sure the
    # column exists (or the ALTERs above have safely failed on older schemas).
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_facts_fragment_state ON facts(fragment_state)"
        )
    except Exception:
        # If the column truly doesn't exist yet, skip index creation for now.
        # On next startup after a successful ALTER this will succeed.
        pass

    conn.commit()
    conn.close()
    logger.info(
        f"\033[92m[Ledger] Database schema initialized/verified for {db_path}.\033[0m"
    )


def migrate_fact_content_to_compressed(
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Optional self-healing migration.

    Ensures all rows in `facts.fact_content` are stored as compressed BLOBs.
    Any legacy plaintext rows (e.g. inserted before compression was enforced
    or via older P2P paths) are converted in-place.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Only touch rows where SQLite reports a non-BLOB type.
        cursor.execute(
            "SELECT fact_id, fact_content FROM facts WHERE typeof(fact_content) != 'blob'"
        )
        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return

        migrated = 0
        for fact_id, raw in rows:
            if raw is None:
                continue
            # For safety, coerce whatever we have to text before compressing.
            text = raw if isinstance(raw, str) else str(raw)
            if not text:
                continue
            try:
                compressed = zlib.compress(text.encode("utf-8"))
            except Exception as e:
                logger.warning(
                    f"[Ledger] Could not compress legacy fact {fact_id[:8]} in {db_path}: {e}"
                )
                continue
            cursor.execute(
                "UPDATE facts SET fact_content = ? WHERE fact_id = ?",
                (compressed, fact_id),
            )
            migrated += 1

        if migrated:
            conn.commit()
            logger.info(
                f"\033[93m[Ledger] Migrated {migrated} legacy fact(s) to compressed storage for {db_path}.\033[0m"
            )
        conn.close()
    except Exception as e:
        logger.warning(
            f"[Ledger] Fact compression migration skipped for {db_path}: {e}"
        )


def get_all_facts_for_analysis(
    db_path: str = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Fetches facts from the ledger."""
    conn = sqlite3.connect(db_path)
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


def insert_uncorroborated_fact(
    fact_id,
    fact_content,
    source_url,
    adl_summary="",
    fragment_state: str = "unknown",
    fragment_score: float = 0.0,
    fragment_reason: str | None = None,
    db_path: str = DEFAULT_DB_PATH,  # <-- ADDED db_path
):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    timestamp = datetime.now(UTC).isoformat()
    compressed_content = zlib.compress(fact_content.encode("utf-8"))
    try:
        cursor.execute(
            """
            INSERT INTO facts (
                fact_id,
                fact_content,
                source_url,
                ingest_timestamp_utc,
                trust_score,
                status,
                adl_summary,
                fragment_state,
                fragment_score,
                fragment_reason
            )
            VALUES (?, ?, ?, ?, 1, 'uncorroborated', ?, ?, ?, ?)
        """,
            (
                fact_id,
                compressed_content,
                source_url,
                timestamp,
                adl_summary,
                fragment_state,
                float(fragment_score or 0.0),
                fragment_reason,
            ),
        )
        conn.commit()
        return {
            "fact_id": fact_id,
            "fact_content": fact_content,
            "source_url": source_url,
        }
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def find_similar_fact_from_different_domain(
    fact_content,
    source_domain,
    all_facts,
    db_path: str = DEFAULT_DB_PATH,  # <-- Added db_path (though not strictly used here, good for consistency)
):
    content_start = fact_content[:60].lower()
    source_domain = source_domain.lower()
    for fact in all_facts:
        existing_domain = _domain_from_url(fact["source_url"])
        if source_domain == existing_domain:
            continue
        raw = fact["fact_content"]
        try:
            existing_text = (
                zlib.decompress(raw).decode("utf-8")
                if isinstance(raw, bytes)
                else raw
            )
        except (zlib.error, AttributeError):
            continue
        if existing_text.lower().startswith(content_start):
            return fact
    return None


def update_fact_corroboration(
    fact_id, new_source_url, db_path: str = DEFAULT_DB_PATH
):  # <-- Added db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT source_url, corroborating_sources, trust_score FROM facts WHERE fact_id = ?",
            (fact_id,),
        )
        row = cursor.fetchone()
        if not row:
            return
        original_url, existing_sources_str, current_score = row

        domains = {_domain_from_url(original_url)}
        if existing_sources_str:
            for s in existing_sources_str.split(","):
                if s.strip():
                    domains.add(_domain_from_url(s))
        new_domain = _domain_from_url(new_source_url)
        domains.add(new_domain)
        new_score = len(domains)
        status = (
            "trusted"
            if new_score >= REQUIRED_CORROBORATING_DOMAINS
            else "uncorroborated"
        )
        new_sources_str = (
            (existing_sources_str + "," + new_source_url)
            if existing_sources_str
            else new_source_url
        )
        cursor.execute(
            "UPDATE facts SET trust_score = ?, status = ?, corroborating_sources = ? WHERE fact_id = ?",
            (new_score, status, new_sources_str, fact_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_facts_as_disputed(
    original_fact_id,
    new_fact_id,
    new_fact_content,
    new_source_url,
    db_path: str = DEFAULT_DB_PATH,  # <-- Added db_path
):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    timestamp = datetime.now(UTC).isoformat()
    try:
        try:
            cursor.execute(
                """
                INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status, contradicts_fact_id)
                VALUES (?, ?, ?, ?, 1, 'disputed', ?)
            """,
                (
                    new_fact_id,
                    new_fact_content,
                    new_source_url,
                    timestamp,
                    original_fact_id,
                ),
            )
        except sqlite3.IntegrityError:
            cursor.execute(
                "UPDATE facts SET status='disputed', contradicts_fact_id=? WHERE fact_id=?",
                (original_fact_id, new_fact_id),
            )
        cursor.execute(
            "UPDATE facts SET status='disputed', contradicts_fact_id=? WHERE fact_id=?",
            (new_fact_id, original_fact_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_relationship(
    fact_id_1, fact_id_2, weight, db_path: str = DEFAULT_DB_PATH
):  # <-- Added db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    id1, id2 = (
        (fact_id_1, fact_id_2)
        if fact_id_1 < fact_id_2
        else (fact_id_2, fact_id_1)
    )
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO fact_relationships (fact_id_1, fact_id_2, weight) VALUES (?, ?, ?)",
            (id1, id2, weight),
        )
        conn.commit()
    finally:
        conn.close()


def get_unprocessed_facts_for_lexicon(
    db_path: str = DEFAULT_DB_PATH,
):  # <-- Added db_path
    """Fetches facts that the brain hasn't learned from yet."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM facts WHERE lexically_processed = 0 AND status != 'disputed'"
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def mark_fact_as_processed(
    fact_id, db_path: str = DEFAULT_DB_PATH
):  # <-- Added db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE facts SET lexically_processed = 1 WHERE fact_id = ?",
        (fact_id,),
    )
    conn.commit()
    conn.close()


def update_lexical_atom(
    word, pos, db_path: str = DEFAULT_DB_PATH
):  # <-- Added db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO lexicon (word, pos_tag, occurrence_count) 
        VALUES (?, ?, 1) 
        ON CONFLICT(word) DO UPDATE SET occurrence_count = occurrence_count + 1
    """,
        (word.lower(), pos),
    )
    conn.commit()
    conn.close()


def update_synapse(
    word_a, word_b, relation, db_path: str = DEFAULT_DB_PATH
):  # <-- Added db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    w1, w2 = (word_a, word_b) if word_a < word_b else (word_b, word_a)
    cursor.execute(
        """
        INSERT INTO synapses (word_a, word_b, relation_type, strength)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(word_a, word_b, relation_type) DO UPDATE SET strength = strength + 1
    """,
        (w1.lower(), w2.lower(), relation),
    )
    conn.commit()
    conn.close()

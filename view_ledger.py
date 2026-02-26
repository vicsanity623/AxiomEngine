#!/usr/bin/env python3
# Axiom - view_ledger.py
# Copyright (C) 2026 The Axiom Contributors
# --- V3.4: DYNAMIC DB PATHING FOR INSPECTION UTILITY ---

import argparse
import os
import sqlite3
import sys
import zlib

from src.ledger import initialize_database

CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
PINK = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"


def print_header(text):
    print(f"\n{CYAN}=== {text} ==={RESET}")


def ensure_ledger_schema(db_path: str) -> None:
    """If the DB has no facts table (e.g. fresh or after reset), initialize schema."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='facts'"
        )
        needs_init = cur.fetchone() is None
    finally:
        conn.close()
    if needs_init:
        initialize_database(db_path)


def print_stats(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        cur.execute("SELECT status, COUNT(*) FROM facts GROUP BY status")
        stats = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM facts")
        total_facts = cur.fetchone()[0]

        try:
            cur.execute("SELECT COUNT(*) FROM fact_relationships")
            rels = cur.fetchone()[0]
        except:
            rels = 0

        try:
            cur.execute("SELECT COUNT(*) FROM lexicon")
            atoms = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM synapses")
            synapses = cur.fetchone()[0]
        except:
            atoms, synapses = 0, 0

        print_header("LEDGER & MESH STATISTICS")
        print(f"Total Facts:        {total_facts}")
        print(f"Fact Relationships: {rels}")
        print(f"Linguistic Atoms:   {atoms}")
        print(f"Neural Synapses:    {synapses}")
        print("-" * 30)

        # Always show trusted (verified), disputed, uncorroborated (0 if missing)
        status_counts = {"trusted": 0, "disputed": 0, "uncorroborated": 0}
        for status, count in stats:
            if status in status_counts:
                status_counts[status] = count
        for status in ("trusted", "disputed", "uncorroborated"):
            count = status_counts[status]
            label = "trusted (verified)" if status == "trusted" else status
            color = (
                GREEN
                if status == "trusted"
                else (RED if status == "disputed" else GRAY)
            )
            print(f"{color}{label.ljust(20)}: {count}{RESET}")

        # Optional fragment statistics (available on newer schemas).
        try:
            cur.execute(
                "SELECT fragment_state, COUNT(*) FROM facts GROUP BY fragment_state"
            )
            frag_rows = cur.fetchall()
            if frag_rows:
                frag_counts = {
                    "unknown": 0,
                    "suspected_fragment": 0,
                    "confirmed_fragment": 0,
                    "rejected_fragment": 0,
                }
                for state, count in frag_rows:
                    if state in frag_counts:
                        frag_counts[state] = count
                print()
                print(
                    f"{PINK}{'fragments (suspect)'.ljust(20)}: {frag_counts['suspected_fragment']}{RESET}"
                )
                print(
                    f"{PINK}{'fragments (confirmed)'.ljust(20)}: {frag_counts['confirmed_fragment']}{RESET}"
                )
        except Exception:
            # Older ledgers without fragment columns: silently skip.
            pass

    except Exception as e:
        print(f"Error reading stats: {e}")
    finally:
        conn.close()


def print_brain(db_path: str, limit=15): # <-- Added db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        print_header(f"TOP NEURAL SYNAPSES (Limit: {limit})")
        cur.execute(
            """
            SELECT word_a, word_b, relation_type, strength 
            FROM synapses 
            ORDER BY strength DESC LIMIT ?
        """,
            (limit,),
        )
        rows = cur.fetchall()

        if not rows:
            print(
                f"{GRAY}Brain is currently vacant. Run a reflection cycle.{RESET}",
            )
            return

        for row in rows:
            print(
                f"  {PINK}{row['word_a'].ljust(12)}{RESET} ←({row['relation_type']})→ {PINK}{row['word_b'].ljust(12)}{RESET} [Strength: {row['strength']}]",
            )

        print_header("HEAVIEST CONCEPTS")
        cur.execute(
            "SELECT word, occurrence_count FROM lexicon ORDER BY occurrence_count DESC LIMIT 10",
        )
        for row in cur.fetchall():
            print(
                f"  {row['word'].ljust(15)} : {row['occurrence_count']} occurrences",
            )

    except Exception as e:
        print(f"Error reading brain: {e}")
    finally:
        conn.close()


def print_facts(db_path: str, limit=20): # <-- Added db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print_header(f"RECENT RECORDS (Limit: {limit})")

    cur.execute(
        "SELECT * FROM facts ORDER BY ingest_timestamp_utc DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()

    for row in rows:
        r = dict(row)

        status = r["status"]
        color = (
            GREEN if status == "trusted" else (RED if status == "disputed" else GRAY)
        )

        # --- DECOMPRESS CONTENT HERE (Crucial Step) ---
        try:
            # The content is now a compressed BLOB (bytes) from ledger.py
            fact_content = zlib.decompress(r["fact_content"]).decode("utf-8")
        except (TypeError, zlib.error):
            fact_content = (
                f"ERROR: Could not decompress fact content (ID: {r['fact_id'][:8]})."
            )

        # Indicator for brain processing
        processed = (
            f"{PINK}◈{RESET}" if r.get("lexically_processed") else f"{GRAY}◇{RESET}"
        )

        # Calculate word count and derive fragment indicator using stored metadata when available.
        word_count = len(fact_content.split())
        frag_state = r.get("fragment_state", "unknown")
        frag_score = r.get("fragment_score", 0.0) or 0.0

        if frag_state == "confirmed_fragment":
            integrity = f"{RED}FRAGMENT!{RESET}"
        elif frag_state == "suspected_fragment" or frag_score >= 0.5:
            integrity = f"{RED}FRAGMENT?{RESET}"
        else:
            # Legacy heuristic fallback on very short sentences.
            integrity = (
                f"{GREEN}COMPLETE{RESET}" if word_count > 8 else f"{RED}FRAGMENT?{RESET}"
            )

        print(
            f"{color}[{status.upper()}]{RESET} {processed} Trust: {r['trust_score']} | Words: {word_count} | {integrity}"
        )
        print(f"   {fact_content}")  # Print the DECOMPRESSED content
        print(f"   {GRAY}Source: {r['source_url']}{RESET}")
        print("")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Axiom Ledger & Brain Inspector",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show summary statistics only",
    )
    parser.add_argument(
        "--brain",
        action="store_true",
        help="Inspect the Lexical Mesh neural pathways",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of items to show",
    )
    # --- NEW: ADD ARGUMENT FOR DB PATH ---
    parser.add_argument(
        "--db",
        type=str,
        default=os.environ.get("AXIOM_DB_PATH", "axiom_ledger.db"),
        help="Specify the path to the ledger.db file to inspect.",
    )
    
    args = parser.parse_args()

    ensure_ledger_schema(args.db)

    if args.stats:
        print_stats(args.db)
    elif args.brain:
        print_stats(args.db)
        print_brain(args.db, args.limit)
    else:
        print_stats(args.db)
        print_facts(args.db, args.limit)
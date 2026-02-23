#!/usr/bin/env python3
# Axiom - view_ledger.py
# Copyright (C) 2026 The Axiom Contributors


import argparse
import zlib
import sqlite3

DB_NAME = "axiom_ledger.db"

CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
PINK = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"


def print_header(text):
    print(f"\n{CYAN}=== {text} ==={RESET}")


def print_stats():
    conn = sqlite3.connect(DB_NAME)
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

        for status, count in stats:
            color = (
                GREEN
                if status == "trusted"
                else (RED if status == "disputed" else GRAY)
            )
            print(f"{color}{status.ljust(15)}: {count}{RESET}")

    except Exception as e:
        print(f"Error reading stats: {e}")
    finally:
        conn.close()


def print_brain(limit=15):
    conn = sqlite3.connect(DB_NAME)
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


def print_facts(limit=20):
    conn = sqlite3.connect(DB_NAME)
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
        
        status = r['status']
        color = GREEN if status == 'trusted' else (RED if status == 'disputed' else GRAY)
        
        # --- DECOMPRESS CONTENT HERE (Crucial Step) ---
        try:
            # The content is now a compressed BLOB (bytes) from ledger.py
            fact_content = zlib.decompress(r['fact_content']).decode('utf-8')
        except (TypeError, zlib.error):
            # Fallback if decompression fails (e.g., it's an old non-compressed record)
            fact_content = f"ERROR: Could not decompress fact content (ID: {r['fact_id'][:8]})."
            
        # Indicator for brain processing
        processed = f"{PINK}◈{RESET}" if r.get('lexically_processed') else f"{GRAY}◇{RESET}"
        
        # Calculate word count and check for fragmentation using the DECOMPRESSED text
        word_count = len(fact_content.split())
        integrity = f"{GREEN}COMPLETE{RESET}" if word_count > 8 else f"{RED}FRAGMENT?{RESET}"

        print(f"{color}[{status.upper()}]{RESET} {processed} Trust: {r['trust_score']} | Words: {word_count} | {integrity}")
        print(f"   {fact_content}") # Print the DECOMPRESSED content
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
    args = parser.parse_args()

    if args.stats:
        print_stats()
    elif args.brain:
        print_stats()
        print_brain(args.limit)
    else:
        print_stats()
        print_facts(args.limit)

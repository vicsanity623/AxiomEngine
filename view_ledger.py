#!/usr/bin/env python3
# Axiom - view_ledger.py
# --- V3.1: INSPECTION TOOL ---

import sqlite3
import sys
import argparse

DB_NAME = "axiom_ledger.db"

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
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
        total = cur.fetchone()[0]
        
        # Check if relationships table exists yet
        try:
            cur.execute("SELECT COUNT(*) FROM fact_relationships")
            rels = cur.fetchone()[0]
        except:
            rels = 0

        print_header("LEDGER STATISTICS")
        print(f"Total Facts:       {total}")
        print(f"Total Connections: {rels}")
        print("-" * 30)
        for status, count in stats:
            color = GREEN if status == 'trusted' else (RED if status == 'disputed' else GRAY)
            print(f"{color}{status.ljust(15)}: {count}{RESET}")

    except Exception as e:
        print(f"Error reading stats: {e}")
    finally:
        conn.close()

def print_facts(limit=20):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print_header(f"RECENT FACTS (Limit: {limit})")
    
    cur.execute("SELECT * FROM facts ORDER BY ingest_timestamp_utc DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    
    for row in rows:
        color = GREEN if row['status'] == 'trusted' else (RED if row['status'] == 'disputed' else GRAY)
        print(f"{color}[{row['status'].upper()}] Trust: {row['trust_score']}{RESET}")
        print(f"   {row['fact_content']}")
        print(f"   {GRAY}Source: {row['source_url']}{RESET}")
        print("")

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    parser.add_argument("--limit", type=int, default=10, help="Number of facts to show")
    args = parser.parse_args()

    if args.stats:
        print_stats()
    else:
        print_stats()
        print_facts(args.limit)
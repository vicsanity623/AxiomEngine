#!/usr/bin/env python3
"""Axiom Terminal Chat.

This module provides a command-line interface to interact directly with the
Axiom ledger and inference engine without requiring an HTTP server.
It supports natural language queries, ledger searching, and lexical mesh lookups.
"""

import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api_query import query_lexical_mesh, search_ledger_for_api
from src.inference_engine import think

CYAN = "\033[96m"
GREEN = "\033[92m"
GRAY = "\033[90m"
RESET = "\033[0m"

DEFAULT_DB = os.environ.get("AXIOM_DB_PATH", "axiom_ledger.db")


def main():
    """Execute the main interactive chat loop.

    Initializes configuration from environment variables, handles the terminal
    input/output loop, and dispatches user commands to the appropriate
    backend functions.
    """
    db_path = os.environ.get("AXIOM_DB_PATH", "axiom_ledger.db")
    if not os.path.exists(db_path):
        print(
            f"{GRAY}[Axiom Chat] Ledger not found at {db_path}. Run the node or ingest first.{RESET}"
        )
        sys.exit(1)

    # How many extra corroborating streams to show after the best match (0 = only the count)
    try:
        extra_streams = int(os.environ.get("AXIOM_CHAT_EXTRA_STREAMS", "10"))
    except ValueError:
        extra_streams = 10

    # Phrases that mean "show more of the last answer's streams"
    show_more_phrases = (
        "show me more",
        "show more",
        "tell me more",
        "tell me more.",
        "what else",
        "what else?",
        "more",
        "other streams",
        "show me other corroboration streams",
        "show other corroboration streams",
        "other corroboration",
        "more streams",
        "more corroboration",
    )

    def is_show_more(msg):
        normalized = (msg or "").strip().lower()
        return any(
            phrase in normalized or normalized == phrase.rstrip(".?")
            for phrase in show_more_phrases
        )

    def format_stream_batch(facts, start_idx, count=10):
        lines = []
        for i, f in enumerate(
            facts[start_idx : start_idx + count], start=start_idx + 1
        ):
            content = (f.get("fact_content") or "").strip()
            if len(content) > 200:
                content = content[:197] + "..."
            source = (f.get("source_url") or "—")[:60]
            lines.append(
                f'  [{i}] ({f.get("status", "?")}, trust {f.get("trust_score", 0)})\n  "{content}"\n  Source: {source}'
            )
        return "\n\n".join(lines) if lines else None

    last_grounded_facts = []
    last_shown_count = 0

    print(f"{CYAN}◈ Axiom Terminal Chat (direct ledger, no HTTP){RESET}")
    print(f"  DB: {db_path}")
    print("  Commands: /search <term> | /mesh <word> | /quit")
    print(
        '  Say "show more" or "tell me more" after a query to see more corroborating streams.'
    )
    print(
        f"  Think uses neural summary + up to {extra_streams} streams (AXIOM_CHAT_EXTRA_STREAMS to change)."
    )
    print()

    while True:
        try:
            line = input(f"{GREEN}you>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not line:
            continue
        if line.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Bye.")
            break

        # "Show more" trigger: show next batch of streams from last answer
        if is_show_more(line):
            if not last_grounded_facts:
                print(
                    f"{CYAN}axiom>{RESET} No previous query to show more from. Ask something first (e.g. Lord Mandelson)."
                )
                continue
            next_batch = format_stream_batch(
                last_grounded_facts, last_shown_count, count=extra_streams
            )
            if not next_batch:
                print(
                    f"{CYAN}axiom>{RESET} No further streams. (Shown {last_shown_count} of {len(last_grounded_facts)}.)"
                )
                continue
            print(
                f"{CYAN}axiom>{RESET} [More corroborating streams]\n\n{next_batch}"
            )
            last_shown_count += min(
                extra_streams, len(last_grounded_facts) - last_shown_count
            )
            continue

        if line.lower().startswith("/search "):
            term = line[8:].strip()
            if not term:
                print(f"{GRAY}Usage: /search <term>{RESET}")
                continue
            results = search_ledger_for_api(
                term, include_uncorroborated=True, db_path=db_path
            )
            print(f"{CYAN}[Search '{term}'] {len(results)} fact(s){RESET}")
            for i, r in enumerate(results[:5]):
                content = (r.get("fact_content") or "")[:200]
                if len(r.get("fact_content") or "") > 200:
                    content += "..."
                print(f"  {i + 1}. [{r.get('status', '?')}] {content}")
            if len(results) > 5:
                print(f"  ... and {len(results) - 5} more")
            continue

        if line.lower().startswith("/mesh "):
            word = line[6:].strip()
            if not word:
                print(f"{GRAY}Usage: /mesh <word>{RESET}")
                continue
            data = query_lexical_mesh(word, db_path=db_path)
            if not data:
                print(f"{GRAY}No mesh data for '{word}'{RESET}")
                continue
            print(
                f"{CYAN}[Mesh '{word}']{RESET} {data.get('properties') or 'no atom'}"
            )
            for a in (data.get("associations") or [])[:8]:
                print(
                    f"  — {a.get('word_a')} ←({a.get('relation_type')})→ {a.get('word_b')} [strength {a.get('strength')}]"
                )
            continue

        # Default: inference (think) with neural summary and extra streams
        out = think(
            line,
            db_path=db_path,
            max_extra_streams=extra_streams,
            use_summary=True,
        )
        response = out.get("response", out) if isinstance(out, dict) else out
        grounded = (
            out.get("grounded_facts", []) if isinstance(out, dict) else []
        )
        last_grounded_facts = grounded
        last_shown_count = 1 + min(extra_streams, max(0, len(grounded) - 1))
        print(f"{CYAN}axiom>{RESET} {response}")


if __name__ == "__main__":
    main()

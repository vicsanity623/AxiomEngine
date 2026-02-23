# Axiom - inference_engine.py
# Copyright (C) 2026 The Axiom Contributors

import logging
import zlib
import sqlite3

from src.axiom_model_loader import load_nlp_model

logger = logging.getLogger(__name__)
NLP_MODEL = load_nlp_model()

DEFAULT_DB_PATH = "axiom_ledger.db"


def think(user_query, db_path: str | None = None):
    """The Inference Pathway:
    1. Shred user query into atoms.
    2. Find concept intersections in the Synapse Mesh.
    3. Retrieve the grounded facts that support the path.
    """
    if not NLP_MODEL:
        return "Cognitive error: NLP model offline."

    if db_path is None:
        db_path = DEFAULT_DB_PATH

    doc = NLP_MODEL(user_query)
    query_atoms = [
        token.text.lower() for token in doc if token.pos_ in ("NOUN", "PROPN")
    ]

    if not query_atoms:
        return "Query contains no grounding atoms. Please specify a subject."

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # We now store fact_content as ZLIB-compressed BLOBs, so we can't
        # use SQL LIKE directly on the column. Instead, fetch candidate facts
        # and match in Python after decompression.
        cursor.execute(
            """
            SELECT fact_id, fact_content, trust_score, status, source_url
            FROM facts
            WHERE status != 'disputed'
            """
        )
        rows = cursor.fetchall()

        grounded_facts = []
        for row in rows:
            raw = row["fact_content"]
            try:
                text = (
                    zlib.decompress(raw).decode("utf-8")
                    if isinstance(raw, (bytes, bytearray))
                    else str(raw)
                )
            except (zlib.error, TypeError, ValueError):
                continue

            text_lower = text.lower()
            if any(atom in text_lower for atom in query_atoms):
                grounded_facts.append(
                    {
                        "fact_id": row["fact_id"],
                        "fact_content": text,
                        "trust_score": row["trust_score"],
                        "status": row["status"],
                        "source_url": row["source_url"],
                    }
                )

        if not grounded_facts:
            return (
                f"Neural path for '{' + '.join(query_atoms)}' is currently vacant. "
                "No verified facts found."
            )

        # Highest trust_score first
        grounded_facts.sort(key=lambda f: f["trust_score"], reverse=True)
        best_match = grounded_facts[0]
        response = f'Verified Record Found: "{best_match["fact_content"]}"'

        if len(grounded_facts) > 1:
            response += (
                f"\n\nAdditionally, {len(grounded_facts) - 1} other corroborated "
                "streams support this trajectory."
            )

        return response
    finally:
        conn.close()

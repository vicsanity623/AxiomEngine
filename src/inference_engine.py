# Axiom - inference_engine.py
# Copyright (C) 2026 The Axiom Contributors

import logging
import zlib
import sqlite3

from src.axiom_model_loader import load_nlp_model

logger = logging.getLogger(__name__)
NLP_MODEL = load_nlp_model()

DB_NAME = "axiom_ledger.db"

def think(user_query, db_path: str = DB_NAME):
    """The Inference Pathway:
    1. Shred user query into atoms.
    2. Find concept intersections in the Synapse Mesh.
    3. Retrieve the grounded facts that support the path.
    """
    if not NLP_MODEL:
        return "Cognitive error: NLP model offline."

    doc = NLP_MODEL(user_query)
    query_atoms = [
        token.text.lower() for token in doc if token.pos_ in ("NOUN", "PROPN")
    ]

    if not query_atoms:
        return "Query contains no grounding atoms. Please specify a subject."

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    results = []

    placeholders = " OR ".join(["fact_content LIKE ?" for _ in query_atoms])
    sql = f"SELECT *, trust_score FROM facts WHERE ({placeholders}) AND status != 'disputed' ORDER BY trust_score DESC LIMIT 5"

    params = [f"%{atom}%" for atom in query_atoms]
    cursor.execute(sql, params)
    grounded_facts = cursor.fetchall()

    if not grounded_facts:
        return f"Neural path for '{' + '.join(query_atoms)}' is currently vacant. No verified facts found."

    best_match = grounded_facts[0]
    response = f'Verified Record Found: "{best_match["fact_content"]}"'

    if len(grounded_facts) > 1:
        response += f"\n\nAdditionally, {len(grounded_facts) - 1} other corroborated streams support this trajectory."

    conn.close()
    return response

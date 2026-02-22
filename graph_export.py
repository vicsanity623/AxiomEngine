# Axiom - graph_export.py
# Copyright (C) 2025 The Axiom Contributors

import json
import sqlite3

DB_NAME = "axiom_ledger.db"

def load_facts_and_relationships(db_path=DB_NAME):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT fact_id, fact_content, status, trust_score FROM facts")
        facts = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT fact_id_1, fact_id_2, weight FROM fact_relationships")
        relationships = [dict(row) for row in cur.fetchall()]
    except: facts, relationships = [], []
    conn.close()
    return facts, relationships

def load_brain_synapses(db_path=DB_NAME, min_strength=2):
    """NEW: Fetches atoms and synapses for brain visualization."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT word, occurrence_count FROM lexicon WHERE occurrence_count >= ?", (min_strength,))
        atoms = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT word_a, word_b, relation_type, strength FROM synapses WHERE strength >= ?", (min_strength,))
        synapses = [dict(row) for row in cur.fetchall()]
    except: atoms, synapses = [], []
    conn.close()
    return atoms, synapses

def to_json_for_viz(db_path=DB_NAME, include_sources=True, topic_filter=None):
    facts, relationships = load_facts_and_relationships(db_path)
    if topic_filter:
        topic_lower = topic_filter.lower()
        matching_ids = {f["fact_id"] for f in facts if topic_lower in (f["fact_content"] or "").lower()}
        if not matching_ids: return {"nodes": [], "edges": []}
        neighbor_ids = set(matching_ids)
        for r in relationships:
            if r["fact_id_1"] in matching_ids or r["fact_id_2"] in matching_ids:
                neighbor_ids.add(r["fact_id_1"]); neighbor_ids.add(r["fact_id_2"])
        facts = [f for f in facts if f["fact_id"] in neighbor_ids]
        relationships = [r for r in relationships if r["fact_id_1"] in neighbor_ids and r["fact_id_2"] in neighbor_ids]

    nodes = [{"id": f["fact_id"], "label": (f["fact_content"][:60] + "..."), "status": f["status"], "value": f["trust_score"]} for f in facts]
    edges = [{"from": r["fact_id_1"], "to": r["fact_id_2"], "value": r["weight"]} for r in relationships]
    return {"nodes": nodes, "edges": edges}

def to_json_for_brain_viz(db_path=DB_NAME):
    """NEW: Formats the Lexical Mesh for PyVis."""
    atoms, synapses = load_brain_synapses(db_path)
    nodes = [{"id": a["word"], "label": a["word"], "value": a["occurrence_count"], "group": "atom"} for a in atoms]
    edges = [{"from": s["word_a"], "to": s["word_b"], "value": s["strength"], "title": s["relation_type"]} for s in synapses]
    return {"nodes": nodes, "edges": edges}
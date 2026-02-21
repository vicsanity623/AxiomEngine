# Axiom - graph_export.py
# Copyright (C) 2025 The Axiom Contributors
# --- V3.1: FIXED COLUMN MAPPING FOR NEW LEDGER ---

import json
import sqlite3

DB_NAME = "axiom_ledger.db"

def load_facts_and_relationships(db_path=DB_NAME):
    """
    Load all facts and relationships.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. Get Facts
    try:
        cur.execute("SELECT fact_id, fact_content, source_url, status, trust_score FROM facts")
        facts = [dict(row) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        facts = []

    # 2. Get Relationships (Note: Column is 'weight', not 'relationship_score')
    try:
        cur.execute("SELECT fact_id_1, fact_id_2, weight FROM fact_relationships")
        relationships = [dict(row) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        relationships = []
        
    conn.close()
    return facts, relationships

def to_json_for_viz(db_path=DB_NAME, include_sources=True, topic_filter=None):
    """
    Export facts + edges as JSON for visualization.
    """
    facts, relationships = load_facts_and_relationships(db_path)
    
    # Filter by Topic if requested
    if topic_filter:
        topic_lower = topic_filter.lower()
        matching_ids = {f["fact_id"] for f in facts if topic_lower in (f["fact_content"] or "").lower()}
        
        if not matching_ids:
            return {"nodes": [], "edges": []}
            
        # Include neighbors (1 hop)
        neighbor_ids = set(matching_ids)
        for r in relationships:
            if r["fact_id_1"] in matching_ids or r["fact_id_2"] in matching_ids:
                neighbor_ids.add(r["fact_id_1"])
                neighbor_ids.add(r["fact_id_2"])
                
        facts = [f for f in facts if f["fact_id"] in neighbor_ids]
        relationships = [
            r for r in relationships
            if r["fact_id_1"] in neighbor_ids and r["fact_id_2"] in neighbor_ids
        ]

    # Build Nodes
    nodes = []
    for f in facts:
        n = {
            "id": f["fact_id"],
            "label": (f["fact_content"][:60] + "...") if len(f["fact_content"]) > 60 else f["fact_content"],
            "full_content": f["fact_content"],
            "status": f["status"],
            "value": f["trust_score"], # Size of node based on trust
            "group": f["status"] # Color by group
        }
        if include_sources:
            n["title"] = f"Source: {f['source_url']}"
        nodes.append(n)

    # Build Edges
    edges = []
    for r in relationships:
        edges.append({
            "from": r["fact_id_1"], 
            "to": r["fact_id_2"], 
            "value": r["weight"], # Thickness of line
            "title": f"Link Strength: {r['weight']}"
        })

    return {"nodes": nodes, "edges": edges}
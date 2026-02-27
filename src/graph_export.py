"""Provide functions to export facts and relationships from a ledger database into JSON format for visualization."""

import sqlite3
import zlib
from typing import Any  # Added for type hinting consistency

# DB_NAME removed. All functions now require db_path.


def _decompress_fact_content(raw: bytes | str | None) -> str:
    """Return decompressed fact text for viz/JSON; raw may be bytes (BLOB) or str."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return zlib.decompress(raw).decode("utf-8")
    except (TypeError, zlib.error, ValueError):
        return "[unable to decompress]"


def load_facts_and_relationships(
    db_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load facts and relationships from the ledger, decompressing fact_content for visualization."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT fact_id, fact_content, status, trust_score, source_url FROM facts",
        )
        rows = cur.fetchall()
        facts = []
        for row in rows:
            d = dict(row)
            d["fact_content"] = _decompress_fact_content(d.get("fact_content"))
            facts.append(d)
        cur.execute(
            "SELECT fact_id_1, fact_id_2, weight FROM fact_relationships",
        )
        relationships = [dict(row) for row in cur.fetchall()]
    except Exception as e:
        print(f"Error loading facts and relationships: {e}")
        conn.close()
        return [], []
    conn.close()
    return facts, relationships


def load_brain_synapses(
    db_path: str, min_strength: int = 2
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch atoms and synapses for brain visualization at a given minimum strength."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT word, occurrence_count FROM lexicon WHERE occurrence_count >= ?",
            (min_strength,),
        )
        atoms = [dict(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT word_a, word_b, relation_type, strength FROM synapses WHERE strength >= ?",
            (min_strength,),
        )
        synapses = [dict(row) for row in cur.fetchall()]
    except Exception:
        atoms, synapses = [], []
    conn.close()
    return atoms, synapses


def to_json_for_viz(
    db_path: str,
    include_sources: bool = True,
    topic_filter: str | None = None,
) -> dict[str, Any]:
    """Export ledger facts and edges to JSON format for visualization."""
    facts, relationships = load_facts_and_relationships(db_path)
    if topic_filter:
        topic_lower = topic_filter.lower()
        matching_ids = {
            f["fact_id"]
            for f in facts
            if topic_lower in (f.get("fact_content") or "").lower()
        }
        if not matching_ids:
            return {"nodes": [], "edges": []}
        neighbor_ids = set(matching_ids)
        for r in relationships:
            if (
                r["fact_id_1"] in matching_ids
                or r["fact_id_2"] in matching_ids
            ):
                neighbor_ids.add(r["fact_id_1"])
                neighbor_ids.add(r["fact_id_2"])
        facts = [f for f in facts if f["fact_id"] in neighbor_ids]
        relationships = [
            r
            for r in relationships
            if r["fact_id_1"] in neighbor_ids
            and r["fact_id_2"] in neighbor_ids
        ]
    return {"nodes": facts, "edges": relationships}

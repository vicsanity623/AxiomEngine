# Axiom - inference_engine.py
# Copyright (C) 2026 The Axiom Contributors

import logging
import sqlite3
import zlib

from src.axiom_model_loader import load_nlp_model
from src.synthesizer import get_weighted_entities

logger = logging.getLogger(__name__)
NLP_MODEL = load_nlp_model()

DEFAULT_DB_PATH = "axiom_ledger.db"


def _refine_streams_to_summary(grounded_facts, query_atoms):
    """Neural refinement: use entity overlap and trust to produce one condensed summary.
    No LLM/transformers — uses Axiom's symbolic mesh (entities, structure).
    Picks the best anchor fact (most shared entities + highest trust) and delivers
    it as the canonical answer, with corroboration count.
    """
    if not grounded_facts or not NLP_MODEL:
        return None

    if len(grounded_facts) == 1:
        text = (grounded_facts[0].get("fact_content") or "").strip()
        return f"{text} (Single stream.)"

    # Entity sets per fact (for overlap)
    fact_entities = []
    for f in grounded_facts:
        content = (f.get("fact_content") or "").strip()
        ents = get_weighted_entities(content) if content else {}
        fact_entities.append(set(ents.keys()))

    # Shared entities: appear in at least 2 streams
    all_entities = set()
    for s in fact_entities:
        all_entities |= s
    shared = set(
        e for e in all_entities if sum(1 for s in fact_entities if e in s) >= 2
    )

    # Anchor: fact with most shared-entity overlap, then highest trust
    def score(f, idx):
        overlap = (
            len(fact_entities[idx] & shared) if idx < len(fact_entities) else 0
        )
        trust = f.get("trust_score") or 0
        return (overlap, trust)

    best_idx = max(
        range(len(grounded_facts)),
        key=lambda i: score(grounded_facts[i], i),
    )
    anchor = grounded_facts[best_idx]
    anchor_text = (anchor.get("fact_content") or "").strip()

    # Optional: if anchor is long, prefer a shorter fact that still has good overlap (natural brevity)
    for i, f in enumerate(grounded_facts):
        if i == best_idx:
            continue
        text = (f.get("fact_content") or "").strip()
        if not text:
            continue
        overlap = len(fact_entities[i] & shared)
        if (
            overlap >= max(1, len(shared) - 2)
            and len(text) < len(anchor_text)
            and (f.get("trust_score") or 0) >= 1
        ):
            anchor_text = text
            break

    return anchor_text


def think(
    user_query,
    db_path: str | None = None,
    max_extra_streams: int = 0,
    use_summary: bool = False,
):
    """The Inference Pathway:
    1. Shred user query into atoms.
    2. Find concept intersections in the Synapse Mesh.
    3. Retrieve the grounded facts that support the path.

    Returns dict with "response" (str) and "grounded_facts" (list) for show-more pagination.
    If use_summary is True and multiple streams exist, response is a refined one-sentence summary.
    """
    if not NLP_MODEL:
        return {
            "response": "Cognitive error: NLP model offline.",
            "grounded_facts": [],
        }

    if db_path is None:
        db_path = DEFAULT_DB_PATH

    doc = NLP_MODEL(user_query)
    query_atoms = [
        token.text.lower() for token in doc if token.pos_ in ("NOUN", "PROPN")
    ]

    if not query_atoms:
        return {
            "response": "Query contains no grounding atoms. Please specify a subject.",
            "grounded_facts": [],
        }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
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
            return {
                "response": (
                    f"Neural path for '{' + '.join(query_atoms)}' is currently vacant. "
                    "No verified facts found."
                ),
                "grounded_facts": [],
            }

        grounded_facts.sort(key=lambda f: f["trust_score"], reverse=True)

        if use_summary and len(grounded_facts) >= 1:
            summary = _refine_streams_to_summary(grounded_facts, query_atoms)
            response = summary or (grounded_facts[0].get("fact_content") or "")
        else:
            best_match = grounded_facts[0]
            response = best_match.get("fact_content") or ""

        extra_count = len(grounded_facts) - 1
        if extra_count > 0:
            response += (
                f"\n\nAdditionally, {extra_count} other corroborated "
                "streams support this trajectory."
            )
            if max_extra_streams > 0:
                for i, f in enumerate(
                    grounded_facts[1 : 1 + max_extra_streams], start=1
                ):
                    content = (f["fact_content"] or "").strip()
                    if len(content) > 200:
                        content = content[:197] + "..."
                    source = (f.get("source_url") or "—")[:60]
                    response += f'\n\n  [{i}] ({f.get("status", "?")}, trust {f.get("trust_score", 0)})\n  "{content}"\n  Source: {source}'

        return {"response": response, "grounded_facts": grounded_facts}
    finally:
        conn.close()

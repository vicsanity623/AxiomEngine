"""Module for synthesizing data using natural language processing."""

import logging
import zlib
from typing import Any

from src.axiom_model_loader import load_nlp_model
from src.ledger import (
    get_all_facts_for_analysis,
    insert_relationship,
    update_synapse,
)

logger = logging.getLogger(__name__)

NLP_MODEL = load_nlp_model()

# Type hint added to global set
IGNORED_ENTITIES: set[str] = {
    "today",
    "yesterday",
    "tomorrow",
    "year",
    "years",
    "week",
    "weeks",
    "percent",
    "millions",
    "billions",
    "one",
    "two",
    "first",
    "second",
    "government",
    "police",
    "state",
    "city",
    "news",
    "report",
    "study",
}


def get_weighted_entities(text: str | None) -> dict[str, int]:
    """Extract entities and assign a 'relevance weight'.

    Return a dictionary: { 'entity_name': weight }
    """
    if not text or not NLP_MODEL:
        return {}

    doc = NLP_MODEL(text)
    # Fixed [var-annotated] by explicitly typing the empty dictionary
    entities: dict[str, int] = {}

    for ent in doc.ents:
        clean_text = ent.text.lower().strip()

        if len(clean_text) < 3 or clean_text in IGNORED_ENTITIES:
            continue
        if clean_text.isdigit():
            continue

        if ent.label_ in {"PERSON", "ORG", "EVENT", "WORK_OF_ART"}:
            weight = 3
        elif ent.label_ in {"GPE", "PRODUCT", "LAW"}:
            weight = 1
        else:
            continue

        if clean_text in entities:
            entities[clean_text] = max(entities[clean_text], weight)
        else:
            entities[clean_text] = weight

    return entities


def link_related_facts(
    new_facts_batch: list[dict[str, Any]] | None, db_path: str | None = None
) -> None:
    """Compare a batch of new facts against the ledger.

    Create links and reinforces Neural Synapses between concepts.
    """
    if not NLP_MODEL or not new_facts_batch:
        return

    logger.info(
        "\n\033[96m--- [The Synthesizer] Beginning Knowledge Graph linking... ---\033[0m",
    )

    # Added typing to the empty list to satisfy strict linters
    new_facts_data: list[dict[str, Any]] = []

    for fact in new_facts_batch:
        content = fact.get("fact_content")
        if isinstance(content, (bytes, bytearray)):
            try:
                content = zlib.decompress(content).decode("utf-8")
            except (zlib.error, ValueError, TypeError):
                continue
        if not content:
            continue
        ents = get_weighted_entities(content)
        if ents:
            new_facts_data.append({"id": fact["fact_id"], "entities": ents})

    if not new_facts_data:
        logger.info(
            "[The Synthesizer] No distinctive entities found in new facts. Skipping linking.",
        )
        return

    all_facts_in_ledger = get_all_facts_for_analysis(
        db_path or "axiom_ledger.db"
    )

    # Adjusted to standard logging formatting to avoid Ruff G004 warnings
    logger.info(
        "\033[96m[The Synthesizer] Indexing %d existing facts for cross-reference...\033[0m",
        len(all_facts_in_ledger),
    )

    links_created = 0

    for existing_fact in all_facts_in_ledger:
        raw = existing_fact["fact_content"]
        try:
            content = (
                zlib.decompress(raw).decode("utf-8")
                if isinstance(raw, bytes)
                else raw
            )
        except (zlib.error, AttributeError):
            continue

        existing_ents = get_weighted_entities(content)

        if not existing_ents:
            continue

        for new_fact in new_facts_data:
            if new_fact["id"] == existing_fact["fact_id"]:
                continue

            # Typed as float to match division below
            total_score = 0.0
            shared_terms: list[str] = []

            for entity, weight in new_fact["entities"].items():
                if entity in existing_ents:
                    avg_weight = (weight + existing_ents[entity]) / 2
                    total_score += avg_weight
                    shared_terms.append(entity)

            if total_score >= 2:
                insert_relationship(
                    new_fact["id"],
                    existing_fact["fact_id"],
                    int(total_score),
                )
                links_created += 1

                if len(shared_terms) > 1:
                    for i, term1 in enumerate(shared_terms):
                        for term2 in shared_terms[i + 1 :]:
                            update_synapse(term1, term2, "conceptual_bridge")

    if links_created > 0:
        logger.info(
            "Linking Success. Created %d new graph connections.", links_created
        )
    else:
        logger.info(
            "\033[93m[The Synthesizer] No strong correlations found.\033[0m",
        )

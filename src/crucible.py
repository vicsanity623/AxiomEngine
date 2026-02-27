"""Process and integrate textual facts into the Axiom knowledge mesh.

This module serves as the core ingestion pipeline for extracting structured
facts from raw text. It performs NLP analysis, validates grammatical integrity,
detects contradictions, and stores verified facts as lexical atoms and synapses
within the knowledge graph.
"""

# Axiom - crucible.py
# Copyright (C) 2026 The Axiom Contributors

import hashlib
import logging
import re
import zlib

from src.axiom_model_loader import load_nlp_model
from src.ledger import (
    find_similar_fact_from_different_domain,
    get_all_facts_for_analysis,
    insert_uncorroborated_fact,
    mark_facts_as_disputed,
    update_fact_corroboration,
    update_lexical_atom,
    update_synapse,
)

logger = logging.getLogger(__name__)

NLP_MODEL = load_nlp_model()

MIN_NAMED_ENTITIES_FOR_FACT = 2

SUBJECTIVITY_INDICATORS = {
    "believe",
    "think",
    "feel",
    "seems",
    "appears",
    "argues",
    "suggests",
    "contends",
    "opines",
    "speculates",
    "reckons",
    "estimates",
    "imagines",
    "hopefully",
    "unfortunately",
    "clearly",
    "obviously",
    "reportedly",
    "allegedly",
    "rumored",
    "likely",
    "probably",
    "possibly",
    "opinion",
    "view",
    "perspective",
    "stance",
    "take",
    "feels",
    "felt",
    "thought",
}


def _generate_adl_summary(doc):
    """Generate a compact, deterministic representation of the sentence structure (ADL).

    Format: [Subject_ROOT_Verb(Lemma)_Entities_Hash]
    """
    subject = next(
        (t.text.lower() for t in doc if "subj" in t.dep_),
        "UNK_SUBJ",
    )
    root_verb = next(
        (t.lemma_.lower() for t in doc if t.dep_ == "ROOT"),
        "UNK_ROOT",
    )

    entities = sorted(
        [
            ent.label_
            for ent in doc.ents
            if ent.label_ in {"ORG", "PERSON", "GPE", "EVENT", "LAW", "LOC"}
        ],
    )

    # Concatenate the most important structural markers
    # Return a hash of this summary for compact storage, or the string itself for debugging
    return f"{subject}|{root_verb}|{'_'.join(entities)}"


def integrate_fact_to_mesh(fact_content):
    """Deconstruct a verified fact into its linguistic atoms and synapses.

    Axiom 'learns' language structure from the facts it gathers.
    """
    if not NLP_MODEL:
        return False

    doc = NLP_MODEL(fact_content)

    for token in doc:
        if token.is_punct or token.is_space:
            continue

        update_lexical_atom(token.text, token.pos_)

        if token.dep_ != "ROOT":
            relation = token.dep_
            update_synapse(token.text, token.head.text, relation)

        if len(doc.ents) > 1:
            for i, ent1 in enumerate(doc.ents):
                for ent2 in doc.ents[i + 1 :]:
                    update_synapse(ent1.text, ent2.text, "shared_context")

    return True


def _sanitize_text(text):
    """Clean up text before NLP processing."""
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(
        r"Read more.*",
        "",
        re.sub(r"\s+", " ", text.strip()),
        flags=re.IGNORECASE,
    )


def _is_valid_grammatical_sentence(doc):
    """Ensure the text is a complete sentence, not a fragment.

    Must have a Subject (nsubj) and a Root Verb.
    """
    has_subject = any(
        token.dep_ == "nsubj" or token.dep_ == "nsubjpass" for token in doc
    )
    has_verb = any(token.pos_ == "VERB" for token in doc)

    return not (not has_subject or not has_verb)


def _count_named_entities(doc):
    """Count distinct named entities (ORG, PERSON, GPE, etc.) in the doc."""
    valid_labels = {"ORG", "PERSON", "GPE", "EVENT", "LAW", "LOC"}
    seen = set()
    for ent in doc.ents:
        if ent.label_ in valid_labels:
            seen.add((ent.text, ent.label_))
    return len(seen)


def _contains_named_entity(doc):
    """Reject and or Accept a fact."""
    return _count_named_entities(doc) >= 1


def _compute_fragment_metadata(doc, raw_sent: str):
    """Heuristic fragment scoring with NO model calls beyond the provided doc.

    This is intentionally simple and deterministic:
    - Short sentences and lack of named entities are treated as more fragment-like.
    - Pronoun-leading sentences without obvious antecedent are suspicious.
    """
    text = (raw_sent or "").strip()
    if not text:
        return 1.0, "confirmed_fragment", "empty"

    words = text.split()
    word_count = len(words)
    lower = text.lower()
    score = 0.0
    reason_parts = []

    # Very short sentences are likely out of context.
    if word_count <= 8:
        score += 0.6
        reason_parts.append("short_sentence")
    elif word_count <= 12:
        score += 0.3
        reason_parts.append("moderately_short")

    # No named entities → more likely to be vague filler.
    if not _contains_named_entity(doc):
        score += 0.25
        reason_parts.append("no_named_entities")

    # Pronoun-leading sentences often rely heavily on previous context.
    pronoun_starts = (
        "he ",
        "she ",
        "they ",
        "it ",
        "this ",
        "that ",
        "these ",
        "those ",
    )
    if any(lower.startswith(p) for p in pronoun_starts):
        score += 0.25
        reason_parts.append("pronoun_start")

    # Odd punctuation or casing.
    if not text.endswith((".", "!", "?")):
        score += 0.15
        reason_parts.append("nonterminal_punctuation")
    if text and text[0].islower():
        score += 0.1
        reason_parts.append("lowercase_start")

    score = max(0.0, min(1.0, score))
    state = "suspected_fragment" if score >= 0.8 or score >= 0.5 else "unknown"
    reason = ",".join(reason_parts) if reason_parts else ""
    return score, state, reason


def _check_for_contradiction(new_doc, all_existing_facts):
    """Scan the ledger for direct contradictions.

    Logic: Same Subject + Same Verb + One is Negated ('not') vs One is Positive.
    """
    new_subj = next(
        (t.text.lower() for t in new_doc if "subj" in t.dep_),
        None,
    )
    new_root = next(
        (t.lemma_.lower() for t in new_doc if t.dep_ == "ROOT"),
        None,
    )
    new_is_negated = any(t.dep_ == "neg" for t in new_doc)

    if not new_subj or not new_root:
        return None

    for fact in all_existing_facts:
        if fact["status"] == "disputed":
            continue

        content = fact[
            "fact_content"
        ]  # NOTE: This is now the ZLIB compressed BLOB

        # DECOMPRESS BLOB FOR ANALYSIS
        try:
            decompressed_content = zlib.decompress(content).decode("utf-8")
        except Exception as e:
            logger.error(f"Decompression failed: {e}")
            # If decompression fails (e.g., checking an old/corrupt record), skip it.
            continue

        existing_doc = NLP_MODEL(decompressed_content)

        ex_subj = next(
            (t.text.lower() for t in existing_doc if "subj" in t.dep_),
            None,
        )
        ex_root = next(
            (t.lemma_.lower() for t in existing_doc if t.dep_ == "ROOT"),
            None,
        )
        ex_is_negated = any(t.dep_ == "neg" for t in existing_doc)

        if (
            new_subj == ex_subj
            and new_root == ex_root
            and new_is_negated != ex_is_negated
        ):
            return fact

    return None  # Added explicit return statement


def extract_facts_from_text(source_url, text_content):
    """Analyze and process text content to extract facts.

    1. Sanitize
    2. Split into sentences
    3. Filter for Grammar & Entities
    4. Check Ledger
    5. Save (Compressed BLOB + ADL Summary)
    """
    logger.info(
        f"\033[2m--- [The Crucible] Analyzing content from {source_url[:50]}... ---\033[0m"
    )

    text_content = _sanitize_text(text_content)
    doc = NLP_MODEL(text_content)

    all_facts_in_ledger = get_all_facts_for_analysis()
    newly_created_facts = []
    contradictions = 0

    for sent in doc.sents:
        raw_sent = sent.text.strip()

        if len(raw_sent) < 25 or len(raw_sent) > 400:
            continue

        if any(word in raw_sent.lower() for word in SUBJECTIVITY_INDICATORS):
            continue

        if raw_sent.lower().startswith(("i ", "we ", "my ", "our ")):
            continue

        sent_doc = NLP_MODEL(raw_sent)

        if not _is_valid_grammatical_sentence(sent_doc):
            continue

        # Require at least MIN_NAMED_ENTITIES so we avoid topic-less single-entity filler.
        if _count_named_entities(sent_doc) < MIN_NAMED_ENTITIES_FOR_FACT:
            continue

        conflicting_fact = _check_for_contradiction(
            sent_doc,
            all_facts_in_ledger,
        )
        if conflicting_fact:
            mark_facts_as_disputed(
                conflicting_fact["fact_id"],
                "new_hash_placeholder",
                raw_sent,
                source_url,
            )
            contradictions += 1
            continue

        domain = re.search(r"https?://(?:www\.)?([^/]+)", source_url).group(1)
        similar_fact = find_similar_fact_from_different_domain(
            raw_sent,
            domain,
            all_facts_in_ledger,
        )

        if similar_fact:
            update_fact_corroboration(similar_fact["fact_id"], source_url)
            continue

        fact_id = hashlib.sha256(raw_sent.encode("utf-8")).hexdigest()

        # --- GENERATE ADL & fragment metadata ---
        adl_summary = _generate_adl_summary(sent_doc)
        fragment_score, fragment_state, fragment_reason = (
            _compute_fragment_metadata(
                sent_doc,
                raw_sent,
            )
        )

        # --- CORRECTED: Call insert_uncorroborated_fact ONCE with all data ---
        result = insert_uncorroborated_fact(
            fact_id,
            raw_sent,
            source_url,
            adl_summary=adl_summary,  # <-- ADL is now correctly passed
            fragment_state=fragment_state,
            fragment_score=fragment_score,
            fragment_reason=fragment_reason,
        )

        if result:
            logger.info(
                f"[ADL TEMP] Generated ADL for new fact {fact_id[:8]}: {adl_summary}",
            )
            newly_created_facts.append(result)

    if contradictions > 0:
        logger.info(
            f"\033[94m[The Crucible] Analysis complete. Found {contradictions} contradictions.\033[0m",
        )

    if newly_created_facts:
        logger.info(
            f"[The Crucible] Created {len(newly_created_facts)} new facts.",
        )
    else:
        logger.info(
            "\033[90m[The Crucible] Analysis complete. No high-confidence facts extracted.\033[0m",
        )

    return newly_created_facts

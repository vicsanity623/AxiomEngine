# Axiom - crucible.py
# Copyright (C) 2025 The Axiom Contributors
# --- V3 STRICT GRAMMAR & ENTITY ENFORCEMENT ---

import re
import hashlib
import spacy
import logging
from axiom_model_loader import load_nlp_model
from ledger import (
    get_all_facts_for_analysis,
    mark_facts_as_disputed,
    find_similar_fact_from_different_domain,
    update_fact_corroboration,
    insert_uncorroborated_fact
)

logger = logging.getLogger(__name__)

NLP_MODEL = load_nlp_model()


SUBJECTIVITY_INDICATORS = {
    "believe", "think", "feel", "seems", "appears", "argues", "suggests",
    "contends", "opines", "speculates", "reckons", "estimates", "imagines",
    "hopefully", "unfortunately", "clearly", "obviously", "reportedly",
    "allegedly", "rumored", "likely", "probably", "possibly", "opinion",
    "view", "perspective", "stance", "take", "feels", "felt", "thought"
}

def _sanitize_text(text):
    """Basic cleanup before NLP processing."""
    if not text: return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"Read more.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _is_valid_grammatical_sentence(doc):
    """
    CRITICAL: Ensures the text is a complete sentence, not a fragment.
    Must have a Subject (nsubj) and a Root Verb.
    """
    has_subject = any(token.dep_ == "nsubj" or token.dep_ == "nsubjpass" for token in doc)
    has_verb = any(token.pos_ == "VERB" for token in doc)
    
    if not has_subject or not has_verb:
        return False
    return True

def _contains_named_entity(doc):
    """
    Quality Control: A 'Fact' is usually about specific entities.
    Reject sentences like "He went to the store" (Who is He?).
    Accept "Elon Musk went to the store."
    """
    valid_labels = {'ORG', 'PERSON', 'GPE', 'EVENT', 'LAW', 'LOC'}
    for ent in doc.ents:
        if ent.label_ in valid_labels:
            return True
    return False

def _check_for_contradiction(new_doc, all_existing_facts):
    """
    Scans the ledger for direct contradictions.
    Logic: Same Subject + Same Verb + One is Negated ('not') vs One is Positive.
    """
    new_subj = next((t.text.lower() for t in new_doc if "subj" in t.dep_), None)
    new_root = next((t.lemma_.lower() for t in new_doc if t.dep_ == "ROOT"), None)
    new_is_negated = any(t.dep_ == "neg" for t in new_doc)

    if not new_subj or not new_root: return None

    for fact in all_existing_facts:
        if fact['status'] == 'disputed': continue
        
        content = fact['fact_content']
        existing_doc = NLP_MODEL(content)
        
        ex_subj = next((t.text.lower() for t in existing_doc if "subj" in t.dep_), None)
        ex_root = next((t.lemma_.lower() for t in existing_doc if t.dep_ == "ROOT"), None)
        ex_is_negated = any(t.dep_ == "neg" for t in existing_doc)

        if new_subj == ex_subj and new_root == ex_root:
            if new_is_negated != ex_is_negated:
                return fact
                
    return None

def extract_facts_from_text(source_url, text_content):
    """
    Main processing pipeline.
    1. Sanitize
    2. Split into sentences
    3. Filter for Grammar & Entities
    4. Check Ledger
    5. Save
    """
    logger.info(f"\033[2m--- [The Crucible] Analyzing content from {source_url[:50]}... ---\033[0m")
    
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
            
        if not _contains_named_entity(sent_doc):
            continue

        conflicting_fact = _check_for_contradiction(sent_doc, all_facts_in_ledger)
        if conflicting_fact:
            mark_facts_as_disputed(
                conflicting_fact['fact_id'], 
                "new_hash_placeholder", 
                raw_sent, 
                source_url
            )
            contradictions += 1
            continue
            
        domain = re.search(r"https?://(?:www\.)?([^/]+)", source_url).group(1)
        similar_fact = find_similar_fact_from_different_domain(raw_sent, domain, all_facts_in_ledger)
        
        if similar_fact:
            update_fact_corroboration(similar_fact['fact_id'], source_url)
            continue
            
        fact_id = hashlib.sha256(raw_sent.encode('utf-8')).hexdigest()
        result = insert_uncorroborated_fact(fact_id, raw_sent, source_url)
        if result:
            newly_created_facts.append(result)

    if contradictions > 0:
        logger.info(f"\033[94m[The Crucible] Analysis complete. Found {contradictions} contradictions.\033[0m")
    
    if newly_created_facts:
        logger.info(f"\033[96m[The Crucible] Created {len(newly_created_facts)} new facts.\033[0m")
    else:
        logger.info(f"\033[90m[The Crucible] Analysis complete. No high-confidence facts extracted.\033[0m")
        
    return newly_created_facts
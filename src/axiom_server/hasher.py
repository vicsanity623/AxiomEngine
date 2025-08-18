"""Hasher - Fact hash tools."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import or_

from axiom_server.common import NLP_MODEL  # We are using the LARGE model here!
from axiom_server.ledger import Fact

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Use the same logger as other parts of the application for consistency
logger = logging.getLogger("axiom-node.hasher")


def _extract_keywords(query_text: str, max_keywords: int = 5) -> list[str]:
    """Return the most important keywords (nouns and proper nouns) from a query."""
    # Process the query with our powerful NLP model
    doc = NLP_MODEL(query_text.lower())

    keywords = []
    # We prioritize proper nouns (like "Trump", "SpaceX") and regular nouns.
    # We ignore stopwords (like "the", "a", "for") and punctuation.
    for token in doc:
        if (
            not token.is_stop
            and not token.is_punct
            and token.pos_ in ["PROPN", "NOUN"]
        ):
            keywords.append(token.lemma_)  # Use the base form of the word

    # Return the most important (first occurring) keywords up to the max limit
    return keywords[:max_keywords]


class FactIndexer:
    """A class to hold our indexed data and provide search capabilities."""

    def __init__(self, session: Session) -> None:
        """Initialize the indexer with a database session."""
        self.session = session
        self.fact_id_to_content: dict[int, str] = {}
        # --- NEW: Store sources for quick lookups ---
        self.fact_id_to_sources: dict[int, list[str]] = {}
        self.fact_id_to_vector = {}
        self.vector_matrix = None
        self.fact_ids: list[int] = []

    def add_fact(self, fact: Fact):
        """Add a single, new fact to the live index in memory."""
        self.add_facts([fact])

    def add_facts(self, facts_to_add: list[Fact]):
        """Add a list of new Fact objects to the live in-memory search index."""
        if not facts_to_add:
            return
        new_facts = [fact for fact in facts_to_add if fact.id not in self.fact_ids]
        if not new_facts:
            logger.info("All provided facts are already indexed. Skipping.")
            return

        new_contents = [fact.content for fact in new_facts]
        new_vectors = [NLP_MODEL(content).vector for content in new_contents]

        for i, fact in enumerate(new_facts):
            self.fact_id_to_content[fact.id] = new_contents[i]
            self.fact_id_to_vector[fact.id] = new_vectors[i]
            # --- NEW: Also index the sources ---
            self.fact_id_to_sources[fact.id] = [source.domain for source in fact.sources]
            self.fact_ids.append(fact.id)

        new_vectors_matrix = np.vstack(new_vectors)
        if self.vector_matrix is None:
            self.vector_matrix = new_vectors_matrix
        else:
            self.vector_matrix = np.vstack([self.vector_matrix, new_vectors_matrix])
        logger.info(f"Successfully added {len(new_facts)} new facts to the search index.")

    def index_facts_from_db(self) -> None:
        """Read all non-disputed facts from the database and builds the index."""
        logger.info("Starting to index facts from the ledger...")
        # Use eager loading to fetch facts and their sources in one efficient query
        from sqlalchemy.orm import joinedload
        facts_to_index = (
            self.session.query(Fact)
            .options(joinedload(Fact.sources))
            .filter(Fact.disputed == False).all()
        )
        if not facts_to_index:
            logger.warning("No facts found in the database to index.")
            return
        self.add_facts(facts_to_index)
        logger.info(f"Initial indexing complete. {len(self.fact_ids)} facts are now searchable.")

    def find_closest_facts(self, query_text: str, top_n: int = 3) -> list[dict]:
        """Perform a HYBRID search with a full semantic fallback."""
        if self.vector_matrix is None or len(self.fact_ids) == 0:
            logger.warning("Fact index is not available. Cannot perform search.")
            return []

        keywords = _extract_keywords(query_text)
        candidate_indices = list(range(len(self.fact_ids))) # Default to all facts
        
        if keywords:
            logger.info(f"Extracted keywords for pre-filtering: {keywords}")
            keyword_filters = [Fact.content.ilike(f"%{key}%") for key in keywords]
            pre_filtered_facts = (
                self.session.query(Fact.id).filter(or_(*keyword_filters)).filter(Fact.disputed == False).all()
            )
            candidate_ids = {fact_id for fact_id, in pre_filtered_facts}
            
            if candidate_ids:
                logger.info(f"Pre-filtering found {len(candidate_ids)} candidate facts.")
                candidate_indices = [i for i, fact_id in enumerate(self.fact_ids) if fact_id in candidate_ids]
            else:
                logger.warning("Keyword pre-filter found no candidates. Falling back to full semantic search.")
        
        if not candidate_indices:
            return []

        candidate_matrix = self.vector_matrix[candidate_indices, :]
        query_vector = NLP_MODEL(query_text).vector.reshape(1, -1)
        
        from sklearn.metrics.pairwise import cosine_similarity
        similarities = cosine_similarity(query_vector, candidate_matrix)[0]
        
        top_candidate_indices = np.argsort(similarities)[-top_n:][::-1]

        results = []
        for i in top_candidate_indices:
            if i >= len(similarities): continue
            similarity_score = similarities[i]
            if similarity_score < 0.3: continue
                
            original_index = candidate_indices[i]
            fact_id = self.fact_ids[original_index]

            # --- MODIFIED: Include the sources in the response ---
            results.append({
                "content": self.fact_id_to_content[fact_id],
                "similarity": float(similarity_score),
                "fact_id": fact_id,
                "sources": self.fact_id_to_sources.get(fact_id, []) # Safely get sources
            })
        return results
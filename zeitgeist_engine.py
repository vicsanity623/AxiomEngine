# Axiom - zeitgeist_engine.py
# Copyright (C) 2025 The Axiom Contributors
# --- V3.1: IMPROVED ENTITY RECOGNITION & FILTERING ---

import feedparser
import spacy
import logging
from collections import Counter
from axiom_model_loader import load_nlp_model

logger = logging.getLogger(__name__)



NLP_MODEL = load_nlp_model()

RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://rss.cnn.com/rss/edition.rss",
    "https://www.politico.com/rss/morning-economy.xml",
    "https://www.reutersagency.com/feed/",
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "https://www.wired.com/feed/rss",
]

# Blacklist of generic terms that are technically entities but boring topics
IGNORED_ENTITIES = {
    "the", "a", "an", "today", "yesterday", "tomorrow", "monday", "tuesday", 
    "wednesday", "thursday", "friday", "saturday", "sunday", "january", 
    "february", "march", "april", "may", "june", "july", "august", "september", 
    "october", "november", "december", "year", "years", "week", "weeks", 
    "day", "days", "morning", "night", "new york times", "bbc", "reuters", 
    "cnn", "npr", "ap", "press", "associated press", "bloomberg", "image", "photo"
}

def get_trending_topics(top_n=5):
    """
    Identifies trending topics using Named Entity Recognition (NER) on RSS headlines.
    Filters out noise to find substantial subjects.
    """
    
    all_entities = []

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo: continue

            # Scan headlines
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                if not title: continue
                
                doc = NLP_MODEL(title)
                
                for ent in doc.ents:
                    text = ent.text.strip()
                    lower_text = text.lower()
                    
                    # 1. Filter by Entity Label (We want People, Orgs, Countries, Events)
                    if ent.label_ not in ("ORG", "PERSON", "GPE", "EVENT", "WORK_OF_ART", "PRODUCT"):
                        continue
                        
                    # 2. Filter Junk
                    if lower_text in IGNORED_ENTITIES: continue
                    if len(text) < 3: continue # Skip "AI", "US", "UK" (too broad sometimes) or "He"
                    if text.isdigit(): continue
                    
                    # 3. Clean possessives (e.g., "Trump's" -> "Trump")
                    if text.endswith("'s"):
                        text = text[:-2]

                    all_entities.append(text)
                    
        except Exception:
            continue

    if not all_entities:
        logger.info("[Zeitgeist] No significant topics found. Defaulting to standard watch list.")
        return ["Artificial Intelligence", "Economy", "SpaceX", "Crypto", "Climate"]

    # Count frequency
    topic_counts = Counter(all_entities)
    
    # Get top 15 most common, then slice
    common = topic_counts.most_common(15)
    
    # Extract just the names
    final_topics = [t[0] for t in common]
    
    # Remove duplicates preserving order (incase cleanup made "Trump's" and "Trump" same)
    seen = set()
    unique_topics = []
    for t in final_topics:
        if t.lower() not in seen:
            unique_topics.append(t)
            seen.add(t.lower())
            
    # Return requested amount
    result = unique_topics[:top_n]
    
    logger.info(f"\033[96m [Zeitgeist Engine] Top topics discovered: {result}\033[0m")
    return result
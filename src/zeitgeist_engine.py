"""Configure and set parser."""

import logging
from collections import Counter

import feedparser

from src.axiom_model_loader import load_nlp_model

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

IGNORED_ENTITIES = {
    "the",
    "a",
    "an",
    "today",
    "yesterday",
    "tomorrow",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "year",
    "years",
    "week",
    "weeks",
    "day",
    "days",
    "morning",
    "night",
    "new york times",
    "bbc",
    "reuters",
    "cnn",
    "npr",
    "ap",
    "press",
    "associated press",
    "bloomberg",
    "image",
    "photo",
}


def get_trending_topics(top_n=100):
    """Identify trending topics using Named Entity Recognition (NER) on RSS headlines.

    Filter out noise to find substantial subjects.
    """
    all_entities = []

    default_watch_list = [
        "Artificial Intelligence",
        "Economy",
        "SpaceX",
        "Crypto",
        "Climate",
        "US Politics",
        "Global Conflict",
    ]

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo:
                continue

            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                if not title:
                    continue

                doc = NLP_MODEL(title)

                for ent in doc.ents:
                    text = ent.text.strip()
                    lower_text = text.lower()

                    if ent.label_ not in (
                        "ORG",
                        "PERSON",
                        "GPE",
                        "EVENT",
                        "WORK_OF_ART",
                        "PRODUCT",
                    ):
                        continue

                    if lower_text in IGNORED_ENTITIES:
                        continue
                    if len(text) < 3:
                        continue
                    if text.isdigit():
                        continue

                    text = text.removesuffix("'s")

                    all_entities.append(text)

        except Exception as e:
            logger.debug(f"[Zeitgeist] Failed to process feed {feed_url}: {e}")
            continue

    if not all_entities:
        logger.info(
            "[Zeitgeist] No substantial topics found via NER. Defaulting to standard watch list.",
        )
        return default_watch_list[:top_n]

    topic_counts = Counter(all_entities)

    common = topic_counts.most_common(15)

    final_topics = [t[0] for t in common]

    seen = set()
    unique_topics = []
    for t in final_topics:
        if t.lower() not in seen:
            unique_topics.append(t)
            seen.add(t.lower())

    result = unique_topics[:top_n]

    if len(result) < top_n:
        for default_topic in default_watch_list:
            if (
                default_topic not in result
                and default_topic not in unique_topics
            ):
                result.append(default_topic)
                if len(result) >= top_n:
                    break

    logger.info(f"Top topics created: {result}\033[0m")
    return result

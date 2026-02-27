"""Contain and configure utility functions for extracting content from various sources."""

import logging
from datetime import datetime

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

RSS_SOURCES = [
    "http://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.npr.org/1001/rss.xml",
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://rss.cnn.com/rss/edition.rss",
    "https://www.politico.com/rss/morning-economy.xml",
    "https://www.sciencedaily.com/rss/top/science.xml",
    "https://feeds.bloomberg.com/markets/news.rss",
    "https://www.reutersagency.com/feed/",
    "https://www.wired.com/feed/rss",
    "https://www.theguardian.com/world/rss",
]


class ContentSanitizer:
    """Define the class for cleanup."""

    @staticmethod
    def is_valid_sentence(text):
        """Check the sentence structure."""
        text = text.strip()
        if len(text) < 45 or len(text) > 500:
            return False
        garbage = [
            "read more",
            "subscribe",
            "cookie",
            "javascript",
            "click here",
            "follow us",
        ]
        if any(g in text.lower() for g in garbage):
            return False
        return not (text[0].isupper() and text[-1] in '.!?"')

    @staticmethod
    def clean_text_block(raw_text, topic):
        """Clean the block of text for sentence cleanup."""
        if not raw_text:
            return ""
        clean_paragraphs = []
        topic_lower = topic.lower()
        topic_parts = topic_lower.split()
        paragraphs = raw_text.split("\n")

        for p in paragraphs:
            p = p.strip()
            if not ContentSanitizer.is_valid_sentence(p):
                continue

            if topic_lower in p.lower() or any(
                w in p.lower() for w in topic_parts if len(w) > 3
            ):
                clean_paragraphs.append(p)

        return "\n\n".join(clean_paragraphs)


def _manual_bs4_extraction(html):
    """Fallback to the extractor using BeautifulSoup.

    Use if Trafilatura fails (common in standalone builds).
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup(["script", "style", "nav", "footer", "header"]):
        script.decompose()

    paragraphs = [p.get_text() for p in soup.find_all("p")]
    return "\n".join(paragraphs)


def _fetch_article_text(url, timeout=12):
    """Fetch article text with a robust fallback for standalone builds."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://www.google.com/",
        }

        resp = requests.get(
            url,
            timeout=timeout,
            headers=headers,
            allow_redirects=True,
        )
        resp.raise_for_status()
        html_content = resp.text

        try:
            text = trafilatura.extract(
                html_content,
                include_comments=False,
                favor_precision=True,
            )
            if text and len(text) > 200:
                return text
        except Exception as e:
            logger.debug(f"Trafilatura failed in standalone mode: {e}")

        return _manual_bs4_extraction(html_content)

    except Exception as e:
        logger.debug(f"Fetch failed for {url}: {e}")
        return None


def find_and_extract(topic, max_sources=3):
    """Navigate source feed to identify extract points."""
    logger.info(
        f"\033[2m--- [Pathfinder] Seeking sources for '{topic}'... ---\033[0m",
    )

    extracted_content = []
    seen_urls = set()
    topic_keywords = set(topic.lower().split())

    for feed_url in RSS_SOURCES:
        if len(extracted_content) >= max_sources:
            break

        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                if len(extracted_content) >= max_sources:
                    break

                link = entry.get("link")
                if not link or link in seen_urls:
                    continue

                title = entry.get("title", "")
                summary = entry.get("summary", "")
                combined_meta = (title + " " + summary).lower()

                if topic.lower() in combined_meta or any(
                    k in combined_meta for k in topic_keywords if len(k) > 3
                ):
                    seen_urls.add(link)

                    entry_time = None
                    if (
                        hasattr(entry, "published_parsed")
                        and entry.published_parsed
                    ):
                        entry_time = datetime(*entry.published_parsed[:6])

                    full_text = _fetch_article_text(link)

                    if full_text:
                        relevant_text = ContentSanitizer.clean_text_block(
                            full_text,
                            topic,
                        )
                        if relevant_text and len(relevant_text) > 100:
                            logger.info(
                                f"\033[92m  -> Matched + Verified: {link[:60]}...\033[0m",
                            )
                            data = {
                                "source_url": link,
                                "content": relevant_text,
                            }
                            if entry_time:
                                data["timestamp"] = entry_time
                            extracted_content.append(data)
                            continue

                    if summary:
                        clean_summary = BeautifulSoup(
                            summary,
                            "html.parser",
                        ).get_text()
                        if ContentSanitizer.is_valid_sentence(clean_summary):
                            logger.info(
                                f"\033[92m  -> Matched (RSS Summary): {link[:60]}...\033[0m",
                            )
                            data = {
                                "source_url": link,
                                "content": clean_summary,
                            }
                            if entry_time:
                                data["timestamp"] = entry_time
                            extracted_content.append(data)

        except Exception as e:
            logger.error(f"An error occurred: {e}")
            continue

    logger.info(f"Success. Found {len(extracted_content)} valid sources.")
    return extracted_content

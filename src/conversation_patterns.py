"""Define and match conversational patterns for the Axiom engine.

This module provides rule-based pattern matching for interpreting user queries
and generating appropriate responses. It supports slot-based templates, regex
compilation, and scoring heuristics to determine the best response for a given input.
"""

import re
from dataclasses import dataclass


def _normalize(text: str) -> str:
    """Lowercase and collapse internal whitespace for matching."""
    return " ".join((text or "").strip().lower().split())


@dataclass
class ConversationPattern:
    """Lightweight, rule-based pattern for fast command → response matching."""

    raw_template: str
    response: str
    weight: float = 1.0
    # Compiled at idle time
    regex: re.Pattern | None = None

    def compile(self) -> None:
        """Compile the raw_template into a regex.

        Supported syntax:
        - `<slot>` becomes a non-greedy capture group `(?P<slot>.+?)`.
        - Literal text is escaped.
        """
        pattern = self.raw_template
        tokens: list[str] = []
        i = 0
        while i < len(pattern):
            if pattern[i] == "<":
                j = pattern.find(">", i + 1)
                if j == -1:
                    # Treat as literal
                    tokens.append(re.escape(pattern[i:]))
                    break
                slot_name = pattern[i + 1 : j].strip() or "slot"
                tokens.append(f"(?P<{slot_name}>.+?)")
                i = j + 1
            else:
                tokens.append(re.escape(pattern[i]))
                i += 1

        # Normalize spaces: allow any whitespace between tokens.
        joined = "".join(tokens)
        joined = re.sub(r"\\ ", r"\\s+", joined)
        self.regex = re.compile(rf"^{joined}$", re.IGNORECASE)


def seed_patterns() -> list[ConversationPattern]:
    """Initialize ledger-independent patterns and responses."""
    return [
        ConversationPattern(
            raw_template="help",
            response="I am Axiom. Ask me to explain internal engines, fetch knowledge, or reason about topics. Try: 'explain the crucible' or 'what is the lexical mesh'.",
            weight=1.5,
        ),
        ConversationPattern(
            raw_template="what can you do",
            response="I continuously ingest news, extract facts, link them into a knowledge graph, and reason about them. You can ask about current events or my internal systems.",
            weight=1.5,
        ),
        ConversationPattern(
            raw_template="how do I use axiom",
            response="Use /think or the chat UI to ask questions in plain language. You can query topics, compare entities, or ask how my subsystems like the Crucible or Lexical Mesh work.",
            weight=1.5,
        ),
        ConversationPattern(
            raw_template="explain the crucible",
            response="The Crucible ingests raw text, extracts structured atomic facts (ADL triplets), and feeds them into the ledger and mesh for reasoning.",
            weight=2.0,
        ),
        ConversationPattern(
            raw_template="what is the lexical mesh",
            response="The Lexical Mesh is a semantic layer built from facts, turning text into synapses that allow fast similarity and association queries.",
            weight=2.0,
        ),
        ConversationPattern(
            raw_template="what is axiom",
            response="Axiom is an always-on knowledge engine that continuously ingests, structures, and reasons about information instead of passively waiting for prompts.",
            weight=2.0,
        ),
        ConversationPattern(
            raw_template="who are you",
            response="I am the Axiom Engine node you are connected to. I build and maintain a knowledge ledger and respond based on that evolving state.",
            weight=1.2,
        ),
        ConversationPattern(
            raw_template="what is <topic>",
            response="You asked for a definition of '<topic>'. I may use my internal knowledge ledger for details, but I can already recognize this as a definition-style request.",
            weight=1.0,
        ),
        ConversationPattern(
            raw_template="tell me about <topic>",
            response="You want a high-level overview of '<topic>'. I can respond using my current knowledge and ongoing ingestion cycles.",
            weight=1.0,
        ),
        ConversationPattern(
            raw_template="how does <system> work",
            response="You are asking how '<system>' operates. I can describe its components and how they interact based on what I know.",
            weight=1.0,
        ),
        # Meta / introspection commands (these may be overridden by macros).
        ConversationPattern(
            raw_template="axiom: status",
            response="Reporting my current internal health and ledger status.",
            weight=2.0,
        ),
        ConversationPattern(
            raw_template="show health",
            response="Summarizing my current system and ledger health.",
            weight=1.5,
        ),
        ConversationPattern(
            raw_template="axiom: map",
            response="Describing my core modules and subsystems.",
            weight=1.5,
        ),
        ConversationPattern(
            raw_template="list modules",
            response="Listing key modules and subsystems that make up Axiom.",
            weight=1.5,
        ),
        ConversationPattern(
            raw_template="show endpoints",
            response="Listing HTTP endpoints I currently expose.",
            weight=1.5,
        ),
    ]


def compile_patterns(patterns: list[ConversationPattern]) -> None:
    """Compile regex for each pattern in-place."""
    for p in patterns:
        p.compile()


def match_query(
    query: str,
    patterns: list[ConversationPattern],
    min_score: float = 0.6,
) -> tuple[bool, str]:
    """Try to match query against known patterns.

    Scoring heuristic (simple, deterministic, non-ML):
    - Exact normalized string match: score = 1.0 * weight
    - Regex full match: score = 0.8 * weight
    - Normalized contains pattern literal (no slots): score = 0.7 * weight
    """
    q_norm = _normalize(query)
    if not q_norm or not patterns:
        return False, ""

    best_score = 0.0
    best_response = ""

    for p in patterns:
        base = p.weight or 1.0
        template_norm = _normalize(p.raw_template)

        # Exact match on normalized text.
        if q_norm == template_norm:
            score = 1.0 * base
            if score > best_score:
                best_score = score
                best_response = p.response
            continue

        # Regex match (supports slots).
        if p.regex is not None and p.regex.match(query):
            score = 0.8 * base
            if score > best_score:
                best_score = score
                best_response = p.response
            continue

        # Simple containment only for non-slot templates.
        if (
            "<" not in p.raw_template
            and template_norm
            and template_norm in q_norm
        ):
            score = 0.7 * base
            if score > best_score:
                best_score = score
                best_response = p.response

    if best_score >= min_score:
        return True, best_response
    return False, ""

"""Common - Shared data."""

from __future__ import annotations

# Axiom - common.py
# Copyright (C) 2025 The Axiom Contributors
# This program is licensed under the Peer Production License (PPL).
# See the LICENSE file for full details.
from typing import Final

import spacy

# It's good practice to disable components you don't need for a speed boost.
# If you are only using the tagger, parser, and NER, you can disable the rest.
NLP_MODEL = spacy.load("en_core_web_lg", disable=["lemmatizer", "attribute_ruler"])


# --- ENHANCED: Sophisticated Subjectivity & Non-Fact Indicators ---
# Expanded with 150+ additional opinion markers, hedges, and promotional language
# Maintains careful categorization for accurate filtering

SUBJECTIVITY_INDICATORS: Final[frozenset[str]] = frozenset({
    # --- Category 1: Direct Opinions & Beliefs (Expanded) ---
    "believe", "think", "feel", "suspect", "assume", "presume", "conclude",
    "i feel", "we feel", "i believe", "we believe", "i think", "we think",
    "in my opinion", "in our view", "from our perspective", "our view is", 
    "personally", "to me", "for me", "in my view", "as i see it", "it seems to me",
    "my impression is", "we maintain", "i contend", "i argue", "i'd say", "we'd argue",
    "my belief is", "we hold", "i consider", "in our judgement", "from my standpoint",
    
    # --- Category 2: Hedges & Speculation (Enhanced) ---
    "seems", "appears", "suggests", "indicates", "implies", "hints", "speculates", 
    "likely", "unlikely", "probably", "possibly", "maybe", "perhaps", "conceivably",
    "arguably", "potentially", "supposedly", "ostensibly", "reportedly", "apparently",
    "could be", "might be", "may be", "can be", "seemingly", "looks like", "gives the impression",
    "somewhat", "sort of", "kind of", "more or less", "essentially", "virtually", "practically",
    "almost", "nearly", "roughly", "approximately", "about", "in a sense", "to some extent",
    
    # --- Category 3: Adverbs of Judgment & Emphasis (Extended) ---
    "unfortunately", "fortunately", "luckily", "tragically", "sadly", "disappointingly",
    "regrettably", "annoyingly", "frustratingly", "alarmingly", "disturbingly", "shockingly",
    "thankfully", "hopefully", "ideally", "mercifully", "happily", "joyfully", "pleasingly",
    "remarkably", "surprisingly", "astonishingly", "amazingly", "incredibly", "unbelievably",
    "notably", "significantly", "crucially", "vitally", "particularly", "especially", "exceptionally",
    "importantly", "interestingly", "curiously", "strangely", "oddly", "noteworthy",
    "clearly", "obviously", "plainly", "evidently", "manifestly", "patently", "undeniably",
    "undoubtedly", "unquestionably", "indisputably", "absolutely", "definitely", "certainly",
    "positively", "simply", "just", "really", "very", "extremely", "utterly", "completely",
    
    # --- Category 4: Unverified Claims & Allegations (Augmented) ---
    "allegedly", "purportedly", "supposedly", "ostensibly", "reportedly", "rumored", 
    "according to sources", "sources say", "insiders claim", "hearsay suggests",
    "anonymously reported", "widely believed", "commonly thought", "generally considered",
    "it is said", "it is claimed", "it is reported", "it is suggested", "it has been floated",
    "claims", "contends", "asserts", "declares", "proposes", "insists", "implies", "hints",
    "as per rumors", "word is", "buzz is", "scuttlebutt is", "the talk is", "gossip has it",
    
    # --- Category 5: Meta-Commentary (Expanded) ---
    "this article", "this report", "this piece", "this content", "this writing",
    "we explore", "we examine", "we investigate", "we analyze", "we discuss", 
    "we consider", "we highlight", "we feature", "we present", "we share", 
    "our list", "our survey", "our rankings", "our selection", "our picks", 
    "as you read", "as you see", "as you notice", "as you may know", "as you might expect",
    "in this section", "in this part", "throughout this", "below we", "above we",
    "what follows", "to illustrate", "to demonstrate", "for example", "for instance",
    "we included", "we chose", "we selected", "we recommend", "we suggest",
    "look no further", "let's examine", "let's consider", "let's turn to", "let's discuss",
    "note that", "remember that", "keep in mind", "it's worth noting", "it's important to see",
    
    # --- Category 6: Vague Generalizations & Platitudes (Broadened) ---
    "in today's world", "in modern society", "in this day and age", "now more than ever",
    "time and again", "as always", "invariably", "without exception", "without fail",
    "it goes without saying", "needless to say", "it is important to note", "it is critical to understand",
    "history shows", "experience teaches", "common wisdom holds", "conventional wisdom says",
    "by all accounts", "by any measure", "by any standard", "in many ways", "in most cases",
    "the fact remains", "the reality is", "truth be told", "if we're being honest", "frankly speaking",
    "at its core", "fundamentally", "essentially", "basically", "ultimately", 
    "when all is said and done", "in the final analysis", "in the grand scheme", "in the big picture",
    
    # --- Category 7: Promotional & "Puff" Language (Amplified) ---
    "game-changer", "paradigm-shift", "industry-disrupting", "market-leading", 
    "world-class", "best-in-class", "top-tier", "gold-standard", "award-winning", 
    "revolutionary", "innovative", "groundbreaking", "trailblazing", "pioneering",
    "state-of-the-art", "cutting-edge", "bleeding-edge", "next-generation", 
    "breathtaking", "stunning", "astonishing", "mind-blowing", "jaw-dropping",
    "unforgettable", "life-changing", "transformative", "eye-opening", "phenomenal",
    "must-see", "must-have", "essential", "indispensable", "critical", "vital",
    "superb", "exceptional", "outstanding", "magnificent", "splendid", "peerless",
    "highly recommended", "universally acclaimed", "widely praised", "rave reviews",
    
    # --- Category 8: Logical Conclusions & Inferences (Extended) ---
    "therefore", "thus", "hence", "consequently", "accordingly", 
    "as a result", "for this reason", "because of this", "due to this",
    "which means", "which suggests", "which implies", "which indicates",
    "it follows that", "this leads to", "points to", "argues for",
    "in conclusion", "to conclude", "in summary", "to summarize", 
    "in essence", "in short", "in brief", "overall", "all things considered",
    "so", "then", "ergo", "wherefore", "that being the case",
})
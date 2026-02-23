# ◈ Synapse Weighting: Axiom's Deterministic Reasoning ◈

This document explains the foundational principle of the **Lexical Mesh**—how Axiom forms conclusions and understands context without relying on probabilistic Large Language Models (LLMs).

---

## 1. The Problem with Probabilistic Models

Traditional LLMs operate on statistical probability. When you ask a question, the model predicts the most likely next word based on patterns learned from trillions of tokens, leading to **hallucinations** (confidently stated falsehoods) when patterns are weak or absent.

Axiom replaces this with **Symbolic Grounding**: Reasoning based on what is **verified** and **structurally repeated** in the Ledger.

---

## 2. The Lexical Mesh Components

Axiom’s "thinking" is built from two primary database structures created during the **Reflection State**:

### A. Atoms (The Lexicon Table)
This is Axiom’s growing dictionary. Every unique word found in a verified fact is stored as an **Atom**.
*   **Attributes:** `word`, `pos_tag` (Part of Speech: NOUN, VERB, etc.), and `occurrence_count`.
*   **Function:** Atoms gain mass as they are encountered, giving the system a semantic fingerprint of the entire knowledge domain.

### B. Synapses (The Neural Pathways)
This is the true "brain." A Synapse is a directional or relational link formed between two Atoms based on the grammar of the sentence where they appeared together.

*   **Attributes:** `word_a`, `word_b`, `relation_type` (the dependency tag from spaCy), and `strength` (the accumulated count of co-occurrences).
*   **The Strength Metric:** This is the core of our deterministic reasoning. **Strength is not a probability; it is a direct count of observed connection instances.**

---

## 3. Deterministic Reasoning via Synapse Traversal

When the Inference Engine receives a query, it doesn't guess the answer. It **navigates a path** between the query's core concepts using the strongest Synapses.

### The Weighting Process:
The strength of a connection is determined by two factors:

1.  **Grammatical Proximity (The Structure):**
    *   Synapses created by **Subject-Verb-Object** structures (e.g., `Trump (nsubj) -> said (ROOT)`) are considered highly reliable structural links.
    *   Synapses created by simple **Adjective-Noun** modifiers are also strong.

2.  **Conceptual Overlap (The Context):**
    *   If two facts share multiple high-weighted concepts (like "Trump," "Tariff," and "Court"), the system creates a **`shared_context`** synapse between the concepts themselves. This connection gains massive strength because multiple independent facts point to the same conceptual nexus.

### The Inference Path Example:
If the user queries for `"US Policy"`, Axiom traces the path:
$$\text{Query Atoms} \rightarrow \text{Strongest Synapses} \rightarrow \text{Verified Facts}$$

1.  Axiom sees "Policy" is heavily connected to "Tariff" (high strength).
2.  It follows the "Tariff" atom to a high-strength synapse pointing to "Trump."
3.  The **Inference Engine** reports the **Fact** associated with that path.

### Security Implication: Immunity to Manipulation
Because all connections must be justified by a **count** derived from a **verified fact**, the system cannot be manipulated by inserting statistical noise (as LLMs are). To change Axiom's "mind," one must inject **new, verified, corroborated facts** into the Ledger that contradict the existing Synapse weights.

---

## ◈ Future Development: The Brain's Evolution

As the network gathers more data, the `occurrence_count` increases, and the Synapse `strength` grows, allowing for increasingly complex and nuanced deterministic reasoning without ever needing a single neural network weight file.
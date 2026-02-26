# Axiom Web Interface — User Guide

This guide explains how to use the **AXIOM** web interface (`index.html`) to query the decentralized knowledge ledger and inspect results.

---

## 1. Overview

The page is a single **AXIOM AGENT** window that combines:

- **Console** — Command-style input and Axiom’s spoken/written answers.
- **Knowledge Canvas** — Ledger results and Lexical Mesh for the query concept.
- **Filters** — Limit, exact match, and uncorroborated-inclusion options.

All of this appears in one continuous panel with a cyberpunk/terminal theme.

---

## 2. Connecting to a Node

- **Default:** The page connects to `http://127.0.0.1:8009` (local node). If you open the page from a different host (e.g. GitHub Pages), it may use a different default (e.g. bootstrap URL).
- **To switch node:** In the input line, type:
  ```text
  connect https://your-node-url.example.com
  ```
  or `connect http://127.0.0.1:8010` for another local port. The header updates to show the active connection.
- **HTTPS:** If the page is served over HTTPS, use `connect https://...`; browsers block mixed content (HTTP from HTTPS).

---

## 3. Asking a Question (Chat)

- Type any question or topic in the **USER@AXIOM:~$** field (e.g. `epstein files`, `economy`, `what is the lexical mesh`).
- Press **Enter** or click **EXECUTE**.
- **AXIOM >>** shows the node’s answer in the console. The answer is **not** read aloud by default; see **Voice** below.

---

## 4. Knowledge Canvas (Ledger + Mesh)

After each query, two panels update using a **concept** extracted from your query (e.g. “trump” from “think trump”):

- **// LEDGER_RESULTS**  
  Matching facts from the node’s ledger: status, trust score, fragment flags, **timestamp line** (e.g. “On Sunday, Sep 15, 2026 it was verified that…”), fact text, and source URL.  
  Source links can go dead; the **timestamp** is the stable fact-check reference.

- **// LEXICAL_MESH**  
  Concepts linked to the query term in Axiom’s brain (word relations and strengths).

**Filters (above the panels):**

- **LIMIT** — Max number of facts to show (10 / 20 / 50).
- **EXACT_MATCH** — Only show facts whose text contains the concept exactly (substring).
- **INCLUDE_UNCORROBORATED** — Include uncorroborated facts; uncheck to see only trusted (and disputed, if any).

---

## 5. Voice (Speech Synthesis)

- **Default:** Voice is **off** (muted) when the page first loads. No automatic reading.
- **Toggle:** Click **MUTE [OFF]** to turn voice **on** (button becomes **MUTE [ON]** and cyan). Click again to mute.
- Your choice is remembered for the session (localStorage).

---

## 6. Fact-Check Timestamps

Each fact card shows a **timestamp line** so you can cite when a claim was recorded, even if the source URL later 404s:

- **Trusted:**  
  *“On [Weekday], [Mon], [DD], [YYYY] it was verified that…”*
- **Uncorroborated:**  
  *“As of [Weekday], [Mon], [DD], [YYYY] uncorroborated claims state that…”*
- **Disputed:**  
  *“As of [Weekday], [Mon], [DD], [YYYY] disputed claims state that…”*

The date comes from the fact’s `ingest_timestamp_utc` stored on the node.

---

## 7. Quick Reference

| Action              | How |
|---------------------|-----|
| Query the ledger    | Type a question, press Enter or EXECUTE. |
| Change node         | `connect https://…` or `connect http://…` |
| Toggle voice        | Click MUTE [OFF] / MUTE [ON]. |
| More/fewer facts    | Change LIMIT (10 / 20 / 50). |
| Stricter matches    | Check EXACT_MATCH. |
| Hide uncorroborated | Uncheck INCLUDE_UNCORROBORATED. |

---

*AXIOM // Decentralized Knowledge Ledger // Open Source (PPL)*

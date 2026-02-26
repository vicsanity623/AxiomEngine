# Metacognitive Engine

## What it does

The **metacognitive engine** runs periodic “meta” checks on the Lexical Mesh and fact ledger. It does **not** process new content; it reviews **existing** data for long-term health and storage efficiency.

### 1. `run_metacognitive_cycle()`

Entry point used by the node. It:

1. **Runs the integrity/prune check** (`prune_integrity_check()`).
2. **Logs** that synapse weight refinement has been “initiated” (actual re-weighting is not implemented yet).

### 2. `prune_integrity_check()`

**Goal:** Remove facts that are both **old** and **low quality or confirmed fragments** so the ledger doesn’t grow without bound with weak data.

**Logic:**

- Selects facts that are:
  - **Older than 90 days** (`ingest_timestamp_utc < cutoff`), and  
  - **Low trust** (`trust_score <= 2`).
- For each such fact:
  - If **ADL summary is too short** (length &lt; 10), **or**
  - If its `fragment_state` is **`confirmed_fragment`**  
    → **DELETE** the fact (considered low-integrity, stale, or a confirmed fragment).
  - Otherwise: keep it (no delete).

**Constants (in code):**

- `PRUNE_THRESHOLD_DAYS = 90` — only consider facts older than this.
- `TRUST_SCORE_FOR_PRUNING = 2` — only consider facts with `trust_score <= 2`.
- `ADL_INTEGRITY_THRESHOLD = 10` — delete only if `len(adl_summary) < 10` **or** confirmed fragment.

So in practice it **deletes** old, low-trust facts that either have a very short (or empty) ADL summary or have been promoted to `confirmed_fragment` by the fragment analysis pipeline.

### 3. `retrieve_adl_based_answer(query_atoms)` (placeholder)

Reserved for future “ADL-driven” inference (querying by ADL/synapses instead of full text). Currently only logs a warning and returns; no behavior to test.

---

## How it’s used in the node

The node runs it **once per main loop**, after reflection and before housekeeping:

```text
_reflection_cycle()
metacognitive_engine.run_metacognitive_cycle()
_prune_ledger()
```

So you **use it** by running the node as usual; you don’t call it manually unless you’re scripting or testing. Fragment classification is refined by the idle fragment audit task; once a stale, low‑trust fact is marked `confirmed_fragment`, the metacognitive engine is responsible for actually deleting it.

---

## How to test it

### Option A: Run the node and watch logs

1. Start the node: `uv run python -m src.node`
2. Each cycle (every ~15 minutes after the first run), look for log lines like:
   - `[Metacognition] Engaging deep structural review...`
   - `[Meta-Prune] Scanning for stale, uncorroborated data older than 90 days...`
   - Either `[Meta-Prune] No records met the garbage collection threshold.` or  
     `[Meta-Prune] Successfully purged N low-integrity, stale facts from storage.`

So you **test it** in the large by running the node and confirming those messages and that old, low-trust facts with short ADL eventually get purged.

### Option B: Unit test (with a temporary DB)

Use a test DB and insert facts that match the prune criteria (old + low trust + short ADL), then call `run_metacognitive_cycle()` and assert that those facts are deleted and others are not. The test file `tests/test_metacognitive_engine.py` (below) does exactly that.

Run:

```bash
uv run pytest tests/test_metacognitive_engine.py -v
```

---

## Summary

| Piece                         | Role                                                                                                  |
|------------------------------|-------------------------------------------------------------------------------------------------------|
| `run_metacognitive_cycle()`  | Entry point; runs prune check + logs “synapse refinement initiated”.                                  |
| `prune_integrity_check()`    | Deletes facts that are &gt;90 days old, trust_score ≤ 2, and either ADL length &lt; 10 or `confirmed_fragment`. |
| `retrieve_adl_based_answer()`| Placeholder; no behavior yet.                                                                          |

You **use** it by running the node; you **test** it via logs or via the unit test that patches the DB and checks pruning + fragment behavior.

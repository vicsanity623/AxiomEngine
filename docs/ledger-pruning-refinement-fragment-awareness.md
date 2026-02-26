### Howpoor quality or malformed facts are detected and pruned.

- **Schema + plumbing**
  - `facts` table now has:
    - `fragment_state TEXT NOT NULL DEFAULT 'unknown'`
    - `fragment_score REAL NOT NULL DEFAULT 0.0`
    - `fragment_reason TEXT`
  - A new index `idx_facts_fragment_state` supports fast fragment queries.
  - `initialize_database` runs defensive `ALTER TABLE` calls so existing DBs get the new columns on startup.
  - `insert_uncorroborated_fact(...)` accepts and stores:
    - `fragment_state`, `fragment_score`, `fragment_reason`.

- **Extractor (Crucible) fragment heuristics**
  - New helper `_compute_fragment_metadata(doc, raw_sent)` computes:
    - A **rule‑based `fragment_score`** using:
      - Very short or moderately short sentence length.
      - Missing named entities.
      - Pronoun‑leading sentences (`he`, `she`, `they`, `it`, `this`, `that`, etc.).
      - Non‑terminal punctuation and lowercase starts.
    - A **`fragment_state`** (`'suspected_fragment'` or `'unknown'`) and a comma‑joined `fragment_reason`.
  - `extract_facts_from_text(...)` now:
    - Generates ADL as before.
    - Calls `_compute_fragment_metadata` for each stored fact.
    - Passes `fragment_state`, `fragment_score`, `fragment_reason` into `insert_uncorroborated_fact`.

- **`view_ledger.py` fragment visibility**
  - **Stats header**:
    - After the usual status counts, it now (when columns exist) prints:
      - `fragments (suspect)  : N`
      - `fragments (confirmed): M`
  - **Recent records listing**:
    - Uses `fragment_state` / `fragment_score` when present:
      - `confirmed_fragment` → `FRAGMENT!` (red).
      - `suspected_fragment` or `fragment_score ≥ 0.5` → `FRAGMENT?` (red).
      - Otherwise falls back to the old length‑based rule (≤8 words → `FRAGMENT?`, else `COMPLETE`).

- **Idle fragment audit (per node)**
  - New idle task `AxiomNode._idle_fragment_audit`:
    - Runs at most **once every 30 minutes** per node, with throttle logging managed by `_maybe_log_idle_throttle`.
    - Samples up to 40 non‑disputed facts at random from the local ledger.
    - Decompresses each fact and applies **simple, model‑free heuristics** (word length, pronoun start, punctuation) to compute a refined `score` and reasons.
    - Updates `fragment_state`, `fragment_score`, `fragment_reason` when they change.
      - Weak evidence → demotes suspected/confirmed to `rejected_fragment`.
      - Strong short/pronoun/odd punctuation evidence → upgrades `unknown` to `suspected_fragment`.
    - Logs a concise summary like:
      - `"[Idle-Fragment:8009] Audited 40 fact(s); updated classifications for 7."`
  - Idle registration:
    - `self.idle_tasks` now includes `_idle_fragment_audit` between data quality and health snapshot.
  - `/debug/idle_state` now reports `last_fragment_audit_age_sec`.

- **Cross‑node fragment opinions (simple, non‑LLM consensus)**
  - New endpoint `GET /fragment_opinion?fact_id=...` on each node:
    - Returns JSON with:
      - `seen` (bool)
      - `status`, `trust_score`
      - `fragment_state`, `fragment_score`
  - Inside `_idle_fragment_audit`, for `suspected_fragment` facts and when peers exist:
    - Queries up to **3 peers** at `/fragment_opinion`.
    - Counts:
      - **positives**: peers that don’t know the fact or also classify it as `suspected_fragment` / `confirmed_fragment`.
      - **negatives**: peers that mark it `rejected_fragment` or have it as **trusted with decent trust**.
    - Decision:
      - `positives > 0` and `negatives == 0` → promote to `confirmed_fragment`.
      - `negatives > 0` and `positives == 0` → demote to `rejected_fragment`.
    - This is fully rule‑based and deterministic—no ML/LLM involved.

- **Metacognitive pruning integration**
  - `prune_integrity_check(...)` now selects `fragment_state` along with ADL.
  - A fact becomes a **deletion candidate** when:
    - It is **old** (beyond the existing 90‑day threshold),
    - Has **low trust** (`trust_score <= TRUST_SCORE_FOR_PRUNING`),
    - And either:
      - ADL is shorter than `ADL_INTEGRITY_THRESHOLD`, **or**
      - `fragment_state == 'confirmed_fragment'`.
  - This means confirmed, low‑trust, stale fragments are now preferentially pruned during metacognitive cycles.

You now have:
- Fragment awareness baked into the schema and extractor.
- Visibility of fragment counts and markings in `view_ledger.py`.
- A deterministic, non‑LLM idle auditor that refines fragment classification and uses simple peer consensus.
- Metacognitive pruning that treats confirmed fragments as first‑class cleanup targets.
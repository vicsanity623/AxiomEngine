### Running Axiom nodes and inspecting the ledger

This doc explains how to start the bootstrap and peer nodes, how idle behavior fits in, and how to inspect/prune the ledger using the built‑in tools.

---

### Node roles and DB files

- **Bootstrap node**
  - Default port: `8009`.
  - Uses DB path:
    - `AXIOM_DB_PATH` env var if set, otherwise `axiom_ledger.db`.
  - Also acts as a **seed** node peers can sync from.

- **Peer nodes**
  - Any other port (e.g. `8010`, `8011`).
  - DB path:
    - `AXIOM_DB_PATH` if set, otherwise `axiom_ledger_<PORT>.db` (e.g. `axiom_ledger_8010.db`).

- **Safe to keep old DBs?**
  - Yes. The code runs migrations on startup:
    - Ensures schema is up to date (blocks, fragment columns, indexes).
    - Compresses any legacy plaintext `fact_content` via `migrate_fact_content_to_compressed()`.
  - You only need to delete DBs if you want a completely fresh knowledge base.

---

### Starting nodes

- **Bootstrap (default)**

```bash
python -m src.node
```

Environment options:

- `PORT` – override port (default `8009`).
- `AXIOM_DB_PATH` – override DB file name/path.
- `BOOTSTRAP_PEER` – optional; for bootstrap usually left unset.

- **Peer node**

```bash
PORT=8010 BOOTSTRAP_PEER=http://127.0.0.1:8009 python -m src.node
```

Each peer:

- Connects to the given `BOOTSTRAP_PEER`.
- Pulls facts and blocks from it.
- Discovers additional peers via `/get_peers` and `X-Axiom-Peer` headers.

---

### Idle behavior and diagnostics

- **Idle suite**
  - Each node runs a background loop that:
    - Executes the main ingestion cycle on a schedule (`AXIOM_MAIN_CYCLE_INTERVAL`, default 900s).
    - Between main cycles, runs an **idle suite** every `AXIOM_IDLE_SUITE_INTERVAL` seconds (default `30s`).
  - The idle suite runs these tasks in sequence (with per‑task throttling):
    - `_idle_learning_cycle` – rediscover relationships, reinforce mesh.
    - `_idle_conversation_training` – compile conversation patterns.
    - `_idle_code_introspection` – code map and endpoint registry.
    - `_idle_data_quality` – duplicate/conflict sampling.
    - `_idle_fragment_audit` – refine fragment classification and gather peer opinions.
    - `_idle_health_snapshot` – light ledger/chain health metrics.
    - `_idle_self_checks` – deterministic self‑queries against `/think`.

- **Seeing idle state**

```bash
curl "http://127.0.0.1:8009/debug/idle_state"
```

Returns:

- `node_port`, `node_role`, `advertised_url`, `db_path`.
- `main_cycle_interval_sec`, `idle_suite_interval_sec`.
- Ages (seconds since last run) for:
  - main cycle, idle learning, code introspection, data quality,
  - fragment audit, health snapshot, self‑checks.

---

### Inspecting the ledger and mesh

Use `view_ledger.py` to see high‑level stats, recent facts, and the lexical mesh.

- **Summary stats only**

```bash
python view_ledger.py --stats --db axiom_ledger.db
```

Shows:

- Total facts, relationships, lexicon size, synapse count.
- Status counts: `trusted`, `disputed`, `uncorroborated`.
- Fragment counts (if the DB has fragment columns):
  - `fragments (suspect)`
  - `fragments (confirmed)`

- **Stats + brain (mesh) overview**

```bash
python view_ledger.py --brain --limit 15 --db axiom_ledger.db
```

Shows, in addition to stats:

- Top synapses: strongest `word_a` ↔ `word_b` relations.
- Heaviest lexicon entries (most frequently seen atoms).

- **Stats + recent facts**

```bash
python view_ledger.py --limit 25 --db axiom_ledger.db
```

Shows, for each of the N most recent facts:

- Status (`[TRUSTED]`, `[DISPUTED]`, `[UNCORROBORATED]`).
- Lexical processing marker (`◈` for processed into mesh, `◇` otherwise).
- Trust score, word count, integrity flag:
  - `COMPLETE`
  - `FRAGMENT?` (suspected fragment)
  - `FRAGMENT!` (confirmed fragment).
- The decompressed fact content.
- Source URL.

---

### Pruning and fragments – operational notes

- You do **not** need to wipe DBs after schema changes:
  - Startup migration will:
    - Backfill new fragment columns.
    - Compress legacy fact content.
  - Idle fragment audits plus metacognitive pruning will progressively:
    - Reclassify short/garbage facts as `suspected_fragment` / `confirmed_fragment`.
    - Delete old, low‑trust, confirmed fragments and shallow ADL entries.

- You **may** choose to reset DBs for a clean slate:
  - Stop all nodes.
  - Delete `axiom_ledger*.db` files.
  - Restart bootstrap and peers; they will rebuild from fresh ingestion cycles.
  - This throws away all collected knowledge; only do this if you explicitly want to re‑crawl with the improved extractor.

---

### Quick checklist for operators

- **After upgrading code:**
  - Restart nodes; confirm logs show:
    - Ledger schema initialized/verified.
    - Optional legacy fact migration (if applicable).
  - Hit `/debug/idle_state` to ensure idle tasks are running.

- **To investigate noise/garbage:**
  - Run `view_ledger.py --limit 50 --db <db>` and scan for `FRAGMENT?` / `FRAGMENT!`.
  - Let nodes run long enough for:
    - `_idle_fragment_audit` to classify.
    - Metacognitive pruning cycles to run.

- **To completely reset knowledge:**
  - Delete DB files and restart nodes (bootstrap first, then peers).
  - Watch new facts accumulate and new blocks commit as cycles run.


### What Idle cycles do.

- **Idle behavior + origin visibility**
  - Idle logs now include the node port, e.g. `"[Idle-Health:8009]"`, `"[Idle-Data:8010]"`, so you can see which node produced each message.
  - Added a **throttle logger** `_maybe_log_idle_throttle` used by all long-interval idle tasks (`learning`, `code`, `data`, `health`, `selfcheck`). It logs (at debug level) when a task is being skipped due to its time window, rate‑limited to at most once per 60s per task.
  - Reworked the scheduler to run a full **idle suite** in a fixed order:
    - `_background_loop` now alternates between main cycles and `_run_idle_suite`, which calls every idle task sequentially.
    - Each suite is bracketed with `"[Idle-Suite:<port>] Start."` / `End.` so idle logs are grouped and ordered per node.

- **`/debug/idle_state` endpoint**
  - Added `AxiomNode.get_idle_state()` returning a JSON snapshot with:
    - `node_port`, `node_role` (`bootstrap`/`peer`), `advertised_url`, `db_path`
    - `main_cycle_interval_sec`, `idle_suite_interval_sec`
    - Ages (seconds since last run) for: main cycle, idle learning, code introspection, data quality, health snapshot, self checks.
  - New route `GET /debug/idle_state` returns this for the current node (503 if not initialized).

- **Hardened P2P sync + health anomaly detection**
  - `bootstrap_sync` and the background P2P sync inside `_run_main_cycle` now **log warnings instead of silently swallowing exceptions**, including the peer URL and error.
  - The immediate handshake thread in `add_or_update_peer` logs a debug message if the handshake fails.
  - `_idle_health_snapshot`:
    - Logs with node origin: `"[Idle-Health:<port>]"`.
    - After computing a snapshot, if `total_blocks > 0` and `total_facts == 0`, logs a **health anomaly warning** noting the db path, to highlight “chain but no facts” conditions.

- **Richer health summary**
  - `get_health_summary()` now prefixes status with node context, e.g.  
    `"Node 8009 (bootstrap node) at http://... . Facts: X, Blocks: Y, Chain height: Z. Status counts: {...} ..."`  
    so `axiom: status` clearly tells you which node and role you’re querying.

- **Normalized fact storage across peers + self‑healing migration**
  - In `p2p.sync_with_peer`:
    - Uses the **decompressed text** from the peer payload to verify the hash.
    - Compresses content with `zlib.compress` before inserting into `facts.fact_content`, ensuring all P2P‑received facts are stored as compressed BLOBs.
    - Logs a warning and skips a fact if compression somehow fails.
  - In `ledger.py`:
    - Added `migrate_fact_content_to_compressed(db_path)` which:
      - Finds rows where `typeof(fact_content) != 'blob'` (legacy plaintext).
      - Compresses them and updates in place.
      - Logs how many facts were migrated.
    - `AxiomNode.__init__` calls this right after `initialize_database(self.db_path)`, so each node repairs its ledger once at startup.

- **Other notes**
  - Added `self.node_role` (`bootstrap` vs `peer`), `self._last_main_cycle_ts`, and a small `_idle_throttle_log` map for internal state.
  - Linting on `node.py`, `p2p.py`, and `ledger.py` passes with no errors.

When you restart the bootstrap and peer nodes, you should now see:
- Idle logs clearly tagged by port and grouped between `Idle-Suite` start/end lines.
- `/debug/idle_state` on each node reflecting when each idle task last actually ran.
- If a node ever has blocks but zero facts, a prominent health anomaly warning in that node’s log, instead of it being silently confusing.
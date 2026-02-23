# Axiom Blockchain Layer

## Overview

Axiom now has a **blockchain layer** on top of the fact ledger. The chain provides:

- **Ordered history**: Blocks commit fact_ids in a canonical order.
- **Integrity**: Each block’s ID is the SHA256 of (previous_block_id, height, timestamp, fact_ids). Tampering breaks the chain.
- **Replication**: Nodes sync chain and facts independently; longest chain wins when appending.

The ledger (facts table) is unchanged; the chain is an **append-only log of commitments** to fact_ids.

---

## Data Model

### Blocks table (in same DB as facts)

| Column             | Type   | Description                          |
|--------------------|--------|--------------------------------------|
| block_id           | TEXT   | SHA256 of block payload (primary key)|
| previous_block_id  | TEXT   | Links to previous block              |
| height             | INTEGER| Block number (0 = genesis)           |
| created_at_utc     | TEXT   | ISO timestamp                         |
| fact_ids           | TEXT   | JSON array of fact_ids in this block |

### Genesis block

- `block_id = "axiom_genesis_v1"`, `previous_block_id = ""`, `height = 0`, `fact_ids = []`.
- Created automatically on first run when the blocks table is empty.

---

## Lifecycle

1. **Content cycle**: Crucible extracts facts → they are inserted into the facts table as today.
2. **Commit**: If the cycle produced new facts, the node creates a **new block** with those fact_ids and appends it to the chain (previous = current head).
3. **Sync**: For each peer, the node:
   - Pulls **facts** (existing P2P: get_fact_ids, get_facts_by_id).
   - Pulls **chain**: GET `/get_chain_head`; if peer’s height &gt; ours, GET `/get_blocks_after?height=N`, then append blocks in order (validating each link and hash).

So: **facts** and **chain** sync independently; the chain does not carry fact content, only fact_ids.

---

## Consensus (longest chain)

- When syncing, a node only **appends** blocks that extend its current head (previous_block_id == our head, height == our height + 1).
- If a peer has a longer chain, we fetch blocks after our height and append them one by one. No reorg logic: we only extend forward.
- First valid block at each height wins (no mining or voting). So the “canonical” chain is whatever this node has after syncing with peers; different nodes can temporarily have different lengths until they sync.

---

## API (for P2P)

- **GET /get_chain_head**  
  Returns `{ "block_id": "...", "height": N }`.

- **GET /get_blocks_after?height=N**  
  Returns `{ "blocks": [ { block_id, previous_block_id, height, created_at_utc, fact_ids }, ... ] }` for all blocks with height &gt; N, in ascending order.

---

## Files

- **src/blockchain.py** – Genesis, create_block, get_chain_head, get_blocks_after, append_block, validate_block.
- **src/ledger.py** – `blocks` table created in `initialize_database()`.
- **src/p2p.py** – `sync_chain_with_peer()`: fetch head, fetch blocks after our height, append.
- **src/node.py** – After each content cycle, create_block(new fact_ids); in loop and bootstrap, call sync_chain_with_peer after fact sync.

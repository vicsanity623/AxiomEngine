# P2P Mesh Verification: Blockchain‑Like Persistence?

## Short answer

- **“Network persists as long as one node is active”** — **Yes**, with the usual caveat: that node must be reachable (e.g. via bootstrap or discovery) so others can sync **from** it. There is no single “chain”; each node has its own copy of the ledger and merges facts by `fact_id`. As long as at least one node holds the data and is up, new or returning nodes can pull from it and the “network” (the shared fact set) persists.
- **“All nodes sync back to bootstrap”** — **No.** Sync is **pull-only**: each node **pulls** from its peers (including bootstrap). Nobody **pushes** to bootstrap. Bootstrap is an **entry point** to get initial peers and ledger, not a central server everything “syncs back” to.

So the mesh is **eventual-consistency / gossip-style**, not a literal blockchain, but it does give you “one node can hold the truth and others can catch up from it.”

---

## How it actually works

### 1. Bootstrap and seeds

- **Seeds:** Hardcoded `seed_nodes = ["https://vics-imac-1.tail137b4f2.ts.net"]` plus optional env `BOOTSTRAP_PEER`.
- **On startup:** The node adds those as peers and runs `bootstrap_sync()`: it **pulls** from each of them (gets fact IDs, then missing facts). So bootstrap is used only as a **source** to sync **from**, not as a sink to sync “back” to.

### 2. Discovery (gossip)

- During **sync**, the node calls the peer’s **`/get_peers`** and adds every returned URL to its own peer list (`add_or_update_peer`). So the mesh grows by **gossip**: you learn about more nodes from the nodes you already talk to.
- Any HTTP request that carries **`X-Axiom-Peer`** is treated as “the caller is a peer” and that URL is added/updated. So whoever connects to you (e.g. to sync or query) becomes a peer. That’s how two nodes “find” each other when one connects to the other.

### 3. Sync direction (pull-only)

- **`sync_with_peer(node_instance, peer_url)`** in `p2p.py` always means: **this node** pulls **from** `peer_url`.
  - GET `/get_fact_ids` from peer → compare with local → GET `/get_facts_by_id` for missing IDs → INSERT into local DB.
- So:
  - **A** syncs with **B** ⇒ **A** downloads from **B** (B does not push to A).
  - If A and B are each other’s peers, then in one cycle A pulls from B, and in the same or next cycle B pulls from A. So data can spread **both ways over time**, but each sync is **one-way (pull)**.
- There is **no** “report back to bootstrap” or “push to a central node.” Bootstrap is just the first place you pull from and the first place you get more peer URLs from.

### 4. Ledger and “persistence”

- Each node has a **local SQLite ledger** (facts, relationships, lexicon, synapses). There is no global “chain” object; the “network” is the union of what each node has, reconciled by **fact_id** (content-addressed: same content ⇒ same ID, so no duplicate facts when syncing).
- **“Network persists as long as one node is active”** means: if at least one node **N** has the data and is **reachable** (others have N as a peer or can bootstrap from N), then:
  - New nodes can point `BOOTSTRAP_PEER` at N (or discover N via gossip) and pull the ledger from N.
  - Returning nodes can re-sync from N (and others) and get back up to date.
- So the **data** persists as long as **at least one** such node is up and reachable; the **protocol** does not require a special “bootstrap server” to push to.

### 5. What’s different from a typical blockchain

- **No chain structure:** No blocks, no previous-block hash, no total ordering of “the” chain. Facts are a set keyed by `fact_id`.
- **No consensus on order:** Order of facts doesn’t matter for deduplication; sync is “do I have this fact_id? If not, fetch it.”
- **No “sync back to bootstrap”:** All sync is pull. Bootstrap is just the initial source (and peer discovery source), not a sink that nodes push to.
- **Similarities:** Data is replicated across nodes; as long as one node has it and is reachable, others can recover; content-addressing (hash of content = fact_id) gives integrity and dedup.

---

## Summary table

| Claim | Verdict | Notes |
|-------|--------|--------|
| Network persists as long as one node is active | ✅ Yes | That node must be reachable (bootstrap or discovered). Others pull from it; no central chain. |
| All nodes sync back to bootstrap | ❌ No | Sync is pull-only. Nodes pull **from** bootstrap (and from other peers). Nothing “syncs back” to bootstrap. |
| Bootstrap is the entry point | ✅ Yes | New/returning nodes use bootstrap (or a discovered peer) to get initial peer list and ledger. |
| Mesh grows by gossip | ✅ Yes | `/get_peers` and `X-Axiom-Peer` spread peer lists so the graph of who-talks-to-whom grows. |

So: the P2P mesh **does** give you “one node can hold the data and the network can persist and recover from it,” but it is **not** “all nodes sync back to bootstrap”—they sync **from** bootstrap (and from each other), and only by **pull**.

# ◈ Contributing to Axiom

First off, thank you for joining the collective. Axiom is a **digital commonwealth**—a public utility for truth that only grows stronger through the diverse contributions of its operators, architects, and auditors.

This document is your mission briefing for getting set up and making your first contribution to the **Lexical Mesh**.

---

## ◈ The Four Pillars of Contribution

You don't need to be a kernel developer to help ground reality. We value all forms of contribution:

| Pillar | Role | Description |
| :--- | :--- | :--- |
| 🛡️ **The Operator** | **Node Runner** | Run a stable node and enable your Funnel to strengthen the network. |
| 🔍 **The Auditor** | **Logic Auditor** | Identify "logical hallucinations" in the Lexical Mesh or Crucible filters. |
| 🏗️ **The Architect** | **Developer** | Refine the deterministic Python engine or the SOTA visualizer UI. |
| ✍️ **The Scribe** | **Documentation**| Improve the clarity of the Lexical Mesh technical specifications. |

---

## ◈ Quick Start: Development Setup

### 1. Prerequisites
Ensure you have **Python 3.13+** installed. We use `uv` for fast dependency management.

### 2. Clone & Environment Setup
```bash
# Clone your fork:
git clone https://github.com/vicsanity623/AxiomEngine.git
cd AxiomEngine

# 1. Create a dedicated, clean environment using uv
uv venv --python 3.13
source .venv/bin/activate

# 2. Install dependencies (Runtime + Development Tools)
uv pip install -e .[tools,tests]

# 3. Download the Analytical AI model (The Lexical Mesh's foundation)
python -m spacy download en_core_web_sm
```

> **Note:** Axiom is strictly **Anti-AI**. Do not attempt to integrate Transformer, Torch, or any LLM-based libraries. We use deterministic, symbolic mapping only.

### 3. Launching Your Local Mesh
You can run multiple nodes on a single machine to test P2P synchronization and Lexical Mesh consistency.

**Node A (The Bootstrap):**
```bash
export PORT=8009
python src/node.py
```

**Node B (The Peer):**
Open a new terminal tab:
```bash
export PORT=8010
export BOOTSTRAP_PEER=http://127.0.0.1:8009
python src/node.py
```
*Your nodes will now begin a bidirectional sync. Verify the graph and mesh growth using `python src/view_ledger.py --brain`.*

---

## ◈ The Development Workflow

### 1. Branching Protocol
Never work directly on `main`. Create a descriptive feature branch:
- `feat/shredder-logic-update`
- `fix/tailscale-handshake-timeout`
- `docs/explain-synapse-weighting`

### 2. Conventional Commits
We use the [Conventional Commits](https://www.conventionalcommits.org/) standard to keep the progress ledger clean:
- `feat(Crucible): add specific entity weight for LAW tags`
- `fix(P2P): deduplicate local vs public node identities`
- `chore: update pyproject.toml for Python 3.13`

### 3. Pull Requests (PRs)
When you are ready, submit a PR against the `main` branch. 
- **Deterministic Check:** Ensure your code does not add probabilistic "guessing" or external API dependencies unless part of an approved module.
- **Visuals:** If you updated the terminal UI or the Lexical Mesh visualizer, include a screenshot!

---

## ◈ Join the Discussion

The Axiom collective coordinates through these primary channels:

- ◈ **Discord:** [Join the Collective](https://discord.gg/axiom) (Technical deep-dives & DAO planning)
- ◈ **GitHub Issues:** [The Project Board](https://github.com/vicsanity623/AxiomEngine/issues) (Track the V4 Terminal progress)

---

## ◈ License
By contributing to Axiom, you agree that your contributions will be licensed under the **Peer Production License (PPL)**. This ensures that our collective work remains a non-commercial public utility forever.

**Thank you for defending the bedrock of reality. ◈**
```

### Key Changes:

1.  **Environment Setup:** Changed `pip install -e .` to the modern `uv` command: **`uv pip install -e .[tools,tests]`**.
2.  **Model Download:** Kept the essential `python -m spacy download en_core_web_sm` command, as models are often external to the package install.
3.  **Launch Protocol:** Changed the launch command to use the correct path structure: **`python src/node.py`**.
4.  **Inspection:** Changed the inspection command to reflect the new path: **`python src/view_ledger.py`**.

This documentation now accurately reflects the advanced, modern toolchain you are using!
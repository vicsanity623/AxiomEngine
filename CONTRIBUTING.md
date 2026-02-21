# ◈ Contributing to Axiom

First off, thank you for joining the collective. Axiom is a **digital commonwealth**—a public utility for truth that only grows stronger through the diverse contributions of its operators, architects, and auditors.

This document is your mission briefing for getting set up and making your first contribution.

---

## ◈ The Four Pillars of Contribution

You don't need to be a kernel developer to help ground reality. We value all forms of contribution:

| Pillar | Role | Description |
| :--- | :--- | :--- |
| 🛡️ **The Operator** | **Node Runner** | Run a stable node to strengthen the network's knowledge base. |
| 🔍 **The Auditor** | **Bug Hunter** | Identify vulnerabilities or "logical hallucinations" in the fact-extraction logic. |
| 🏗️ **The Architect** | **Developer** | Write core Python code for the Crucible, Synthesizer, or P2P protocol. |
| ✍️ **The Scribe** | **Documentation**| Improve clarity in guides, whitepapers, or technical specs. |

---

## ◈ Quick Start: Development Setup

### 1. Prerequisites
Ensure you have **Python 3.10+** installed. We also recommend using a virtual environment (`venv` or `conda`).

### 2. Clone & Install
```bash
# Fork the repo on GitHub, then clone your fork:
git clone https://github.com/YOUR_USERNAME/AxiomEngine.git
cd AxiomEngine

# Install required Python libraries
pip install -r requirements.txt

# Download the Analytical AI model (The Crucible's brain)
python -m spacy download en_core_web_sm
```

> **Note:** Axiom is self-sufficient. **No API keys are required** for development. The engine gathers knowledge from public RSS streams.

### 3. Launching Your Local Mesh
You can run multiple nodes on a single machine to test P2P synchronization.

**Node A (The Bootstrap):**
```bash
export PORT=5000
python node.py
```

**Node B (The Peer):**
Open a new terminal tab:
```bash
export PORT=5001
export BOOTSTRAP_PEER=http://127.0.0.1:5000
python node.py
```
*Your nodes will now begin a bidirectional sync. Node A will automatically learn about Node B once the first connection is made via the `X-Axiom-Peer` header.*

---

## ◈ The Development Workflow

### 1. Branching Protocol
Never work directly on `main`. Create a descriptive feature branch:
- `feat/add-subjectivity-filter`
- `fix/p2p-timeout-logic`
- `docs/update-dao-charter`

### 2. Conventional Commits
We use the [Conventional Commits](https://www.conventionalcommits.org/) standard to keep the ledger of our progress clean:
- `feat(Crucible): add weighted entity recognition`
- `fix(P2P): resolve sqlite lock on high-volume sync`
- `chore: update requirements.txt`

### 3. Pull Requests (PRs)
When you are ready, submit a PR against the `main` branch. 
- **Be Descriptive:** Explain *what* you changed and *why* it improves the grounding engine.
- **Visuals:** If you changed the CLI output or the Knowledge Graph, include a screenshot!

---

## ◈ Join the Discussion

The Axiom collective coordinates through these primary channels:

- ◈ **Discord:** [Join the Collective](https://discord.gg/axiom) (Technical deep-dives & DAO planning)
- ◈ **Reddit:** [r/AxiomEngine](https://reddit.com/r/AxiomEngine) (General discussion & news)
- ◈ **GitHub Issues:** [The Project Board](https://github.com/vicsanity623/AxiomEngine/issues) (Track what we are building)

---

## ◈ License
By contributing to Axiom, you agree that your contributions will be licensed under the **Peer Production License (PPL)**. This ensures that our collective work remains a non-commercial public utility forever.

**Thank you for defending the bedrock of reality. ◈**
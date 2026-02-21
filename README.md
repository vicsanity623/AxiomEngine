# Axiom: The Decentralized Grounding Engine ◈

<div align="center">

![Axiom Banner](https://raw.githubusercontent.com/vicsanity623/AxiomEngine/main/main/Axiom.PNG)

[![License: PPL](https://img.shields.io/badge/License-PPL-blue.svg)](https://github.com/ArtisticIntentionz/AxiomEngine/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-cyan.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/badge/Release-v3.0.1--Genesis-green.svg)]()
[![Build](https://img.shields.io/badge/Build-Passing-brightgreen.svg)]()
[![Discord](https://img.shields.io/badge/Discord-Join%20Collective-7289DA.svg)]()

**Axiom is an autonomous, anonymous P2P network designed to serve as the bedrock for shared reality.**

[Website](https://axiom.network) • [Documentation](docs/INTRO.md) • [Whitepaper](whitepaper.pdf) • [DAO Charter](DAO.md) • [Discord](https://discord.gg/axiom)

</div>

---

## ◈ The Vision: A Grounding Engine for a Fractured World

Our digital world is in a state of cognitive crisis. We are drowning in "engagement-optimized" misinformation, paranoia-inducing algorithms, and emotional manipulation. 

**Axiom is not a "Truth Engine" or a lie detector.** It is a **Grounding Engine**. It is designed to ease the mind by filtering the signal from the noise, providing a clean, objective, and verifiable record of facts—autonomous, decentralized, and immune to corporate or political control.

> *"Truth matters, and it should belong to everyone. Axiom is the digital commonwealth where reality is preserved."*

---

## ◈ Core Architecture: How It Works

Axiom operates as a **Decentralized Knowledge Organism**. Every node runs a continuous four-phase cycle:

| Phase | System | Description |
| :--- | :--- | :--- |
| **01: Discovery** | **Zeitgeist Engine** | Scans public RSS streams to identify trending topics without using tracking APIs. |
| **02: Extraction** | **Pathfinder** | Surgically pulls content from trusted sources using a fortified, bot-resistant scraper. |
| **03: Verification**| **The Crucible** | Uses **Analytical AI (spaCy)** to extract objective facts while discarding opinions and speculation. |
| **04: Linking** | **The Synthesizer** | Builds a **Knowledge Graph** by identifying shared entities (people, places, orgs) across the ledger. |

---

## ◈ Why Axiom?

### 🛡️ Immune to Hallucination
Unlike Generative AI (LLMs), Axiom uses **Analytical NLP**. It cannot "invent" facts; it can only extract and verify what is actually there.

### 🕵️ Radical Anonymity
Queries are routed through a **Tor-style anonymous circuit**. You have the right to be curious without being surveyed.

### 🧬 The Corroboration Rule
A fact is never trusted on first sight. It remains `uncorroborated` until an independent, high-trust source makes the same claim. Contradictions are flagged as `disputed`.

### 🔌 No API Dependencies
Axiom is self-sustaining. It gathers knowledge directly from the open web (RSS), meaning it cannot be "shut off" by a single provider.

---

## ◈ Comparison to Alternatives

| Feature | Axiom | Search (Google) | Encyclopedias | LLMs (ChatGPT) |
| :--- | :---: | :---: | :---: | :---: |
| **Governed By** | Community (DAO) | Corporation | Foundation | Corporation |
| **Privacy** | Circuit-Anonymity | Active Tracking | IP Logging | Prompt Logging |
| **Incentive** | Accuracy/Trust | Ad Revenue | Human Consensus | Engagement |
| **Unit of Data** | Weighted Facts | Ads & Links | Articles | Probable Tokens |
| **Censorship** | Resistance | Algorithmic | Editorial | Hard-Coded |

---

## ◈ Quick Start (Genesis Stage)

### Build Standalone Node
To produce a single executable that runs without a system Python (Self-Compile):

```bash
# Clone the repository
git clone https://github.com/ArtisticIntentionz/AxiomEngine.git
cd AxiomEngine

# Install build dependencies
pip install pyinstaller
python -m spacy download en_core_web_sm

# Build for your OS (Windows .exe or macOS .dmg)
python build_standalone.py
```

### Run the Node
Launch the node and join the genesis network:
```bash
./dist/AxiomNode
```

### Visualize the Constellation
View your local knowledge graph as an interactive 3D constellation:
```bash
python visualize_graph.py --topic "AI" -o galaxy.html
open galaxy.html
```

---

## ◈ The Roadmap

- [x] **V1: Genesis** - Core P2P sync and RSS extraction.
- [x] **V2: The Crucible** - Analytical fact extraction and subjectivity filtering.
- [x] **V3: Synthesizer** - Entity linking and Knowledge Graph integration.
- [ ] **V4: Client Alpha** - Desktop GUI for anonymous network querying.
- [ ] **V5: DAO Launch** - On-chain governance and reputation-based voting.

---

## ◈ Contributing

We are building a digital commonwealth. Whether you are a cryptographer, an AI researcher, or a writer, we need your help.

1. Review the [Contributing Guide](CONTRIBUTING.md).
2. Grab an issue from the [Issue Tracker](https://github.com/ArtisticIntentionz/AxiomEngine/issues).
3. Join the [Discord](https://discord.gg/axiom) to discuss protocol changes.

---

## ◈ License

Axiom is licensed under the **Peer Production License (PPL)**. 
This ensures the software remains a non-commercial public utility, owned by the workers and users who build it. 

*Copyright (c) 2025 The Axiom Contributors.*
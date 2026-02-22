# Axiom: The Decentralized Grounding Engine ◈

<div align="center">

<img src="https://raw.githubusercontent.com/vicsanity623/AxiomEngine/main/main/Axiom.png" width="750" alt="Axiom Logo">

<br />

[![License: PPL](https://img.shields.io/badge/License-PPL-blue.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-cyan.svg)](https://www.python.org/downloads/)
[![Release](https://img.shields.io/badge/Release-v0.2.0--voice-magenta.svg)]()
[![Build](https://github.com/vicsanity623/AxiomEngine/actions/workflows/build.yml/badge.svg?branch=main)](https://github.com/vicsanity623/AxiomEngine/actions/workflows/build.yml)
[![Network](https://img.shields.io/badge/Network-P2P--Live-00f0ff.svg)]()

**Autonomous. Anonymous. Anti-AI. The deterministic bedrock for shared reality.**

[Website](TBD) • [Documentation](TBD) • [DAO Charter](DAO_CHARTER.md) • [Discord](TBD)

</div>

---

## ◈ The Vision: Clarity Over Hallucination

Axiom is a **Grounding Engine** designed for a world in cognitive crisis. We are drowning in engagement-optimized misinformation and "Black Box" AI hallucinations.

**Axiom is strictly Anti-AI.** We reject the probabilistic "guessing" of Transformers and Large Language Models. Instead, Axiom builds a **Lexical Mesh**—a deterministic, symbolic map of language and facts gathered directly from verified RSS streams. It is an autonomous public utility for truth, immune to corporate or political manipulation.

> *"Truth is not a probability. Axiom is the digital commonwealth where reality is preserved to provide peace of mind."*

---

## ◈ Architecture: The Living Mesh

Every Axiom node operates as a self-sustaining organism, executing a continuous five-phase cycle:

| Phase | Engine | Action |
| :--- | :--- | :--- |
| **01: Discovery** | **Zeitgeist** | Identifies trending topics via public RSS without tracking APIs. |
| **02: Extraction**| **Pathfinder**| Surgically pulls content using a fortified, bot-resistant scraper. |
| **03: Verification**| **The Crucible**| Uses Analytical NLP to extract facts while discarding opinions. |
| **04: Linking** | **Synthesizer**| Builds a Knowledge Graph by identifying shared entities. |
| **05: Reflection** | **Lexical Mesh**| Shreds facts into semantic synapses to build a "Linguistic Brain." |

---

## ◈ Unique Technological Pillars
````mermaid
flowchart TD
    Start([Start Heartbeat]) --> Discovery[Zeitgeist Engine:<br/>Scans Public RSS Headlines]
    Discovery --> Extraction[Pathfinder:<br/>Fortified Scraper Pulls Content]
    Extraction --> Validation{The Crucible:<br/>Analytical NLP}
    
    Validation -->|Reject| Noise[Speculation, Bias,<br/>Subjectivity Filtered]
    Validation -->|Verify| Corroboration[Corroboration Rule:<br/>Multiple Source Agreement]
    
    Corroboration --> Linking[The Synthesizer:<br/>Knowledge Graph Entity Linking]
    Linking --> Reflection[Lexical Mesh:<br/>Linguistic Shredding & Synapses]
    
    Reflection --> Memory[(Immutable SQL Ledger:<br/>Facts + Brain)]
    Memory --> Sleep[Idle State:<br/>Wait for Next Cycle]
    Sleep --> Start

    subgraph Brain_Architecture [Deterministic Intelligence]
        Linking
        Reflection
        Memory
    end

    style Brain_Architecture fill:#0a0f14,stroke:#ff00ff,color:#ff00ff
    style Validation fill:#1e293b,stroke:#00f0ff,color:#00f0ff
    style Start fill:#22c55e,stroke:#fff,color:#000
    style Noise fill:#ff0055,stroke:#fff,color:#fff
````
### 🧠 The Lexical Mesh (The Glass Box)
Unlike LLMs that use trillions of hidden weights, Axiom learns language through **Linguistic Atoms** and **Neural Synapses** stored in an open SQL ledger. You can query exactly *why* Axiom associates two concepts. **Zero GPU required.**
````mermaid
graph TD
    subgraph Global_Mesh [◈ Axiom Self-Healing Mesh ◈]
        A((Genesis Node<br/>iMac 8009)) <-->|Gossip Discovery| B((Peer Node B<br/>London))
        B <-->|Fact Sync| C((Peer Node C<br/>Tokyo))
        C <-->|Linguistic Gossip| A
        B <-->|Reputation Check| D((Peer Node D<br/>Berlin))
        D <-->|Gossip Discovery| A
    end

    subgraph Resilience_Logic [Security & Persistence]
        Node_Down{Node Offline?} -->|YES| Mesh_Active[Remaining Nodes<br/>Maintain Ledger]
        Mesh_Active -->|Return| Re-Sync[Automatic Handshake<br/>Catch-up Sync]
        Re-Sync -->|Success| Integrity_Restored[Network 100% Corrected]
    end

    style Global_Mesh fill:#0a0f14,stroke:#00f0ff,color:#e0e0e0
    style A fill:#00f0ff,stroke:#fff,color:#000
    style B fill:#1e293b,stroke:#00f0ff,color:#fff
    style C fill:#1e293b,stroke:#00f0ff,color:#fff
    style D fill:#1e293b,stroke:#00f0ff,color:#fff
    style Resilience_Logic fill:#050505,stroke:#22c55e,color:#22c55e
````

### 🕵️ Radical Anonymity
Queries are routed through a private P2P mesh. Using the built-in **Tailscale Funnel** integration, you can securely query your node from your mobile device anywhere in the world.

### 🧬 The Corroboration Rule
A fact is never trusted on first sight. It remains `uncorroborated` until an independent source makes the same claim. Direct contradictions are flagged as `disputed`.

---

## ◈ Quick Start

### 1. Installation (Source)
```bash
# Clone and enter
git clone https://github.com/vicsanity623/AxiomEngine.git
cd AxiomEngine

# Install hardened dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 2. Launching the Node
```bash
# Start the engine and join the Genesis Network
python node.py
```

### 3. Build Portable Binary (.dmg / .exe)
Axiom includes a hardened build system for **Python 3.13** that generates a professional installer with a "Drag to Applications" shortcut.
```bash
python build_standalone.py
```

---

## ◈ Inspection & Visualization

Axiom provides high-fidelity tools to watch the network think in real-time.

*   **Audit the Ledger & Brain:**
    ```bash
    python view_ledger.py
    python view_ledger.py --stats  # General Health
    python view_ledger.py --brain  # Top Neural Synapses
    ```

*   **Visualize the Constellation:**
    ```bash
    python visualize_graph.py          # Fact-to-Fact Knowledge Graph and Brain Graph
    ```

---

## ◈ Roadmap

- [x] **V1: Genesis** - Core P2P sync and RSS discovery.
- [x] **V2: The Crucible** - Analytical fact extraction and subjectivity filters.
- [x] **V3: Synthesizer** - Weighted Knowledge Graph linking.
- [x] **V3.2: Lexical Mesh** - Non-LLM linguistic brain and "Reflection" idle cycles.
- [x] **V4: Universal Terminal** - Mobile-ready Web UI served directly from the node.
- [ ] **V5: DAO Governance** - Reputation-weighted protocol voting.

---

## ◈ Contributing & License

Axiom is a **Peer Production** project. We need architects, auditors, and node operators to help defend the bedrock of reality. 

*   **License:** [Peer Production License (PPL)](LICENSE) - Ensuring Axiom remains a non-commercial utility for the people.
*   **Discord:** [Join the Collective](TBD)

**◈ Thank you for defending the bedrock of reality. ◈**

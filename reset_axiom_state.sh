#!/usr/bin/env bash

set -euo pipefail

# Script's project dir (e.g. /Volumes/XTRA/AxiomEngine) — only this tree is reset
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Parent (e.g. /Volumes/XTRA) — used only to find axiom*.db in sibling node dirs
PARENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Resetting Axiom Engine state (project: $SCRIPT_DIR)"

# 1) Remove Axiom ledger DBs in this project and in sibling node dirs (e.g. AxiomEngineNode2, AxiomSystem)
echo "Removing Axiom ledger DBs (bootstrap + peers)..."
find "$SCRIPT_DIR" -maxdepth 2 -type f -name "axiom*.db" -print -delete 2>/dev/null || true
find "$PARENT_DIR" -maxdepth 2 -type f -name "axiom*.db" -print -delete 2>/dev/null || true

# 2) Remove only Axiom-related journals in this project (not every *.sqlite on the volume)
find "$SCRIPT_DIR" -maxdepth 2 -type f \( -name "axiom*.db-journal" -o -name "axiom*.sqlite" \) -print -delete 2>/dev/null || true

# 3) Clear Python bytecode caches only inside this project
echo "Removing Python __pycache__ folders (this project only)..."
find "$SCRIPT_DIR" -type d -name "__pycache__" -print -exec rm -rf {} + 2>/dev/null || true

echo "Done. Ledgers and Python caches cleared."


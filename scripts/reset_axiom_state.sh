#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Resetting Axiom Engine state in: $ROOT_DIR"

# 1) Remove ledger database(s) for all nodes (bootstrap + peers)
echo "Removing Axiom ledger DBs (bootstrap + peers)..."
find "$ROOT_DIR" -maxdepth 2 -type f -name "axiom*.db" -print -delete 2>/dev/null || true

# 2) Remove any stray SQLite journals
find "$ROOT_DIR" -maxdepth 2 -type f \( -name "*.db-journal" -o -name "*.sqlite" -o -name "*.sqlite3" \) -print -delete 2>/dev/null || true

# 3) Clear Python bytecode caches
echo "Removing Python __pycache__ folders..."
find "$ROOT_DIR" -type d -name "__pycache__" -print -exec rm -rf {} + 2>/dev/null || true

echo "Done. Ledgers and Python caches cleared."


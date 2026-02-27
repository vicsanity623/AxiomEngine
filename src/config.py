"""Manage tunable parameters for the Axiom Node via environment variables."""

# Axiom - config.py
# Copyright (C) 2026 The Axiom Contributors

import os


def _int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# --- Fact verification ---
# Number of distinct source domains required before a fact becomes "trusted".
# Example: 50 = faster verification, 200 = stricter.
REQUIRED_CORROBORATING_DOMAINS = _int(
    "AXIOM_REQUIRED_CORROBORATING_DOMAINS",
    100,
)

# --- Peer reputation ---
# Initial reputation for a newly discovered peer. Lower = trust earned slower.
PEER_REP_INITIAL = _float("AXIOM_PEER_REP_INITIAL", 0.2)

# Reputation change per failed sync (subtracted).
PEER_REP_PENALTY = _float("AXIOM_PEER_REP_PENALTY", 0.05)

# Reputation change per successful "up to date" sync. Smaller = longer to reach TRUSTED.
PEER_REP_REWARD_UPTIME = _float("AXIOM_PEER_REP_REWARD_UPTIME", 0.001)

# Multiplier for log10(1 + new_facts_count) when sync brings new facts.
PEER_REP_REWARD_NEW_DATA = _float("AXIOM_PEER_REP_REWARD_NEW_DATA", 0.01)

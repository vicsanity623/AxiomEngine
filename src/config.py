# Axiom - config.py
# Copyright (C) 2026 The Axiom Contributors
#
# Tunable parameters via environment variables. Restart the node after changing.
#
# Facts:
#   AXIOM_REQUIRED_CORROBORATING_DOMAINS  (int, default 100) – domains before "trusted"
#
# Peer reputation:
#   AXIOM_PEER_REP_INITIAL         (float, default 0.2)  – new peer starting rep
#   AXIOM_PEER_REP_PENALTY        (float, default 0.05) – per failed sync
#   AXIOM_PEER_REP_REWARD_UPTIME  (float, default 0.001)– per success, up-to-date
#   AXIOM_PEER_REP_REWARD_NEW_DATA (float, default 0.01)– factor for new-facts bonus

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
# Initial reputation for a newly discovered peer (0.0–1.0). Lower = trust earned slower.
PEER_REP_INITIAL = _float("AXIOM_PEER_REP_INITIAL", 0.2)

# Reputation change per failed sync (subtracted).
PEER_REP_PENALTY = _float("AXIOM_PEER_REP_PENALTY", 0.05)

# Reputation change per successful "up to date" sync. Smaller = longer to reach TRUSTED.
PEER_REP_REWARD_UPTIME = _float("AXIOM_PEER_REP_REWARD_UPTIME", 0.001)

# Multiplier for log10(1 + new_facts_count) when sync brings new facts.
PEER_REP_REWARD_NEW_DATA = _float("AXIOM_PEER_REP_REWARD_NEW_DATA", 0.01)

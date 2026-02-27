"""Axiom - self_check.py

Deterministic self-query checks for the /think endpoint.
These are light sanity checks, not full tests.
"""

from dataclasses import dataclass

import requests


@dataclass
class SelfCheckCase:
    query: str
    must_contain: list[str]


SELF_CHECKS: list[SelfCheckCase] = [
    SelfCheckCase(
        query="what is the lexical mesh",
        must_contain=["lexical mesh"],
    ),
    SelfCheckCase(
        query="explain the crucible",
        must_contain=["crucible"],
    ),
    SelfCheckCase(
        query="what can you do",
        must_contain=["ingest", "knowledge"],
    ),
]


def run_self_checks(base_url: str, timeout: float = 3.0) -> list[dict]:
    """Run a small suite of self-queries against /think and report pass/fail."""
    results: list[dict] = []
    for case in SELF_CHECKS:
        try:
            resp = requests.get(
                f"{base_url}/think",
                params={"query": case.query},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            answer = str(data.get("response", "")).lower()
            missing = [
                kw for kw in case.must_contain if kw.lower() not in answer
            ]
            ok = not missing
            results.append(
                {
                    "query": case.query,
                    "ok": ok,
                    "missing_keywords": missing,
                }
            )
        except Exception as e:
            results.append(
                {
                    "query": case.query,
                    "ok": False,
                    "error": str(e),
                }
            )
    return results

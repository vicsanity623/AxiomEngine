"""
Axiom - data_quality.py

Local-only helpers for fact deduplication and simple conflict detection.
These are designed for small, throttled idle tasks, not full offline jobs.
"""

import hashlib
import sqlite3
import zlib
from dataclasses import dataclass
from typing import Dict, List, Tuple


def _safe_text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        try:
            return zlib.decompress(raw).decode("utf-8")
        except Exception:
            try:
                return raw.decode("utf-8", errors="ignore")  # type: ignore[arg-type]
            except Exception:
                return ""
    return str(raw)


def _fingerprint(text: str) -> str:
    """Cheap, stable fingerprint for duplicate detection."""
    normalized = " ".join(text.strip().lower().split())[:512]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class DuplicateGroup:
    fingerprint: str
    fact_ids: List[str]


@dataclass
class ConflictGroup:
    subject: str
    predicate: str
    objects: List[str]
    fact_ids: List[str]


def find_duplicate_candidates(
    db_path: str,
    sample_size: int = 500,
) -> List[DuplicateGroup]:
    """
    Sample a subset of facts and group obvious duplicates by content fingerprint.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT fact_id, fact_content FROM facts ORDER BY RANDOM() LIMIT ?",
            (sample_size,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    buckets: Dict[str, List[str]] = {}
    for row in rows:
        text = _safe_text(row["fact_content"])
        if not text:
            continue
        fp = _fingerprint(text)
        buckets.setdefault(fp, []).append(row["fact_id"])

    return [
        DuplicateGroup(fingerprint=fp, fact_ids=fids)
        for fp, fids in buckets.items()
        if len(fids) > 1
    ]


def _parse_adl_triplet(text: str) -> Tuple[str, str, str]:
    """
    Very small helper for ADL-like 'subject|verb|object' strings.
    Returns (subject, verb, object) or empty strings if parsing fails.
    """
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3:
        return "", "", ""
    return parts[0], parts[1], parts[2]


def find_conflict_candidates(
    db_path: str,
    sample_size: int = 500,
) -> List[ConflictGroup]:
    """
    Look for simple conflicts where the same subject+predicate pair appears with
    multiple distinct objects in ADL-style facts.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT fact_id, fact_content FROM facts ORDER BY RANDOM() LIMIT ?",
            (sample_size,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    buckets: Dict[Tuple[str, str], Dict[str, List[str]]] = {}

    for row in rows:
        text = _safe_text(row["fact_content"])
        if not text:
            continue
        subj, pred, obj = _parse_adl_triplet(text)
        if not subj or not pred or not obj:
            continue
        key = (subj, pred)
        obj_map = buckets.setdefault(key, {})
        obj_map.setdefault(obj, []).append(row["fact_id"])

    conflicts: List[ConflictGroup] = []
    for (subj, pred), obj_map in buckets.items():
        if len(obj_map) <= 1:
            continue
        objects: List[str] = list(obj_map.keys())
        fact_ids: List[str] = []
        for fids in obj_map.values():
            fact_ids.extend(fids)
        conflicts.append(
            ConflictGroup(
                subject=subj,
                predicate=pred,
                objects=objects,
                fact_ids=fact_ids,
            )
        )

    return conflicts


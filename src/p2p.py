"""Confifgure the logic for the p2p mesh."""

import hashlib
import logging
import sqlite3
import zlib

import requests

from src.blockchain import (
    append_block,
    get_chain_head,
    replace_chain_with_peer_blocks,
)

logger = logging.getLogger(__name__)


def verify_hash(content, fact_id):
    """Ensure the fact ID is the mathematical hash of the content."""
    if not content or not fact_id:
        return False
    calculated_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return calculated_hash == fact_id


def sync_with_peer(node_instance, peer_url, db_path: str):
    """Synchronize the local ledger and the peer list. Implement 'Gossip Discovery' to ensure the network loop remains intact."""
    logger.info(
        f"\033[2m--- [P2P Sync] Attempting to sync with peer: {peer_url} ---\033[0m",
    )

    conn = None
    try:
        headers = {"X-Axiom-Peer": node_instance.advertised_url}

        try:
            peer_list_resp = requests.get(
                f"{peer_url}/get_peers",
                timeout=5,
                headers=headers,
            )
            if peer_list_resp.status_code == 200:
                discovered_peers = peer_list_resp.json().get("peers", {})
                for p_url in discovered_peers:
                    if p_url != node_instance.advertised_url:
                        node_instance.add_or_update_peer(p_url)
        except Exception:
            logger.debug(
                f"[P2P Discovery] Could not fetch peer list from {peer_url}",
            )

        response = requests.get(
            f"{peer_url}/get_fact_ids",
            timeout=10,
            headers=headers,
        )
        response.raise_for_status()
        peer_fact_ids = set(response.json().get("fact_ids", []))

        # USE THE PASSED db_path
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT fact_id FROM facts")
        local_fact_ids = {row[0] for row in cursor.fetchall()}

        missing_fact_ids = list(peer_fact_ids - local_fact_ids)

        if not missing_fact_ids:
            logger.info(
                f"\033[93m[P2P Sync] Ledger is already up-to-date with {peer_url}.\033[0m",
            )
            conn.close()
            return "SUCCESS_UP_TO_DATE", []

        logger.info(
            f"\033[92m[P2P Sync] Found {len(missing_fact_ids)} new facts. Requesting data...\033[0m",
        )

        chunk_size = 50
        facts_added_count = 0
        new_facts_payload = []

        for i in range(0, len(missing_fact_ids), chunk_size):
            chunk = missing_fact_ids[i : i + chunk_size]
            try:
                resp = requests.post(
                    f"{peer_url}/get_facts_by_id",
                    json={"fact_ids": chunk},
                    timeout=20,
                    headers=headers,
                )
                resp.raise_for_status()
                batch = resp.json().get("facts", [])
                new_facts_payload.extend(batch)
            except Exception as e:
                logger.error(
                    f"\033[91m[P2P Sync] Error fetching batch from {peer_url}: {e}\033[0m",
                )
                continue

        for fact in new_facts_payload:
            content_text = fact.get("fact_content") or ""
            if not verify_hash(content_text, fact.get("fact_id")):
                logger.warning(
                    f"\033[91m[P2P Security] WARNING: Peer {peer_url} sent invalid hash. Dropping.\033[0m",
                )
                continue

            incoming_trust = float(fact.get("trust_score", 0.1))
            sanitized_trust = min(incoming_trust, 0.5)

            try:
                try:
                    compressed_content = zlib.compress(
                        content_text.encode("utf-8")
                    )
                except Exception as e:
                    logger.warning(
                        f"\033[91m[P2P Sync] Could not compress incoming fact {fact.get('fact_id', '')[:8]} from {peer_url}: {e}\033[0m"
                    )
                    continue
                cursor.execute(
                    """
                    INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        fact["fact_id"],
                        compressed_content,
                        fact.get("source_url", "unknown_peer"),
                        fact.get("ingest_timestamp_utc"),
                        sanitized_trust,
                        "uncorroborated",
                    ),
                )
                facts_added_count += 1
            except sqlite3.IntegrityError:
                continue

        conn.commit()
        conn.close()

        if facts_added_count > 0:
            logger.info(
                f"\033[92m[P2P Sync] Sync success. Created {facts_added_count} new local records from {peer_url}.\033[0m",
            )
            return "SUCCESS_NEW_FACTS", new_facts_payload

        logger.info(
            f"\033[93m[P2P Sync] Completed with no new facts from {peer_url} (already up-to-date).\033[0m",
        )
        return "SUCCESS_UP_TO_DATE", []

    except requests.exceptions.RequestException:
        logger.error(
            f"\033[91m[P2P Sync] Connection failed with {peer_url}.\033[0m",
        )
        return "CONNECTION_FAILED", []
    except Exception as e:
        logger.error(f"\033[91m[P2P Sync] General error: {e}\033[0m")
        if conn:
            conn.close()
        return "SYNC_ERROR", []


def sync_chain_with_peer(node_instance, peer_url, db_path: str):
    """Sync blockchain from peer: if peer has a longer chain, fetch new blocks and append.

    Return (blocks_appended_count, peer_chain_height) for logging.
    """
    try:
        headers = {"X-Axiom-Peer": node_instance.advertised_url}
        head_resp = requests.get(
            f"{peer_url}/get_chain_head",
            timeout=5,
            headers=headers,
        )
        head_resp.raise_for_status()
        peer_head = head_resp.json()
        peer_height = int(peer_head.get("height", -1))
        peer_height = int(peer_head.get("height", -1))
        if peer_height < 0:
            return 0, peer_height

        # Use the same db_path as the rest of this node so that
        # chain height reflects the correct ledger file.
        our_head = get_chain_head(db_path=db_path)
        our_height = -1 if our_head is None else our_head[1]

        if peer_height <= our_height:
            return 0, peer_height

        # If peer is ahead, try incremental sync first.
        blocks_resp = requests.get(
            f"{peer_url}/get_blocks_after",
            params={"height": our_height},
            timeout=15,
            headers=headers,
        )
        blocks_resp.raise_for_status()
        blocks = blocks_resp.json().get("blocks", [])

        appended = 0
        for blk in blocks:
            if append_block(blk, db_path=db_path):
                appended += 1
            else:
                # Incremental append failed (divergence detected).
                # We must attempt to adopt the full chain if the peer is taller.
                if peer_height > our_height:
                    logger.warning(
                        f"[P2P Chain] Divergence detected. Attempting full chain adoption from {peer_url} (Height {peer_height})."
                    )
                    try:
                        full_resp = requests.get(
                            f"{peer_url}/get_blocks_after",
                            params={"height": 0},
                            timeout=15,
                            headers=headers,
                        )
                        full_resp.raise_for_status()
                        peer_blocks = full_resp.json().get("blocks", [])
                        if peer_blocks and replace_chain_with_peer_blocks(
                            peer_blocks, db_path=db_path
                        ):
                            logger.info(
                                f"\033[92m[P2P Chain] Adopted peer chain from {peer_url} (longest-chain wins, height now {peer_height}).\033[0m",
                            )
                            return len(peer_blocks), peer_height
                        logger.error(
                            "[P2P Chain] Chain adoption failed after divergence. Peer's full history starting at height 0 is unusable/inconsistent."
                        )
                    except Exception as e:
                        logger.debug(
                            f"[P2P Chain] Could not adopt peer chain: {e}"
                        )

                # Stop trying to append the rest of this partial batch
                break

        if appended > 0:
            logger.info(
                f"\033[92m[P2P Chain] Appended {appended} block(s) from {peer_url} (height now {our_height + appended}).\033[0m",
            )
        return appended, peer_height
    except requests.exceptions.RequestException as e:
        logger.debug(f"[P2P Chain] Could not sync chain from {peer_url}: {e}")
        return 0, -1
    except Exception as e:
        logger.warning(f"[P2P Chain] Chain sync error: {e}")
        return 0, -1

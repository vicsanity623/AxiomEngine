# Axiom - p2p.py
# Copyright (C) 2025 The Axiom Contributors
# This program is licensed under the Peer Production License (PPL).
# See the LICENSE file for full details.
# --- V3.0: SECURE SYNC WITH HASH VERIFICATION ---

import requests
import sqlite3
import hashlib
import logging
from ledger import DB_NAME

logger = logging.getLogger(__name__)

def verify_hash(content, fact_id):
    """
    Security Check: Ensures the fact ID is the mathematical hash of the content.
    Prevents peers from sending spoofed data.
    """
    if not content or not fact_id: return False
    # We must encode to utf-8 before hashing, matching the creation logic
    calculated_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    return calculated_hash == fact_id

def sync_with_peer(node_instance, peer_url):
    """
    Synchronizes the local ledger with a peer's ledger.
    Includes validation to reject corrupt or malicious data.
    """
    logger.info(f"\033[2m--- [P2P Sync] Attempting to sync with peer: {peer_url} ---\033[0m")
    
    conn = None
    try:
        # Step 1: Get the peer's list of all fact IDs (send our URL so peer can register us)
        headers = {"X-Axiom-Peer": node_instance.advertised_url}
        response = requests.get(f"{peer_url}/get_fact_ids", timeout=10, headers=headers)
        response.raise_for_status()
        peer_fact_ids = set(response.json().get('fact_ids', []))

        # Step 2: Get the local list of all fact IDs
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT fact_id FROM facts")
        local_fact_ids = set(row[0] for row in cursor.fetchall())
        
        # Step 3: Determine which facts are missing locally
        missing_fact_ids = list(peer_fact_ids - local_fact_ids)

        if not missing_fact_ids:
            logger.info(f"\033[93m[P2P Sync] Ledger is already up-to-date with {peer_url}.\033[0m")
            conn.close()
            return 'SUCCESS_UP_TO_DATE', []

        # Step 4: Request the full data for only the missing facts
        logger.info(f"\033[92m[P2P Sync] Found {len(missing_fact_ids)} new facts to download. Requesting data...\033[0m")
        
        # We request in chunks of 50 to avoid timeouts if there are thousands of new facts
        chunk_size = 50
        facts_added_count = 0
        new_facts_payload = []

        for i in range(0, len(missing_fact_ids), chunk_size):
            chunk = missing_fact_ids[i:i + chunk_size]
            
            try:
                resp = requests.post(
                    f"{peer_url}/get_facts_by_id", json={"fact_ids": chunk}, timeout=20, headers=headers
                )
                resp.raise_for_status()
                batch = resp.json().get('facts', [])
                new_facts_payload.extend(batch)
            except Exception as e:
                logger.error(f"\033[91m[P2P Sync] Error fetching batch from {peer_url}: {e}\033[0m")
                continue

        # Step 5: Insert and VALIDATE the new facts
        for fact in new_facts_payload:
            # SECURITY CHECK 1: Verify Hash
            if not verify_hash(fact.get('fact_content'), fact.get('fact_id')):
                logger.warning(f"\033[91m[P2P Security] WARNING: Peer {peer_url} sent fact with invalid hash. Dropping.\033[0m")
                continue

            # SECURITY CHECK 2: Sanitize Trust Score
            # We accept the peer's trust score, but we cap it at 0.5 to ensure 
            # local verification is required to reach full trust (1.0).
            incoming_trust = float(fact.get('trust_score', 0.1))
            sanitized_trust = min(incoming_trust, 0.5)

            try:
                cursor.execute("""
                    INSERT INTO facts (fact_id, fact_content, source_url, ingest_timestamp_utc, trust_score, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    fact['fact_id'], 
                    fact['fact_content'], 
                    fact.get('source_url', 'unknown_peer'), 
                    fact.get('ingest_timestamp_utc'),
                    sanitized_trust, 
                    'uncorroborated' # Always mark P2P data as uncorroborated initially
                ))
                facts_added_count += 1
            except sqlite3.IntegrityError:
                # Fact already exists (race condition), ignore.
                continue
            except Exception as e:
                logger.error(f"\033[91m[P2P Sync] Database insert error: {e}\033[0m")

        conn.commit()
        conn.close()
        
        if facts_added_count > 0:
            logger.info(f"\033[92m[P2P Sync] Successfully integrated {facts_added_count} new facts.\033[0m")
            return 'SUCCESS_NEW_FACTS', new_facts_payload
        else:
            return 'SUCCESS_UP_TO_DATE', []

    except requests.exceptions.RequestException as e:
        logger.error(f"\033[91m[P2P Sync] Connection failed with {peer_url}.\033[0m")
        return 'CONNECTION_FAILED', []
    except Exception as e:
        logger.error(f"\033[91m[P2P Sync] General error: {e}\033[0m")
        if conn: conn.close()
        return 'SYNC_ERROR', []
# Axiom - node.py
# Copyright (C) 2026 The Axiom Contributors

import logging
import math
import os
import random
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# --- IMPORT AXIOM MODULES ---
from src import (
    crucible,
    inference_engine,
    metacognitive_engine,
    synthesizer,
    universal_extractor,
    zeitgeist_engine,
)
from src.api_query import query_lexical_mesh, search_ledger_for_api
from src.axiom_logger import setup_logger
from src.ledger import (
    get_unprocessed_facts_for_lexicon,
    initialize_database,
    mark_fact_as_processed,
)
from src.blockchain import create_block, get_blocks_after, get_chain_head
from src.p2p import sync_chain_with_peer, sync_with_peer

setup_logger()
logger = logging.getLogger("node")

app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})
node_instance = None


def print_banner():
    c = "\033[96m"
    r = "\033[0m"
    print(c)
    print(r"""
╔═══════════════════════════════════════════════════════════════════════════════════════════════╗
   █████╗ ██╗  ██╗██╗ ██████╗ ███╗   ███╗      ███████╗███╗   ██╗ ██████╗ ██╗███╗   ██╗███████╗
  ██╔══██╗╚██╗██╔╝██║██╔═══██╗████╗ ████║      ██╔════╝████╗  ██║██╔════╝ ██║████╗  ██║██╔════╝
  ███████║ ╚███╔╝ ██║██║   ██║██╔████╔██║█████╗ █████╗  ██╔██╗ ██║██║  ███╗██║██╔██╗ ██║█████╗  
  ██╔══██║ ██╔██╗ ██║██║   ██║██║╚██╔╝██║╚════╝ ██╔══╝  ██║╚██╗██║██║   ██║██║██║╚██╗██║██╔══╝  
  ██║  ██║██╔╝ ██╗██║╚██████╔╝██║ ╚═╝ ██║       ███████╗██║ ╚████║╚██████╔╝██║██║ ╚████║███████╗
  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝     ╚═╝       ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝╚═╝  ╚═══╝╚══════╝

                                  ◈ AXIOM-ENGINE v3.3 ◈
╚═══════════════════════════════════════════════════════════════════════════════════════════════╝
""")
    print(r)


def _normalize_bootstrap_peer(raw_value, self_port):
    if not raw_value or not str(raw_value).strip():
        return None
    raw = str(raw_value).strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")
    if ":" in raw and not raw.replace(":", "").isdigit():
        return "http://" + raw if not raw.startswith("http") else raw
    if raw.isdigit():
        return f"http://127.0.0.1:{raw}"
    return "http://" + raw


class AxiomNode:
    def __init__(self, host="0.0.0.0", port=8009, bootstrap_peer=None):
        self.host = host
        self.port = port
        self.self_url = f"http://{self.host}:{port}"

        if port == 8009:
            self.advertised_url = (
                os.environ.get("ADVERTISED_URL")
                or "https://vics-imac-1.tail137b4f2.ts.net"
            )
        else:
            self.advertised_url = f"http://127.0.0.1:{port}"

        self.peers = {}
        self._topic_rotation_index = random.randint(0, 10)
        self._last_mesh_print = 0

        seed_nodes = ["https://vics-imac-1.tail137b4f2.ts.net"]
        for seed in seed_nodes:
            self.add_or_update_peer(seed)

        peer_url = _normalize_bootstrap_peer(bootstrap_peer, port)
        if peer_url:
            self.add_or_update_peer(peer_url)

        self.investigation_queue = []
        self.active_proposals = {}
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        self.db_path = os.environ.get("AXIOM_DB_PATH", "axiom_ledger.db")

        initialize_database(self.db_path)
        self.search_ledger_for_api = search_ledger_for_api

    def bootstrap_sync(self):
        if not self.peers:
            logger.info(
                "\033[92mNo bootstrap peers defined. Starting as Genesis Node.\033[0m",
            )
            return
        logger.info(
            "\033[93m[Init] Performing initial sync with bootstrap peers...\033[0m",
        )
        for peer_url in list(self.peers.keys()):
            try:
                sync_status, new_facts = sync_with_peer(
                    self,
                    peer_url,
                    self.db_path,
                )
                self._update_reputation(peer_url, sync_status, len(new_facts))
                sync_chain_with_peer(self, peer_url, self.db_path)
            except:
                pass

    def print_mesh_status(self):
        now = time.time()
        if now - self._last_mesh_print < 5:
            return
        self._last_mesh_print = now
        print()
        if not self.peers:
            logger.info("[Mesh] Waiting for incoming connections...")
        else:
            logger.info("\033[96m◈ Active Knowledge Mesh ◈\033[0m")
            sorted_peers = sorted(
                self.peers.items(),
                key=lambda item: item[1]["reputation"],
                reverse=True,
            )
            for peer, data in sorted_peers:
                rep = data["reputation"]
                color = (
                    "\033[92m"
                    if rep > 0.7
                    else ("\033[93m" if rep > 0.1 else "\033[96m")
                )
                status = (
                    "TRUSTED"
                    if rep > 0.7
                    else ("ACTIVE" if rep > 0.1 else "HANDSHAKE")
                )
                logger.info(
                    f"  {color}- {peer.ljust(45)} : {rep:.4f} [{status}]\033[0m",
                )
        print("-" * 60)

    def add_or_update_peer(self, peer_url):
        if not peer_url:
            return
        peer_url = peer_url.strip().rstrip("/")

        if peer_url == self.advertised_url or peer_url == self.self_url:
            return

        bootstrap_aliases = ["8009", "tail137b4f2.ts.net"]
        if any(alias in peer_url for alias in bootstrap_aliases):
            if self.port != 8009:
                peer_url = "http://127.0.0.1:8009"

        if peer_url in self.peers:
            self.peers[peer_url]["last_seen"] = datetime.now(
                UTC,
            ).isoformat()
            return

        from src.config import PEER_REP_INITIAL

        self.peers[peer_url] = {
            "reputation": PEER_REP_INITIAL,
            "first_seen": datetime.now(UTC).isoformat(),
            "last_seen": datetime.now(UTC).isoformat(),
        }
        logger.info(f"\033[92m[Mesh] New node identified: {peer_url}\033[0m")

        def immediate_handshake():
            time.sleep(2)
            try:
                sync_status, new_facts = sync_with_peer(
                    self,
                    peer_url,
                    self.db_path,
                )
                self._update_reputation(peer_url, sync_status, len(new_facts))
                self.print_mesh_status()
            except:
                pass

        threading.Thread(target=immediate_handshake, daemon=True).start()

    def _update_reputation(self, peer_url, sync_status, new_facts_count):
        if peer_url not in self.peers:
            return
        from src.config import (
            PEER_REP_PENALTY,
            PEER_REP_REWARD_NEW_DATA,
            PEER_REP_REWARD_UPTIME,
        )

        current_rep = self.peers[peer_url]["reputation"]
        if sync_status in ("CONNECTION_FAILED", "SYNC_ERROR"):
            new_rep = current_rep - PEER_REP_PENALTY
        elif sync_status == "SUCCESS_UP_TO_DATE":
            new_rep = current_rep + PEER_REP_REWARD_UPTIME
        elif sync_status == "SUCCESS_NEW_FACTS":
            new_rep = (
                current_rep
                + PEER_REP_REWARD_UPTIME
                + (
                    math.log10(1 + new_facts_count)
                    * PEER_REP_REWARD_NEW_DATA
                )
            )
        else:
            new_rep = current_rep
        self.peers[peer_url]["reputation"] = max(0.0, min(1.0, new_rep))

    def _fetch_from_peer(self, peer_url, search_term):
        try:
            query_url = f"{peer_url}/local_query?term={search_term}&include_uncorroborated=true"
            response = requests.get(query_url, timeout=5)
            response.raise_for_status()
            return response.json().get("results", [])
        except:
            return []

    def _reflection_cycle(self):
        logger.info(
            "\033[95m[Reflection] Starting Lexical Mesh integration... ---\033[0m",
        )
        unprocessed_facts = get_unprocessed_facts_for_lexicon()
        if not unprocessed_facts:
            logger.info("Success: Lexical Mesh is up to date.")
            return
        logger.info(
            f"[Reflection]Success. Shredding {len(unprocessed_facts)} facts into semantic synapses...",
        )
        for fact in unprocessed_facts:
            try:
                if crucible.integrate_fact_to_mesh(fact["fact_content"]):
                    mark_fact_as_processed(fact["fact_id"])
            except:
                pass
        logger.info(
            "Success: Neural pathways strengthened. Idle cycle complete.",
        )

    def _background_loop(self):
        logger.info("Starting continuous background cycle.")
        while True:
            logger.info("\033[2m[AXIOM ENGINE CYCLE START]\033[0m")
            newly_created_facts = []
            try:
                topics = zeitgeist_engine.get_trending_topics(top_n=100)
                if topics:
                    topic = topics[self._topic_rotation_index % len(topics)]
                    self._topic_rotation_index += 1
                    logger.info(
                        f"\033[96mSelected topic for this cycle: {topic}\033[0m",
                    )
                    content_list = universal_extractor.find_and_extract(
                        topic,
                        max_sources=3,
                    )
                    for item in content_list:
                        new_facts = crucible.extract_facts_from_text(
                            item["source_url"],
                            item["content"],
                        )
                        if new_facts:
                            newly_created_facts.extend(new_facts)
                    if newly_created_facts:
                        synthesizer.link_related_facts(newly_created_facts)
            except Exception as e:
                logger.error(f"Error: {e}")

            logger.info("\033[2m[AXIOM ENGINE CYCLE FINISH]\033[0m")

            if newly_created_facts:
                fact_ids = [f["fact_id"] for f in newly_created_facts]
                
                # Call create_block, which returns the block dict or None on failure/race
                new_block = create_block(fact_ids) 
                
                if new_block:
                    logger.info(f"\033[96m[Chain] Committed block HEIGHT {new_block['height']} with {len(fact_ids)} fact(s).\033[0m")
                else:
                    logger.warning(f"[Chain] Failed to commit block for {len(fact_ids)} facts. Check for race condition or duplicate ID.")

            for peer_url in list(self.peers.keys()):
                try:
                    sync_status, new_facts = sync_with_peer(
                        self,
                        peer_url,
                        self.db_path,
                    )
                    self._update_reputation(
                        peer_url,
                        sync_status,
                        len(new_facts),
                    )
                    sync_chain_with_peer(self, peer_url, self.db_path)
                except:
                    pass
            self._reflection_cycle()
            metacognitive_engine.run_metacognitive_cycle(self.db_path)
            self._prune_ledger()
            self.print_mesh_status()
            time.sleep(900)

    def _prune_ledger(self):
        """Deletes old, uncorroborated facts to manage node storage size."""
        PRUNE_THRESHOLD_DAYS = 1

        cutoff = datetime.now(UTC) - timedelta(days=PRUNE_THRESHOLD_DAYS)

        logger.info(
            f"[Housekeeping] Pruning facts older than {PRUNE_THRESHOLD_DAYS} days...",
        )

        # --- FIX: Use self.db_path instead of referencing undefined 'db_path' ---
        conn = sqlite3.connect(self.db_path) 
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM facts 
            WHERE ingest_timestamp_utc < ? 
            AND status = 'uncorroborated' 
            AND (corroborating_sources IS NULL OR corroborating_sources = '')
        """,
            (cutoff.isoformat(),),
        )

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info(
            f"[Housekeeping] Deleted {deleted_count} stale, uncorroborated records.",
        )

    def start_background_tasks(self):
        background_thread = threading.Thread(
            target=self._background_loop,
            daemon=True,
        )
        background_thread.start()


def _register_sync_caller():
    caller_url = (
        (request.headers.get("X-Axiom-Peer") or "").strip().rstrip("/")
    )
    if caller_url:
        node_instance.add_or_update_peer(caller_url)


@app.route("/local_query", methods=["GET"])
def handle_local_query():
    _register_sync_caller()
    search_term = request.args.get("term", "")
    include_uncorroborated = (
        request.args.get("include_uncorroborated", "false").lower() == "true"
    )
    results = node_instance.search_ledger_for_api(search_term, include_uncorroborated=include_uncorroborated, db_path=node_instance.db_path) 
    return jsonify({"results": results})


@app.route("/mesh_query", methods=["GET"])
def handle_mesh_query():
    search_term = request.args.get("term", "")
    data = query_lexical_mesh(search_term, db_path=node_instance.db_path)
    return jsonify(data)


@app.route("/get_peers", methods=["GET"])
def handle_get_peers():
    _register_sync_caller()
    return jsonify({"peers": node_instance.peers})


@app.route("/get_chain_head", methods=["GET"])
def handle_get_chain_head():
    _register_sync_caller()
    head = get_chain_head(db_path=node_instance.db_path)
    if head is None:
        return jsonify({"block_id": None, "height": -1})
    block_id, height = head
    return jsonify({"block_id": block_id, "height": height})


@app.route("/get_blocks_after", methods=["GET"])
def handle_get_blocks_after():
    _register_sync_caller()
    try:
        height = int(request.args.get("height", -1))
    except (TypeError, ValueError):
        height = -1
    blocks = get_blocks_after(height, db_path=node_instance.db_path)
    return jsonify({"blocks": blocks})


@app.route("/get_fact_ids", methods=["GET"])
def handle_get_fact_ids():
    _register_sync_caller()
    conn = sqlite3.connect(node_instance.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT fact_id FROM facts")
    fact_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({"fact_ids": fact_ids})


@app.route("/get_facts_by_id", methods=["POST"])
def handle_get_facts_by_id():
    _register_sync_caller()
    requested_ids = request.json.get("fact_ids", [])
    all_facts = node_instance.search_ledger_for_api(
        "",
        include_uncorroborated=True,
    )
    facts_to_return = [f for f in all_facts if f["fact_id"] in requested_ids]
    return jsonify({"facts": facts_to_return})


@app.route("/think", methods=["GET"])
def handle_thinking():
    query = request.args.get("query", "")
    if not query:
        return jsonify({"response": "System standby. Awaiting input."})

    answer = inference_engine.think(query, db_path=node_instance.db_path)
    return jsonify({"response": answer})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_static_files(path):
    if path != "" and os.path.exists(os.path.join(app.root_path, path)):
        return send_from_directory(app.root_path, path)
    # If the user types anything else, serve index.html
    return send_from_directory(app.root_path, "index.html")


@app.route("/sys_status", methods=["GET"])
def handle_sys_status():
    """Receives UI status updates (like mute state) from the web client."""
    muted = request.args.get("muted", "false").lower() == "true"
    if muted:
        logger.info("[SYS_INIT] Speech Synthesis: MUTED")
    else:
        logger.info("[SYS_INIT] Speech Synthesis: ACTIVE")
    return jsonify({"status": "received"})


if __name__ == "__main__":
    if node_instance is None:
        print_banner()
        port_val = int(os.environ.get("PORT", 8009))
        bootstrap_val = os.environ.get("BOOTSTRAP_PEER")
        node_instance = AxiomNode(port=port_val, bootstrap_peer=bootstrap_val)
        node_instance.bootstrap_sync()
        node_instance.start_background_tasks()
    logger.info(
        f"\033[2mAxiom Identity: {node_instance.advertised_url}\033[0m",
    )
    app.run(host="0.0.0.0", port=node_instance.port, debug=False)

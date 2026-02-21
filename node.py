# Axiom - node.py
# Copyright (C) 2025 The Axiom Contributors
# --- V3.0: CLEANED & INTEGRATED WITH NO-API MODULES ---

import time
import threading
import sys
import requests
import random
import math
import os
import traceback
import sqlite3
import logging
from flask import Flask, jsonify, request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# --- IMPORT AXIOM MODULES ---
import zeitgeist_engine
import universal_extractor
import crucible
import synthesizer
from ledger import initialize_database
from api_query import search_ledger_for_api
from p2p import sync_with_peer
from graph_export import to_json_for_viz
from axiom_logger import setup_logger
from axiom_model_loader import load_nlp_model

# --- SETUP LOGGING & GLOBAL CONFIG ---
setup_logger()
logger = logging.getLogger("node")
app = Flask(__name__)
node_instance = None

def print_banner():
    # Bright Cyan
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

                                  ◈ AXIOM-ENGINE v3.0 ◈
╚═══════════════════════════════════════════════════════════════════════════════════════════════╝
""")
    print(r)

def _normalize_bootstrap_peer(raw_value, self_port):
    """
    BOOTSTRAP_PEER must be a full URL so P2P can connect (e.g. http://192.168.0.4:5000).
    If only a port is given (e.g. 5000), convert to http://127.0.0.1:5000 for same-machine peers.
    """

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
    """
    A class representing a single, complete Axiom node.
    Manages the background learning cycle, peer synchronization, and API routing.
    """

    def __init__(self, host='0.0.0.0', port=5000, bootstrap_peer=None):
        self.host = host
        self.port = port
        self.self_url = f"http://{self.host}:{port}"
        self.advertised_url = os.environ.get("ADVERTISED_URL") or (
            f"http://127.0.0.1:{port}" if host == "0.0.0.0" else self.self_url
        )
        self.peers = {} 
        self._topic_rotation_index = random.randint(0, 10) 
        peer_url = _normalize_bootstrap_peer(bootstrap_peer, port)
        if peer_url:
            if (peer_url == self.self_url or peer_url == self.advertised_url or
                (f":{self.port}" in peer_url and ("127.0.0.1" in peer_url or "localhost" in peer_url))):
                logger.warning(f"Skipping bootstrap peer {peer_url} (cannot sync with self).")
            else:
                self.peers[peer_url] = {
                    "reputation": 0.5,
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "last_seen": datetime.now(timezone.utc).isoformat()
                }
                logger.info(f"\033[93mBootstrap peer registered: {peer_url}\033[0m")
        
        self.investigation_queue = [] 
        self.active_proposals = {}
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        
        initialize_database()
        self.search_ledger_for_api = search_ledger_for_api

    def bootstrap_sync(self):
        """
        NEW FUNCTION: Runs immediately on startup.
        Connects to the bootstrap peer to download the existing knowledge graph
        BEFORE starting the local learning loop.
        """
        if not self.peers:
            logger.info("No bootstrap peers defined. Starting fresh network.")
            return

        logger.info("\033[93m[Init] Performing initial sync with bootstrap peers...\033[0m")
        
        for peer_url in list(self.peers.keys()):
            try:
                sync_status, new_facts = sync_with_peer(self, peer_url)
                self._update_reputation(peer_url, sync_status, len(new_facts))
                
                if sync_status == 'SUCCESS_NEW_FACTS':
                    logger.info(f"[Init] Initial sync complete. Acquired {len(new_facts)} facts from network.")
                elif sync_status == 'SUCCESS_UP_TO_DATE':
                    logger.info(f"[Init] Node is already up to date with {peer_url}.")
            except Exception as e:
                logger.error(f"[Init] Failed to bootstrap from {peer_url}: {e}")

    def add_or_update_peer(self, peer_url):
        if peer_url and peer_url not in self.peers and peer_url != self.self_url and peer_url != self.advertised_url:
            self.peers[peer_url] = {
                "reputation": 0.1,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat()
            }
        elif peer_url in self.peers:
             self.peers[peer_url]['last_seen'] = datetime.now(timezone.utc).isoformat()

    def _update_reputation(self, peer_url, sync_status, new_facts_count):
        """Adjusts peer reputation based on sync results."""

        if peer_url not in self.peers: return
        
        REP_PENALTY = 0.1
        REP_REWARD_UPTIME = 0.02
        REP_REWARD_NEW_DATA = 0.1
        
        current_rep = self.peers[peer_url]['reputation']
        
        if sync_status in ('CONNECTION_FAILED', 'SYNC_ERROR'):
            new_rep = current_rep - REP_PENALTY
        elif sync_status == 'SUCCESS_UP_TO_DATE':
            new_rep = current_rep + REP_REWARD_UPTIME
        elif sync_status == 'SUCCESS_NEW_FACTS':
            new_rep = current_rep + REP_REWARD_UPTIME + (math.log10(1 + new_facts_count) * REP_REWARD_NEW_DATA)
        else:
            new_rep = current_rep
            
        self.peers[peer_url]['reputation'] = max(0.0, min(1.0, new_rep))

    def _fetch_from_peer(self, peer_url, search_term):
        try:
            query_url = f"{peer_url}/local_query?term={search_term}&include_uncorroborated=true"
            response = requests.get(query_url, timeout=5)
            response.raise_for_status()
            return response.json().get('results', [])
        except requests.exceptions.RequestException:
            return []

    def _background_loop(self):
        """
        The heartbeat of the node.
        1. Identifies what to learn (Zeitgeist).
        2. Extracts data (Universal Extractor).
        3. Processes data (Crucible).
        4. Links data (Synthesizer).
        5. Syncs with Peers (P2P).
        """

        logger.info("Starting continuous background cycle.")
        while True:
            # We use a visual separator for the log
            logger.info(f"\033[2m[AXIOM ENGINE CYCLE START]\033[0m")
            # --- PHASE 1: DISCOVERY & EXTRACTION ---
            try:
                topic_to_investigate = None
                
                if self.investigation_queue:
                    topic_to_investigate = self.investigation_queue.pop(0)
                else:
                    topics = zeitgeist_engine.get_trending_topics(top_n=5)
                    if topics:
                        topic_to_investigate = topics[self._topic_rotation_index % len(topics)]
                        self._topic_rotation_index += 1
                        logger.info(f"Selected topic for this cycle: {topic_to_investigate}")

                if topic_to_investigate:
                    content_list = universal_extractor.find_and_extract(topic_to_investigate, max_sources=3)
                    
                    newly_created_facts = []
                    for item in content_list:
                        new_facts = crucible.extract_facts_from_text(item['source_url'], item['content'])
                        if new_facts:
                            newly_created_facts.extend(new_facts)
                    
                    if newly_created_facts:
                        synthesizer.link_related_facts(newly_created_facts)

            except Exception as e:
                logger.error(f"CRITICAL ERROR IN LEARNING LOOP: {e}")
                traceback.print_exc()

            logger.info(f"\033[2m[AXIOM ENGINE CYCLE FINISH]\033[0m")
            
            # --- P2P SYNC ---
            sorted_peers = sorted(self.peers.items(), key=lambda item: item[1]['reputation'], reverse=True)
            
            for peer_url, peer_data in sorted_peers:
                try:
                    sync_status, new_facts = sync_with_peer(self, peer_url)
                    self._update_reputation(peer_url, sync_status, len(new_facts))
                except Exception as e:
                    logger.error(f"\033[91mUnexpected error syncing with {peer_url}: {e}\033[0m")

            # --- STATUS REPORT ---
            if not self.peers: 
                logger.info("\033[93mNo peers known.\033[0m")
            else:
                logger.info("\033[96m--- Peer Reputations ---\033[0m")
                for peer, data in sorted(self.peers.items(), key=lambda item: item[1]['reputation'], reverse=True):
                    logger.info(f"\033[96m  - {peer}: {data['reputation']:.4f}\033[0m")
            
            time.sleep(900)  

    def start_background_tasks(self):
        """Starts the background loop in a separate daemon thread."""

        background_thread = threading.Thread(target=self._background_loop, daemon=True)
        background_thread.start()

# ==============================================================================
#                                FLASK API ROUTES
# ==============================================================================
@app.route('/local_query', methods=['GET'])
def handle_local_query():
    search_term = request.args.get('term', '')
    include_uncorroborated = request.args.get('include_uncorroborated', 'false').lower() == 'true'
    results = node_instance.search_ledger_for_api(search_term, include_uncorroborated=include_uncorroborated)
    return jsonify({"results": results})

@app.route('/get_peers', methods=['GET'])
def handle_get_peers():
    return jsonify({'peers': node_instance.peers})

@app.route('/graph', methods=['GET'])
def handle_graph():
    """Knowledge graph as JSON for visualization. Optional ?topic=Trump to filter by term."""

    topic = request.args.get('topic', '').strip() or None
    data = to_json_for_viz(include_sources=True, topic_filter=topic)
    return jsonify(data)

def _register_sync_caller():
    """If the request includes X-Axiom-Peer, register that node as a peer (bidirectional discovery)."""

    caller_url = (request.headers.get("X-Axiom-Peer") or "").strip().rstrip("/")
    if not caller_url:
        return
    if caller_url == node_instance.self_url or caller_url == node_instance.advertised_url:
        return
    if f":{node_instance.port}" in caller_url and ("127.0.0.1" in caller_url or "localhost" in caller_url):
        return
    was_new = caller_url not in node_instance.peers
    node_instance.add_or_update_peer(caller_url)
    if was_new:
        logger.info(f"\033[92mRegistered new peer from sync: {caller_url}\033[0m")

@app.route('/get_fact_ids', methods=['GET'])
def handle_get_fact_ids():
    """Returns a list of all fact hashes this node possesses."""
    _register_sync_caller()
    conn = sqlite3.connect('axiom_ledger.db')
    cursor = conn.cursor()
    cursor.execute("SELECT fact_id FROM facts")
    fact_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'fact_ids': fact_ids})

@app.route('/get_facts_by_id', methods=['POST'])
def handle_get_facts_by_id():
    """Bulk retrieval of facts by ID for P2P syncing."""
    _register_sync_caller()
    requested_ids = request.json.get('fact_ids', [])
    all_facts = node_instance.search_ledger_for_api('', include_uncorroborated=True)
    facts_to_return = [fact for fact in all_facts if fact['fact_id'] in requested_ids]
    return jsonify({'facts': facts_to_return})

@app.route('/anonymous_query', methods=['POST'])
def handle_anonymous_query():
    """
    Onion-routing style query handler.
    If 'circuit' is empty, I am the exit node -> Perform query.
    If 'circuit' has nodes, I am a relay -> Forward to next node.
    """
    data = request.json
    search_term = data.get('term')
    circuit = data.get('circuit', [])
    sender_peer = data.get('sender_peer')
    
    node_instance.add_or_update_peer(sender_peer)
    
    if not circuit:
        # I am the Exit Node
        all_facts = {}
        # 1. Get local data
        local_results = node_instance.search_ledger_for_api(search_term, include_uncorroborated=True)
        for fact in local_results: 
            all_facts[fact['fact_id']] = fact
        
        # 2. Ask peers (Distributed Search)
        future_to_peer = {
            node_instance.thread_pool.submit(node_instance._fetch_from_peer, peer, search_term): peer 
            for peer in node_instance.peers
        }
        for future in future_to_peer:
            peer_results = future.result()
            for fact in peer_results:
                if fact['fact_id'] not in all_facts:
                    all_facts[fact['fact_id']] = fact
        
        return jsonify({"results": list(all_facts.values())})
    else:
        next_node_url = circuit.pop(0)
        try:
            payload = {
                'term': search_term, 
                'circuit': circuit, 
                'sender_peer': node_instance.self_url
            }
            response = requests.post(f"{next_node_url}/anonymous_query", json=payload, timeout=10)
            response.raise_for_status()
            return jsonify(response.json())
        except requests.exceptions.RequestException: 
            return jsonify({"error": f"Relay node {next_node_url} is offline."}), 504

@app.route('/dao/proposals', methods=['GET'])
def handle_get_proposals(): 
    return jsonify(node_instance.active_proposals)

@app.route('/dao/submit_proposal', methods=['POST'])
def handle_submit_proposal():
    data = request.json
    proposer_url = data.get('proposer_url')
    aip_id = data.get('aip_id')
    aip_text = data.get('aip_text')
    
    if not all([proposer_url, aip_id, aip_text]): 
        return jsonify({"status": "error", "message": "Missing parameters."}), 400
    
    if proposer_url in node_instance.peers and node_instance.peers[proposer_url]['reputation'] >= 0.75:
        if aip_id not in node_instance.active_proposals:
            node_instance.active_proposals[aip_id] = {
                "text": aip_text, 
                "proposer": proposer_url, 
                "votes": {}
            }
            return jsonify({"status": "success", "message": f"AIP {aip_id} submitted."})
        else: 
            return jsonify({"status": "error", "message": "Proposal ID already exists."}), 409
    else: 
        return jsonify({"status": "error", "message": "Insufficient reputation to submit proposals."}), 403

@app.route('/dao/submit_vote', methods=['POST'])
def handle_submit_vote():
    data = request.json
    voter_url = data.get('voter_url')
    aip_id = data.get('aip_id')
    vote_choice = data.get('choice') # 'yes' or 'no'
    
    if not all([voter_url, aip_id, vote_choice]): 
        return jsonify({"status": "error", "message": "Missing parameters."}), 400
    
    if aip_id not in node_instance.active_proposals: 
        return jsonify({"status": "error", "message": "Proposal not found."}), 404
    
    voter_data = node_instance.peers.get(voter_url)
    if not voter_data: 
        return jsonify({"status": "error", "message": "Unknown peer."}), 403
    
    voter_reputation = voter_data.get('reputation', 0)
    
    node_instance.active_proposals[aip_id]['votes'][voter_url] = {
        "choice": vote_choice, 
        "weight": voter_reputation
    }
    return jsonify({"status": "success", "message": "Vote recorded."})

if __name__ == "__main__" or "gunicorn" in sys.modules:
    if node_instance is None:
        print_banner()
        is_production = "gunicorn" in sys.modules
        logger.info(f"Initializing global instance for {'PRODUCTION' if is_production else 'DEVELOPMENT'}...")
        
        port_val = int(os.environ.get("PORT", 5000))
        bootstrap_val = os.environ.get("BOOTSTRAP_PEER")
        node_instance = AxiomNode(port=port_val, bootstrap_peer=bootstrap_val)
        node_instance.bootstrap_sync()
        node_instance.start_background_tasks()

if __name__ == "__main__":
    logger.info("Starting Flask Development Server...")
    app.run(host='0.0.0.0', port=node_instance.port, debug=False)
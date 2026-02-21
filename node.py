# Axiom - node.py
# Copyright (C) 2025 The Axiom Contributors

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
from flask_cors import CORS

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

setup_logger()
logger = logging.getLogger("node")

app = Flask(__name__)
CORS(app)

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

                                  ◈ AXIOM-ENGINE v3.1 ◈
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
    def __init__(self, host='0.0.0.0', port=8009, bootstrap_peer=None):
        self.host = host
        self.port = port
        self.self_url = f"http://{self.host}:{port}"
        self.advertised_url = os.environ.get("ADVERTISED_URL") or "https://vics-imac-1.tail137b4f2.ts.net"
        
        self.peers = {} 
        self._topic_rotation_index = random.randint(0, 10) 
        
        peer_url = _normalize_bootstrap_peer(bootstrap_peer, port)
        if peer_url:
            if (peer_url == self.self_url or peer_url == self.advertised_url):
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
        if not self.peers:
            logger.info("No bootstrap peers defined. Operating as Genesis Node.")
            return

        logger.info("\033[93m[Init] Performing initial sync with bootstrap peers...\033[0m")
        for peer_url in list(self.peers.keys()):
            try:
                sync_status, new_facts = sync_with_peer(self, peer_url)
                self._update_reputation(peer_url, sync_status, len(new_facts))
                if sync_status == 'SUCCESS_NEW_FACTS':
                    logger.info(f"[Init] Initial sync complete. Acquired {len(new_facts)} facts.")
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
        if peer_url not in self.peers: return
        REP_PENALTY, REP_REWARD_UPTIME, REP_REWARD_NEW_DATA = 0.1, 0.02, 0.1
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
        except: return []

    def _background_loop(self):
        logger.info("Starting continuous background cycle.")
        while True:
            logger.info(f"\033[2m[AXIOM ENGINE CYCLE START]\033[0m")
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
                        if new_facts: newly_created_facts.extend(new_facts)
                    if newly_created_facts: synthesizer.link_related_facts(newly_created_facts)
            except Exception as e:
                logger.error(f"CRITICAL ERROR IN LOOP: {e}")
            
            logger.info(f"\033[2m[AXIOM ENGINE CYCLE FINISH]\033[0m")
            
            # P2P SYNC
            for peer_url, _ in list(self.peers.items()):
                try:
                    sync_status, new_facts = sync_with_peer(self, peer_url)
                    self._update_reputation(peer_url, sync_status, len(new_facts))
                except: pass

            time.sleep(900)  

    def start_background_tasks(self):
        background_thread = threading.Thread(target=self._background_loop, daemon=True)
        background_thread.start()

# --- API ROUTES ---
@app.route('/local_query', methods=['GET'])
def handle_local_query():
    search_term = request.args.get('term', '')
    include_uncorroborated = request.args.get('include_uncorroborated', 'false').lower() == 'true'
    results = node_instance.search_ledger_for_api(search_term, include_uncorroborated=include_uncorroborated)
    return jsonify({"results": results})

@app.route('/get_peers', methods=['GET'])
def handle_get_peers():
    return jsonify({'peers': node_instance.peers})

def _register_sync_caller():
    caller_url = (request.headers.get("X-Axiom-Peer") or "").strip().rstrip("/")
    if not caller_url or caller_url == node_instance.advertised_url: return
    node_instance.add_or_update_peer(caller_url)

@app.route('/get_fact_ids', methods=['GET'])
def handle_get_fact_ids():
    _register_sync_caller()
    conn = sqlite3.connect('axiom_ledger.db')
    cursor = conn.cursor()
    cursor.execute("SELECT fact_id FROM facts")
    fact_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'fact_ids': fact_ids})

@app.route('/get_facts_by_id', methods=['POST'])
def handle_get_facts_by_id():
    _register_sync_caller()
    requested_ids = request.json.get('fact_ids', [])
    all_facts = node_instance.search_ledger_for_api('', include_uncorroborated=True)
    facts_to_return = [f for f in all_facts if f['fact_id'] in requested_ids]
    return jsonify({'facts': facts_to_return})

# --- BOOTSTRAP LOGIC ---
if __name__ == "__main__" or "gunicorn" in sys.modules:
    if node_instance is None:
        print_banner()
        # Set port to 8009 to match your Tailscale Funnel setup
        port_val = int(os.environ.get("PORT", 8009))
        bootstrap_val = os.environ.get("BOOTSTRAP_PEER")
        
        node_instance = AxiomNode(port=port_val, bootstrap_peer=bootstrap_val)
        node_instance.bootstrap_sync()
        node_instance.start_background_tasks()

if __name__ == "__main__":
    logger.info(f"Axiom Funnel Active: {node_instance.advertised_url}")
    app.run(host='0.0.0.0', port=node_instance.port, debug=False)
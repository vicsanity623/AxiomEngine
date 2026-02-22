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
from ledger import initialize_database, get_unprocessed_facts_for_lexicon, mark_fact_as_processed
from api_query import search_ledger_for_api, query_lexical_mesh
from p2p import sync_with_peer
from graph_export import to_json_for_viz
from axiom_logger import setup_logger
from axiom_model_loader import load_nlp_model

setup_logger()
logger = logging.getLogger("node")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

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
    def __init__(self, host='0.0.0.0', port=8009, bootstrap_peer=None):
        self.host = host
        self.port = port
        self.self_url = f"http://{self.host}:{port}"
        
        # Identity Logic
        if port == 8009:
            self.advertised_url = os.environ.get("ADVERTISED_URL") or "https://vics-imac-1.tail137b4f2.ts.net"
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
        
        initialize_database()
        self.search_ledger_for_api = search_ledger_for_api

    def bootstrap_sync(self):
        if not self.peers:
            logger.info("\033[92mNo bootstrap peers defined. Starting as Genesis Node.\033[0m")
            return
        logger.info("\033[93m[Init] Performing initial sync with bootstrap peers...\033[0m")
        for peer_url in list(self.peers.keys()):
            try:
                sync_status, new_facts = sync_with_peer(self, peer_url)
                self._update_reputation(peer_url, sync_status, len(new_facts))
            except: pass

    def print_mesh_status(self):
        now = time.time()
        if now - self._last_mesh_print < 5: return
        self._last_mesh_print = now
        print("")
        if not self.peers:
            logger.info("\033[90m[Mesh] Waiting for incoming connections...\033[0m")
        else:
            logger.info("\033[96m◈ Active Knowledge Mesh ◈\033[0m")
            sorted_peers = sorted(self.peers.items(), key=lambda item: item[1]['reputation'], reverse=True)
            for peer, data in sorted_peers:
                rep = data['reputation']
                color = "\033[92m" if rep > 0.7 else ("\033[93m" if rep > 0.1 else "\033[96m")
                status = "TRUSTED" if rep > 0.7 else ("ACTIVE" if rep > 0.1 else "HANDSHAKE")
                logger.info(f"  {color}- {peer.ljust(45)} : {rep:.4f} [{status}]\033[0m")
        print("-" * 60)

    def add_or_update_peer(self, peer_url):
        if not peer_url: return
        peer_url = peer_url.strip().rstrip("/")
        
        # 1. ME CHECK
        if peer_url == self.advertised_url or peer_url == self.self_url:
            return

        bootstrap_aliases = ["8009", "tail137b4f2.ts.net"]
        if any(alias in peer_url for alias in bootstrap_aliases):
            if self.port != 8009:
                peer_url = "http://127.0.0.1:8009"

        # 3. DEDUPLICATE
        if peer_url in self.peers:
             self.peers[peer_url]['last_seen'] = datetime.now(timezone.utc).isoformat()
             return

        # 4. REGISTER
        self.peers[peer_url] = {
            "reputation": 0.5, 
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_seen": datetime.now(timezone.utc).isoformat()
        }
        logger.info(f"\033[92m[Mesh] New node identified: {peer_url}\033[0m")
        
        def immediate_handshake():
            time.sleep(2)
            try:
                sync_status, new_facts = sync_with_peer(self, peer_url)
                self._update_reputation(peer_url, sync_status, len(new_facts))
                self.print_mesh_status() 
            except: pass
        
        threading.Thread(target=immediate_handshake, daemon=True).start()

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

    def _reflection_cycle(self):
        logger.info("\033[95m[Reflection] Starting Lexical Mesh integration... ---\033[0m")
        unprocessed_facts = get_unprocessed_facts_for_lexicon()
        if not unprocessed_facts:
            logger.info("Success: Lexical Mesh is up to date.")
            return
        logger.info(f"\033[96m[Reflection] Shredding {len(unprocessed_facts)} facts into semantic synapses...\033[0m")
        for fact in unprocessed_facts:
            try:
                if crucible.integrate_fact_to_mesh(fact['fact_content']):
                    mark_fact_as_processed(fact['fact_id'])
            except: pass
        logger.info("Success: Neural pathways strengthened. Idle cycle complete.")

    def _background_loop(self):
        logger.info("Starting continuous background cycle.")
        while True:
            logger.info(f"\033[2m[AXIOM ENGINE CYCLE START]\033[0m")
            try:
                topics = zeitgeist_engine.get_trending_topics(top_n=5)
                if topics:
                    topic = topics[self._topic_rotation_index % len(topics)]
                    self._topic_rotation_index += 1
                    logger.info(f"\033[96mSelected topic for this cycle: {topic}\033[0m")
                    content_list = universal_extractor.find_and_extract(topic, max_sources=3)
                    newly_created_facts = []
                    for item in content_list:
                        new_facts = crucible.extract_facts_from_text(item['source_url'], item['content'])
                        if new_facts: newly_created_facts.extend(new_facts)
                    if newly_created_facts: synthesizer.link_related_facts(newly_created_facts)
            except Exception as e:
                logger.error(f"Error: {e}")

            logger.info(f"\033[2m[AXIOM ENGINE CYCLE FINISH]\033[0m")
            for peer_url in list(self.peers.keys()):
                try:
                    sync_status, new_facts = sync_with_peer(self, peer_url)
                    self._update_reputation(peer_url, sync_status, len(new_facts))
                except: pass
            self._reflection_cycle()
            self.print_mesh_status()
            time.sleep(900)

    def start_background_tasks(self):
        background_thread = threading.Thread(target=self._background_loop, daemon=True)
        background_thread.start()

# --- API ROUTES ---

def _register_sync_caller():
    caller_url = (request.headers.get("X-Axiom-Peer") or "").strip().rstrip("/")
    if caller_url:
        node_instance.add_or_update_peer(caller_url)

@app.route('/local_query', methods=['GET'])
def handle_local_query():
    _register_sync_caller()
    search_term = request.args.get('term', '')
    include_uncorroborated = request.args.get('include_uncorroborated', 'false').lower() == 'true'
    results = node_instance.search_ledger_for_api(search_term, include_uncorroborated=include_uncorroborated)
    return jsonify({"results": results})

@app.route('/mesh_query', methods=['GET'])
def handle_mesh_query():
    search_term = request.args.get('term', '')
    data = query_lexical_mesh(search_term)
    return jsonify(data)

@app.route('/get_peers', methods=['GET'])
def handle_get_peers():
    _register_sync_caller()
    return jsonify({'peers': node_instance.peers})

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

@app.route('/')
def serve_index():
    try:
        with open('index.html', 'r') as f:
            return f.read()
    except:
        return "index.html not found.", 404

if __name__ == "__main__":
    if node_instance is None:
        print_banner()
        port_val = int(os.environ.get("PORT", 8009))
        bootstrap_val = os.environ.get("BOOTSTRAP_PEER")
        node_instance = AxiomNode(port=port_val, bootstrap_peer=bootstrap_val)
        node_instance.bootstrap_sync()
        node_instance.start_background_tasks()
    logger.info(f"\033[2mAxiom Identity: {node_instance.advertised_url}\033[0m")
    app.run(host='0.0.0.0', port=node_instance.port, debug=False)
"""Node - Implementation of a single, P2P-enabled node of the Axiom fact network."""

from __future__ import annotations

# Copyright (C) 2025 The Axiom Contributors
# This program is licensed under the Peer Production License (PPL).
# See the LICENSE file for full details.
import argparse
import hashlib
import json
import logging
import random
import sys
import threading
import time
from datetime import datetime
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from axiom_server import (
    crucible,
    discovery_rss,
    merkle,
    verification_engine,
    zeitgeist_engine,
)
from axiom_server.api_query import semantic_search_ledger
from axiom_server.crucible import _extract_dates
from axiom_server.hasher import FactIndexer
from axiom_server.ledger import (
    ENGINE,
    Block,
    Entity,
    Fact,
    FactLink,
    Peer,
    Proposal,
    SerializedFact,
    SessionMaker,
    Source,
    add_block_from_peer_data,
    create_genesis_block,
    get_chain_as_dicts,
    get_latest_block,
    initialize_database,
    replace_chain,
)
from axiom_server.p2p.constants import (
    BOOTSTRAP_IP_ADDR,
    BOOTSTRAP_PORT,
)
from axiom_server.p2p.node import (
    ApplicationData,
    Message,
    Node as P2PBaseNode,
    PeerLink,
)

__version__ = "3.2.0" # Version bump for new reputation model

logger = logging.getLogger("axiom-node")
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(
        "[%(name)s] %(asctime)s | %(levelname)s | %(filename)s:%(lineno)s >>> %(message)s",
    )
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)
logger.propagate = False
background_thread_logger = logging.getLogger("axiom-node.background-thread")

# ==============================================================================
# === NEW ADVANCED REPUTATION CONSTANTS ========================================
# ==============================================================================
REWARD_GOOD_BLOCK = 0.00000001
REWARD_SHARED_PEERS = 0.000000005
PENALTY_BAD_DATA = -0.02
PENALTY_CONNECTION_SPAM = -0.02
CONNECTION_COOLDOWN_SECONDS = 3600  # 1 hour
TERMINATION_THRESHOLD = 0.0
STARTING_REPUTATION = 0.1
# ==============================================================================

CORROBORATION_THRESHOLD = 2
db_lock = threading.Lock()
fact_indexer_lock = threading.Lock()
fact_indexer: FactIndexer | None = None

# ==============================================================================
# === NEW ADVANCED REPUTATION MANAGEMENT FUNCTIONS =============================
# ==============================================================================
def get_or_create_peer(session, public_key: str, ip: str, port: int) -> Peer | None:
    """Finds a peer, creates one if new, and checks for connection spam."""
    if not public_key:
        return None
    
    peer = session.query(Peer).filter(Peer.public_key == public_key).first()
    current_time = time.time()
    
    if peer:
        # Check for connection spam (reboot abuse)
        time_since_last_connect = current_time - peer.last_connection_time
        if 0 < time_since_last_connect < CONNECTION_COOLDOWN_SECONDS:
            logger.warning(f"Peer {public_key[:10]}... connected too frequently. Applying penalty.")
            change_reputation(session, public_key, PENALTY_CONNECTION_SPAM)
        
        peer.last_seen = datetime.now(datetime.UTC).isoformat()
        peer.last_known_ip = ip
        peer.last_known_port = port
        peer.last_connection_time = current_time
    else:
        peer = Peer(
            public_key=public_key,
            last_known_ip=ip,
            last_known_port=port,
            reputation_score=STARTING_REPUTATION,
            last_connection_time=current_time
        )
        session.add(peer)
        logger.info(f"New peer discovered and added to reputation database: {public_key[:10]}...")
    return peer

def change_reputation(session, public_key: str, amount: float):
    """Changes a peer's score, clamping it between 0.0 and 1.0."""
    if not public_key:
        return
        
    peer = session.query(Peer).filter(Peer.public_key == public_key).first()
    if peer:
        new_score = peer.reputation_score + amount
        # Clamp the score to the 0-1 range
        peer.reputation_score = max(0.0, min(1.0, new_score))
        logger.info(f"Updated reputation for peer {peer.public_key[:10]}... by {amount:+.8f}. New score: {peer.reputation_score:.8f}")

def log_peer_reputation_summary(session):
    """Logs a summary of all known peer reputations."""
    background_thread_logger.info("--- Peer Reputation Summary ---")
    all_peers = session.query(Peer).order_by(Peer.reputation_score.desc()).all()
    if not all_peers:
        background_thread_logger.info("No peers in reputation database.")
        return
    for peer in all_peers:
        status = "TERMINATED" if peer.reputation_score <= TERMINATION_THRESHOLD else "Active"
        background_thread_logger.info(f"  - Peer: {peer.public_key[:15]}... | Score: {peer.reputation_score:.8f} | Status: {status}")
    background_thread_logger.info("-----------------------------")

# ==============================================================================
# === AXIOM NODE CLASS (MODIFIED FOR ADVANCED REPUTATION) ======================
# ==============================================================================
class AxiomNode(P2PBaseNode):
    """A class representing a single Axiom node, inheriting P2P capabilities."""

    def __init__(self, host: str, port: int, bootstrap_peer: str | None, public_ip: str | None) -> None:
        logger.info(f"Initializing Axiom Node on {host}:{port}")
        temp_p2p = P2PBaseNode.start(ip_address=host, port=port)
        super().__init__(
            ip_address=temp_p2p.ip_address, port=temp_p2p.port, public_ip=temp_p2p.public_ip,
            serialized_port=temp_p2p.serialized_port, private_key=temp_p2p.private_key,
            public_key=temp_p2p.public_key, serialized_public_key=temp_p2p.serialized_public_key,
            peer_links=temp_p2p.peer_links, server_socket=temp_p2p.server_socket
        )
        self.peer_links_lock = threading.Lock()
        self.initial_sync_complete = threading.Event()
        self.bootstrap_peer = bootstrap_peer
        self.new_block_received = threading.Event()
        self.active_proposals: dict[int, Proposal] = {}
        initialize_database(ENGINE)
        with SessionMaker() as session:
            create_genesis_block(session)
        if bootstrap_peer:
            parsed_url = urlparse(bootstrap_peer)
            bootstrap_host = parsed_url.hostname or BOOTSTRAP_IP_ADDR
            bootstrap_port = parsed_url.port or BOOTSTRAP_PORT
            threading.Thread(target=self.bootstrap, args=(bootstrap_host, bootstrap_port), daemon=True).start()

    def _handle_application_message(
        self,
        peer_link: PeerLink,
        content: ApplicationData,
    ) -> None:
        """Dispatch all high-level P2P messages, now with advanced reputation checks."""
        try:
            # --- THIS IS THE FIX ---
            # Correctly serialize the public key object to a string for database use.
            if peer_link.peer.public_key:
                # Use the utility function to reliably convert the key object to a PEM string
                peer_pub_key_str = _serialize_public_key(peer_link.peer.public_key).decode('utf-8')
            else:
                peer_pub_key_str = None
            # --- END OF FIX ---
            
            with db_lock, SessionMaker() as session:
                # The get_or_create_peer function now receives the correct string format
                peer_record = get_or_create_peer(session, peer_pub_key_str, peer_link.peer.ip_address, peer_link.peer.port)
                
                if peer_record and peer_record.reputation_score <= TERMINATION_THRESHOLD:
                    logger.warning(f"TERMINATED: Ignoring message from peer {peer_pub_key_str[:10]}... due to zero reputation score.")
                    return

                message = json.loads(content.data)
                msg_type = message.get("type")

                if msg_type == "CHAIN_RESPONSE":
                    logger.info("Received full blockchain from peer. Beginning sync process...")
                    chain_data = message.get("chain")
                    if not chain_data:
                        logger.warning("CHAIN_RESPONSE received but contained no 'chain' data.")
                        return
                    success = replace_chain(session, chain_data)
                    if success:
                        logger.info("Blockchain synchronization successful!")
                        self.initial_sync_complete.set()
                        change_reputation(session, peer_pub_key_str, REWARD_GOOD_BLOCK * 10) # Major reward
                    else:
                        logger.error("Blockchain synchronization failed.")
                        change_reputation(session, peer_pub_key_str, PENALTY_BAD_DATA)

                elif msg_type == "GET_CHAIN_REQUEST":
                    logger.info(f"Peer {message.get('peer_addr')} requested our blockchain. Sending response...")
                    chain_data_json_str = self._get_chain_for_peer()
                    self._send_message(peer_link, Message.application_data(chain_data_json_str))

                elif msg_type == "new_block_header":
                    msg_data = message.get("data")
                    new_block = add_block_from_peer_data(session, msg_data)
                    if new_block:
                        self.new_block_received.set()
                        change_reputation(session, peer_pub_key_str, REWARD_GOOD_BLOCK)
                    else:
                        change_reputation(session, peer_pub_key_str, PENALTY_BAD_DATA)
                
                # Also reward for sharing peers, which was missing from the application message handler
                elif msg_type == "PEERS_SHARING":
                    change_reputation(session, peer_pub_key_str, REWARD_SHARED_PEERS)

                session.commit()

        except Exception as e:
            background_thread_logger.error(f"Error processing peer message: {e}")

    def _background_work_loop(self) -> None:
        """The main work cycle for the node."""
        if self.bootstrap_peer:
            logger.info("Worker node started. Waiting for initial blockchain sync...")
            synced = self.initial_sync_complete.wait(timeout=60.0)
            if not synced:
                logger.warning("Initial sync timed out. Proceeding with local chain.")
            else:
                logger.info("Initial sync complete.")
        background_thread_logger.info("Starting continuous Axiom work cycle.")
        while True:
            background_thread_logger.info("Axiom engine cycle start: Listening for new content...")
            new_block_candidate, latest_block_before_mining, facts_sealed_in_block = None, None, []
            with db_lock, SessionMaker() as session:
                try:
                    topics = zeitgeist_engine.get_trending_topics(top_n=1)
                    content_list = discovery_rss.get_content_from_prioritized_feed() if topics else []
                    if not content_list:
                        background_thread_logger.info("No new content found. Proceeding to verification phase.")
                    else:
                        facts_for_sealing = []
                        adder = crucible.CrucibleFactAdder(session, fact_indexer)
                        for item in content_list:
                            domain = urlparse(item["source_url"]).netloc
                            source = session.query(Source).filter(Source.domain == domain).one_or_none() or Source(domain=domain)
                            session.add(source)
                            new_facts = crucible.extract_facts_from_text(item["content"])
                            for fact in new_facts:
                                fact.hash = hashlib.sha256(fact.content.encode("utf-8")).hexdigest()
                                fact.sources.append(source)
                                facts_for_sealing.append(fact)
                            session.commit()
                            with fact_indexer_lock:
                                for fact in new_facts:
                                    adder.add(fact)
                        if facts_for_sealing:
                            background_thread_logger.info(f"Preparing to mine a new block with {len(facts_for_sealing)} facts...")
                            latest_block_before_mining = get_latest_block(session)
                            fact_hashes = sorted([f.hash for f in facts_for_sealing])
                            new_block_candidate = Block(height=latest_block_before_mining.height + 1, previous_hash=latest_block_before_mining.hash, fact_hashes=json.dumps(fact_hashes), timestamp=time.time())
                            facts_sealed_in_block = facts_for_sealing
                except Exception as e:
                    background_thread_logger.exception(f"Error during fact gathering: {e}")
            if new_block_candidate:
                self.new_block_received.clear()
                was_sealed = self.seal_block_interruptibly(new_block_candidate, difficulty=4)
                if was_sealed:
                    with db_lock, SessionMaker() as session:
                        current_chain_head = get_latest_block(session)
                        if current_chain_head.height > latest_block_before_mining.height:
                            background_thread_logger.warning("Mined a block, but the chain grew. Discarding our block (stale).")
                        else:
                            session.add(new_block_candidate)
                            session.commit()
                            background_thread_logger.info(f"Successfully sealed and added Block #{new_block_candidate.height}.")
                            broadcast_data = {"type": "new_block_header", "data": new_block_candidate.to_dict()}
                            self.broadcast_application_message(json.dumps(broadcast_data))
                            background_thread_logger.info("Broadcasted new block header to network.")
                            if facts_sealed_in_block:
                                background_thread_logger.info(f"Updating search index with {len(facts_sealed_in_block)} new facts...")
                                with fact_indexer_lock:
                                    fact_indexer.add_facts(facts_sealed_in_block)
                                background_thread_logger.info("Search index update complete.")
                else:
                    background_thread_logger.info("Mining was interrupted. Abandoning our work.")
            with db_lock, SessionMaker() as session:
                try:
                    background_thread_logger.info("Starting verification phase...")
                    facts_to_verify = session.query(Fact).filter(Fact.status == "ingested").all()
                    if not facts_to_verify:
                        background_thread_logger.info("No new facts to verify.")
                    else:
                        background_thread_logger.info(f"Found {len(facts_to_verify)} facts to verify.")
                        for fact in facts_to_verify:
                            claims = verification_engine.find_corroborating_claims(fact, session)
                            if len(claims) >= CORROBORATION_THRESHOLD:
                                fact.status = "corroborated"
                                background_thread_logger.info(f"Fact '{fact.hash[:8]}' has been corroborated with {len(claims)} pieces of evidence.")
                                fact.score += 10
                        session.commit()
                except Exception as e:
                    background_thread_logger.exception(f"Error during verification phase: {e}")
                
                log_peer_reputation_summary(session) # Log summary before sleeping
            background_thread_logger.info("Axiom cycle finished. Sleeping.")
            time.sleep(10800)

    def seal_block_interruptibly(self, block: Block, difficulty: int) -> bool:
        fact_hashes_list = json.loads(block.fact_hashes)
        block.merkle_root = merkle.MerkleTree(fact_hashes_list).root.hex() if fact_hashes_list else hashlib.sha256(b"").hexdigest()
        target = "0" * difficulty
        while True:
            if block.nonce % 1000 == 0 and self.new_block_received.is_set(): return False
            block.hash = block.calculate_hash()
            if block.hash.startswith(target):
                logger.info(f"Block sealed! Hash: {block.hash}")
                return True
            block.nonce += 1

    def start(self) -> None:
        work_thread = threading.Thread(target=self._background_work_loop, daemon=True)
        peer_thread = threading.Thread(target=self._peer_management_loop, daemon=True)
        work_thread.start()
        peer_thread.start()
        logger.info("Starting P2P network update loop...")
        while True:
            time.sleep(0.1)
            self.update()

    def _get_chain_for_peer(self) -> str:
        with db_lock, SessionMaker() as session:
            chain_dicts = get_chain_as_dicts(session)
            return json.dumps({"type": "CHAIN_RESPONSE", "chain": chain_dicts})

    def _peer_management_loop(self) -> None:
        logger.info("Starting peer management loop.")
        while True:
            try:
                with db_lock, SessionMaker() as session:
                    high_reputation_peers = session.query(Peer).filter(Peer.reputation_score > TERMINATION_THRESHOLD).order_by(Peer.reputation_score.desc()).limit(20).all()
                if not high_reputation_peers:
                    time.sleep(60)
                    continue
                num_to_ask = min(3, len(high_reputation_peers))
                peers_to_ask_records = random.sample(high_reputation_peers, num_to_ask)
                logger.info(f"Asking {len(peers_to_ask_records)} reputable peer(s) for their peer lists...")
                with self.peer_links_lock:
                    for peer_record in peers_to_ask_records:
                        peer_link = self.search_link_by_peer(lambda p: p.public_key and p.public_key.hex() == peer_record.public_key)
                        if peer_link:
                            self._send_message(peer_link, Message.peers_request())
                        else:
                            self._create_link(peer_record.last_known_ip, peer_record.last_known_port)
                time.sleep(300)
            except Exception as e:
                logger.error(f"Error in peer management loop: {e}", exc_info=True)
                time.sleep(60)

    @classmethod
    def start_node(cls, host: str, port: int, bootstrap_peer: str | None, public_ip: str | None) -> AxiomNode:
        p2p_instance = P2PBaseNode.start(ip_address=host, port=port, public_ip=public_ip)
        axiom_instance = cls(host=p2p_instance.ip_address, port=p2p_instance.port, bootstrap_peer=bootstrap_peer, public_ip=p2p_instance.public_ip)
        axiom_instance.serialized_port, axiom_instance.private_key, axiom_instance.public_key = p2p_instance.serialized_port, p2p_instance.private_key, p2p_instance.public_key
        axiom_instance.serialized_public_key, axiom_instance.peer_links, axiom_instance.server_socket = p2p_instance.serialized_public_key, p2p_instance.peer_links, p2p_instance.server_socket
        return axiom_instance

app = Flask(__name__)
CORS(app)
node_instance: AxiomNode
fact_indexer: FactIndexer

def get_facts_related_to_entity(session, entity_name: str) -> list[Fact]:
    normalized_name = entity_name.lower().strip()
    entity = session.query(Entity).filter(Entity.name == normalized_name).first()
    return entity.facts if entity else []

@app.route("/get_facts_by_entity", methods=["GET"])
def get_facts_by_entity_route():
    entity_name = request.args.get("name")
    if not entity_name:
        return jsonify({"error": "Missing 'name' query parameter"}), 400
    with db_lock, SessionMaker() as session:
        facts = get_facts_related_to_entity(session, entity_name)
        fact_dicts = [fact.to_dict() for fact in facts]
        return jsonify({"entity": entity_name, "related_facts_count": len(fact_dicts), "related_facts": fact_dicts})

@app.route("/chat", methods=["POST"])
def handle_chat_query() -> Response | tuple[Response, int]:
    data, query = request.get_json(), ""
    if data and "query" in data: query = data["query"]
    else: return jsonify({"error": "Missing 'query' in request body"}), 400
    with fact_indexer_lock:
        closest_facts = fact_indexer.find_closest_facts(query)
    return jsonify({"results": closest_facts})

@app.route("/get_timeline/<topic>", methods=["GET"])
def handle_get_timeline(topic: str) -> Response:
    with db_lock, SessionMaker() as session:
        initial_facts = semantic_search_ledger(session, topic, min_status="ingested", top_n=50)
        if not initial_facts:
            return jsonify({"timeline": [], "message": "No facts found for this topic."})
        def get_date_from_fact(fact: Fact):
            return min(_extract_dates(fact.content)) if _extract_dates(fact.content) else datetime.min
        sorted_facts = sorted(initial_facts, key=get_date_from_fact)
        timeline_data = [SerializedFact.from_fact(f).model_dump() for f in sorted_facts]
        return jsonify({"timeline": timeline_data})

@app.route("/get_chain_height", methods=["GET"])
def handle_get_chain_height() -> Response:
    with db_lock, SessionMaker() as session:
        latest_block = get_latest_block(session)
        return jsonify({"height": latest_block.height if latest_block else -1})

@app.route("/get_blocks", methods=["GET"])
def handle_get_blocks() -> Response:
    since_height = int(request.args.get("since", -1))
    with SessionMaker() as session:
        blocks = session.query(Block).filter(Block.height > since_height).order_by(Block.height.asc()).all()
        blocks_data = [{"height": b.height, "hash": b.hash, "previous_hash": b.previous_hash, "timestamp": b.timestamp, "nonce": b.nonce, "fact_hashes": json.loads(b.fact_hashes), "merkle_root": b.merkle_root} for b in blocks]
        return jsonify({"blocks": blocks_data})

@app.route("/status", methods=["GET"])
def handle_get_status() -> Response:
    with SessionMaker() as session:
        latest_block = get_latest_block(session)
        height = latest_block.height if latest_block else 0
        return jsonify({"status": "ok", "latest_block_height": height, "version": __version__})

@app.route("/local_query", methods=["GET"])
def handle_local_query() -> Response:
    search_term = request.args.get("term") or ""
    with SessionMaker() as session:
        results = semantic_search_ledger(session, search_term)
        fact_models = [SerializedFact.from_fact(fact).model_dump() for fact in results]
        return jsonify({"results": fact_models})

@app.route("/get_peers", methods=["GET"])
def handle_get_peers() -> Response:
    return jsonify({"peers": [link.fmt_addr() for link in node_instance.iter_links()] if node_instance else []})

@app.route("/get_fact_ids", methods=["GET"])
def handle_get_fact_ids() -> Response:
    with SessionMaker() as session:
        return jsonify({"fact_ids": [fact.id for fact in session.query(Fact).with_entities(Fact.id)]})

@app.route("/get_fact_hashes", methods=["GET"])
def handle_get_fact_hashes() -> Response:
    with SessionMaker() as session:
        return jsonify({"fact_hashes": [fact.hash for fact in session.query(Fact).with_entities(Fact.hash)]})

@app.route("/get_facts_by_id", methods=["POST"])
def handle_get_facts_by_id() -> Response:
    requested_ids: set[int] = set((request.json or {}).get("fact_ids", []))
    with SessionMaker() as session:
        facts = list(session.query(Fact).filter(Fact.id.in_(requested_ids)))
        return jsonify({"facts": [SerializedFact.from_fact(fact).model_dump() for fact in facts]})

@app.route("/get_facts_by_hash", methods=["POST"])
def handle_get_facts_by_hash() -> Response:
    requested_hashes: set[str] = set((request.json or {}).get("fact_hashes", []))
    with SessionMaker() as session:
        facts = list(session.query(Fact).filter(Fact.hash.in_(requested_hashes)))
        return jsonify({"facts": [SerializedFact.from_fact(fact).model_dump() for fact in facts]})

@app.route("/get_merkle_proof", methods=["GET"])
def handle_get_merkle_proof() -> Response | tuple[Response, int]:
    fact_hash, block_height_str = request.args.get("fact_hash"), request.args.get("block_height")
    if not fact_hash or not block_height_str:
        return jsonify({"error": "fact_hash and block_height are required"}), 400
    try: block_height = int(block_height_str)
    except ValueError: return jsonify({"error": "block_height must be an integer"}), 400
    with SessionMaker() as session:
        block = session.query(Block).filter(Block.height == block_height).one_or_none()
        if not block: return jsonify({"error": f"Block at height {block_height} not found"}), 404
        fact_hashes_in_block = json.loads(block.fact_hashes)
        if fact_hash not in fact_hashes_in_block: return jsonify({"error": "Fact hash not found in block"}), 404
        merkle_tree = merkle.MerkleTree(fact_hashes_in_block)
        try:
            proof = merkle_tree.get_proof(fact_hashes_in_block.index(fact_hash))
        except (ValueError, IndexError) as exc:
            logger.error(f"Error generating Merkle proof: {exc}")
            return jsonify({"error": "Failed to generate Merkle proof"}), 500
        return jsonify({"fact_hash": fact_hash, "block_height": block_height, "merkle_root": block.merkle_root, "proof": proof})

@app.route("/anonymous_query", methods=["POST"])
def handle_anonymous_query() -> Response | tuple[Response, int]:
    return jsonify({"error": "Not implemented"}), 501
@app.route("/dao/proposals", methods=["GET"])
def handle_get_proposals() -> tuple[Response, int]:
    return jsonify({"error": "Not implemented"}), 501
@app.route("/dao/submit_proposal", methods=["POST"])
def handle_submit_proposal() -> Response | tuple[Response, int]:
    return jsonify({"error": "Not implemented"}), 501
@app.route("/dao/submit_vote", methods=["POST"])
def handle_submit_vote() -> Response | tuple[Response, int]:
    return jsonify({"error": "Not implemented"}), 501
@app.route("/verify_fact", methods=["POST"])
def handle_verify_fact() -> Response | tuple[Response, int]:
    fact_id = (request.json or {}).get("fact_id")
    if not fact_id: return jsonify({"error": "fact_id is required"}), 400
    with SessionMaker() as session:
        fact_to_verify = session.get(Fact, fact_id)
        if not fact_to_verify: return jsonify({"error": "Fact not found"}), 404
        corroborating_claims = verification_engine.find_corroborating_claims(fact_to_verify, session)
        citations_report = verification_engine.verify_citations(fact_to_verify)
        return jsonify({"target_fact_id": fact_to_verify.id, "target_content": fact_to_verify.content, "corroboration_analysis": {"status": f"Found {len(corroborating_claims)} corroborating claims.", "corroborations": corroborating_claims}, "citation_analysis": {"status": f"Found {len(citations_report)} citations.", "citations": citations_report}})

@app.route("/get_fact_context/<fact_hash>", methods=["GET"])
def handle_get_fact_context(fact_hash: str) -> Response | tuple[Response, int]:
    with SessionMaker() as session:
        target_fact = session.query(Fact).filter(Fact.hash == fact_hash).one_or_none()
        if not target_fact: return jsonify({"error": "Fact not found"}), 404
        links = session.query(FactLink).filter((FactLink.fact1_id == target_fact.id) | (FactLink.fact2_id == target_fact.id)).all()
        related_facts_data = [{"relationship": link.relationship_type.value, "fact": SerializedFact.from_fact(link.fact2 if link.fact1_id == target_fact.id else link.fact1).model_dump()} for link in links]
        return jsonify({"target_fact": SerializedFact.from_fact(target_fact).model_dump(), "related_facts": related_facts_data})

def main() -> None:
    global node_instance, fact_indexer
    parser = argparse.ArgumentParser(description="Run an Axiom P2P Node.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host IP to bind to.")
    parser.add_argument("--p2p-port", type=int, default=5002, help="Port for P2P communication.")
    parser.add_argument("--api-port", type=int, default=8002, help="Port for the Flask API server.")
    parser.add_argument("--bootstrap-peer", type=str, default=None, help="URL of a peer to bootstrap to.")
    parser.add_argument("--public-ip", type=str, default=None, help="Public IP address of this node.")
    args = parser.parse_args()
    try:
        node_instance = AxiomNode(host=args.host, port=args.p2p_port, bootstrap_peer=args.bootstrap_peer, public_ip=args.public_ip)
        node_instance.get_chain_callback = node_instance._get_chain_for_peer
        logger.info("--- Initializing Fact Indexer for Hybrid Search ---")
        with SessionMaker() as db_session:
            fact_indexer = FactIndexer(db_session)
            fact_indexer.index_facts_from_db()
        api_thread = threading.Thread(target=lambda: app.run(host=args.host, port=args.api_port, debug=False, use_reloader=False), daemon=True)
        api_thread.start()
        logger.info(f"Flask API server started on http://{args.host}:{args.api_port}")
        node_instance.start()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received. Exiting.")
    except Exception as exc:
        logger.critical(f"A critical error occurred during node startup: {exc}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
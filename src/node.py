# Axiom - node.py
# Copyright (C) 2026 The Axiom Contributors

import logging
import math
import os
import random
import sqlite3
import threading
import time
import zlib
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
from src.blockchain import create_block, get_blocks_after, get_chain_head
from src.code_introspector import build_endpoint_registry, build_module_map
from src.conversation_patterns import (
    compile_patterns,
    match_query,
    seed_patterns,
)
from src.data_quality import (
    find_conflict_candidates,
    find_duplicate_candidates,
)
from src.ledger import (
    get_unprocessed_facts_for_lexicon,
    initialize_database,
    mark_fact_as_processed,
    migrate_fact_content_to_compressed,
)
from src.p2p import sync_chain_with_peer, sync_with_peer
from src.self_check import run_self_checks
from src.system_health import compute_health_snapshot

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

        # Scheduler configuration for main cycles and idle ticks.
        self.main_cycle_interval = int(
            os.environ.get("AXIOM_MAIN_CYCLE_INTERVAL", "900")
        )
        self.idle_tick_interval = float(
            os.environ.get("AXIOM_IDLE_TICK_INTERVAL", "1.0")
        )
        # How often to run the full idle suite (coarse-grained grouping of idle tasks).
        self.idle_suite_interval = float(
            os.environ.get("AXIOM_IDLE_SUITE_INTERVAL", "150.0")
        )

        # Idle task registry state.
        self.idle_tasks = []
        self._idle_task_index = 0
        self._last_idle_learning_ts = 0.0

        # Conversation subsystem (populated during idle training).
        self._conversation_patterns = []
        self._conversation_training_state = {}
        # Code introspection and health snapshots.
        self._code_map = None
        self._endpoint_registry = []
        self._last_code_introspection_ts = 0.0
        self._duplicate_summary = []
        self._conflict_summary = []
        self._last_data_quality_ts = 0.0
        self._health_snapshot = None
        self._last_health_snapshot_ts = 0.0
        self._self_check_results = []
        self._last_self_check_ts = 0.0
        self._last_main_cycle_ts = 0.0
        self._last_fragment_audit_ts = 0.0
        self._idle_throttle_log = {}
        self._idle_suite_header_active = False
        self.node_role = "bootstrap" if port == 8009 else "peer"

        if port == 8009:
            # Bootstrap node must always use the canonical database name
            self.db_path = os.environ.get("AXIOM_DB_PATH", "axiom_ledger.db")
        else:
            # Peer node uses port-specific name if no ENV var is set
            default_db_name = f"axiom_ledger_{port}.db"
            self.db_path = os.environ.get("AXIOM_DB_PATH", default_db_name)

        initialize_database(self.db_path)
        # Optional self-healing migration to keep fact storage consistent.
        migrate_fact_content_to_compressed(self.db_path)
        self.search_ledger_for_api = search_ledger_for_api

        # Register built-in idle tasks.
        self.idle_tasks.append(self._idle_learning_cycle)
        self.idle_tasks.append(self._idle_conversation_training)
        self.idle_tasks.append(self._idle_code_introspection)
        self.idle_tasks.append(self._idle_data_quality)
        self.idle_tasks.append(self._idle_fragment_audit)
        self.idle_tasks.append(self._idle_health_snapshot)
        self.idle_tasks.append(self._idle_self_checks)

    def bootstrap_sync(self):
        if not self.peers:
            logger.info(
                "\033[92mNo bootstrap peers defined. Starting as Genesis Node.\033[0m",
            )
            return None
        logger.info(
            "\033[93m[Init] Performing initial sync with bootstrap peers...\033[0m",
        )
        chain_updated = False
        for peer_url in list(self.peers.keys()):
            try:
                sync_status, new_facts = sync_with_peer(
                    self,
                    peer_url,
                    self.db_path,
                )
                self._update_reputation(peer_url, sync_status, len(new_facts))
                # Check chain sync result
                appended, peer_height = sync_chain_with_peer(
                    self,
                    peer_url,
                    self.db_path,
                )
                if appended > 0 or (
                    peer_height > get_chain_head(self.db_path)[1]
                ):
                    chain_updated = True
            except Exception as e:
                logger.warning(
                    "[Init] Error during bootstrap sync with %s: %s",
                    peer_url,
                    e,
                )
        return chain_updated

    def print_mesh_status(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_mesh_print < 5:
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
            except Exception as e:
                logger.debug(
                    "[Mesh] Immediate handshake with %s failed: %s",
                    peer_url,
                    e,
                )

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
                + (math.log10(1 + new_facts_count) * PEER_REP_REWARD_NEW_DATA)
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
        unprocessed_facts = get_unprocessed_facts_for_lexicon(self.db_path)
        if not unprocessed_facts:
            logger.info("Success: Lexical Mesh is up to date.")
            return
        logger.info(
            f"[Reflection]Success. Shredding {len(unprocessed_facts)} facts into semantic synapses...",
        )
        for fact in unprocessed_facts:
            try:
                raw = fact.get("fact_content")
                text = raw
                if isinstance(raw, (bytes, bytearray)):
                    try:
                        text = zlib.decompress(raw).decode("utf-8")
                    except (zlib.error, ValueError):
                        continue
                if crucible.integrate_fact_to_mesh(text):
                    mark_fact_as_processed(fact["fact_id"], self.db_path)
            except Exception:
                pass
        logger.info(
            "Success: Neural pathways strengthened. Idle cycle complete.",
        )

    def _idle_learning_cycle(self):
        """Productive tasks between main cycles: rediscover links, reinforce synapses."""
        try:
            # Throttle heavy idle learning so it does not run on every tick.
            now = time.time()
            interval = 300.0
            if now - self._last_idle_learning_ts < interval:
                self._maybe_log_idle_throttle(
                    "learning",
                    interval,
                    now,
                    self._last_idle_learning_ts,
                )
                return

            self._ensure_idle_suite_header()

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT fact_id, fact_content, trust_score, status FROM facts WHERE status != 'disputed' ORDER BY RANDOM() LIMIT 30"
            )
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return
            sample = []
            for row in rows:
                raw = row["fact_content"]
                try:
                    text = (
                        zlib.decompress(raw).decode("utf-8")
                        if isinstance(raw, (bytes, bytearray))
                        else (raw or "")
                    )
                except (zlib.error, ValueError, TypeError):
                    continue
                if text:
                    sample.append(
                        {"fact_id": row["fact_id"], "fact_content": text}
                    )
            if sample:
                logger.info(
                    "\033[2m[Idle:%s] Relationship rediscovery: re-linking %d facts against full ledger...\033[0m",
                    self.port,
                    len(sample),
                )
                synthesizer.link_related_facts(sample, db_path=self.db_path)
            # Reinforce synapses: re-integrate a few high-trust facts into the mesh
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT fact_id, fact_content FROM facts WHERE status != 'disputed' AND (trust_score >= 2 OR status = 'trusted') ORDER BY RANDOM() LIMIT 5"
            )
            reinforce_rows = cur.fetchall()
            conn.close()
            reinforced = 0
            for row in reinforce_rows:
                raw = row[1]
                try:
                    text = (
                        zlib.decompress(raw).decode("utf-8")
                        if isinstance(raw, (bytes, bytearray))
                        else (raw or "")
                    )
                except (zlib.error, ValueError, TypeError):
                    continue
                if text and crucible.integrate_fact_to_mesh(text):
                    reinforced += 1
            if reinforced:
                logger.info(
                    "\033[2m[Idle:%s] Synapse reinforcement: re-integrated %d high-trust fact(s) into mesh.\033[0m",
                    self.port,
                    reinforced,
                )
            # Only mark as run if we reached the end without early return.
            self._last_idle_learning_ts = now
        except Exception as e:
            logger.info("[Idle:%s] Learning cycle skipped: %s", self.port, e)

    def _run_main_cycle(self):
        """One full main cycle: fetch topics, integrate facts, sync peers, and housekeeping."""
        self._last_main_cycle_ts = time.time()
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
                    synthesizer.link_related_facts(
                        newly_created_facts,
                        db_path=self.db_path,
                    )
        except Exception as e:
            logger.error(f"Error: {e}")

        logger.info("\033[2m[AXIOM ENGINE CYCLE FINISH]\033[0m")

        if newly_created_facts:
            fact_ids = [f["fact_id"] for f in newly_created_facts]

            # Ensure blocks are written to this node's active ledger file.
            new_block = create_block(fact_ids, db_path=self.db_path)

            if new_block:
                logger.info(
                    f"\033[96m[Chain] Committed block HEIGHT {new_block['height']} with {len(fact_ids)} fact(s).\033[0m",
                )
            else:
                logger.warning(
                    f"[Chain] Failed to commit block for {len(fact_ids)} facts. Check for race condition or duplicate ID.",
                )

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
            except Exception as e:
                logger.warning(
                    "[P2P Sync] Background sync with %s failed: %s",
                    peer_url,
                    e,
                )

        self._reflection_cycle()
        metacognitive_engine.run_metacognitive_cycle(self.db_path)
        self._prune_ledger()
        self.print_mesh_status(force=True)

    def _idle_conversation_training(self):
        """Incrementally prepare conversation patterns for fast, non-ledger responses.

        Work is intentionally small per tick: compile a few patterns at a time.
        """
        # Initialize state on first run.
        if not self._conversation_patterns:
            self._conversation_patterns = seed_patterns()
            self._conversation_training_state = {"compiled_index": 0}

        compiled_index = int(
            self._conversation_training_state.get("compiled_index", 0)
        )

        # Compile a bounded batch of patterns per idle tick.
        batch_size = 2
        upper = min(
            compiled_index + batch_size, len(self._conversation_patterns)
        )
        if compiled_index >= upper:
            # All patterns compiled; nothing else to do this tick.
            return

        to_compile = self._conversation_patterns[compiled_index:upper]
        compile_patterns(to_compile)
        self._conversation_training_state["compiled_index"] = upper

        # Log occasionally when we make progress.
        if upper == len(self._conversation_patterns):
            self._ensure_idle_suite_header()
            logger.info(
                "[Idle-Conv:%s] Conversation patterns ready: %d",
                self.port,
                len(self._conversation_patterns),
            )

    def _idle_code_introspection(self):
        """Periodically refresh an internal map of modules and HTTP endpoints.

        This is throttled to avoid unnecessary filesystem work.
        """
        now = time.time()
        # Run at most once per hour.
        interval = 3600.0
        if now - self._last_code_introspection_ts < interval:
            self._maybe_log_idle_throttle(
                "code",
                interval,
                now,
                self._last_code_introspection_ts,
            )
            return

        self._ensure_idle_suite_header()

        src_root = os.path.dirname(os.path.abspath(__file__))
        try:
            self._code_map = build_module_map(src_root)
            node_path = os.path.join(src_root, "node.py")
            self._endpoint_registry = build_endpoint_registry(node_path)
            self._last_code_introspection_ts = now
            logger.info(
                "[Idle-Code:%s] Refreshed code map (%d modules, %d endpoints).",
                self.port,
                len(self._code_map or {}),
                len(self._endpoint_registry or []),
            )
        except Exception as e:
            logger.info(
                "[Idle-Code:%s] Code introspection skipped: %s", self.port, e
            )

    def _idle_data_quality(self):
        """Periodically sample the ledger for duplicate and conflicting facts.

        Results are cached in-memory for later inspection or reporting.
        """
        now = time.time()
        # Run at most once every 15 minutes.
        interval = 900.0
        if now - self._last_data_quality_ts < interval:
            self._maybe_log_idle_throttle(
                "data",
                interval,
                now,
                self._last_data_quality_ts,
            )
            return

        self._ensure_idle_suite_header()

        try:
            dupes = find_duplicate_candidates(self.db_path, sample_size=300)
            conflicts = find_conflict_candidates(self.db_path, sample_size=300)
            self._duplicate_summary = dupes
            self._conflict_summary = conflicts
            self._last_data_quality_ts = now
            logger.info(
                "[Idle-Data:%s] Sampled data quality: %d duplicate groups, %d conflict groups.",
                self.port,
                len(dupes),
                len(conflicts),
            )
        except Exception as e:
            logger.info(
                "[Idle-Data:%s] Data quality scan skipped: %s", self.port, e
            )

    def _idle_health_snapshot(self):
        """Periodically compute a lightweight health snapshot of the ledger/db."""
        now = time.time()
        # Run at most once every 10 minutes.
        interval = 600.0
        if now - self._last_health_snapshot_ts < interval:
            self._maybe_log_idle_throttle(
                "health",
                interval,
                now,
                self._last_health_snapshot_ts,
            )
            return

        self._ensure_idle_suite_header()

        try:
            self._health_snapshot = compute_health_snapshot(self.db_path)
            self._last_health_snapshot_ts = now
            logger.info(
                "[Idle-Health:%s] Updated health snapshot: %s",
                self.port,
                self._health_snapshot,
            )
            try:
                total_facts = int(self._health_snapshot.get("total_facts", 0))
                total_blocks = int(
                    self._health_snapshot.get("total_blocks", 0)
                )
                if total_blocks > 0 and total_facts == 0:
                    logger.warning(
                        "[Idle-Health:%s] Anomaly detected: chain has %d block(s) but facts table is empty for db %s.",
                        self.port,
                        total_blocks,
                        self.db_path,
                    )
            except Exception:
                # Never allow anomaly checks to break idle cycles.
                pass
        except Exception as e:
            logger.info(
                "[Idle-Health:%s] Health snapshot skipped: %s", self.port, e
            )

    def _idle_self_checks(self):
        """Occasionally run a few deterministic self-queries against our own /think endpoint."""
        now = time.time()
        # Run at most once every 3 hours.
        interval = 10800.0
        if now - self._last_self_check_ts < interval:
            self._maybe_log_idle_throttle(
                "selfcheck",
                interval,
                now,
                self._last_self_check_ts,
            )
            return

        self._ensure_idle_suite_header()

        # Use the local self_url to avoid any external DNS/network dependency.
        base_url = self.self_url
        try:
            self._self_check_results = run_self_checks(base_url)
            self._last_self_check_ts = now
            logger.info(
                "[Idle-SelfCheck:%s] Completed self-checks: %s",
                self.port,
                self._self_check_results,
            )
        except Exception as e:
            logger.info(
                "[Idle-SelfCheck:%s] Self-checks skipped: %s", self.port, e
            )

    def _idle_fragment_audit(self):
        """Periodically scan a small sample of facts to refine fragment
        classification and, when appropriate, seek simple consensus
        from peers about low-quality fragments.
        """
        now = time.time()
        interval = 300.0  # 5 minutes between audits per node
        if now - self._last_fragment_audit_ts < interval:
            self._maybe_log_idle_throttle(
                "fragment_audit",
                interval,
                now,
                self._last_fragment_audit_ts,
            )
            return

        self._ensure_idle_suite_header()

        import sqlite3 as _sqlite3

        try:
            conn = _sqlite3.connect(self.db_path)
            conn.row_factory = _sqlite3.Row
            cur = conn.cursor()

            # Sample a bounded number of candidate facts.
            cur.execute(
                """
                SELECT fact_id, fact_content, fragment_state, fragment_score, status
                FROM facts
                WHERE status != 'disputed'
                ORDER BY RANDOM()
                LIMIT 40
                """
            )
            rows = cur.fetchall()
            if not rows:
                conn.close()
                self._last_fragment_audit_ts = now
                return

            import zlib as _zlib

            updated = 0
            for row in rows:
                fact_id = row["fact_id"]
                fragment_state = row["fragment_state"] or "unknown"
                fragment_score = float(row["fragment_score"] or 0.0)

                raw = row["fact_content"]
                try:
                    text = (
                        _zlib.decompress(raw).decode("utf-8")
                        if isinstance(raw, (bytes, bytearray))
                        else (raw or "")
                    )
                except Exception:
                    continue

                text = text.strip()
                if not text:
                    continue

                words = text.split()
                word_count = len(words)
                lower = text.lower()

                # Simple, model-free heuristic refinement.
                score = 0.0
                reasons = []
                if word_count <= 8:
                    score += 0.6
                    reasons.append("short_sentence")
                elif word_count <= 12:
                    score += 0.3
                    reasons.append("moderately_short")

                pronoun_starts = (
                    "he ",
                    "she ",
                    "they ",
                    "it ",
                    "this ",
                    "that ",
                    "these ",
                    "those ",
                )
                if any(lower.startswith(p) for p in pronoun_starts):
                    score += 0.25
                    reasons.append("pronoun_start")

                if not text.endswith((".", "!", "?")):
                    score += 0.15
                    reasons.append("nonterminal_punctuation")

                score = max(0.0, min(1.0, score))

                new_state = fragment_state
                if score >= 0.8:
                    new_state = "suspected_fragment"
                elif score >= 0.5:
                    if fragment_state == "unknown":
                        new_state = "suspected_fragment"
                else:
                    # If we previously suspected a fragment but evidence is weak, release it.
                    if fragment_state in (
                        "suspected_fragment",
                        "confirmed_fragment",
                    ):
                        new_state = "rejected_fragment"

                # Lightweight peer consensus: if all sampled peers either
                # do not know this fact or also treat it as fragment-like,
                # we may bump it to confirmed_fragment.
                if new_state == "suspected_fragment" and self.peers:
                    positives = 0
                    negatives = 0
                    headers = {"X-Axiom-Peer": self.advertised_url}
                    for peer_url in list(self.peers.keys())[:3]:
                        try:
                            resp = requests.get(
                                f"{peer_url}/fragment_opinion",
                                params={"fact_id": fact_id},
                                timeout=3,
                                headers=headers,
                            )
                            if resp.status_code != 200:
                                continue
                            data = resp.json()
                            if not data.get("seen"):
                                positives += 1
                                continue
                            peer_state = (
                                data.get("fragment_state") or "unknown"
                            )
                            peer_status = data.get("status")
                            peer_trust = float(
                                data.get("trust_score", 0.0) or 0.0
                            )
                            if peer_state in (
                                "suspected_fragment",
                                "confirmed_fragment",
                            ):
                                positives += 1
                            elif peer_state == "rejected_fragment" or (
                                peer_status == "trusted" and peer_trust >= 2
                            ):
                                negatives += 1
                        except Exception:
                            continue

                    if positives > 0 and negatives == 0:
                        new_state = "confirmed_fragment"
                    elif negatives > 0 and positives == 0:
                        new_state = "rejected_fragment"

                if (
                    new_state != fragment_state
                    or abs(score - fragment_score) > 0.05
                ):
                    cur.execute(
                        """
                        UPDATE facts
                        SET fragment_state = ?, fragment_score = ?, fragment_reason = ?
                        WHERE fact_id = ?
                        """,
                        (
                            new_state,
                            score,
                            ",".join(reasons) if reasons else None,
                            fact_id,
                        ),
                    )
                    updated += 1

            if updated:
                conn.commit()
                logger.info(
                    "[Idle-Fragment:%s] Audited %d fact(s); updated classifications for %d.",
                    self.port,
                    len(rows),
                    updated,
                )

            conn.close()
            self._last_fragment_audit_ts = now
        except Exception as e:
            logger.info(
                "[Idle-Fragment:%s] Fragment audit skipped: %s", self.port, e
            )

    # --- Helpers for meta-commands exposed via /think ---

    def get_system_map_summary(self) -> str:
        if not self._code_map:
            return "System map is not ready yet. Idle introspection will build it shortly."
        module_count = len(self._code_map)
        # Highlight a few key modules if present.
        interesting = [
            name
            for name in self._code_map.keys()
            if any(
                key in name
                for key in (
                    "node.py",
                    "crucible",
                    "synthesizer",
                    "blockchain",
                    "p2p",
                )
            )
        ]
        interesting = sorted(set(interesting))[:8]
        parts = [f"I currently see {module_count} Python modules under src/."]
        if interesting:
            parts.append(
                "Key subsystems include: " + ", ".join(interesting) + "."
            )
        return " ".join(parts)

    def get_endpoints_summary(self) -> str:
        if not self._endpoint_registry:
            return "Endpoint registry is not ready yet. Idle code introspection will populate it."
        lines = []
        for ep in self._endpoint_registry[:20]:
            path = ep.get("path") or "/"
            methods = ",".join(ep.get("methods", []))
            func = ep.get("function", "")
            lines.append(f"{methods} {path} -> {func}")
        extra = ""
        if len(self._endpoint_registry) > 20:
            extra = f" (+{len(self._endpoint_registry) - 20} more)"
        return "Exposed HTTP endpoints:\n" + "\n".join(lines) + extra

    def get_health_summary(self) -> str:
        if not self._health_snapshot:
            return "Health snapshot is not ready yet. Idle health checks will compute it."
        snap = self._health_snapshot
        total = snap.get("total_facts", 0)
        blocks = snap.get("total_blocks", 0)
        height = snap.get("chain_height", 0)
        avg_trust = snap.get("avg_trust_score")
        status_counts = snap.get("status_counts", {})
        role_label = f"{self.node_role} node"
        parts = [
            f"Node {self.port} ({role_label}) at {self.advertised_url}.",
            f"Facts: {total}, Blocks: {blocks}, Chain height: {height}.",
            f"Status counts: {status_counts}.",
        ]
        if avg_trust is not None:
            parts.append(f"Average trust score: {avg_trust:.3f}.")
        return " ".join(parts)

    def get_idle_state(self) -> dict:
        """Introspect idle scheduling and last-run timestamps for debugging."""
        now = time.time()

        def age(ts: float) -> float | None:
            return None if not ts else max(0.0, now - ts)

        return {
            "node_port": self.port,
            "node_role": self.node_role,
            "advertised_url": self.advertised_url,
            "db_path": self.db_path,
            "main_cycle_interval_sec": self.main_cycle_interval,
            "idle_suite_interval_sec": self.idle_suite_interval,
            "last_main_cycle_age_sec": age(self._last_main_cycle_ts),
            "last_idle_learning_age_sec": age(self._last_idle_learning_ts),
            "last_code_introspection_age_sec": age(
                self._last_code_introspection_ts
            ),
            "last_data_quality_age_sec": age(self._last_data_quality_ts),
            "last_health_snapshot_age_sec": age(self._last_health_snapshot_ts),
            "last_self_check_age_sec": age(self._last_self_check_ts),
            "last_fragment_audit_age_sec": age(self._last_fragment_audit_ts),
        }

    def _run_idle_tick(self):
        """Run a single idle task, if any are registered."""
        if not self.idle_tasks:
            return
        task = self.idle_tasks[self._idle_task_index % len(self.idle_tasks)]
        self._idle_task_index += 1
        try:
            task()
        except Exception as e:
            logger.info(
                "[Idle] Task %s skipped: %s",
                getattr(task, "__name__", "unknown"),
                e,
            )

    def _run_idle_suite(self):
        """Run all registered idle tasks in a fixed sequence so their logs
        appear grouped together for easier debugging.
        """
        if not self.idle_tasks:
            return
        self._idle_suite_header_active = False
        for task in self.idle_tasks:
            try:
                task()
            except Exception as e:
                logger.info(
                    "[Idle] Task %s skipped: %s",
                    getattr(task, "__name__", "unknown"),
                    e,
                )
        if self._idle_suite_header_active:
            logger.info("[Idle-Suite:%s] End.", self.port)

    def _maybe_log_idle_throttle(
        self,
        name: str,
        interval: float,
        now: float,
        last_run_ts: float,
    ):
        """Log (at debug level) that an idle task is being throttled, but
        rate-limit those logs so they do not flood the console.
        """
        last_log_ts = self._idle_throttle_log.get(name, 0.0)
        # At most once per 60s per task.
        if now - last_log_ts < 60.0:
            return
        elapsed = now - last_run_ts if last_run_ts else 0.0
        remaining = max(0.0, interval - elapsed)
        logger.debug(
            "[Idle-%s:%s] Throttled; next eligible in %.0fs (elapsed %.0fs).",
            name,
            self.port,
            remaining,
            elapsed,
        )
        self._idle_throttle_log[name] = now

    def _ensure_idle_suite_header(self):
        """Ensure we only emit the Idle-Suite Start line once per suite,
        and only when at least one idle task actually performs work.
        """
        if self._idle_suite_header_active:
            return
        logger.info("[Idle-Suite:%s] Start.", self.port)
        self._idle_suite_header_active = True

    def _background_loop(self):
        logger.info("Starting continuous background cycle.")
        next_cycle = time.time()
        next_idle_suite = time.time() + self.idle_suite_interval
        while True:
            now = time.time()
            if now >= next_cycle:
                self._run_main_cycle()
                next_cycle = now + self.main_cycle_interval
            elif now >= next_idle_suite:
                self._run_idle_suite()
                next_idle_suite = now + self.idle_suite_interval
            else:
                # Sleep until the next scheduled event (idle suite or main cycle),
                # whichever comes first, but never longer than idle_tick_interval.
                sleep_for = min(
                    self.idle_tick_interval,
                    max(0.0, next_idle_suite - now),
                    max(0.0, next_cycle - now),
                )
                time.sleep(sleep_for)

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
    results = node_instance.search_ledger_for_api(
        search_term,
        include_uncorroborated=include_uncorroborated,
        db_path=node_instance.db_path,
    )
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

    # Macro-style meta commands that do not require ledger lookups.
    normalized = " ".join(query.strip().lower().split())
    if normalized in ("axiom: status", "show health"):
        return jsonify({"response": node_instance.get_health_summary()})
    if normalized in ("axiom: map", "list modules"):
        return jsonify({"response": node_instance.get_system_map_summary()})
    if normalized in ("show endpoints",):
        return jsonify({"response": node_instance.get_endpoints_summary()})

    # Fast, non-ledger conversational routing next.
    handled = False
    direct_answer = ""
    try:
        if hasattr(node_instance, "_conversation_patterns"):
            handled, direct_answer = match_query(
                query,
                getattr(node_instance, "_conversation_patterns", []),
            )
    except Exception:
        handled = False
        direct_answer = ""

    if handled and direct_answer:
        return jsonify({"response": direct_answer})

    out = inference_engine.think(query, db_path=node_instance.db_path)
    answer = out.get("response", out) if isinstance(out, dict) else out
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


@app.route("/debug/idle_state", methods=["GET"])
def handle_idle_state():
    """Debug-only endpoint exposing idle scheduling state."""
    if node_instance is None:
        return jsonify({"error": "Node is not initialized"}), 503
    return jsonify(node_instance.get_idle_state())


@app.route("/fragment_opinion", methods=["GET"])
def handle_fragment_opinion():
    """Return this node's opinion about a specific fact's fragment status.
    Used for simple cross-node consensus during idle fragment audits.
    """
    if node_instance is None:
        return jsonify({"error": "Node is not initialized"}), 503

    fact_id = request.args.get("fact_id", "").strip()
    if not fact_id:
        return jsonify({"error": "Missing fact_id"}), 400

    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(node_instance.db_path)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT status, trust_score, fragment_state, fragment_score
            FROM facts
            WHERE fact_id = ?
            """,
            (fact_id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"seen": False})

        status, trust_score, fragment_state, fragment_score = row
        return jsonify(
            {
                "seen": True,
                "status": status,
                "trust_score": float(trust_score or 0.0),
                "fragment_state": fragment_state or "unknown",
                "fragment_score": float(fragment_score or 0.0),
            }
        )
    finally:
        conn.close()


if __name__ == "__main__":
    if node_instance is None:
        print_banner()
        port_val = int(os.environ.get("PORT", 8009))
        bootstrap_val = os.environ.get("BOOTSTRAP_PEER")
        node_instance = AxiomNode(port=port_val, bootstrap_peer=bootstrap_val)

        initial_sync_complete = True
        if (
            port_val != 8009 and node_instance.peers
        ):  # Only run explicit sync for non-bootstrap peers
            initial_sync_complete = node_instance.bootstrap_sync()
            if not initial_sync_complete:
                logger.warning(
                    "[INIT] Initial chain sync failed. Relying on background loop."
                )

        node_instance.start_background_tasks()
    logger.info(
        f"\033[2mAxiom Identity: {node_instance.advertised_url}\033[0m",
    )
    app.run(host="0.0.0.0", port=node_instance.port, debug=False)

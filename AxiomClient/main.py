# Axiom Client - Desktop Application main.py
# Copyright (C) 2025 The Axiom Contributors
# This program is licensed under the Peer Production License (PPL).
# See the LICENSE file for full details.
# --- V3.0: DARK MODE GUI & ENHANCED RESULTS DISPLAY ---

import sys
import requests
import random
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLineEdit, 
                             QTextEdit, QPushButton, QLabel, QProgressBar, QFrame)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QColor, QPalette

# --- CONFIGURATION ---
# Default to local node. In production, this would be a list of public seed nodes.
BOOTSTRAP_NODES = ["http://127.0.0.1:5000"] 
CIRCUIT_LENGTH = 3

# --- STYLING (The "Axiom" Aesthetic) ---
DARK_STYLESHEET = """
    QWidget {
        background-color: #0f172a;
        color: #e2e8f0;
        font-family: 'Segoe UI', Arial, sans-serif;
    }
    QLineEdit {
        background-color: #1e293b;
        border: 2px solid #334155;
        border-radius: 5px;
        padding: 8px;
        color: #00f0ff;
        font-size: 14px;
    }
    QLineEdit:focus {
        border: 2px solid #00f0ff;
    }
    QPushButton {
        background-color: #00f0ff;
        color: #000000;
        border-radius: 5px;
        padding: 10px;
        font-weight: bold;
        font-size: 14px;
    }
    QPushButton:hover {
        background-color: #00cbd6;
    }
    QPushButton:disabled {
        background-color: #334155;
        color: #94a3b8;
    }
    QTextEdit {
        background-color: #1e293b;
        border: 1px solid #334155;
        color: #e2e8f0;
        font-size: 13px;
        line-height: 1.4;
    }
    QLabel#Title {
        color: #00f0ff;
        font-size: 28px;
        font-weight: bold;
        letter-spacing: 2px;
    }
    QLabel#Status {
        color: #94a3b8;
        font-style: italic;
    }
"""

class NetworkWorker(QThread):
    """
    Background thread for network operations (Discovery -> Circuit -> Query).
    """
    finished = pyqtSignal(dict) 
    progress = pyqtSignal(str) 

    def __init__(self, query_term):
        super().__init__()
        self.query_term = query_term

    def run(self):
        try:
            # 1. Discover Network
            self.progress.emit("Scanning Axiom network...")
            peers = self._get_network_peers(BOOTSTRAP_NODES)
            
            # If no peers found, we fall back to the bootstrap node itself
            if not peers:
                peers = BOOTSTRAP_NODES
                self.progress.emit(f"No peers found. Defaulting to local node.")
            else:
                self.progress.emit(f"Network discovery complete. Found {len(peers)} nodes.")

            # 2. Build Circuit
            circuit = self._build_anonymous_circuit(peers, CIRCUIT_LENGTH)
            self.progress.emit(f"Circuit established: {len(circuit)} hops.")

            # 3. Send Query
            entry_node = circuit[0]
            self.progress.emit(f"Sending query via {entry_node}...")
            
            # We strip the entry node from the circuit list passed in payload
            relay_circuit = circuit[1:] if len(circuit) > 1 else []
            
            response = requests.post(
                f"{entry_node}/anonymous_query",
                json={
                    'term': self.query_term, 
                    'circuit': relay_circuit, 
                    'sender_peer': "client_user" # Clients identify differently than nodes
                },
                timeout=15
            )
            response.raise_for_status()
            self.finished.emit(response.json())
        
        except requests.exceptions.ConnectionError:
            self.finished.emit({"error": "Connection failed. Is your local Axiom node running?"})
        except Exception as e:
            self.finished.emit({"error": f"Network Error: {str(e)}"})

    def _get_network_peers(self, bootstrap_nodes):
        found_peers = set()
        for node_url in bootstrap_nodes:
            try:
                response = requests.get(f"{node_url}/get_peers", timeout=3)
                if response.status_code == 200:
                    data = response.json().get('peers', {})
                    # Add the bootstrap node itself
                    found_peers.add(node_url)
                    # Add its peers
                    for peer in data.keys():
                        found_peers.add(peer)
            except:
                continue
        return list(found_peers)

    def _build_anonymous_circuit(self, peers, length):
        # Filter out invalid URLs
        valid_peers = [p for p in peers if p.startswith("http")]
        if not valid_peers: return []
        
        if len(valid_peers) < length:
            random.shuffle(valid_peers)
            return valid_peers
        return random.sample(valid_peers, length)


class AxiomClientApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Axiom Client v3.0")
        self.setGeometry(200, 200, 800, 600)
        self.network_worker = None
        self.initUI()
        
        # Apply the Cyberpunk/Dark Theme
        self.setStyleSheet(DARK_STYLESHEET)

    def initUI(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        self.setLayout(layout)

        # Title
        self.title_label = QLabel("◈ AXIOM")
        self.title_label.setObjectName("Title") # For CSS targeting
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # Input
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter topic to investigate (e.g. 'Elon Musk', 'AI')...")
        self.query_input.returnPressed.connect(self.start_search)
        layout.addWidget(self.query_input)

        # Button
        self.search_button = QPushButton("INITIATE SEARCH")
        self.search_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_button.clicked.connect(self.start_search)
        layout.addWidget(self.search_button)

        # Status
        self.status_label = QLabel("System Ready.")
        self.status_label.setObjectName("Status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Results Area
        self.results_output = QTextEdit()
        self.results_output.setReadOnly(True)
        layout.addWidget(self.results_output)

    def start_search(self):
        query = self.query_input.text().strip()
        if not query: return

        self.search_button.setEnabled(False)
        self.search_button.setText("SEARCHING NETWORK...")
        self.results_output.clear()
        
        self.network_worker = NetworkWorker(query)
        self.network_worker.progress.connect(self.update_status)
        self.network_worker.finished.connect(self.display_results)
        self.network_worker.start()

    def update_status(self, message):
        self.status_label.setText(f"Process: {message}")

    def display_results(self, response_data):
        self.status_label.setText("Search Complete.")
        self.search_button.setEnabled(True)
        self.search_button.setText("INITIATE SEARCH")
        
        if not response_data or response_data.get("error"):
            err = response_data.get("error", "Unknown error")
            self.results_output.setHtml(f"<h3 style='color:#ff4444'>ERROR</h3><p>{err}</p>")
            return

        results = response_data.get('results', [])
        
        if not results:
            self.results_output.setHtml("<p style='color:#94a3b8'>No facts found in the public ledger for this topic.</p>")
            return

        # Sort: Trusted first, then by trust score
        sorted_results = sorted(
            results, 
            key=lambda x: (x.get('status') == 'trusted', x.get('trust_score', 0)), 
            reverse=True
        )

        html = ""
        for i, fact in enumerate(sorted_results):
            status = fact.get('status', 'uncorroborated')
            score = fact.get('trust_score', 1)
            content = fact.get('fact_content', '')
            source = fact.get('source_url', 'Unknown')
            
            # Color Coding Logic matches Node Console
            if status == 'trusted':
                status_html = f"<span style='color:#22c55e; font-weight:bold'>[TRUSTED]</span>"
                border_color = "#22c55e"
            elif status == 'disputed':
                status_html = f"<span style='color:#ef4444; font-weight:bold'>[DISPUTED]</span>"
                border_color = "#ef4444"
            else:
                status_html = f"<span style='color:#00f0ff'>[UNCORROBORATED]</span>"
                border_color = "#334155"

            html += f"""
            <div style="border-left: 4px solid {border_color}; padding-left: 10px; margin-bottom: 15px;">
                <div style="font-size:11px; color:#94a3b8;">
                    {status_html} &nbsp; TRUST SCORE: {score}
                </div>
                <div style="font-size:14px; margin-top:5px; margin-bottom:5px;">
                    {content}
                </div>
                <div style="font-size:10px; color:#64748b;">
                    SOURCE: {source}
                </div>
            </div>
            <hr style="border: 0; height: 1px; background: #1e293b;">
            """
        
        self.results_output.setHtml(html)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AxiomClientApp()
    ex.show()
    sys.exit(app.exec())
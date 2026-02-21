# Axiom - visualize_graph.py
# Copyright (C) 2025 The Axiom Contributors
# --- V3.1: VISUALIZER COMPATIBILITY FIX ---

import argparse
import sys
import os

DB_NAME = "axiom_ledger.db"

def _status_color(status):
    if status == "trusted": return "#00ffcc" # Cyan/Green
    if status == "disputed": return "#ff4444" # Red
    return "#888888" # Gray for uncorroborated

def build_pyvis_html(out_path="axiom_graph.html", db_path=DB_NAME, topic=None):
    try:
        from pyvis.network import Network
        from graph_export import to_json_for_viz
    except ImportError:
        print("Error: Missing libraries. Run: pip install pyvis")
        sys.exit(1)

    print(f"Generating graph from {db_path}...")
    
    # Get Data
    data = to_json_for_viz(db_path, include_sources=True, topic_filter=topic)
    nodes = data['nodes']
    edges = data['edges']
    
    if not nodes:
        print("No facts found to visualize.")
        return

    # Initialize PyVis
    net = Network(height="900px", width="100%", bgcolor="#111111", font_color="white", select_menu=True)
    
    # Add Nodes
    for n in nodes:
        net.add_node(
            n['id'], 
            label=n['label'], 
            title=n.get('title', ''), 
            color=_status_color(n['status']),
            value=n['value']
        )
        
    # Add Edges
    for e in edges:
        net.add_edge(e['from'], e['to'], value=e['value'], color="#333333")

    # Physics Options (Force Directed)
    net.force_atlas_2based(gravity=-50, central_gravity=0.01, spring_length=100, spring_strength=0.08, damping=0.4)
    
    net.save_graph(out_path)
    print(f"Graph saved to: {os.path.abspath(out_path)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", help="Filter graph by topic")
    parser.add_argument("-o", "--output", default="axiom_graph.html", help="Output filename")
    args = parser.parse_args()
    
    build_pyvis_html(out_path=args.output, topic=args.topic)
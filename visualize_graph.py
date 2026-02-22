# Axiom - visualize_graph.py
# Copyright (C) 2025 The Axiom Contributors

import argparse
import sys
import os

DB_NAME = "axiom_ledger.db"

def _status_color(status):
    if status == "trusted": return "#00ffcc" # Cyan
    if status == "disputed": return "#ff4444" # Red
    if status == "atom": return "#ff00ff"    # Pink (Brain Mode)
    return "#888888" # Gray

def build_pyvis_html(out_path="axiom_graph.html", db_path=DB_NAME, topic=None, brain_mode=False):
    try:
        from pyvis.network import Network
        import graph_export
    except ImportError:
        print("Error: Missing libraries. Run: pip install pyvis")
        sys.exit(1)

    print(f"Generating {'BRAIN' if brain_mode else 'LEDGER'} graph...")
    
    # Select Data Mode
    if brain_mode:
        data = graph_export.to_json_for_brain_viz(db_path)
        bg_color = "#0a0a0a" # Darker background for brain
    else:
        data = graph_export.to_json_for_viz(db_path, topic_filter=topic)
        bg_color = "#111111"
    
    nodes, edges = data['nodes'], data['edges']
    if not nodes:
        print("No data found to visualize. Run more engine cycles.")
        return

    net = Network(height="900px", width="100%", bgcolor=bg_color, font_color="white", select_menu=True)
    
    for n in nodes:
        # Determine color: use group if in brain mode, status otherwise
        color_key = n.get('group', n.get('status'))
        net.add_node(n['id'], label=n['label'], color=_status_color(color_key), value=n['value'])
        
    for e in edges:
        # Brain synapses are cyan, Fact links are gray
        edge_color = "#00f0ff" if brain_mode else "#333333"
        net.add_edge(e['from'], e['to'], value=e['value'], color=edge_color)

    # Use Force-Atlas-2 for that "Neural Net" look
    net.force_atlas_2based(gravity=-60, central_gravity=0.01, spring_length=100, spring_strength=0.08)
    
    net.save_graph(out_path)
    print(f"Graph saved to: {os.path.abspath(out_path)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", help="Filter ledger graph by topic")
    parser.add_argument("--brain", action="store_true", help="Visualize the Lexical Mesh (Neural Brain)")
    parser.add_argument("-o", "--output", default="axiom_graph.html", help="Output filename")
    args = parser.parse_args()
    
    build_pyvis_html(out_path=args.output, topic=args.topic, brain_mode=args.brain)
# Axiom - visualize_graph.py
# Copyright (C) 2026 The Axiom Contributors

import argparse
import json

DB_NAME = "axiom_ledger.db"


def get_node_colors(status, is_brain):
    """Returns raw hex colors for the JS Canvas Renderer."""
    if is_brain:
        return "#ff00ff"
    if status == "trusted":
        return "#22c55e"
    if status == "disputed":
        return "#ff0055"
    return "#00f0ff"


def inject_sota_engine(filepath, total_nodes, node_data_json, mode_label):
    """Injects the 3D Math, Plasma Engine, and SOTA HUD Modal into the specific file."""
    with open(filepath, encoding="utf-8") as file:
        html = file.read()

    html = html.replace("background-color: #ffffff;", "")

    cyberpunk_css = """
    <style>
        html, body {
            background-color: #000000 !important;
            background: #000000 !important;
            color: #00f0ff !important;
            font-family: 'Courier New', Courier, monospace !important;
            margin: 0; padding: 0; overflow: hidden;
            width: 100vw; height: 100vh;
        }
        #mynetwork { border: none !important; background-color: #000000 !important; height: 100vh !important; width: 100vw !important; outline: none !important;}
        
        #hud {
            position: absolute; top: 20px; left: 20px;
            background: rgba(5, 5, 5, 0.95); border: 1px solid #00f0ff;
            padding: 15px; border-radius: 2px; z-index: 1000;
            box-shadow: 0 0 15px rgba(0, 240, 255, 0.1);
            text-transform: uppercase;
        }

        #axiom-modal {
            position: absolute; top: 20px; right: -450px; 
            width: 380px; max-height: 85vh;
            background: rgba(5, 8, 12, 0.98);
            border: 1px solid rgba(0, 240, 255, 0.4); 
            border-left: 4px solid #00f0ff;
            padding: 25px; border-radius: 4px; z-index: 2000;
            box-shadow: -10px 0 40px rgba(0, 0, 0, 1);
            transition: right 0.3s cubic-bezier(0.1, 0.8, 0.2, 1);
            backdrop-filter: blur(15px);
            display: flex; flex-direction: column;
        }
        #axiom-modal.active { right: 20px; }
        .modal-header { font-size: 18px; font-weight: bold; color: #ffffff; margin-bottom: 5px; padding-bottom: 10px; border-bottom: 1px dashed rgba(0, 240, 255, 0.3); text-transform: uppercase; letter-spacing: 2px; }
        .modal-status { font-size: 12px; margin-bottom: 10px; font-weight: bold; }
        .modal-content { font-size: 15px; color: #e0e0e0; line-height: 1.8; margin-bottom: 20px; overflow-y: auto; padding: 15px; background: rgba(0, 240, 255, 0.05); border: 1px solid rgba(0, 240, 255, 0.15); border-radius: 2px; white-space: pre-wrap; word-wrap: break-word; }
        .modal-meta { font-size: 11px; color: #666; word-break: break-all; border-top: 1px solid #222; padding-top: 15px; line-height: 1.5; }
        .close-btn { position: absolute; top: 15px; right: 15px; color: #ff0055; cursor: pointer; font-weight: bold; font-size: 20px; z-index: 2001; }
        .modal-content::-webkit-scrollbar { width: 4px; }
        .modal-content::-webkit-scrollbar-thumb { background: #00f0ff; border-radius: 10px; }
        .vis-tooltip { display: none !important; }
    </style>
    </head>
    """
    html = html.replace("</head>", cyberpunk_css)

    engine_js = f"""
    <div id="hud">
        <div style="color:#00f0ff; font-weight:bold; font-size:14px; margin-bottom:10px; border-bottom:1px dashed #00f0ff; padding-bottom:5px;">◈ AXIOM HUD :: {mode_label}</div>
        <div class="hud-line">ENTITIES: <span class="hud-val">{total_nodes}</span></div>
        <div class="hud-line">PHYSICS: <span class="hud-val" id="hud-physics" style="color:#ff00ff;">BOOTING</span></div>
        <div class="hud-line">SYSTEM: <span class="hud-val" style="color:#22c55e;">ACTIVE</span></div>
    </div>

    <div id="axiom-modal">
        <div class="close-btn" onclick="closeModal()">✕</div>
        <div class="modal-header" id="modal-title">NODE ID</div>
        <div class="modal-status" id="modal-status">[STATUS]</div>
        <div class="modal-content" id="modal-text">Content...</div>
        <div class="modal-meta" id="modal-meta">Meta...</div>
    </div>

    <script>
        const axiomData = {node_data_json};
        let physicsActive = true;
        let animationTime = 0;
        const CAMERA_Z = 1000;
        let cachedPositions = null;
        let cachedEdges = null;
        const MAX_EDGES_FOR_FANCY = 800;

        const initInterval = setInterval(() => {{
            if (typeof network !== 'undefined') {{ clearInterval(initInterval); startAxiomEngine(); }}
        }}, 100);

        function startAxiomEngine() {{
            network.on("stabilizationProgress", function(params) {{
                let progress = Math.round((params.iterations / params.total) * 100);
                document.getElementById('hud-physics').innerText = `STABILIZING... ${{progress}}%`;
            }});

            network.once("stabilizationIterationsDone", function() {{
                network.setOptions({{ physics: false }});
                physicsActive = false;
                cachedPositions = network.getPositions();
                cachedEdges = edges.get();
                document.getElementById('hud-physics').innerText = "FROZEN (60 FPS)";
                document.getElementById('hud-physics').style.color = "#22c55e";
                requestAnimationFrame(renderLoop);
            }});
            
            // Failsafe if stabilization is too fast
            setTimeout(() => {{ if(physicsActive) network.emit("stabilizationIterationsDone"); }}, 2000);

            // CLICK HANDLER
            network.on("click", function(params) {{
                if (params.nodes.length > 0) {{
                    const nodeId = params.nodes[0];
                    const data = axiomData[nodeId];
                    if (data) {{
                        document.getElementById('modal-title').innerText = data.is_brain ? "Linguistic Atom" : "Verified Record";
                        document.getElementById('modal-status').innerText = `[${{data.status.toUpperCase()}}]`;
                        document.getElementById('modal-status').style.color = data.color;
                        document.getElementById('axiom-modal').style.borderLeftColor = data.color;
                        document.getElementById('modal-text').innerText = data.content;
                        let metaHtml = data.source ? `<b>SOURCE:</b><br><a href="${{data.source}}" target="_blank" style="color:#00f0ff;">${{data.source}}</a>` : `<b>STRENGTH:</b> ${{data.value}}`;
                        document.getElementById('modal-meta').innerHTML = metaHtml;
                        document.getElementById('axiom-modal').classList.add('active');
                        document.getElementById('modal-text').scrollTop = 0;
                    }}
                }} else {{ closeModal(); }}
            }});

            // When the user drags nodes, refresh cached positions so the renderer stays in sync.
            network.on("dragEnd", function() {{
                cachedPositions = network.getPositions();
            }});

            network.on("beforeDrawing", function (ctx) {{
                const positions = cachedPositions || network.getPositions();
                const edgesData = cachedEdges || edges.get();
                ctx.globalCompositeOperation = "screen";
                if (!physicsActive) animationTime += 0.02;

                const totalEdges = edgesData.length || 0;
                const edgeStep = totalEdges > MAX_EDGES_FOR_FANCY ? Math.ceil(totalEdges / MAX_EDGES_FOR_FANCY) : 1;
                for (let ei = 0; ei < totalEdges; ei += edgeStep) {{
                    const edge = edgesData[ei];
                    let p1 = positions[edge.from], p2 = positions[edge.to];
                    if (!p1 || !p2) return;
                    let d1 = axiomData[edge.from], d2 = axiomData[edge.to];
                    
                    let proj1 = {{x: p1.x * (CAMERA_Z/(CAMERA_Z+d1.z)), y: p1.y * (CAMERA_Z/(CAMERA_Z+d1.z)), s: (CAMERA_Z/(CAMERA_Z+d1.z))}};
                    let proj2 = {{x: p2.x * (CAMERA_Z/(CAMERA_Z+d2.z)), y: p2.y * (CAMERA_Z/(CAMERA_Z+d2.z)), s: (CAMERA_Z/(CAMERA_Z+d2.z))}};
                    let dx = proj2.x - proj1.x, dy = proj2.y - proj1.y;
                    let dist = Math.sqrt(dx*dx + dy*dy), angle = Math.atan2(dy, dx);

                    ctx.save();
                    ctx.translate(proj1.x, proj1.y); ctx.rotate(angle);
                    for (let w = 1; w <= 2; w++) {{
                        ctx.beginPath(); ctx.strokeStyle = (w === 1) ? d1.color : d2.color;
                        ctx.lineWidth = 1.0; ctx.shadowBlur = 10; ctx.shadowColor = ctx.strokeStyle;
                        ctx.globalAlpha = 0.7;
                        const segmentStep = dist > 300 ? 12 : 6;
                        for (let i = 0; i <= dist; i += segmentStep) {{
                            let env = Math.sin((i / dist) * Math.PI);
                            let off = (Math.sin(i * 0.03 * w + animationTime) + Math.cos(i * 0.06 - animationTime * 1.3)) * 6 * env;
                            if (i === 0) ctx.moveTo(i, off); else ctx.lineTo(i, off);
                        }}
                        ctx.stroke();
                    }}
                    ctx.restore();
                }}

                ctx.globalCompositeOperation = "source-over";
                for (let nodeId in positions) {{
                    let pos = positions[nodeId], data = axiomData[nodeId];
                    if (!data) continue; 
                    let s_ = CAMERA_Z / (CAMERA_Z + data.z);
                    let proj = {{x: pos.x * s_, y: pos.y * s_, s: s_}};
                    let size = (Math.min(data.value * 3 + 10, 40)) * proj.s;
                    ctx.fillStyle = data.color; ctx.shadowColor = data.color; ctx.shadowBlur = 20 * proj.s;
                    ctx.fillRect(proj.x - size/2, proj.y - size/2, size, size);
                    ctx.fillStyle = "#ffffff"; ctx.shadowBlur = 0;
                    ctx.fillRect(proj.x - size/4, proj.y - size/4, size/2, size/2);
                }}
            }});
        }}
        function closeModal() {{ document.getElementById('axiom-modal').classList.remove('active'); network.unselectAll(); }}
        function renderLoop() {{ if (!physicsActive) network.redraw(); requestAnimationFrame(renderLoop); }}
    </script>
    </body>
    """
    html = html.replace("</body>", engine_js)
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(html)


def build_pyvis_html(out_path, data, mode_label, is_brain):
    from pyvis.network import Network

    nodes, edges = data["nodes"], data["edges"]
    if not nodes:
        return

    node_data_dict = {}
    added_node_ids = set()

    for n in nodes:
        added_node_ids.add(n["id"])
        z = 200 if is_brain else (0 if n.get("status") == "trusted" else -200)
        content = n.get("label") or n.get("full_content") or ""
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        node_data_dict[n["id"]] = {
            "content": content,
            "status": n.get(
                "status",
                "brain" if is_brain else "uncorroborated",
            ),
            "value": n["value"],
            "source": n.get("source_url", "") or "",
            "is_brain": is_brain,
            "color": get_node_colors(n.get("status", ""), is_brain),
            "z": z,
        }

    net = Network(height="100vh", width="100%", bgcolor="#000000")
    vis_options = {
        "nodes": {
            "color": "rgba(0,0,0,0)",
            "font": {"size": 0},
            "borderWidth": 0,
            "shadow": {"enabled": False},
        },
        "edges": {"color": "rgba(0,0,0,0)", "shadow": {"enabled": False}},
        "physics": {
            "solver": "forceAtlas2Based",
            "forceAtlas2Based": {
                "gravitationalConstant": -150,
                "centralGravity": 0.02,
                "springLength": 200,
                "springConstant": 0.05,
                "damping": 0.6,
                "avoidOverlap": 0.5,
            },
            "stabilization": {"enabled": True, "iterations": 150},
        },
        "interaction": {"hover": False, "dragNodes": True, "selectable": True},
    }
    net.set_options(json.dumps(vis_options))

    for n in nodes:
        net.add_node(n["id"], label=" ", value=n["value"], size=25)

    for e in edges:
        if e["from"] in added_node_ids and e["to"] in added_node_ids:
            net.add_edge(e["from"], e["to"], value=e["value"])

    net.save_graph(out_path)
    inject_sota_engine(
        out_path,
        len(nodes),
        json.dumps(node_data_dict),
        mode_label,
    )


if __name__ == "__main__":
    from src import graph_export

    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", help="Filter ledger graph by topic")
    args = parser.parse_args()

    print("Generating Ledger HUD: axiom_graph.html")
    ledger_data = graph_export.to_json_for_viz(
        DB_NAME,
        topic_filter=args.topic,
    )
    build_pyvis_html("axiom_graph.html", ledger_data, "FACT_LEDGER", False)

    print("Generating Brain HUD: axiom_brain.html")
    brain_data = graph_export.to_json_for_brain_viz(DB_NAME)
    build_pyvis_html("axiom_brain.html", brain_data, "LEXICAL_MESH", True)

    print("\033[92mSuccess: Dual Sovereign HUDs generated.\033[0m")

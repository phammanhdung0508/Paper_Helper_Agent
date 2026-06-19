import json
import os
from typing import List, Dict, Any
from app.agents import MasteryEvaluatorAgent

# Load local vis-network js content if available for offline usage, otherwise fallback to CDN
_dir = os.path.dirname(os.path.abspath(__file__))
_local_js_path = os.path.join(_dir, "static", "vis-network.min.js")
if os.path.exists(_local_js_path):
    try:
        with open(_local_js_path, "r", encoding="utf-8") as _f:
            _vis_js_content = f"<script type='text/javascript'>\n{_f.read()}\n</script>"
    except Exception:
        _vis_js_content = '<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
else:
    _vis_js_content = '<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'

def get_color_for_score(score: int) -> str:
    """Returns the HEX color corresponding to the mastery score level."""
    if score < 1:
        return "#b6b6ba"  # Grey (unstarted)
    elif score < 25:
        return "#7e9bc8"  # Blue (familiar)
    elif score < 50:
        return "#8b78d9"  # Violet (developing)
    elif score < 75:
        return "#4fae84"  # Light green (competent)
    else:
        return "#16a06d"  # Deep emerald (mastered)

def generate_vis_html(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], selected_id: str = None) -> str:
    """Generates an interactive Vis.js network graph HTML string."""
    vis_nodes = []
    for n in nodes:
        scores = {
            "memory": n.get("memory", 0),
            "comprehension": n.get("comprehension", 0),
            "structure": n.get("structure", 0),
            "application": n.get("application", 0)
        }
        unified_score = MasteryEvaluatorAgent.calculate_unified_score(scores)
        color = get_color_for_score(unified_score)
        
        # Highlight node if selected
        border_color = "#ffffff" if n["id"] == selected_id else color
        border_width = 4 if n["id"] == selected_id else 2
        
        vis_nodes.append({
            "id": n["id"],
            "label": n["label"],
            "title": f"Mastery: {unified_score}%",
            "color": {
                "background": color,
                "border": border_color,
                "highlight": {
                    "background": color,
                    "border": "#ffffff"
                }
            },
            "borderWidth": border_width,
            "shape": "dot",
            "size": 20 + unified_score * 0.15  # Node size grows slightly with mastery!
        })
        
    vis_edges = []
    for e in edges:
        # Match type to edge styling
        dashes = False
        color = "#475569"
        if e["type"] == "prerequisite":
            dashes = True
            color = "#8b78d9"
        elif e["type"] == "causal":
            color = "#ef4444"
            
        vis_edges.append({
            "from": e["source"],
            "to": e["target"],
            "label": e["type"],
            "arrows": "to",
            "dashes": dashes,
            "color": {"color": color, "highlight": "#ffffff"},
            "title": e.get("description", "")
        })

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Knowledge Graph</title>
        {_vis_js_content}
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: #0f172a; /* Slate 900 */
                font-family: 'Outfit', sans-serif;
                overflow: hidden;
            }}
            #network {{
                width: 100vw;
                height: 100vh;
                position: relative;
            }}
            #legend {{
                position: absolute;
                bottom: 15px;
                left: 15px;
                background: rgba(15, 23, 42, 0.85);
                border: 1px solid #1e293b;
                padding: 10px;
                border-radius: 8px;
                color: #e2e8f0;
                font-size: 11px;
                z-index: 10;
                backdrop-filter: blur(4px);
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                margin-bottom: 4px;
            }}
            .legend-color {{
                width: 12px;
                height: 12px;
                border-radius: 50%;
                margin-right: 8px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            #helper {{
                position: absolute;
                top: 15px;
                left: 15px;
                color: #94a3b8;
                font-size: 12px;
                z-index: 10;
                pointer-events: none;
            }}
        </style>
    </head>
    <body>
        <div id="helper">Click on a concept node to view details & evaluate mastery</div>
        
        <div id="legend">
            <div style="font-weight: 600; margin-bottom: 6px; border-bottom: 1px solid #334155; padding-bottom: 3px;">Mastery Score levels</div>
            <div class="legend-item"><div class="legend-color" style="background: #b6b6ba;"></div>Unstarted (0)</div>
            <div class="legend-item"><div class="legend-color" style="background: #7e9bc8;"></div>Familiar (1-24)</div>
            <div class="legend-item"><div class="legend-color" style="background: #8b78d9;"></div>Developing (25-49)</div>
            <div class="legend-item"><div class="legend-color" style="background: #4fae84;"></div>Competent (50-74)</div>
            <div class="legend-item"><div class="legend-color" style="background: #16a06d;"></div>Mastered (75-100)</div>
        </div>

        <div id="network"></div>

        <script type="text/javascript">
            // Parse network data
            var nodesData = {nodes_json};
            var edgesData = {edges_json};

            var container = document.getElementById('network');
            var data = {{
                nodes: new vis.DataSet(nodesData),
                edges: new vis.DataSet(edgesData)
            }};
            
            var options = {{
                nodes: {{
                    shape: 'dot',
                    font: {{
                        size: 14,
                        color: '#f8fafc',
                        face: 'Outfit'
                    }},
                    shadow: {{
                        enabled: true,
                        color: 'rgba(0,0,0,0.5)',
                        size: 8,
                        x: 2,
                        y: 4
                    }}
                }},
                edges: {{
                    width: 2.5,
                    font: {{
                        size: 10,
                        color: '#94a3b8',
                        face: 'Outfit',
                        align: 'middle',
                        strokeWidth: 0
                    }},
                    smooth: {{
                        type: 'cubicBezier',
                        roundness: 0.4
                    }},
                    shadow: {{
                        enabled: true,
                        color: 'rgba(0,0,0,0.3)',
                        size: 3,
                        x: 1,
                        y: 2
                    }}
                }},
                physics: {{
                    solver: 'forceAtlas2Based',
                    forceAtlas2Based: {{
                        gravitationalConstant: -80,
                        centralGravity: 0.015,
                        springLength: 120,
                        springConstant: 0.06,
                        damping: 0.9
                    }},
                    stabilization: {{
                        iterations: 150,
                        updateInterval: 25
                    }}
                }},
                interaction: {{
                    hover: true,
                    tooltipDelay: 200
                }}
            }};
            
            var network = new vis.Network(container, data, options);
            
            // Send selected node ID to Gradio via window message
            network.on("selectNode", function (params) {{
                if (params.nodes.length > 0) {{
                    var nodeId = params.nodes[0];
                    window.parent.postMessage(nodeId, "*");
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html

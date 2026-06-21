import json
import logging
import os
from typing import List, Dict, Any
from app.agents import MasteryEvaluatorAgent

logger = logging.getLogger(__name__)

# Load local vis-network js content if available for offline usage, otherwise fallback to CDN
_dir = os.path.dirname(os.path.abspath(__file__))
_local_js_path = os.path.join(_dir, "static", "vis-network.min.js")
if os.path.exists(_local_js_path):
    try:
        with open(_local_js_path, "r", encoding="utf-8") as _f:
            _vis_js_content = f"<script type='text/javascript'>\n{_f.read()}\n</script>"
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"Failed to read local vis-network.min.js: {e}. Falling back to CDN.")
        _vis_js_content = '<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
else:
    _vis_js_content = '<script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'

# Load local three.js content for offline 3D rendering
_local_three_path = os.path.join(_dir, "static", "three.min.js")
if os.path.exists(_local_three_path):
    try:
        with open(_local_three_path, "r", encoding="utf-8") as _f:
            _three_js_content = f"<script type='text/javascript'>\n{_f.read()}\n</script>"
    except (FileNotFoundError, IOError) as e:
        logger.warning(f"Failed to read local three.min.js: {e}. Falling back to CDN.")
        _three_js_content = '<script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
else:
    _three_js_content = '<script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'

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
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: #0f172a; /* Slate 900 */
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
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
                        face: 'system-ui, -apple-system, sans-serif'
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
                        face: 'system-ui, -apple-system, sans-serif',
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
            
            // Send selected node ID to Next.js parent via window message
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

def generate_three_html(spec_json: Dict[str, Any]) -> str:
    """
    Generates a fully self-contained WebGL 3D semantic vector space HTML string.
    Loads offline three.min.js, sets up dragging controls, projects HTML labels,
    and shows rich tooltips on hover.
    """
    points = spec_json.get("points", [])
    connections = spec_json.get("connections", [])
    
    points_json = json.dumps(points)
    connections_json = json.dumps(connections)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>3D Semantic Vector Space</title>
        {_three_js_content}
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: #0b0f19; /* Sleek dark blue/slate */
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                overflow: hidden;
                color: #f8fafc;
                user-select: none;
            }}
            #canvas-container {{
                width: 100vw;
                height: 100vh;
                position: relative;
            }}
            .node-label {{
                position: absolute;
                transform: translate(-50%, -100%);
                background: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #e2e8f0;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 500;
                pointer-events: none;
                white-space: nowrap;
                backdrop-filter: blur(2px);
                transition: opacity 0.15s ease;
                z-index: 5;
            }}
            #tooltip {{
                position: absolute;
                display: none;
                background: rgba(15, 23, 42, 0.95);
                border: 1px solid #3b82f6; /* Accent blue */
                color: #f8fafc;
                padding: 10px 14px;
                border-radius: 8px;
                font-size: 12px;
                line-height: 1.4;
                pointer-events: none;
                z-index: 100;
                max-width: 250px;
                backdrop-filter: blur(8px);
                box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
            }}
            #instructions {{
                position: absolute;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(15, 23, 42, 0.8);
                border: 1px solid rgba(255, 255, 255, 0.08);
                padding: 8px 16px;
                border-radius: 9999px;
                font-size: 11px;
                color: #94a3b8;
                pointer-events: none;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                backdrop-filter: blur(4px);
                z-index: 10;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            }}
            .accent-text {{
                color: #3b82f6;
                font-weight: 600;
            }}
        </style>
    </head>
    <body>
        <div id="canvas-container">
            <div id="labels-container"></div>
            <div id="tooltip"></div>
            <div id="instructions">
                Drag to <span class="accent-text">Rotate</span> &bull; Scroll to <span class="accent-text">Zoom</span> &bull; Hover to <span class="accent-text">Inspect</span>
            </div>
        </div>

        <script>
            // Parse point and connection specifications
            const pointsData = {points_json};
            const connectionsData = {connections_json};

            // Setup scene, camera, renderer
            const scene = new THREE.Scene();
            scene.fog = new THREE.FogExp2(0x0b0f19, 0.03); // Sleek fog depth effect

            const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
            camera.position.z = 8;

            const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            document.getElementById('canvas-container').appendChild(renderer.domElement);

            // Add lighting
            const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
            scene.add(ambientLight);

            const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
            dirLight.position.set(5, 10, 7);
            scene.add(dirLight);

            // Setup central rotation group
            const group = new THREE.Group();
            scene.add(group);

            // Create HTML elements for text labels
            const labelsContainer = document.getElementById('labels-container');
            const spheres = [];
            const pointMap = {{}};

            // Render Nodes
            pointsData.forEach(p => {{
                // Geometry & premium materials
                const size = 0.25;
                const geometry = new THREE.SphereGeometry(size, 32, 32);
                
                // Embellish material with slight emissivity/shininess
                const material = new THREE.MeshPhongMaterial({{
                    color: new THREE.Color(p.color || '#8b78d9'),
                    shininess: 80,
                    specular: 0xffffff,
                    emissive: new THREE.Color(p.color || '#8b78d9'),
                    emissiveIntensity: 0.15
                }});

                const sphere = new THREE.Mesh(geometry, material);
                sphere.position.set(p.x, p.y, p.z);
                sphere.userData = p;
                
                group.add(sphere);
                spheres.push(sphere);
                pointMap[p.label] = sphere.position;

                // Create text label DOM node
                const labelDiv = document.createElement('div');
                labelDiv.className = 'node-label';
                labelDiv.id = 'label-' + p.label.replace(/\\s+/g, '-');
                labelDiv.innerText = p.label;
                labelsContainer.appendChild(labelDiv);
            }});

            // Render Connections/Lines
            connectionsData.forEach(c => {{
                const startPos = pointMap[c.source];
                const endPos = pointMap[c.target];
                if (startPos && endPos) {{
                    const points = [startPos, endPos];
                    const geometry = new THREE.BufferGeometry().setFromPoints(points);
                    
                    const material = new THREE.LineBasicMaterial({{
                        color: new THREE.Color(c.color || '#475569'),
                        transparent: true,
                        opacity: 0.5,
                        linewidth: 2.0
                    }});

                    const line = new THREE.Line(geometry, material);
                    group.add(line);
                }}
            }});

            // Add simple grid background for visual reference
            const gridHelper = new THREE.GridHelper(20, 20, 0x1e293b, 0x1e293b);
            gridHelper.position.y = -3.5;
            scene.add(gridHelper);

            // Drag Rotation Event Handlers
            let isDragging = false;
            let previousMousePosition = {{ x: 0, y: 0 }};

            document.addEventListener('mousedown', e => {{
                isDragging = true;
                previousMousePosition = {{ x: e.clientX, y: e.clientY }};
            }});

            document.addEventListener('mousemove', e => {{
                if (!isDragging) return;
                const deltaMove = {{
                    x: e.clientX - previousMousePosition.x,
                    y: e.clientY - previousMousePosition.y
                }};
                group.rotation.y += deltaMove.x * 0.005;
                group.rotation.x += deltaMove.y * 0.005;
                previousMousePosition = {{ x: e.clientX, y: e.clientY }};
            }});

            document.addEventListener('mouseup', () => {{ isDragging = false; }});

            // Touch events
            document.addEventListener('touchstart', e => {{
                if (e.touches.length === 1) {{
                    isDragging = true;
                    previousMousePosition = {{ x: e.touches[0].clientX, y: e.touches[0].clientY }};
                }}
            }});

            document.addEventListener('touchmove', e => {{
                if (!isDragging || e.touches.length !== 1) return;
                const deltaMove = {{
                    x: e.touches[0].clientX - previousMousePosition.x,
                    y: e.touches[0].clientY - previousMousePosition.y
                }};
                group.rotation.y += deltaMove.x * 0.008;
                group.rotation.x += deltaMove.y * 0.008;
                previousMousePosition = {{ x: e.touches[0].clientX, y: e.touches[0].clientY }};
            }});

            document.addEventListener('touchend', () => {{ isDragging = false; }});

            // Zoom functionality via Scroll
            document.addEventListener('wheel', e => {{
                camera.position.z = Math.max(3, Math.min(20, camera.position.z + e.deltaY * 0.008));
            }}, {{ passive: true }});

            // Raycaster for hovering and tooltips
            const raycaster = new THREE.Raycaster();
            const mouse = new THREE.Vector2();
            const tooltip = document.getElementById('tooltip');

            document.addEventListener('mousemove', e => {{
                mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
                mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;

                raycaster.setFromCamera(mouse, camera);
                const intersects = raycaster.intersectObjects(spheres);

                if (intersects.length > 0) {{
                    const sphere = intersects[0].object;
                    const p = sphere.userData;
                    
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.clientX + 15) + 'px';
                    tooltip.style.top = (e.clientY + 15) + 'px';
                    tooltip.innerHTML = `
                        <div style="font-weight:600; font-size:13px; color:#3b82f6; margin-bottom:4px;">${{p.label}}</div>
                        <div style="color:#cbd5e1; margin-bottom:6px;">${{p.description || 'Semantic cluster item'}}</div>
                        <div style="color:#64748b; font-size:10px; font-family:monospace;">Coords: [${{p.x.toFixed(2)}}, ${{p.y.toFixed(2)}}, ${{p.z.toFixed(2)}}]</div>
                    `;
                    document.body.style.cursor = 'pointer';

                    // Pulse/hover effect: scale sphere up slightly
                    spheres.forEach(s => s.scale.set(1, 1, 1));
                    sphere.scale.set(1.4, 1.4, 1.4);
                }} else {{
                    tooltip.style.display = 'none';
                    document.body.style.cursor = 'default';
                    spheres.forEach(s => s.scale.set(1, 1, 1));
                }}
            }});

            // Map 3D positions to 2D HTML labels
            function updateLabels() {{
                pointsData.forEach(p => {{
                    const vector = new THREE.Vector3(p.x, p.y, p.z);
                    // Account for group rotation/position transformations
                    vector.applyMatrix4(group.matrixWorld);
                    vector.project(camera);
                    
                    const x = (vector.x * 0.5 + 0.5) * window.innerWidth;
                    const y = (-(vector.y * 0.5) + 0.5) * window.innerHeight;

                    const el = document.getElementById('label-' + p.label.replace(/\\s+/g, '-'));
                    if (el) {{
                        if (vector.z > 1) {{
                            el.style.display = 'none';
                        }} else {{
                            el.style.display = 'block';
                            el.style.left = x + 'px';
                            el.style.top = (y - 15) + 'px';
                            
                            // Adjust opacity based on depth distance
                            const distance = camera.position.distanceTo(new THREE.Vector3(p.x, p.y, p.z).applyMatrix4(group.matrixWorld));
                            el.style.opacity = Math.max(0.2, Math.min(1.0, 10 / distance));
                        }}
                    }}
                }});
            }}

            // Window Resize Handler
            window.addEventListener('resize', () => {{
                camera.aspect = window.innerWidth / window.innerHeight;
                camera.updateProjectionMatrix();
                renderer.setSize(window.innerWidth, window.innerHeight);
            }});

            // Animation loop
            function animate() {{
                requestAnimationFrame(animate);

                // Auto rotate group slowly if user isn't interacting
                if (!isDragging) {{
                    group.rotation.y += 0.001;
                }}

                updateLabels();
                renderer.render(scene, camera);
            }}

            animate();
        </script>
    </body>
    </html>
    """
    return html

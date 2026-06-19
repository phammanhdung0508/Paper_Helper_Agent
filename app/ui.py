import gradio as gr
import os
from typing import Dict, Any, List, Tuple
import uuid
import json
import plotly.graph_objects as go
from langchain_core.messages import HumanMessage, AIMessage
from langfuse import Langfuse

from app import config
from app import database
from app import visualizer
from app import graph
from app.agents import ConceptGraphAgent, VisualSandboxAgent, MasteryEvaluatorAgent

# Global state / caches
active_document_id = None

# Custom CSS for modern premium glassmorphic dark-mode look
CUSTOM_CSS = """
body, .gradio-container {
    background-color: #0b0f19 !important;
    color: #f8fafc !important;
    font-family: 'Outfit', 'Inter', sans-serif !important;
}
.tabs {
    border: none !important;
}
.tab-nav {
    border-bottom: 2px solid #1e293b !important;
    margin-bottom: 15px !important;
}
.tab-nav button {
    font-weight: 600 !important;
    color: #94a3b8 !important;
}
.tab-nav button.selected {
    color: #8b78d9 !important;
    border-bottom: 2px solid #8b78d9 !important;
}
.glass-panel {
    background: rgba(17, 24, 39, 0.7) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    padding: 15px !important;
}
.progress-bar-container {
    width: 100%;
    background-color: #1e293b;
    border-radius: 6px;
    margin-bottom: 8px;
    overflow: hidden;
    height: 12px;
}
.progress-bar-fill {
    height: 100%;
    border-radius: 6px;
    transition: width 0.5s ease-in-out;
}
"""

# HTML message helper
def make_progress_bar(label: str, score: int, color: str) -> str:
    return f"""
    <div style="margin-bottom: 10px;">
        <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 600; margin-bottom: 3px;">
            <span>{label}</span>
            <span>{score}%</span>
        </div>
        <div class="progress-bar-container">
            <div class="progress-bar-fill" style="width: {score}%; background-color: {color};"></div>
        </div>
    </div>
    """

def get_concept_details_html(concept: Dict[str, Any]) -> str:
    if not concept:
        return "<div style='color: #94a3b8; text-align: center; margin-top: 50px;'>Select a node in the graph to view its mastery profile</div>"
        
    scores = {
        "memory": concept.get("memory", 0),
        "comprehension": concept.get("comprehension", 0),
        "structure": concept.get("structure", 0),
        "application": concept.get("application", 0)
    }
    
    unified_score = MasteryEvaluatorAgent.calculate_unified_score(scores)
    color = visualizer.get_color_for_score(unified_score)
    
    html = f"""
    <div style="padding: 10px;">
        <h2 style="margin-top: 0; font-size: 20px; font-weight: 600; color: #f8fafc; border-bottom: 1px solid #1e293b; padding-bottom: 10px;">{concept['label']}</h2>
        <p style="font-size: 13px; color: #94a3b8; line-height: 1.5; margin-bottom: 15px;">{concept['explanation']}</p>
        
        <div style="background: rgba(30, 41, 59, 0.4); border-radius: 8px; padding: 12px; border: 1px solid #1e293b; margin-bottom: 18px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <span style="font-size: 13px; font-weight: 600; color: #94a3b8;">Unified Mastery Score</span>
                <span style="font-size: 18px; font-weight: 700; color: {color};">{unified_score}%</span>
            </div>
            <div style="font-size: 11px; color: #64748b;">Primary Ref: Page {concept['page_number']}</div>
        </div>
        
        <h3 style="font-size: 14px; font-weight: 600; color: #e2e8f0; margin-bottom: 10px;">Mastery Dimensions</h3>
        {make_progress_bar("Memory Recall", scores['memory'], "#7e9bc8")}
        {make_progress_bar("Conceptual Comprehension", scores['comprehension'], "#8b78d9")}
        {make_progress_bar("Structural Relationships", scores['structure'], "#4fae84")}
        {make_progress_bar("Practical Application", scores['application'], "#16a06d")}
    </div>
    """
    return html

def build_visual_spec_display(spec: Dict[str, Any]):
    if not spec:
        return gr.update(visible=False), gr.update(value="", visible=True), gr.update(visible=False)
        
    spec_type = spec.get("type", "")
    title = spec.get("title", "")
    desc = spec.get("description", "")
    spec_json = spec.get("spec_json", {})
    
    md_header = f"## {title}\n*{desc}*\n\n---\n"
    
    if spec_type == "plotly":
        fig = go.Figure()
        data = spec_json.get("data", [])
        layout = spec_json.get("layout", {})
        
        for trace in data:
            trace_type = trace.get("type", "scatter")
            x = trace.get("x", [])
            y = trace.get("y", [])
            name = trace.get("name", "")
            line = trace.get("line", {})
            
            if trace_type == "scatter":
                fig.add_trace(go.Scatter(x=x, y=y, mode=trace.get("mode", "lines"), name=name, line=line))
            elif trace_type == "bar":
                fig.add_trace(go.Bar(x=x, y=y, name=name))
                
        layout["paper_bgcolor"] = "rgba(0,0,0,0)"
        layout["plot_bgcolor"] = "rgba(0,0,0,0)"
        layout["font"] = {"color": "#94a3b8", "family": "Outfit"}
        layout["margin"] = {"t": 40, "b": 40, "l": 40, "r": 40}
        fig.update_layout(layout)
        
        return gr.update(value=fig, visible=True), gr.update(value=md_header, visible=True), gr.update(visible=False)
        
    elif spec_type == "katex":
        steps = spec_json.get("steps", [])
        md = md_header
        for i, step in enumerate(steps):
            md += f"### Step {i+1}\n"
            md += f"$${step['formula']}$$\n\n"
            md += f"*{step['explanation']}*\n\n"
            md += "---\n"
        return gr.update(visible=False), gr.update(value=md, visible=True), gr.update(visible=False)
        
    elif spec_type == "canvas":
        steps = spec_json.get("steps", [])
        md = md_header + "### System Walkthrough:\n\n"
        for i, step in enumerate(steps):
            md += f"**Step {i+1}: {step.get('title', 'Action')}**\n"
            md += f"{step.get('description', '')}\n"
            if 'details' in step:
                md += f"- *Details: {step['details']}*\n"
            md += "\n"
        return gr.update(visible=False), gr.update(value=md, visible=True), gr.update(visible=False)
        
    return gr.update(visible=False), gr.update(value="Unsupported Spec", visible=True), gr.update(visible=False)

# --- UI Callback Handlers at Module Scope ---

def update_doc_list():
    docs = database.get_documents()
    choices = [(d["name"], d["id"]) for d in docs]
    if not choices:
        choices = [("Lab 3 Company Policies", "company_policies")]
    
    active_id = active_document_id or (choices[0][1] if choices else "")
    return gr.update(choices=choices, value=active_id), choices

def load_document_workspace(doc_id):
    global active_document_id
    active_document_id = doc_id
    
    if not doc_id:
        return (
            gr.update(value="No document selected"),
            gr.update(maximum=1, minimum=1, value=1),
            "",
            "",
            "<div style='color:#94a3b8; text-align:center; padding:100px;'>Select a workspace to view graph.</div>",
            gr.update(choices=[], value=""),
            gr.update(visible=False),
            gr.update(value=""),
            gr.update(visible=False)
        )
        
    doc = database.get_document(doc_id)
    pages = database.get_document_pages(doc_id)
    page_count = len(pages)
    stats_html = f"""
    <div style="font-size:12px; color:#94a3b8; line-height:1.5;">
        <div><strong>Document ID:</strong> {doc_id}</div>
        <div><strong>Page Count:</strong> {page_count} pages</div>
        <div><strong>Added On:</strong> {doc['added_at'] if doc else 'System Default'}</div>
    </div>
    """
    
    page_text = pages[0]["text"] if pages else ""
    
    db_nodes = database.get_concepts(doc_id)
    db_edges = database.get_concept_edges(doc_id)
    
    if not db_nodes and pages:
        total_text = "\n".join([p["text"] for p in pages])
        db_nodes, db_edges = ConceptGraphAgent.build_graph(doc_id, total_text)
        database.save_concepts(db_nodes)
        database.save_concept_edges(db_edges)
        
        for n in db_nodes:
            c_id = f"{doc_id}_concept_{n['label'].lower().replace(' ', '_')}"
            spec = VisualSandboxAgent.generate_spec(doc_id, c_id, n['label'], n['explanation'])
            database.save_visual_specs([spec])
            
        db_nodes = database.get_concepts(doc_id)
        db_edges = database.get_concept_edges(doc_id)
        
    vis_html = visualizer.generate_vis_html(db_nodes, db_edges)
    concepts_choices = [(n["label"], n["id"]) for n in db_nodes]
    
    return (
        stats_html,
        gr.update(maximum=page_count or 1, minimum=1, value=1),
        page_text,
        f"Page 1 contains {len([n for n in db_nodes if n['page_number'] == 1])} concepts.",
        vis_html,
        gr.update(choices=concepts_choices, value=concepts_choices[0][1] if concepts_choices else ""),
        gr.update(visible=False),
        gr.update(value=""),
        gr.update(visible=False)
    )

def handle_pdf_upload(file, custom_name):
    if file is None:
        return "Please upload a file."
        
    try:
        doc_id = database.ingest_document(file.name, custom_name)
        docs = database.get_documents()
        choices = [(d["name"], d["id"]) for d in docs]
        return f"Successfully ingested PDF: **{custom_name or os.path.basename(file.name)}**", gr.update(choices=choices, value=doc_id)
    except Exception as e:
        return f"**Ingestion Error:** {str(e)}", gr.update()

def handle_page_slide(doc_id, page_num):
    if not doc_id:
        return "", ""
    pages = database.get_document_pages(doc_id)
    if not pages or page_num > len(pages):
        return "Page not found", ""
        
    page_text = pages[page_num - 1]["text"]
    db_nodes = database.get_concepts(doc_id)
    page_concepts = [n["label"] for n in db_nodes if n["page_number"] == page_num]
    
    if page_concepts:
        concepts_md = "**Concepts on this page:**\n\n" + ", ".join([f"`{c}`" for c in page_concepts])
    else:
        concepts_md = "*No specific visual concepts spotted on this page.*"
        
    return page_text, concepts_md

def handle_node_selected(node_id, doc_id):
    if not node_id or not doc_id:
        return gr.update(), gr.update()
        
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM concepts WHERE id = ?", (node_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return gr.update(), gr.update()
        
    concept = dict(row)
    html_profile = get_concept_details_html(concept)
    return html_profile, gr.update(visible=True), node_id, gr.update(value="")

def handle_generate_quiz(concept_id):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT label, explanation FROM concepts WHERE id = ?", (concept_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return "Concept not found.", ""
        
    question = MasteryEvaluatorAgent.generate_quiz_question(row["label"], row["explanation"])
    return f"**Assessment Question:**\n{question}", question

def handle_submit_answer(concept_id, question, answer, doc_id):
    if not concept_id or not answer:
        return "Please write an answer before submitting.", gr.update()
        
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM concepts WHERE id = ?", (concept_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return "Concept not found.", gr.update()
        
    concept = dict(row)
    prev_scores = {
        "memory": concept["memory"],
        "comprehension": concept["comprehension"],
        "structure": concept["structure"],
        "application": concept["application"]
    }
    
    result = MasteryEvaluatorAgent.evaluate_response(
        concept["label"], concept["explanation"], question, answer, prev_scores
    )
    
    database.update_concept_mastery(concept_id, result["scores"])
    database.add_evaluation_journal(
        doc_id, concept_id, f"Q: {question}\nA: {answer}", prev_scores, result["scores"], result["reasoning"]
    )
    
    db_nodes = database.get_concepts(doc_id)
    db_edges = database.get_concept_edges(doc_id)
    vis_html = visualizer.generate_vis_html(db_nodes, db_edges, selected_id=concept_id)
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM concepts WHERE id = ?", (concept_id,))
    row_updated = cursor.fetchone()
    conn.close()
    concept_updated = dict(row_updated)
    
    profile_html = get_concept_details_html(concept_updated)
    
    eval_result_md = f"""
    ### Assessment Feedback:
    - **Memory:** {result['scores']['memory']}% (+{result['scores']['memory'] - prev_scores['memory']})
    - **Comprehension:** {result['scores']['comprehension']}% (+{result['scores']['comprehension'] - prev_scores['comprehension']})
    - **Structure:** {result['scores']['structure']}% (+{result['scores']['structure'] - prev_scores['structure']})
    - **Application:** {result['scores']['application']}% (+{result['scores']['application'] - prev_scores['application']})
    
    **Assessor Reasoning:**
    {result['reasoning']}
    
    **Recommendation:**
    {result['recommendation']}
    """
    
    return eval_result_md, vis_html, profile_html

def handle_sandbox_concept(concept_id, doc_id):
    if not concept_id:
        return gr.update(visible=False), gr.update(value="No concept selected"), gr.update(visible=False), ""
        
    spec = database.get_concept_visual_spec(doc_id, concept_id)
    if not spec:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT label, explanation FROM concepts WHERE id = ?", (concept_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            spec = VisualSandboxAgent.generate_spec(doc_id, concept_id, row["label"], row["explanation"])
            database.save_visual_specs([spec])
            
    plotly_disp, desc_md, canvas_disp = build_visual_spec_display(spec)
    type_lbl = f"**Visualization Type:** {spec.get('type', 'Unknown').upper()}" if spec else ""
    return plotly_disp, desc_md, canvas_disp, type_lbl

def handle_chat(query, chat_history, doc_id, session_id):
    if not query:
        return "", chat_history, "*Assistant Status: Please enter a query.*", ""
        
    trace_id = str(uuid.uuid4())
    messages = []
    for h in chat_history:
        messages.append(HumanMessage(content=h[0]))
        messages.append(AIMessage(content=h[1]))
    messages.append(HumanMessage(content=query))
    
    callbacks = []
    if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
        try:
            from langfuse.callback import CallbackHandler
            cb = CallbackHandler(
                public_key=config.LANGFUSE_PUBLIC_KEY,
                secret_key=config.LANGFUSE_SECRET_KEY,
                host=config.LANGFUSE_HOST,
                trace_id=trace_id,
                session_id=session_id,
                user_id="default_student_501",
                tags=["v1-router-gpt-4o-mini"]
            )
            callbacks.append(cb)
        except Exception as e:
            print(f"Error loading Langfuse Callback: {e}")
            
    config_dict = {"configurable": {"thread_id": session_id}}
    if callbacks:
        config_dict["callbacks"] = callbacks
        
    inputs = {
        "messages": messages,
        "current_doc_id": doc_id or "company_policies"
    }
    
    try:
        response = graph.graph.invoke(inputs, config_dict)
        ai_reply = response["messages"][-1].content
        route_taken = response.get("route", "unknown")
        
        chat_history.append((query, ai_reply))
        database.add_chat_message(session_id, "user", query, trace_id)
        database.add_chat_message(session_id, "assistant", ai_reply, trace_id)
        
        if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
            try:
                lf = Langfuse(
                    public_key=config.LANGFUSE_PUBLIC_KEY,
                    secret_key=config.LANGFUSE_SECRET_KEY,
                    host=config.LANGFUSE_HOST
                )
                lf.trace(id=trace_id).update(
                    metadata={
                        "session_id": session_id,
                        "user_id": "default_student_501",
                        "route_taken": route_taken
                    }
                )
            except Exception as e:
                print(f"Error updating Langfuse trace metadata: {e}")
                
        status_md = f"*Assistant Status: Routed via **{route_taken.upper()} AGENT** | Trace ID: `{trace_id[:8]}...`*"
        return "", chat_history, status_md, trace_id
    except Exception as e:
        err_reply = f"Error generating response: {str(e)}"
        chat_history.append((query, err_reply))
        return "", chat_history, f"*Assistant Status: Failed. {str(e)}*", trace_id

def handle_feedback(rating, trace_id):
    if not trace_id:
        return "Error: No active transaction trace found. Submit a chat question first."
        
    if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
        return "Offline: Feedback ignored (Langfuse credentials not set)."
        
    try:
        lf = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_HOST
        )
        score_value = 1.0 if rating == "up" else 0.0
        lf.score(
            trace_id=trace_id,
            name="helpfulness",
            value=score_value
        )
        return f"Feedback logged successfully: {'👍 Positive' if score_value == 1.0 else '👎 Negative'}"
    except Exception as e:
        return f"Feedback Failed: {str(e)}"

def handle_clear_chat(session_id):
    return [], gr.update(value=str(uuid.uuid4())), "*Assistant Status: Chat history cleared.*"

def handle_save_config(openai_key):
    config.OPENAI_API_KEY = openai_key
    try:
        with open(".env", "w") as f:
            f.write(f"OPENAI_API_KEY={openai_key}\n")
            f.write(f"LANGFUSE_PUBLIC_KEY={config.LANGFUSE_PUBLIC_KEY}\n")
            f.write(f"LANGFUSE_SECRET_KEY={config.LANGFUSE_SECRET_KEY}\n")
            f.write(f"LANGFUSE_HOST={config.LANGFUSE_HOST}\n")
        return "Configurations saved successfully!"
    except Exception as e:
        return f"Failed to save .env file: {str(e)}"

def refresh_system_stats():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM documents")
    docs_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM concepts")
    concepts_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM chat_messages")
    messages_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM evaluation_journal")
    evals_count = cursor.fetchone()[0]
    
    conn.close()
    
    stats_md = f"""
    - **Ingested Document Workspaces:** {docs_count}
    - **Extracted Concepts Spotted:** {concepts_count}
    - **Conversational Chat Messages:** {messages_count}
    - **Mastery Assessments Submitted:** {evals_count}
    """
    return stats_md

def get_concept_visual_spec(doc_id: str, concept_id: str) -> Dict[str, Any]:
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM visual_specs WHERE doc_id = ? AND concept_id = ?", (doc_id, concept_id))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d['spec_json'] = json.loads(d['spec_json'])
        except Exception:
            pass
        return d
    return None

database.get_concept_visual_spec = get_concept_visual_spec

# --- Main UI Builder ---

def create_ui():
    custom_js = """
    function() {
        window.addEventListener('message', function(event) {
            const el = document.querySelector('#selected-node-input textarea') || document.querySelector('#selected-node-input input');
            if (el) {
                el.value = event.data;
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
    }
    """
    
    with gr.Blocks(css=CUSTOM_CSS, js=custom_js, title="Paper Helper & Visual Study Companion") as demo:
        
        # Header Row
        with gr.Row(elem_classes="glass-panel"):
            with gr.Column(scale=4):
                gr.HTML("""
                <h1 style="margin: 0; font-size: 24px; font-weight: 700; background: linear-gradient(to right, #8b78d9, #4fae84); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    Paper Helper & Visual Study Companion
                </h1>
                <p style="margin: 5px 0 0 0; font-size: 13px; color: #94a3b8;">
                    Local-first multi-agent chatbot & interactive study dashboard (LangGraph & Langfuse)
                </p>
                """)
            with gr.Column(scale=1):
                status_box = gr.HTML(value="""
                <div style="text-align: right; font-size: 11px; color: #94a3b8;">
                    <div>OpenAI Key: <span style="color: #4fae84; font-weight: 600;">Active</span></div>
                    <div>Langfuse Stack: <span style="color: #8b78d9; font-weight: 600;">Localhost:3000</span></div>
                </div>
                """)
                
        # State variables
        current_doc_id = gr.State("")
        current_concept_id = gr.State("")
        last_trace_id = gr.State("")
        current_quiz_question = gr.State("")
        
        # Tabs
        with gr.Tabs():
            
            # Tab 1: Workspace & PDF Ingestion
            with gr.TabItem("Workspace & Ingestion"):
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Upload New Document</h3>")
                        pdf_uploader = gr.File(label="Upload PDF Document (Max 150 pages)", file_types=[".pdf"])
                        custom_doc_name = gr.Textbox(label="Custom Document Name (Optional)")
                        ingest_btn = gr.Button("Ingest & Analyze Document", variant="primary")
                        ingest_status = gr.Markdown(value="Upload a file and click Ingest to start.")
                        
                    with gr.Column(scale=1, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Select Ingested Document</h3>")
                        document_selector = gr.Dropdown(label="Active Document Workspace", choices=[], interactive=True)
                        doc_stats = gr.HTML(value="No document selected")
                        
                        gr.HTML("<h3>Read Extracted Pages</h3>")
                        page_slider = gr.Slider(label="Page", minimum=1, maximum=1, step=1, value=1, interactive=True)
                        page_content_viewer = gr.Textbox(label="Extracted Page Content", lines=8, max_lines=15, interactive=False)
                        page_concepts_list = gr.Markdown("No concepts extracted for this page.")

            # Tab 2: Interactive Study Graph (Knowledge Graph & Mastery Map)
            with gr.TabItem("Interactive Study Graph"):
                with gr.Row():
                    with gr.Column(scale=3, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Knowledge Graph & Mastery Map</h3>")
                        # Hidden element to receive events from iframe
                        hidden_node_input = gr.Textbox(elem_id="selected-node-input", visible=False)
                        
                        # Graph display component
                        graph_iframe = gr.HTML(
                            value="<div style='color:#94a3b8; text-align:center; padding:100px;'>Select or Ingest a document workspace to build and visualize the study network graph.</div>",
                            height=600
                        )
                    
                    with gr.Column(scale=2, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Concept Mastery Profile</h3>")
                        concept_profile_panel = gr.HTML(value="<div style='color: #94a3b8; text-align: center; margin-top: 50px;'>Select a node in the graph to view its mastery profile</div>")
                        
                        # Evaluation section
                        with gr.Group(visible=False) as evaluation_group:
                            gr.HTML("<h3>Concept Mastery Evaluator Agent</h3>")
                            quiz_question_disp = gr.Markdown("")
                            generate_quiz_btn = gr.Button("Generate Assessment Question", variant="secondary")
                            student_answer_input = gr.Textbox(label="Your Answer", lines=3, placeholder="Write your explanation or mathematical solution here...")
                            submit_answer_btn = gr.Button("Submit Assessment", variant="primary")
                            evaluation_result_disp = gr.Markdown("")

            # Tab 3: Visual Sandbox
            with gr.TabItem("Visual Sandbox"):
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Visual Walkthrough Planner</h3>")
                        sandbox_concept_selector = gr.Dropdown(label="Select Concept Visual Sandbox", choices=[], interactive=True)
                        sandbox_type_disp = gr.Markdown("Choose a concept to generate its visual sandbox spec.")
                        
                    with gr.Column(scale=3, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Sandbox Rendering</h3>")
                        sandbox_desc_md = gr.Markdown("")
                        sandbox_plotly_disp = gr.Plotly(visible=False)
                        sandbox_canvas_disp = gr.HTML(visible=False)

            # Tab 4: Scoped Chat
            with gr.TabItem("Scoped Chat"):
                with gr.Row():
                    with gr.Column(scale=4, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Scoped PDF & Policy Assistant</h3>")
                        chat_history_disp = gr.Chatbot(label="Conversation", height=450, bubble_full_width=False)
                        with gr.Row():
                            chat_input = gr.Textbox(label="Type your query...", placeholder="Ask a question about the document policies or general topics...", scale=8)
                            chat_send_btn = gr.Button("Send", variant="primary", scale=1)
                        
                        route_status_indicator = gr.Markdown("*Assistant Status: Ready*")
                        
                        with gr.Row():
                            gr.HTML("<span style='font-size:13px; color:#94a3b8;'>Was this response helpful?</span>", scale=4)
                            thumbs_up_btn = gr.Button("👍 Yes", size="sm", scale=1)
                            thumbs_down_btn = gr.Button("👎 No", size="sm", scale=1)
                            feedback_status_lbl = gr.Label(show_label=False, scale=3)
                            
                    with gr.Column(scale=1, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Chat Settings</h3>")
                        session_id_disp = gr.Textbox(label="Active Session UUID", value=str(uuid.uuid4()), interactive=False)
                        clear_history_btn = gr.Button("Clear Chat History", variant="secondary")

            # Tab 5: Settings & Logs
            with gr.TabItem("Settings & System"):
                with gr.Row():
                    with gr.Column(scale=1, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Configuration</h3>")
                        openai_api_field = gr.Textbox(label="OpenAI API Key", value=config.OPENAI_API_KEY, type="password")
                        save_config_btn = gr.Button("Save Configurations")
                        
                    with gr.Column(scale=2, elem_classes="glass-panel"):
                        gr.HTML("<h3 style='margin-top:0;'>Local Observability Status</h3>")
                        gr.HTML("""
                        <div style="background:#1e293b; padding:15px; border-radius:8px;">
                            <p><strong>Self-Hosted Langfuse URL:</strong> <a href="http://localhost:3000" target="_blank" style="color:#8b78d9;">http://localhost:3000</a></p>
                            <p>To start your Langfuse Docker Compose stack, execute in your terminal:</p>
                            <pre style="background:#0f172a; padding:8px; border-radius:4px; font-family:monospace; color:#4fae84;">docker-compose up -d</pre>
                            <p style="font-size:12px; color:#94a3b8; margin-bottom:0;">Once started, sign up, create project credentials, and paste the keys in your .env file to enable tracing dashboard.</p>
                        </div>
                        """)
                        gr.HTML("<h3>Database Health & Statistics</h3>")
                        db_stats_disp = gr.Markdown("Loading statistics...")

        # --- Trigger mappings ---
        demo.load(update_doc_list, outputs=[document_selector]).then(
            lambda doc_sel: load_document_workspace(doc_sel),
            inputs=[document_selector],
            outputs=[doc_stats, page_slider, page_content_viewer, page_concepts_list, graph_iframe, sandbox_concept_selector, evaluation_group, quiz_question_disp, quiz_question_disp]
        ).then(refresh_system_stats, outputs=[db_stats_disp])
        
        document_selector.change(
            load_document_workspace,
            inputs=[document_selector],
            outputs=[doc_stats, page_slider, page_content_viewer, page_concepts_list, graph_iframe, sandbox_concept_selector, evaluation_group, quiz_question_disp, quiz_question_disp]
        ).then(refresh_system_stats, outputs=[db_stats_disp])
        
        ingest_btn.click(
            handle_pdf_upload,
            inputs=[pdf_uploader, custom_doc_name],
            outputs=[ingest_status, document_selector]
        ).then(refresh_system_stats, outputs=[db_stats_disp])
        
        page_slider.change(
            handle_page_slide,
            inputs=[document_selector, page_slider],
            outputs=[page_content_viewer, page_concepts_list]
        )
        
        hidden_node_input.change(
            handle_node_selected,
            inputs=[hidden_node_input, document_selector],
            outputs=[concept_profile_panel, evaluation_group, current_concept_id, evaluation_result_disp]
        )
        
        generate_quiz_btn.click(
            handle_generate_quiz,
            inputs=[current_concept_id],
            outputs=[quiz_question_disp, current_quiz_question]
        )
        
        submit_answer_btn.click(
            handle_submit_answer,
            inputs=[current_concept_id, current_quiz_question, student_answer_input, document_selector],
            outputs=[evaluation_result_disp, graph_iframe, concept_profile_panel]
        ).then(refresh_system_stats, outputs=[db_stats_disp])
        
        sandbox_concept_selector.change(
            handle_sandbox_concept,
            inputs=[sandbox_concept_selector, document_selector],
            outputs=[sandbox_plotly_disp, sandbox_desc_md, sandbox_canvas_disp, sandbox_type_disp]
        )
        
        chat_send_btn.click(
            handle_chat,
            inputs=[chat_input, chat_history_disp, document_selector, session_id_disp],
            outputs=[chat_input, chat_history_disp, route_status_indicator, last_trace_id]
        ).then(refresh_system_stats, outputs=[db_stats_disp])
        
        chat_input.submit(
            handle_chat,
            inputs=[chat_input, chat_history_disp, document_selector, session_id_disp],
            outputs=[chat_input, chat_history_disp, route_status_indicator, last_trace_id]
        ).then(refresh_system_stats, outputs=[db_stats_disp])
        
        thumbs_up_btn.click(
            lambda tid: handle_feedback("up", tid),
            inputs=[last_trace_id],
            outputs=[feedback_status_lbl]
        )
        
        thumbs_down_btn.click(
            lambda tid: handle_feedback("down", tid),
            inputs=[last_trace_id],
            outputs=[feedback_status_lbl]
        )
        
        clear_history_btn.click(
            handle_clear_chat,
            inputs=[session_id_disp],
            outputs=[chat_history_disp, session_id_disp, route_status_indicator]
        )
        
        save_config_btn.click(
            handle_save_config,
            inputs=[openai_api_field],
            outputs=[openai_api_field]
        )

    return demo

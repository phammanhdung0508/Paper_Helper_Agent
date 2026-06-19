import os
import shutil
import uuid
import json
from typing import List, Dict, Any, Tuple
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import config
from app import database
from app import graph
from app import visualizer
from app.agents import ConceptGraphAgent, VisualSandboxAgent, MasteryEvaluatorAgent

_backend_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_backend_dir)

# Ensure DB is initialized
database.db_init()

def initialize_default_policies():
    """Ensures that the default company policies are loaded for Lab 3 compatibility."""
    docs = database.get_documents()
    has_policies = any(d["id"] == "company_policies" for d in docs)
    
    if not has_policies:
        policies_path = os.path.join(_project_root, "data", "company_policies.txt")
        if os.path.exists(policies_path):
            conn = database.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "INSERT OR IGNORE INTO documents (id, name, file_path) VALUES (?, ?, ?)",
                ("company_policies", "Default Company Policies", policies_path)
            )
            
            with open(policies_path, "r") as f:
                content = f.read()
                
            cursor.execute(
                "INSERT OR IGNORE INTO pages (id, doc_id, page_number, text) VALUES (?, ?, ? , ?)",
                ("company_policies_page_1", "company_policies", 1, content)
            )
            
            # Seed mock concepts for company policies so it is immediately viewable offline
            cursor.execute("""
            INSERT OR IGNORE INTO concepts (id, doc_id, label, explanation, page_number, memory, comprehension, structure, application)
            VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0)
            """, ("company_policies_concept_travel_allowance", "company_policies", "Travel Allowance", "Standard meal reimbursement allowance up to maximum $150 per day.", 1))
            
            cursor.execute("""
            INSERT OR IGNORE INTO concepts (id, doc_id, label, explanation, page_number, memory, comprehension, structure, application)
            VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0)
            """, ("company_policies_concept_remote_work", "company_policies", "Remote Work Policy", "Hybrid schedule minimum 2 days onsite, manager approval, 6 months tenure.", 1))
            
            cursor.execute("""
            INSERT OR IGNORE INTO concepts (id, doc_id, label, explanation, page_number, memory, comprehension, structure, application)
            VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0)
            """, ("company_policies_concept_equipment_refreshes", "company_policies", "Equipment Refresh", "Standard engineering laptop M3 MacBook Pro, refreshed every 3 years.", 1))
            
            # Seed mock edges
            cursor.execute("""
            INSERT OR IGNORE INTO concept_edges (source, target, doc_id, type, description)
            VALUES (?, ?, ?, ?, ?)
            """, ("company_policies_concept_travel_allowance", "company_policies_concept_remote_work", "company_policies", "parallel", "Both are standard corporate benefits."))
            
            cursor.execute("""
            INSERT OR IGNORE INTO concept_edges (source, target, doc_id, type, description)
            VALUES (?, ?, ?, ?, ?)
            """, ("company_policies_concept_remote_work", "company_policies_concept_equipment_refreshes", "company_policies", "prerequisite", "Need a primary laptop refreshed and secure before working remotely."))
            
            conn.commit()
            conn.close()
            
            try:
                database.index_document_in_vector_store("company_policies", [content])
                print("Successfully loaded default company policies in SQLite and Chroma collection.")
            except Exception as e:
                print(f"Error seeding Chroma: {e}. SQLite seed succeeded.")
        else:
            print("Warning: data/company_policies.txt not found. Skip default initialization.")

app = FastAPI(title="Paper Helper API Server", version="1.0.0")

@app.on_event("startup")
def startup_event():
    initialize_default_policies()

# CORS middleware for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Schemas
class ChatRequest(BaseModel):
    query: str
    chat_history: List[List[str]] = []
    doc_id: str = ""
    session_id: str = ""

class ChatResponse(BaseModel):
    response: str
    route_taken: str
    trace_id: str

class FeedbackRequest(BaseModel):
    rating: str
    trace_id: str

class FeedbackResponse(BaseModel):
    status: str

class QuizRequest(BaseModel):
    concept_id: str

class QuizResponse(BaseModel):
    question: str

class QuizSubmitRequest(BaseModel):
    concept_id: str
    question: str
    answer: str
    doc_id: str

class QuizSubmitResponse(BaseModel):
    scores: Dict[str, int]
    reasoning: str
    recommendation: str
    feedback_md: str

# Endpoints
@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Paper Helper API is running."}

@app.get("/api/stats")
def get_stats():
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
    
    return {
        "documents_count": docs_count,
        "concepts_count": concepts_count,
        "messages_count": messages_count,
        "evaluations_count": evals_count
    }

@app.get("/api/documents")
def list_documents():
    docs = database.get_documents()
    # Default corporate policies fallback
    choices = [{"name": d["name"], "id": d["id"]} for d in docs]
    if not choices:
        choices = [{"name": "Lab 3 Company Policies", "id": "company_policies"}]
    return choices

@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), custom_name: str = Form(None)):
    try:
        # Create temp folder for upload validation
        os.makedirs("uploads", exist_ok=True)
        temp_path = os.path.join("uploads", f"{uuid.uuid4()}_{file.filename}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        doc_id = database.ingest_document(temp_path, custom_name)
        
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        return {"doc_id": doc_id, "name": custom_name or file.filename}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/documents/{doc_id}/pages/{page_num}")
def get_page(doc_id: str, page_num: int):
    if doc_id == "company_policies":
        # Fallback for corporate policies
        policies_file = os.path.join(_project_root, "data", "company_policies.txt")
        if os.path.exists(policies_file):
            with open(policies_file, "r") as f:
                content = f.read()
            return {"text": content, "concepts": ["Corporate Policies"]}
        return {"text": "No policies file found.", "concepts": []}
        
    pages = database.get_document_pages(doc_id)
    if not pages or page_num > len(pages) or page_num < 1:
        raise HTTPException(status_code=404, detail="Page not found")
        
    page_text = pages[page_num - 1]["text"]
    db_nodes = database.get_concepts(doc_id)
    page_concepts = [n["label"] for n in db_nodes if n["page_number"] == page_num]
    
    return {
        "text": page_text,
        "concepts": page_concepts,
        "total_pages": len(pages)
    }

@app.get("/api/documents/{doc_id}/concepts")
def get_concepts_graph(doc_id: str):
    db_nodes = database.get_concepts(doc_id)
    db_edges = database.get_concept_edges(doc_id)
    
    # If nodes have not been generated yet, build them on first retrieval
    if not db_nodes and doc_id != "company_policies":
        pages = database.get_document_pages(doc_id)
        if pages:
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
            
    return {"nodes": db_nodes, "edges": db_edges}

@app.get("/api/documents/{doc_id}/graph-html")
def get_graph_html(doc_id: str, selected_id: str = None):
    db_nodes = database.get_concepts(doc_id)
    db_edges = database.get_concept_edges(doc_id)
    
    # If nodes have not been generated yet, build them on first retrieval
    if not db_nodes and doc_id != "company_policies":
        pages = database.get_document_pages(doc_id)
        if pages:
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
            
    from fastapi.responses import HTMLResponse
    html_content = visualizer.generate_vis_html(db_nodes, db_edges, selected_id=selected_id)
    return HTMLResponse(content=html_content)

@app.get("/api/documents/{doc_id}/visual-specs/{concept_id}")
def get_visual_spec(doc_id: str, concept_id: str):
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
        else:
            raise HTTPException(status_code=404, detail="Concept not found")
            
    return spec

@app.get("/api/documents/{doc_id}/visual-specs/{concept_id}/three-html")
def get_visual_spec_three_html(doc_id: str, concept_id: str):
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
        else:
            raise HTTPException(status_code=404, detail="Concept not found")
            
    if spec.get("type") != "three":
        raise HTTPException(status_code=400, detail="This visual specification is not of type 'three'")
        
    from fastapi.responses import HTMLResponse
    html_content = visualizer.generate_three_html(spec.get("spec_json", {}))
    return HTMLResponse(content=html_content)

@app.post("/api/chat", response_model=ChatResponse)
def run_agent_chat(payload: ChatRequest):
    from langchain_core.messages import HumanMessage, AIMessage
    
    query = payload.query
    chat_history = payload.chat_history
    doc_id = payload.doc_id or "company_policies"
    session_id = payload.session_id or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    
    # Rebuild langchain messages history
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
        "current_doc_id": doc_id
    }
    
    try:
        response = graph.graph.invoke(inputs, config_dict)
        ai_reply = response["messages"][-1].content
        route_taken = response.get("route", "unknown")
        
        database.add_chat_message(session_id, "user", query, trace_id)
        database.add_chat_message(session_id, "assistant", ai_reply, trace_id)
        
        # Attach route_taken metadata via SDK trace update
        if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
            try:
                from langfuse import Langfuse
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
                
        return ChatResponse(response=ai_reply, route_taken=route_taken, trace_id=trace_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feedback", response_model=FeedbackResponse)
def log_chat_feedback(payload: FeedbackRequest):
    if not payload.trace_id:
        raise HTTPException(status_code=400, detail="trace_id is required")
        
    if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
        return FeedbackResponse(status="Offline: Langfuse credentials not set")
        
    try:
        from langfuse import Langfuse
        lf = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_HOST
        )
        score_value = 1.0 if payload.rating == "up" else 0.0
        lf.score(
            trace_id=payload.trace_id,
            name="helpfulness",
            value=score_value
        )
        return FeedbackResponse(status=f"Feedback logged successfully: {payload.rating}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/evaluation/question", response_model=QuizResponse)
def generate_quiz(payload: QuizRequest):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT label, explanation FROM concepts WHERE id = ?", (payload.concept_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Concept not found")
        
    question = MasteryEvaluatorAgent.generate_quiz_question(row["label"], row["explanation"])
    return QuizResponse(question=question)

@app.post("/api/evaluation/submit", response_model=QuizSubmitResponse)
def submit_answer(payload: QuizSubmitRequest):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM concepts WHERE id = ?", (payload.concept_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Concept not found")
        
    concept = dict(row)
    prev_scores = {
        "memory": concept["memory"],
        "comprehension": concept["comprehension"],
        "structure": concept["structure"],
        "application": concept["application"]
    }
    
    result = MasteryEvaluatorAgent.evaluate_response(
        concept["label"], concept["explanation"], payload.question, payload.answer, prev_scores
    )
    
    database.update_concept_mastery(payload.concept_id, result["scores"])
    database.add_evaluation_journal(
        payload.doc_id, payload.concept_id, f"Q: {payload.question}\nA: {payload.answer}", prev_scores, result["scores"], result["reasoning"]
    )
    
    eval_result_md = f"""
### Assessment Feedback:
- **Memory Recall:** {result['scores']['memory']}% (+{result['scores']['memory'] - prev_scores['memory']})
- **Conceptual Comprehension:** {result['scores']['comprehension']}% (+{result['scores']['comprehension'] - prev_scores['comprehension']})
- **Structural Relationships:** {result['scores']['structure']}% (+{result['scores']['structure'] - prev_scores['structure']})
- **Practical Application:** {result['scores']['application']}% (+{result['scores']['application'] - prev_scores['application']})

**Assessor Reasoning:**
{result['reasoning']}

**Recommendation:**
{result['recommendation']}
"""
    
    return QuizSubmitResponse(
        scores=result["scores"],
        reasoning=result["reasoning"],
        recommendation=result["recommendation"],
        feedback_md=eval_result_md
    )

# Helper function
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

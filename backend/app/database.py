import sqlite3
import os
import shutil
import uuid
import pypdf
from typing import List, Dict, Any, Tuple
import json
import warnings

from app import config

# Silence LangChainDeprecationWarning
try:
    from langchain_core._api import LangChainDeprecationWarning
    warnings.filterwarnings("ignore", category=LangChainDeprecationWarning)
except ImportError:
    pass

# SQLite Helpers
def get_db_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create documents table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        file_path TEXT,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create pages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pages (
        id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        text TEXT NOT NULL,
        FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
    )
    """)
    
    # Create concepts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS concepts (
        id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        label TEXT NOT NULL,
        explanation TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        memory INTEGER DEFAULT 0,
        comprehension INTEGER DEFAULT 0,
        structure INTEGER DEFAULT 0,
        application INTEGER DEFAULT 0,
        FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
    )
    """)
    
    # Create concept_edges table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS concept_edges (
        source TEXT NOT NULL,
        target TEXT NOT NULL,
        doc_id TEXT NOT NULL,
        type TEXT NOT NULL,
        description TEXT,
        PRIMARY KEY (source, target, doc_id),
        FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE
    )
    """)
    
    # Create visual_specs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visual_specs (
        id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        concept_id TEXT NOT NULL,
        type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        spec_json TEXT NOT NULL,
        FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE,
        FOREIGN KEY(concept_id) REFERENCES concepts(id) ON DELETE CASCADE
    )
    """)
    
    # Create chat_messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        trace_id TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create evaluation_journal table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS evaluation_journal (
        id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        concept_id TEXT NOT NULL,
        interaction TEXT NOT NULL,
        prev_scores TEXT NOT NULL,
        new_scores TEXT NOT NULL,
        reasoning TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE,
        FOREIGN KEY(concept_id) REFERENCES concepts(id) ON DELETE CASCADE
    )
    """)
    
    # Create jobs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        doc_id TEXT NOT NULL,
        type TEXT NOT NULL,
        status TEXT NOT NULL,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """)
    
    # Create LLM response cache table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS llm_cache (
        id TEXT PRIMARY KEY,
        task TEXT NOT NULL,
        prompt_hash TEXT NOT NULL,
        schema_name TEXT NOT NULL,
        response_json TEXT NOT NULL,
        provider TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Create LLM call log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS llm_call_log (
        id TEXT PRIMARY KEY,
        task TEXT NOT NULL,
        provider TEXT NOT NULL,
        success INTEGER NOT NULL,
        latency_ms INTEGER NOT NULL,
        error_category TEXT,
        cache_hit INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

# Ingestion & Quality check
def check_pdf_quality(file_path: str) -> Tuple[bool, int, str]:
    """
    Checks the PDF quality:
    - Page count must be <= 150
    - Text must be readable (not image-only scan)
    Returns: (is_valid, page_count, error_or_warning_message)
    """
    try:
        reader = pypdf.PdfReader(file_path)
        page_count = len(reader.pages)
        
        if page_count > 150:
            return False, page_count, f"Document has {page_count} pages. Maximum allowed is 150 pages."
            
        total_text = ""
        for i in range(min(5, page_count)): # Check first 5 pages for text content
            page_text = reader.pages[i].extract_text() or ""
            total_text += page_text.strip()
            
        if len(total_text.strip()) < 50:
            return False, page_count, "This document appears to be an image-only scan or empty. OCR/text extraction might be limited."
            
        return True, page_count, ""
    except Exception as e:
        return False, 0, f"Failed to parse PDF: {str(e)}"

def extract_pdf_pages(file_path: str) -> List[str]:
    """Extracts text page-by-page from the PDF."""
    reader = pypdf.PdfReader(file_path)
    pages_text = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages_text.append(text)
    return pages_text

def get_embeddings():
    """Returns LangChain compatible embedding function."""
    if config.OPENAI_API_KEY:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(openai_api_key=config.OPENAI_API_KEY)
    else:
        # Fallback local embeddings
        from langchain_community.embeddings import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def get_vector_store(doc_id: str):
    """Returns persistent Chroma Vector Store for doc_id."""
    from langchain_community.vectorstores import Chroma
    persist_directory = os.path.join(config.USER_DATA_DIR, "chroma_db")
    return Chroma(
        collection_name=f"doc_{doc_id.replace('-', '_')}",
        embedding_function=get_embeddings(),
        persist_directory=persist_directory
    )

def index_document_in_vector_store(doc_id: str, pages_text: List[str]):
    """Chunks and indexes the document pages in the Chroma vector store."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_core.documents import Document
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = []
    for i, page_text in enumerate(pages_text):
        if not page_text.strip():
            continue
        chunks = text_splitter.split_text(page_text)
        for chunk in chunks:
            docs.append(Document(
                page_content=chunk,
                metadata={"doc_id": doc_id, "page_number": i + 1}
            ))
            
    if docs:
        vector_store = get_vector_store(doc_id)
        vector_store.add_documents(docs)

def ingest_document(file_path: str, custom_name: str = None) -> str:
    """
    Ingests a document: validates, copies PDF, extracts text to DB, and indexes in Chroma.
    Returns doc_id.
    """
    is_valid, page_count, message = check_pdf_quality(file_path)
    if not is_valid:
        raise ValueError(message)
        
    doc_id = str(uuid.uuid4())
    doc_name = custom_name or os.path.basename(file_path)
    
    # Create document folder and copy PDF
    doc_dir = os.path.join(config.DOCS_DIR, doc_id)
    os.makedirs(doc_dir, exist_ok=True)
    dest_pdf_path = os.path.join(doc_dir, "original.pdf")
    shutil.copy2(file_path, dest_pdf_path)
    
    # DB Insertion
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO documents (id, name, file_path) VALUES (?, ?, ?)",
        (doc_id, doc_name, dest_pdf_path)
    )
    
    pages_text = extract_pdf_pages(file_path)
    page_data = [
        (f"{doc_id}_page_{i+1}", doc_id, i + 1, page_text)
        for i, page_text in enumerate(pages_text)
    ]
    cursor.executemany(
        "INSERT INTO pages (id, doc_id, page_number, text) VALUES (?, ?, ?, ?)",
        page_data
    )
        
    conn.commit()
    conn.close()
    
    # Vector store indexing
    index_document_in_vector_store(doc_id, pages_text)
    
    return doc_id

# CRUD Helpers
def get_documents() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, file_path, added_at FROM documents ORDER BY added_at DESC")
    docs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return docs

def get_document(doc_id: str) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, file_path, added_at FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_document(doc_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
    
    # Delete folder
    doc_dir = os.path.join(config.DOCS_DIR, doc_id)
    if os.path.exists(doc_dir):
        shutil.rmtree(doc_dir)
        
    # Delete Chroma collection
    try:
        vector_store = get_vector_store(doc_id)
        vector_store.delete_collection()
    except Exception:
        pass

def get_document_pages(doc_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT page_number, text FROM pages WHERE doc_id = ? ORDER BY page_number ASC", (doc_id,))
    pages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return pages

# Concepts and Graph CRUD
def save_concepts(concepts: List[Dict[str, Any]]):
    """
    Saves a list of concept dictionaries:
    Each dict should contain: doc_id, label, explanation, page_number.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    for c in concepts:
        concept_id = f"{c['doc_id']}_concept_{c['label'].lower().replace(' ', '_')}"
        cursor.execute("""
        INSERT OR REPLACE INTO concepts (id, doc_id, label, explanation, page_number, memory, comprehension, structure, application)
        VALUES (?, ?, ?, ?, ?, COALESCE((SELECT memory FROM concepts WHERE id=?), 0),
                              COALESCE((SELECT comprehension FROM concepts WHERE id=?), 0),
                              COALESCE((SELECT structure FROM concepts WHERE id=?), 0),
                              COALESCE((SELECT application FROM concepts WHERE id=?), 0))
        """, (concept_id, c['doc_id'], c['label'], c['explanation'], c['page_number'], concept_id, concept_id, concept_id, concept_id))
    conn.commit()
    conn.close()

def get_concepts(doc_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, doc_id, label, explanation, page_number, memory, comprehension, structure, application FROM concepts WHERE doc_id = ?", (doc_id,))
    concepts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return concepts

def save_concept_edges(edges: List[Dict[str, Any]]):
    """
    Saves a list of concept edge dictionaries:
    Each dict should contain: source, target, doc_id, type, description.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    for e in edges:
        cursor.execute("""
        INSERT OR REPLACE INTO concept_edges (source, target, doc_id, type, description)
        VALUES (?, ?, ?, ?, ?)
        """, (e['source'], e['target'], e['doc_id'], e['type'], e.get('description', '')))
    conn.commit()
    conn.close()

def get_concept_edges(doc_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT source, target, doc_id, type, description FROM concept_edges WHERE doc_id = ?", (doc_id,))
    edges = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return edges

def update_concept_mastery(concept_id: str, scores: Dict[str, int]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE concepts 
    SET memory = ?, comprehension = ?, structure = ?, application = ?
    WHERE id = ?
    """, (scores['memory'], scores['comprehension'], scores['structure'], scores['application'], concept_id))
    conn.commit()
    conn.close()

# Visual specs CRUD
def save_visual_specs(specs: List[Dict[str, Any]]):
    """
    Saves visual specifications:
    Each dict should contain: doc_id, concept_id, type, title, description, spec_json (dict or serialized string).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    for s in specs:
        spec_id = f"{s['doc_id']}_visual_{s['concept_id'].split('_')[-1]}"
        spec_json_str = s['spec_json'] if isinstance(s['spec_json'], str) else json.dumps(s['spec_json'])
        cursor.execute("""
        INSERT OR REPLACE INTO visual_specs (id, doc_id, concept_id, type, title, description, spec_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (spec_id, s['doc_id'], s['concept_id'], s['type'], s['title'], s['description'], spec_json_str))
    conn.commit()
    conn.close()

def get_visual_specs(doc_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, doc_id, concept_id, type, title, description, spec_json FROM visual_specs WHERE doc_id = ?", (doc_id,))
    specs = []
    for row in cursor.fetchall():
        d = dict(row)
        try:
            d['spec_json'] = json.loads(d['spec_json'])
        except Exception:
            pass
        specs.append(d)
    conn.close()
    return specs

# Chat Messages
def add_chat_message(session_id: str, role: str, content: str, trace_id: str = None) -> str:
    msg_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO chat_messages (id, session_id, role, content, trace_id)
    VALUES (?, ?, ?, ?, ?)
    """, (msg_id, session_id, role, content, trace_id))
    conn.commit()
    conn.close()
    return msg_id

def get_chat_history(session_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT role, content, trace_id, timestamp 
    FROM chat_messages 
    WHERE session_id = ? 
    ORDER BY timestamp ASC
    """, (session_id,))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return history

# Evaluation Journal
def add_evaluation_journal(doc_id: str, concept_id: str, interaction: str, prev_scores: Dict[str, int], new_scores: Dict[str, int], reasoning: str):
    j_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO evaluation_journal (id, doc_id, concept_id, interaction, prev_scores, new_scores, reasoning)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (j_id, doc_id, concept_id, interaction, json.dumps(prev_scores), json.dumps(new_scores), reasoning))
    conn.commit()
    conn.close()

# LLM Cache CRUD
def cache_lookup(task: str, prompt_hash: str, schema_name: str):
    """Returns cached response JSON string if found, else None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT response_json FROM llm_cache
    WHERE task = ? AND prompt_hash = ? AND schema_name = ?
    ORDER BY created_at DESC LIMIT 1
    """, (task, prompt_hash, schema_name))
    row = cursor.fetchone()
    conn.close()
    return row["response_json"] if row else None

def cache_store(task: str, prompt_hash: str, schema_name: str, response_json: str, provider: str):
    """Stores a successful LLM response in the cache."""
    cache_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO llm_cache (id, task, prompt_hash, schema_name, response_json, provider)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (cache_id, task, prompt_hash, schema_name, response_json, provider))
    conn.commit()
    conn.close()

def log_llm_call(task: str, provider: str, success: bool, latency_ms: int, error_category: str = None, cache_hit: bool = False):
    """Logs an LLM provider call for monitoring and analytics."""
    log_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO llm_call_log (id, task, provider, success, latency_ms, error_category, cache_hit)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (log_id, task, provider, int(success), latency_ms, error_category, int(cache_hit)))
    conn.commit()
    conn.close()

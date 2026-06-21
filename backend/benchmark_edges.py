import time
import os
import sqlite3
import uuid
from typing import List, Dict, Any

from app import config
from app import database

# Ensure DB is initialized
database.db_init()

def generate_dummy_edges(count: int, doc_id: str) -> List[Dict[str, Any]]:
    edges = []
    for i in range(count):
        edges.append({
            'source': f'concept_{i}',
            'target': f'concept_{i+1}',
            'doc_id': doc_id,
            'type': 'related_to',
            'description': f'Dummy description {i}'
        })
    return edges

def run_benchmark():
    # Setup test document
    doc_id = "test_benchmark_doc"

    # Generate 10,000 edges
    edges = generate_dummy_edges(10000, doc_id)

    # Pre-insert document to satisfy foreign key constraint
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO documents (id, name, file_path) VALUES (?, ?, ?)", (doc_id, "benchmark_doc", "/dummy/path"))
    conn.commit()
    conn.close()

    # Clear existing edges for this doc to ensure clean run
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM concept_edges WHERE doc_id = ?", (doc_id,))
    conn.commit()
    conn.close()

    print(f"Benchmarking save_concept_edges with {len(edges)} edges...")
    start_time = time.time()

    # Call the function
    database.save_concept_edges(edges)

    end_time = time.time()
    duration = end_time - start_time

    print(f"Execution time: {duration:.4f} seconds")

    # Verify insertion
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) as cnt FROM concept_edges WHERE doc_id = ?", (doc_id,))
    count = cursor.fetchone()['cnt']
    conn.close()
    print(f"Successfully inserted {count} edges.")

    # Clean up
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM concept_edges WHERE doc_id = ?", (doc_id,))
    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    run_benchmark()

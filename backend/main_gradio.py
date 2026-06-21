import os
from app import database
from app import config

def initialize_default_policies():
    """Ensures that the default company policies are loaded for Lab 3 compatibility."""
    docs = database.get_documents()
    has_policies = any(d["id"] == "company_policies" for d in docs)

    if not has_policies:
        policies_path = os.path.join("data", "company_policies.txt")
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

            # Index text in vector store
            try:
                database.index_document_in_vector_store("company_policies", [content])
                print("Successfully loaded default company policies in SQLite and Chroma collection.")
            except Exception as e:
                print(f"Error seeding Chroma: {e}. SQLite seed succeeded.")
        else:
            print("Warning: data/company_policies.txt not found. Skip default initialization.")

if __name__ == "__main__":
    print("Initializing SQLite Database...")
    database.db_init()

    print("Checking default workspace data...")
    initialize_default_policies()

    print("Booting Gradio App Server...")
    from app.ui import create_ui
    demo = create_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)

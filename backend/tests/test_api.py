from fastapi.testclient import TestClient
from main import app
import pytest
from unittest.mock import patch, MagicMock

client = TestClient(app)

def test_api_health():
    """Verify that health check returns 200 and ok status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_api_stats():
    """Verify that stats count aggregation returns mock DB statistics."""
    with patch("main.database.get_db_connection") as mock_conn:
        mock_cursor = MagicMock()
        mock_conn.return_value.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = [5] # count representation
        
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["documents_count"] == 5
        assert data["concepts_count"] == 5

def test_api_list_documents():
    """Verify that the documents listing endpoint extracts all active workspaces."""
    with patch("main.database.get_documents") as mock_get_docs:
        mock_get_docs.return_value = [{"id": "doc-uuid-1", "name": "Test Document", "file_path": "path1"}]
        response = client.get("/api/documents")
        assert response.status_code == 200
        assert response.json() == [{"id": "doc-uuid-1", "name": "Test Document"}]

def test_api_get_concepts():
    """Verify concept retrieval returns existing concepts and edges in database."""
    with patch("main.database.get_concepts") as mock_concepts, \
         patch("main.database.get_concept_edges") as mock_edges:
        mock_concepts.return_value = [{"id": "c1", "label": "Concept 1", "explanation": "explanation 1", "page_number": 1}]
        mock_edges.return_value = []
        response = client.get("/api/documents/doc-uuid-1/concepts")
        assert response.status_code == 200
        assert "nodes" in response.json()
        assert response.json()["nodes"][0]["label"] == "Concept 1"

def test_api_get_graph_html():
    """Verify interactive graphing endpoint returns generate_vis_html content."""
    with patch("main.database.get_concepts") as mock_concepts, \
         patch("main.database.get_concept_edges") as mock_edges, \
         patch("main.visualizer.generate_vis_html") as mock_gen_html:
        mock_concepts.return_value = []
        mock_edges.return_value = []
        mock_gen_html.return_value = "<html>Graph Mock</html>"
        response = client.get("/api/documents/doc-uuid-1/graph-html")
        assert response.status_code == 200
        assert "Graph Mock" in response.text

def test_api_get_visual_spec_three_html():
    """Verify that Threejs rendering returns generated WebGL document successfully."""
    with patch("main.database.get_concept_visual_spec") as mock_get_spec, \
         patch("main.visualizer.generate_three_html") as mock_gen_html:
        mock_get_spec.return_value = {"type": "three", "spec_json": {"points": [], "connections": []}}
        mock_gen_html.return_value = "<html>WebGL 3D Mock</html>"
        response = client.get("/api/documents/doc-uuid-1/visual-specs/c1/three-html")
        assert response.status_code == 200
        assert "WebGL 3D Mock" in response.text

def test_api_chat():
    """Verify that multi-agent routing chat returns compiled invoke response."""
    with patch("main.graph.graph") as mock_graph, \
         patch("main.database.add_chat_message") as mock_add:
        mock_graph.invoke.return_value = {
            "messages": [MagicMock(content="Answer from Multi-Agent system")],
            "route": "general"
        }
        payload = {
            "query": "hello",
            "chat_history": [],
            "doc_id": "company_policies",
            "session_id": "session-123"
        }
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200
        assert response.json()["response"] == "Answer from Multi-Agent system"
        assert response.json()["route_taken"] == "general"

def test_api_feedback():
    """Verify that observability feedback score logging handles settings offline gracefully."""
    with patch("main.config") as mock_config:
        mock_config.LANGFUSE_PUBLIC_KEY = "" # offline fallback
        payload = {
            "rating": "up",
            "trace_id": "trace-123"
        }
        response = client.post("/api/feedback", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "Offline: Langfuse credentials not set"

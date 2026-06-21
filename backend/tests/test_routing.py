import pytest
from langchain_core.messages import HumanMessage
from app.graph import router_node, AgentState, local_regex_router

def test_router_general_greetings():
    """Verify that basic greetings route to the general agent."""
    state = AgentState(
        messages=[HumanMessage(content="Hello! How are you today?")],
        route="unknown",
        context=[],
        current_doc_id=""
    )
    result = router_node(state)
    assert result["route"] == "general"

def test_router_general_math():
    """Verify that math queries route to the general agent."""
    state = AgentState(
        messages=[HumanMessage(content="Can you compute 25 * 4 + 10?")],
        route="unknown",
        context=[],
        current_doc_id=""
    )
    result = router_node(state)
    assert result["route"] == "general"

def test_router_rag_travel_meals():
    """Verify that queries about travel allowance route to RAG."""
    state = AgentState(
        messages=[HumanMessage(content="How much can I spend on meals while traveling?")],
        route="unknown",
        context=[],
        current_doc_id=""
    )
    result = router_node(state)
    assert result["route"] == "rag"

def test_router_rag_remote_work():
    """Verify that queries about hybrid schedules route to RAG."""
    state = AgentState(
        messages=[HumanMessage(content="What are the remote work schedule rules?")],
        route="unknown",
        context=[],
        current_doc_id=""
    )
    result = router_node(state)
    assert result["route"] == "rag"

def test_router_rag_equipment_refresh():
    """Verify that laptop queries route to RAG."""
    state = AgentState(
        messages=[HumanMessage(content="When can I refresh my Macbook Pro?")],
        route="unknown",
        context=[],
        current_doc_id=""
    )
    result = router_node(state)
    assert result["route"] == "rag"

def test_router_fallback_to_active_doc():
    """Verify that if an active document workspace exists, queries route to RAG by default."""
    state = AgentState(
        messages=[HumanMessage(content="What does section 2 say?")],
        route="unknown",
        context=[],
        current_doc_id="some-uuid-1234"
    )
    result = router_node(state)
    assert result["route"] == "rag"

def test_router_general_greetings_with_active_doc():
    """Verify that basic greetings route to the general agent even with an active document."""
    state = AgentState(
        messages=[HumanMessage(content="Hello! How are you today?")],
        route="unknown",
        context=[],
        current_doc_id="some-uuid-1234"
    )
    result = router_node(state)
    assert result["route"] == "general"

def test_router_general_math_with_active_doc():
    """Verify that math queries route to the general agent even with an active document."""
    state = AgentState(
        messages=[HumanMessage(content="Can you compute 25 * 4 + 10?")],
        route="unknown",
        context=[],
        current_doc_id="some-uuid-1234"
    )
    result = router_node(state)
    assert result["route"] == "general"

def test_router_general_coding_with_active_doc():
    """Verify that coding queries route to the general agent even with an active document."""
    state = AgentState(
        messages=[HumanMessage(content="Write a Python function to compute Fibonacci numbers.")],
        route="unknown",
        context=[],
        current_doc_id="some-uuid-1234"
    )
    result = router_node(state)
    assert result["route"] == "general"

def test_local_regex_router_rag_keywords():
    """Verify that queries with RAG keywords are routed to RAG."""
    assert local_regex_router("What is the travel policy?", "") == "rag"
    assert local_regex_router("How much is the meal allowance?", "") == "rag"
    assert local_regex_router("I need a new macbook.", "doc-123") == "rag"

def test_local_regex_router_general_no_doc():
    """Verify that queries without RAG keywords and no active doc are routed to general."""
    assert local_regex_router("Hello there!", "") == "general"
    assert local_regex_router("What is 2 + 2?", "") == "general"
    assert local_regex_router("Write a python script", "") == "general"

def test_local_regex_router_general_with_doc():
    """Verify that general queries (greetings, math, coding) with an active doc and NO doc terms route to general."""
    assert local_regex_router("Hello there!", "doc-123") == "general"
    assert local_regex_router("What is 2 + 2?", "doc-123") == "general"
    assert local_regex_router("Write a python script", "doc-123") == "general"

def test_local_regex_router_general_with_doc_terms():
    """Verify that general queries that include doc terms with an active doc route to RAG."""
    assert local_regex_router("Hello! What is in this document?", "doc-123") == "rag"
    assert local_regex_router("Calculate the sum in section 2", "doc-123") == "rag"
    assert local_regex_router("Write a summary of this pdf", "doc-123") == "rag"

def test_local_regex_router_unknown_with_doc():
    """Verify that queries with no RAG keywords, no general terms, but with an active doc route to RAG."""
    assert local_regex_router("What about the other thing?", "doc-123") == "rag"
    assert local_regex_router("Can you explain more?", "doc-123") == "rag"

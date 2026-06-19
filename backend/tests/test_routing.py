import pytest
from langchain_core.messages import HumanMessage
from app.graph import router_node, AgentState

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

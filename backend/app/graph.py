import os
from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app import config
from app import database
from app.llm_client import CodexCliClient, run_async

_app_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_app_dir))

class TextResponse(BaseModel):
    response: str = Field(description="The textual reply to the user query.")

# Define Graph State
class AgentState(BaseModel):
    messages: List[Any] = Field(default_factory=list)
    route: str = Field(default="unknown")
    context: List[str] = Field(default_factory=list)
    current_doc_id: str = Field(default="")

# Structured Router Schema
class RouteDecision(BaseModel):
    route: Literal["general", "rag"] = Field(
        description="Choose 'rag' if the user's query refers to the uploaded document, company policies, travel allowance, hybrid schedule, equipment policy, or internal documents. Choose 'general' if the query is a greeting, pleasantry, coding query, math problem, general knowledge, or general chat."
    )
    reasoning: str = Field(description="Brief reasoning for routing selection.")

def local_regex_router(query: str, current_doc_id: str) -> str:
    """Classifies user query locally using keywords and active document context."""
    query_lower = query.lower().strip()
    rag_keywords = [
        "policy", "travel", "allowance", "hybrid", "schedule", "equipment", 
        "macbook", "laptop", "refresh", "reimburse", "meals", "office", "work"
    ]
    is_rag = any(kw in query_lower for kw in rag_keywords)
    
    if not is_rag and current_doc_id != "":
        # If a document is active, check if the query is a general query (greetings, math, coding, casual chat)
        greetings = ["hello", "hi", "hey", "good morning", "good afternoon", "greetings", "how are you", "what's up", "yo"]
        math_terms = ["compute", "calculate", "solve", "math", "equation", "sum", "integral", "derivative", "+", "*", "/"]
        coding_terms = ["code", "programming", "python", "javascript", "html", "css", "function", "bug", "write a", "program", "develop"]
        general_chat = ["joke", "who are you", "what are you", "how are you", "tell me a"]
        
        words = query_lower.split()
        is_general_query = (
            any(g in words for g in greetings) or 
            any(kw in query_lower for kw in math_terms) or 
            any(kw in query_lower for kw in coding_terms) or 
            any(kw in query_lower for kw in general_chat)
        )
        
        doc_terms = ["section", "page", "document", "pdf", "file", "author", "paper", "writeup", "text"]
        has_doc_terms = any(dt in query_lower for dt in doc_terms)
        
        if is_general_query and not has_doc_terms:
            return "general"
        else:
            return "rag"
            
    return "rag" if is_rag else "general"

# Node 1: Router Node
def router_node(state: AgentState) -> Dict[str, Any]:
    """Analyzes user query and decides whether to route to RAG or General Chat."""
    last_message = state.messages[-1]
    query = last_message.content if hasattr(last_message, "content") else str(last_message)
    
    # Check if we have OpenAI key
    if not config.OPENAI_API_KEY:
        # Fallback local regex routing
        route = local_regex_router(query, state.current_doc_id)
        return {"route": route, "context": []}
        
    try:
        client = CodexCliClient()
        
        # We prompt the router
        system_prompt = (
            "You are an expert enterprise query router. Classify the user query into either 'rag' or 'general'. "
            "If the query is related to the uploaded document context or company policies (travel, remote work, equipment), select 'rag'. "
            "If it is general chit-chat, math, programming, general knowledge, greetings, select 'general'."
        )
        prompt = f"System Prompt:\n{system_prompt}\n\nQuery to route: {query}"
        decision = run_async(client.run_json(
            task="route_query",
            prompt=prompt,
            schema=RouteDecision
        ))
        return {"route": decision.route, "context": []}
    except Exception as e:
        print(f"Error in router LLM: {e}. Falling back to default routing.")
        # Simple fallback
        route = local_regex_router(query, state.current_doc_id)
        return {"route": route, "context": []}

# Node 2: General Chatbot Node
def general_agent_node(state: AgentState) -> Dict[str, Any]:
    """Handles general chit-chat and greetings."""
    if not config.OPENAI_API_KEY:
        reply = "Hello! I am the Paper Helper General Assistant, running in offline mode. Please configure your OpenAI API Key in the settings or .env file to enable full chat functionality."
        return {"messages": [AIMessage(content=reply)]}
        
    try:
        client = CodexCliClient()
        system_prompt = (
            "You are a friendly, helpful general corporate assistant. Answer the user's questions clearly. "
            "Keep the responses engaging, professional, and concise."
        )
        # Format chat history
        history_text = "".join(
            f"{'User' if getattr(msg, 'type', '') == 'human' else 'Assistant'}: {getattr(msg, 'content', str(msg))}\n"
            for msg in state.messages[:-1]
        )
        
        user_query = state.messages[-1]
        query_content = getattr(user_query, "content", str(user_query))
        
        prompt = (
            f"System Prompt:\n{system_prompt}\n\n"
            f"Chat History:\n{history_text}\n"
            f"User: {query_content}"
        )
        
        llm_reply = run_async(client.run_json(
            task="general_chat",
            prompt=prompt,
            schema=TextResponse
        ))
        return {"messages": [AIMessage(content=llm_reply.response)]}
    except Exception as e:
        return {"messages": [AIMessage(content=f"Error in General Agent: {str(e)}")]}

# Node 3: RAG Chatbot Node
def rag_agent_node(state: AgentState) -> Dict[str, Any]:
    """Retrieves document context and answers queries grounded ONLY in the retrieved text."""
    last_message = state.messages[-1]
    query = last_message.content if hasattr(last_message, "content") else str(last_message)
    
    doc_id = state.current_doc_id
    if not doc_id:
        # Check if there is a company policies collection (Lab 3 requirement)
        doc_id = "company_policies"
        
    # Retrieve context
    context_chunks = []
    try:
        vector_store = database.get_vector_store(doc_id)
        # Retrieve top 4 similar chunks
        results = vector_store.similarity_search(query, k=4)
        for res in results:
            page_num = res.metadata.get("page_number", "unknown")
            context_chunks.append(f"[Page {page_num}]: {res.page_content}")
    except Exception as e:
        print(f"Error retrieving context: {e}")
        # Let's fallback to querying SQLite text or policies directly if Chroma isn't indexed
        if doc_id == "company_policies":
            policies_file = os.path.join(_project_root, "data", "company_policies.txt")
            if os.path.exists(policies_file):
                with open(policies_file, "r") as f:
                    context_chunks = [f"[Page 1]: {f.read()}"]
        else:
            # Get pages from SQLite
            pages = database.get_document_pages(doc_id)
            for p in pages[:3]:
                context_chunks.append(f"[Page {p['page_number']}]: {p['text'][:300]}")
                
    context_str = "\n\n".join(context_chunks)
    
    if not config.OPENAI_API_KEY:
        reply = (
            "Offline Mode: Retrieved the following context chunks from the document:\n\n"
            f"{context_str}\n\n"
            "Please configure your OpenAI API Key to get a synthesized response."
        )
        return {"messages": [AIMessage(content=reply)], "context": context_chunks}
        
    try:
        client = CodexCliClient()
        system_prompt = (
            "You are a strict Retrieval-Augmented Generation (RAG) assistant. "
            "Your task is to answer the user query ONLY using the provided retrieved context. "
            "Do NOT use external knowledge. Always include page references (e.g. [Page X]) in your answers "
            "when referring to specific information. "
            "If the provided context does not contain the answer, say exactly: "
            "'I am sorry, but the provided document does not contain that information.'\n\n"
            f"--- START RETRIEVED CONTEXT ---\n{context_str}\n--- END RETRIEVED CONTEXT ---"
        )
        # Format chat history
        history_text = "".join(
            f"{'User' if getattr(msg, 'type', '') == 'human' else 'Assistant'}: {getattr(msg, 'content', str(msg))}\n"
            for msg in state.messages[:-1]
        )
            
        user_query = state.messages[-1]
        query_content = getattr(user_query, "content", str(user_query))
        
        prompt = (
            f"System Prompt:\n{system_prompt}\n\n"
            f"Chat History:\n{history_text}\n"
            f"User: {query_content}"
        )
        
        llm_reply = run_async(client.run_json(
            task="rag_chat",
            prompt=prompt,
            schema=TextResponse
        ))
        return {"messages": [AIMessage(content=llm_reply.response)], "context": context_chunks}
    except Exception as e:
        return {"messages": [AIMessage(content=f"Error in RAG Agent: {str(e)}")], "context": context_chunks}

# Define the conditional edge router function
def route_decision_edge(state: AgentState) -> Literal["general_agent", "rag_agent"]:
    if state.route == "rag":
        return "rag_agent"
    return "general_agent"

# Build and Compile the Graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("router", router_node)
workflow.add_node("general_agent", general_agent_node)
workflow.add_node("rag_agent", rag_agent_node)

# Add Edges
workflow.set_entry_point("router")
workflow.add_conditional_edges(
    "router",
    route_decision_edge,
    {
        "general_agent": "general_agent",
        "rag_agent": "rag_agent"
    }
)
workflow.add_edge("general_agent", END)
workflow.add_edge("rag_agent", END)

# Memory Checkpointer
memory = MemorySaver()
graph = workflow.compile(checkpointer=memory)

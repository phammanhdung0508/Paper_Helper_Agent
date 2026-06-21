"""
Supervisor Agent — lightweight deterministic orchestration layer.

The Supervisor sits above specialist agents and handles:
1. Routing user requests to the correct specialist agent
2. Selecting the LLM provider order for each task
3. Executing the specialist agent via LLMRouterClient
4. Validating structured outputs
5. Retrying or falling back when provider calls fail
6. Returning the final response or a graceful error

The Supervisor is NOT an LLM call itself — it uses deterministic
rules and configuration to orchestrate specialist agents.
"""

from typing import Dict, Any, Optional
from app import config
from app import database
from app.llm_client import LLMRouterClient, LLMError


class SupervisorAgent:
    """
    Central orchestration layer above specialist agents.

    Supported actions:
        - "chat"          → routes to RAG or General agent via LangGraph
        - "concept_spot"  → delegates to ConceptGraphAgent
        - "visual_gen"    → delegates to VisualSandboxAgent
        - "kg_build"      → delegates to ConceptGraphAgent
        - "evaluate"      → delegates to MasteryEvaluatorAgent
        - "general"       → delegates to general chat agent
    """

    def __init__(self):
        self.llm_client = LLMRouterClient()

    def route_and_execute(self, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point. Routes the action to the correct specialist agent.

        Args:
            action: one of "chat", "concept_spot", "visual_gen", "kg_build", "evaluate", "general"
            context: dict with keys like "query", "doc_id", "concept_id", etc.

        Returns:
            dict with the result from the specialist agent
        """
        try:
            if action == "concept_spot" or action == "kg_build":
                return self._handle_kg_build(context)
            elif action == "visual_gen":
                return self._handle_visual_gen(context)
            elif action == "evaluate":
                return self._handle_evaluate(context)
            elif action == "quiz_gen":
                return self._handle_quiz_gen(context)
            elif action == "chat":
                return self._handle_chat(context)
            elif action == "general":
                return self._handle_general(context)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown action: {action}. Supported: chat, concept_spot, visual_gen, kg_build, evaluate, quiz_gen, general"
                }
        except LLMError as e:
            return {
                "status": "error",
                "error_category": e.category,
                "message": f"Supervisor: all providers failed for action '{action}': {e.message}"
            }
        except Exception as e:
            return {
                "status": "error",
                "error_category": "unknown",
                "message": f"Supervisor: unexpected error during '{action}': {str(e)}"
            }

    def _handle_kg_build(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Delegates to ConceptGraphAgent.build_graph()."""
        from app.agents import ConceptGraphAgent
        doc_id = context.get("doc_id", "")
        document_text = context.get("document_text", "")

        if not document_text:
            # Try loading from database
            pages = database.get_document_pages(doc_id)
            if pages:
                document_text = "\n".join([p["text"] for p in pages])

        if not document_text:
            return {"status": "error", "message": "No document text available for knowledge graph generation."}

        nodes, edges = ConceptGraphAgent.build_graph(doc_id, document_text, llm_client=self.llm_client)
        database.save_concepts(nodes)
        database.save_concept_edges(edges)

        return {"status": "success", "nodes": nodes, "edges": edges}

    def _handle_visual_gen(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Delegates to VisualSandboxAgent.generate_spec()."""
        from app.agents import VisualSandboxAgent
        doc_id = context.get("doc_id", "")
        concept_id = context.get("concept_id", "")
        concept_label = context.get("concept_label", "")
        concept_explanation = context.get("concept_explanation", "")

        spec = VisualSandboxAgent.generate_spec(
            doc_id, concept_id, concept_label, concept_explanation,
            llm_client=self.llm_client
        )
        database.save_visual_specs([spec])

        return {"status": "success", "spec": spec}

    def _handle_evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Delegates to MasteryEvaluatorAgent.evaluate_response()."""
        from app.agents import MasteryEvaluatorAgent
        concept_label = context.get("concept_label", "")
        concept_explanation = context.get("concept_explanation", "")
        question = context.get("question", "")
        student_answer = context.get("student_answer", "")
        current_scores = context.get("current_scores", {
            "memory": 0, "comprehension": 0, "structure": 0, "application": 0
        })

        result = MasteryEvaluatorAgent.evaluate_response(
            concept_label, concept_explanation, question, student_answer,
            current_scores, llm_client=self.llm_client
        )

        return {"status": "success", **result}

    def _handle_chat(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Delegates to the LangGraph workflow (graph.py)."""
        from app.graph import graph as langgraph_workflow

        inputs = {
            "messages": context.get("messages", []),
            "current_doc_id": context.get("current_doc_id", "")
        }
        config_dict = context.get("config_dict", {})

        response = langgraph_workflow.invoke(inputs, config_dict)
        ai_reply = response["messages"][-1].content
        route_taken = response.get("route", "unknown")

        return {
            "status": "success",
            "ai_reply": ai_reply,
            "route_taken": route_taken,
            "response_raw": response
        }

    def _handle_general(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Delegates to the LangGraph workflow (graph.py) as general chat."""
        return self._handle_chat(context)

    def _handle_quiz_gen(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Delegates to MasteryEvaluatorAgent.generate_quiz_question()."""
        from app.agents import MasteryEvaluatorAgent
        concept_label = context.get("concept_label", "")
        concept_explanation = context.get("concept_explanation", "")

        question = MasteryEvaluatorAgent.generate_quiz_question(
            concept_label, concept_explanation, llm_client=self.llm_client
        )
        return {"status": "success", "question": question}


# Singleton instance
supervisor = SupervisorAgent()

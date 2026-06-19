import json
from typing import List, Dict, Any, Optional, Literal, Tuple
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app import config
from app import database

# Define schemas for structured outputs
class ConceptNode(BaseModel):
    id: str = Field(description="Unique snake_case or camelCase ID for the concept.")
    label: str = Field(description="Short readable label (e.g., 'Circulatory System').")
    explanation: str = Field(description="A concise definition of the concept.")
    page_number: int = Field(description="The primary page number where this concept is defined.")

class RelationshipEdge(BaseModel):
    source: str = Field(description="Source concept ID.")
    target: str = Field(description="Target concept ID.")
    type: Literal["prerequisite", "composition", "causal", "specialisation", "parallel", "contrast"]
    description: str = Field(description="A brief description of why these concepts are related.")

class KnowledgeGraph(BaseModel):
    nodes: List[ConceptNode]
    edges: List[RelationshipEdge]

class KatexStep(BaseModel):
    formula: str = Field(description="KaTeX formula (without $$ wrapper, e.g., 'E = mc^2').")
    explanation: str = Field(description="Textual explanation of what this step means.")

class PlotlySpec(BaseModel):
    title: str = Field(description="Plot title.")
    x_range: List[float] = Field(description="[min, max] range for x axis.")
    function_type: str = Field(description="Type of function, e.g., 'normal_distribution', 'linear', 'exponential', 'cosine_similarity'.")
    parameters: Dict[str, Any] = Field(description="Parameters for the function.")

class VisualSpecOutput(BaseModel):
    type: Literal["plotly", "katex", "canvas"]
    title: str
    description: str
    plotly_spec: Optional[PlotlySpec] = None
    katex_steps: Optional[List[KatexStep]] = None
    canvas_steps: Optional[List[Dict[str, Any]]] = None

class MasteryAssessment(BaseModel):
    memory: int = Field(description="Updated memory score (0-100).", ge=0, le=100)
    comprehension: int = Field(description="Updated comprehension score (0-100).", ge=0, le=100)
    structure: int = Field(description="Updated structure score (0-100).", ge=0, le=100)
    application: int = Field(description="Updated application score (0-100).", ge=0, le=100)
    reasoning: str = Field(description="Brief assessment of the student's answer.")
    recommendation: str = Field(description="Recommended next study step.")

# Agent 1: Knowledge Graph Builder Agent
class ConceptGraphAgent:
    @staticmethod
    def build_graph(doc_id: str, document_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extracts 6-25 concepts and relationship edges from the document text."""
        if not config.OPENAI_API_KEY:
            return ConceptGraphAgent._mock_graph(doc_id)
            
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=config.OPENAI_API_KEY,
                max_retries=3
            )
            structured_llm = llm.with_structured_output(KnowledgeGraph)
            
            # Since document text can be long, we take a slice of the text
            # representing the first 15000 characters and last 10000 characters.
            sample_text = document_text
            if len(document_text) > 25000:
                sample_text = document_text[:15000] + "\n... [TRUNCATED] ...\n" + document_text[-10000:]
                
            system_prompt = (
                "You are an expert curriculum designer and knowledge engineer. "
                "Analyze the provided document text and extract between 6 and 20 core educational concepts. "
                "Define relationship edges between these concepts. "
                "Identify which concepts are prerequisites for others, which ones causal, compose a larger concept, etc. "
                "Ensure all node IDs match between nodes and edges, there are no self-loops, and all node IDs are unique."
            )
            
            graph_data = structured_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Document Text:\n{sample_text}")
            ])
            
            nodes = []
            node_id_to_label = {}
            for n in graph_data.nodes:
                node_id_to_label[n.id] = n.label
                nodes.append({
                    "doc_id": doc_id,
                    "label": n.label,
                    "explanation": n.explanation,
                    "page_number": n.page_number
                })
                
            edges = []
            valid_node_ids = {n.id for n in graph_data.nodes}
            for e in graph_data.edges:
                # Basic sanitization
                if e.source in valid_node_ids and e.target in valid_node_ids and e.source != e.target:
                    source_label = node_id_to_label[e.source]
                    target_label = node_id_to_label[e.target]
                    edges.append({
                        "doc_id": doc_id,
                        "source": f"{doc_id}_concept_{source_label.lower().replace(' ', '_')}",
                        "target": f"{doc_id}_concept_{target_label.lower().replace(' ', '_')}",
                        "type": e.type,
                        "description": e.description
                    })
            return nodes, edges
        except Exception as e:
            print(f"Error in ConceptGraphAgent: {e}. Falling back to mocks.")
            return ConceptGraphAgent._mock_graph(doc_id)

    @staticmethod
    def _mock_graph(doc_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Generates high-quality mock graphs for course labs."""
        # Check if the doc_id belongs to Lab 3 or Lab 4 based on metadata or just give standard
        nodes = [
            {"doc_id": doc_id, "label": "LangGraph", "explanation": "A library for building stateful, multi-actor applications with LLMs using graph structures.", "page_number": 3},
            {"doc_id": doc_id, "label": "State Management", "explanation": "A shared, structured data object passed between nodes that stores messages and variables.", "page_number": 3},
            {"doc_id": doc_id, "label": "Router Node", "explanation": "A semantic classifier node that uses LLMs to route traffic dynamically to the correct agent node.", "page_number": 3},
            {"doc_id": doc_id, "label": "RAG Agent", "explanation": "An agent that retrieves context from a vector store to generate precise, grounded answers.", "page_number": 5},
            {"doc_id": doc_id, "label": "Vector Store", "explanation": "A database for storing high-dimensional vector embeddings of text chunks for similarity matching.", "page_number": 4},
            {"doc_id": doc_id, "label": "Chroma DB", "explanation": "A local embedded vector database used in LangChain for fast similarity search.", "page_number": 4},
            {"doc_id": doc_id, "label": "Gradio UI", "explanation": "A python library for building customizable web interfaces for machine learning models.", "page_number": 6},
            {"doc_id": doc_id, "label": "Langfuse", "explanation": "An open-source LLM engineering platform for self-hosted observability, tracing, and feedback evaluation.", "page_number": 2}
        ]
        
        # Format concept IDs
        # id format matches database: {doc_id}_concept_{label.lower().replace(' ', '_')}
        edges = [
            {"doc_id": doc_id, "source": f"{doc_id}_concept_langgraph", "target": f"{doc_id}_concept_state_management", "type": "composition", "description": "LangGraph uses State objects to manage workflow state."},
            {"doc_id": doc_id, "source": f"{doc_id}_concept_state_management", "target": f"{doc_id}_concept_router_node", "type": "prerequisite", "description": "Router Node reads state messages to decide next node."},
            {"doc_id": doc_id, "source": f"{doc_id}_concept_router_node", "target": f"{doc_id}_concept_rag_agent", "type": "causal", "description": "Router Node triggers the RAG Agent if corporate queries are identified."},
            {"doc_id": doc_id, "source": f"{doc_id}_concept_rag_agent", "target": f"{doc_id}_concept_vector_store", "type": "composition", "description": "RAG Agent relies on Vector Store to fetch grounded context."},
            {"doc_id": doc_id, "source": f"{doc_id}_concept_vector_store", "target": f"{doc_id}_concept_chroma_db", "type": "specialisation", "description": "Chroma DB is a concrete embedded implementation of a Vector Store."},
            {"doc_id": doc_id, "source": f"{doc_id}_concept_langgraph", "target": f"{doc_id}_concept_gradio_ui", "type": "parallel", "description": "Gradio UI wraps the compiled LangGraph workflow in an interactive web application."},
            {"doc_id": doc_id, "source": f"{doc_id}_concept_langgraph", "target": f"{doc_id}_concept_langfuse", "type": "parallel", "description": "Langfuse instruments LangGraph nodes and traces executions in production."}
        ]
        return nodes, edges

# Agent 2: Visualization Planner Agent
class VisualSandboxAgent:
    @staticmethod
    def generate_spec(doc_id: str, concept_id: str, concept_label: str, concept_explanation: str) -> Dict[str, Any]:
        """Plans and generates a structured spec for a concept."""
        if not config.OPENAI_API_KEY:
            return VisualSandboxAgent._mock_spec(doc_id, concept_id, concept_label)
            
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=config.OPENAI_API_KEY,
                max_retries=3
            )
            structured_llm = llm.with_structured_output(VisualSpecOutput)
            
            prompt = (
                f"You are a visual education designer. Generate a visualization specification for this concept:\n"
                f"Label: {concept_label}\n"
                f"Explanation: {concept_explanation}\n\n"
                "Decide which visualization type fits best:\n"
                "1. 'plotly' if it has graphs, distributions, functions, or numeric plotting (e.g. Cosine Similarity curve, normal distribution, learning rate curve).\n"
                "2. 'katex' if it involves equations, mathematical derivations, or steps (e.g. Mastery display formula, cosine formula, vector distance math).\n"
                "3. 'canvas' if it is a multi-step sequence flow or mechanical animation (e.g. RAG pipeline flow: split -> embed -> index -> retrieve).\n\n"
                "Provide rich rendering data in the corresponding field."
            )
            
            spec = structured_llm.invoke([
                SystemMessage(content="You generate structured visualization specifications for concepts."),
                HumanMessage(content=prompt)
            ])
            
            spec_dict = {
                "doc_id": doc_id,
                "concept_id": concept_id,
                "type": spec.type,
                "title": spec.title,
                "description": spec.description,
                "spec_json": {}
            }
            
            if spec.type == "plotly" and spec.plotly_spec:
                spec_dict["spec_json"] = spec.plotly_spec.dict()
            elif spec.type == "katex" and spec.katex_steps:
                spec_dict["spec_json"] = {"steps": [step.dict() for step in spec.katex_steps]}
            elif spec.type == "canvas" and spec.canvas_steps:
                spec_dict["spec_json"] = {"steps": spec.canvas_steps}
                
            return spec_dict
        except Exception as e:
            print(f"Error in VisualSandboxAgent: {e}. Falling back to mocks.")
            return VisualSandboxAgent._mock_spec(doc_id, concept_id, concept_label)

    @staticmethod
    def _mock_spec(doc_id: str, concept_id: str, label: str) -> Dict[str, Any]:
        lbl = label.lower()
        if "rag" in lbl or "vector" in lbl or "chroma" in lbl:
            # Let's show Cosine Similarity math for vector/rag
            return {
                "doc_id": doc_id,
                "concept_id": concept_id,
                "type": "katex",
                "title": "Vector Cosine Similarity",
                "description": "Cosine similarity measures the cosine of the angle between two multi-dimensional vectors, determining how semantically close two text chunks are.",
                "spec_json": {
                    "steps": [
                        {"formula": "\\cos(\\theta) = \\frac{\\mathbf{A} \\cdot \\mathbf{B}}{\\|\\mathbf{A}\\| \\|\\mathbf{B}\\|}", "explanation": "The general formula for cosine similarity. A and B are high-dimensional document embedding vectors."},
                        {"formula": "\\mathbf{A} \\cdot \\mathbf{B} = \\sum_{i=1}^{n} A_i B_i", "explanation": "The dot product represents the alignment of individual dimensions of semantic features."},
                        {"formula": "\\|\\mathbf{A}\\| = \\sqrt{\\sum_{i=1}^{n} A_i^2}", "explanation": "The vector norm represents the magnitude or length of the embedding vector."}
                    ]
                }
            }
        elif "langfuse" in lbl or "observability" in lbl:
            # Renders a Plotly latency chart
            return {
                "doc_id": doc_id,
                "concept_id": concept_id,
                "type": "plotly",
                "title": "LLM Generation Latency Distribution",
                "description": "Visualizes how response generation latency changes across model versions (e.g. gpt-4o-mini vs gpt-4o).",
                "spec_json": {
                    "data": [
                        {
                            "x": [1.2, 1.5, 1.8, 2.0, 2.2, 2.5, 3.0, 3.5, 4.2],
                            "y": [5, 12, 25, 40, 32, 18, 8, 3, 1],
                            "type": "scatter",
                            "mode": "lines+markers",
                            "name": "gpt-4o-mini (Faster)",
                            "line": {"color": "#4fae84"}
                        },
                        {
                            "x": [2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.5],
                            "y": [2, 6, 15, 28, 35, 22, 12, 5, 2],
                            "type": "scatter",
                            "mode": "lines+markers",
                            "name": "gpt-4o (Slower)",
                            "line": {"color": "#8b78d9"}
                        }
                    ],
                    "layout": {
                        "xaxis": {"title": "Latency (seconds)"},
                        "yaxis": {"title": "Frequency (Count)"},
                        "paper_bgcolor": "rgba(0,0,0,0)",
                        "plot_bgcolor": "rgba(0,0,0,0)",
                        "font": {"color": "#ffffff"}
                    }
                }
            }
        else:
            # Let's show the Mastery display formula as default
            return {
                "doc_id": doc_id,
                "concept_id": concept_id,
                "type": "katex",
                "title": "Mastery Evaluation Weighting Formula",
                "description": "Calculates the unified mastery score from individual scores across Memory, Comprehension, Structure, and Application.",
                "spec_json": {
                    "steps": [
                        {"formula": "\\text{Mastery} = M \\times 0.25 + C \\times 0.30 + S \\times 0.20 + A \\times 0.25", "explanation": "The weighted formula: Comprehension (30%) and Application (25%) are weighted highest as they indicate active mastery."},
                        {"formula": "\\text{Monotone Clamp: } Score_{new} = \\max(Score_{prev}, Score_{eval})", "explanation": "Ensures demonstrated knowledge scores never decrease, protecting historical student records."}
                    ]
                }
            }

# Agent 3: Mastery Evaluator Agent
class MasteryEvaluatorAgent:
    @staticmethod
    def generate_quiz_question(concept_label: str, explanation: str) -> str:
        """Generates a study question to evaluate the user's comprehension of the concept."""
        if not config.OPENAI_API_KEY:
            return f"Explain the core concept of '{concept_label}' and list two main features or details of it."
            
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.7,
                openai_api_key=config.OPENAI_API_KEY,
                max_retries=3
            )
            prompt = (
                f"You are an academic examiner. Generate one short, challenging essay question to evaluate a student's comprehension of the following concept:\n"
                f"Concept: {concept_label}\n"
                f"Definition: {explanation}\n\n"
                "The question should require the student to explain the concept in their own words or apply it to a scenario. Do not make it multiple choice."
            )
            response = llm.invoke([
                SystemMessage(content="You generate assessment questions for study concepts."),
                HumanMessage(content=prompt)
            ])
            return response.content
        except Exception:
            return f"Explain the core concept of '{concept_label}' and list two main features or details of it."

    @staticmethod
    def evaluate_response(concept_label: str, explanation: str, question: str, student_answer: str, current_scores: Dict[str, int]) -> Dict[str, Any]:
        """Evaluates student's written response and calculates updated four-axis mastery scores with monotone clamping."""
        prev = current_scores
        
        if not config.OPENAI_API_KEY:
            # Default increment offline
            new_scores = {
                "memory": min(100, prev.get("memory", 0) + 20),
                "comprehension": min(100, prev.get("comprehension", 0) + 15),
                "structure": min(100, prev.get("structure", 0) + 10),
                "application": min(100, prev.get("application", 0) + 10)
            }
            clamped = MasteryEvaluatorAgent.clamp_monotone(prev, new_scores)
            return {
                "scores": clamped,
                "reasoning": "Offline evaluation completed. Incremented scores based on simulated submission.",
                "recommendation": "Review the concept visualization sandbox to reinforce mathematical/logical understanding."
            }
            
        try:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                openai_api_key=config.OPENAI_API_KEY,
                max_retries=3
            )
            structured_llm = llm.with_structured_output(MasteryAssessment)
            
            prompt = (
                f"Evaluate the student's mastery of the concept '{concept_label}'.\n"
                f"Concept Definition: {explanation}\n"
                f"Question Asked: {question}\n"
                f"Student's Answer: {student_answer}\n\n"
                f"Current baseline scores:\n"
                f"Memory: {prev.get('memory', 0)}, Comprehension: {prev.get('comprehension', 0)}, "
                f"Structure: {prev.get('structure', 0)}, Application: {prev.get('application', 0)}\n\n"
                "Return updated scores (0-100) reflecting demonstrated mastery in the response. "
                "Keep in mind the scores are developmental. Provide your reasoning and recommendations."
            )
            
            assessment = structured_llm.invoke([
                SystemMessage(content="You are an expert learning assessor. Evaluate student responses strictly and fairly."),
                HumanMessage(content=prompt)
            ])
            
            new_scores = {
                "memory": assessment.memory,
                "comprehension": assessment.comprehension,
                "structure": assessment.structure,
                "application": assessment.application
            }
            clamped = MasteryEvaluatorAgent.clamp_monotone(prev, new_scores)
            
            return {
                "scores": clamped,
                "reasoning": assessment.reasoning,
                "recommendation": assessment.recommendation
            }
        except Exception as e:
            print(f"Error in MasteryEvaluatorAgent: {e}")
            new_scores = {
                "memory": min(100, prev.get("memory", 0) + 10),
                "comprehension": min(100, prev.get("comprehension", 0) + 10),
                "structure": min(100, prev.get("structure", 0) + 10),
                "application": min(100, prev.get("application", 0) + 10)
            }
            clamped = MasteryEvaluatorAgent.clamp_monotone(prev, new_scores)
            return {
                "scores": clamped,
                "reasoning": f"Evaluation fallback due to LLM error: {str(e)}",
                "recommendation": "Please try submitting your answer again once network connections are verified."
            }

    @staticmethod
    def clamp_monotone(prev: Dict[str, int], next_scores: Dict[str, int]) -> Dict[str, int]:
        """Monotone clamping: scores cannot decrease."""
        return {
            "memory": max(prev.get("memory", 0), min(100, max(0, round(next_scores.get("memory", 0))))),
            "comprehension": max(prev.get("comprehension", 0), min(100, max(0, round(next_scores.get("comprehension", 0))))),
            "structure": max(prev.get("structure", 0), min(100, max(0, round(next_scores.get("structure", 0))))),
            "application": max(prev.get("application", 0), min(100, max(0, round(next_scores.get("application", 0))))),
        }

    @staticmethod
    def calculate_unified_score(scores: Dict[str, int]) -> int:
        """Weighted score displays: Memory (25%), Comprehension (30%), Structure (20%), Application (25%)."""
        return round(
            scores.get("memory", 0) * 0.25 +
            scores.get("comprehension", 0) * 0.30 +
            scores.get("structure", 0) * 0.20 +
            scores.get("application", 0) * 0.25
        )

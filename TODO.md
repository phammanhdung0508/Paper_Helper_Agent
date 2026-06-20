# TODO: Local Visual PDF Study Companion

## Project Direction

Build a local-first study companion that transforms text-based PDFs into interactive learning experiences. The target product stack is **Next.js + FastAPI**, with animation/visualization powered by **Three.js or similar web-native renderers**. The MVP focuses on PDF ingestion, concept spotting, visual sandboxes, scoped PDF chat, a simple knowledge graph, and a lightweight mastery map.

The project should run locally on the user's computer and use the user's own OpenAI Codex CLI account where possible. The app should not require a paid hosted backend or proxy user documents through a developer-owned server. Gradio is not the target UI for the product.

## Recommended Tools And Technologies

### Target Architecture

Primary target stack:

- Next.js frontend for the PDF viewer, concept tags, visual sandbox, Knowledge Graph, Mastery Map, and chat UI.
- FastAPI backend for PDF ingestion, local storage, retrieval, agent workflows, Codex CLI calls, and observability hooks.
- SQLite database for local state.
- Filesystem storage for uploaded PDFs, generated artifacts, and optional exports.

Desktop packaging later:

- Electron can wrap the Next.js + FastAPI app after the local web app is stable.
- Tauri can be considered later if app size becomes important.
- Do not start with desktop packaging unless required.

Recommended direction:

- Start with Next.js running locally and FastAPI running locally.
- Treat Electron/Tauri as a packaging layer, not the first milestone.
- Do not use Gradio for the product UI.

### Frontend UI

- React
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui, optional for fast polished components
- Zustand or Jotai for lightweight client state
- React Hook Form, optional for forms

Main UI panels:

- PDF viewer panel
- concept tag panel
- visual sandbox panel
- scoped chat panel
- knowledge graph/mastery map panel
- setup/auth wizard for Codex login

### Backend API

Recommended backend stack:

- FastAPI
- Python 3.11+
- Pydantic for request/response schemas
- Uvicorn for local development server
- SQLite for local persistence
- Chroma, FAISS, or LanceDB for retrieval/vector search
- subprocess management for Codex CLI calls

Backend responsibilities:

- PDF upload and validation
- text extraction by page
- chunking and retrieval
- concept spotting
- visual spec generation
- Knowledge Graph generation and sanitization
- scoped chat/RAG
- mastery evaluation
- local job queue/state
- Langfuse tracing, if enabled

Suggested FastAPI packages:

- `fastapi`
- `uvicorn`
- `pydantic`
- `python-multipart`
- `sqlalchemy` or direct `sqlite3`
- `aiosqlite`, optional
- `pypdf` or `pymupdf`

### Desktop And Local System Access

For MVP:

- Run Next.js and FastAPI as local development servers.
- Store data under a local app data directory.
- Start Codex CLI subprocesses from the FastAPI backend.

For packaged desktop later:

- Electron main process can launch the FastAPI backend and Next.js frontend.
- Electron can manage local file access and app lifecycle.
- Avoid exposing raw Node.js APIs directly to the renderer.

Suggested Electron packages:

- `electron`
- `electron-builder`, later for packaging
- `concurrently`, useful during development

### PDF Processing

Recommended tools:

- `PyMuPDF`: recommended for FastAPI backend text extraction and future layout/bounding-box support.
- `pypdf`: simpler fallback for page text extraction.
- `pdfjs-dist`: recommended in the Next.js frontend for PDF rendering/text layer display.
- `pdfplumber`: optional if table/layout extraction becomes important.

MVP recommendation:

- Use `PyMuPDF` or `pypdf` in FastAPI for page-level text extraction.
- Use `pdfjs-dist` in Next.js for rendering pages.
- Do not implement exact word-coordinate overlay in the first version.

Future tools for pixel-level overlays:

- `pdfjs-dist` text layer APIs
- canvas rendering
- bounding-box extraction from PDF.js text items

### Local Database

Recommended stack:

- SQLite
- SQLAlchemy, SQLModel, or direct `sqlite3` from FastAPI
- Alembic, optional if using SQLAlchemy migrations

Why:

- local-first
- simple backup
- works offline
- easy to ship with a local FastAPI app
- enough for documents, concepts, chat history, mastery scores, and jobs

Optional alternatives:

- `better-sqlite3` + Drizzle if the backend is moved to Node/Electron later.
- Prisma + SQLite if using a TypeScript backend later.
- LowDB for quick prototypes only, but weaker for relational state.

### Vector Search / RAG

Include a minimal retrieval layer for scoped PDF chat.

Options:

- Chroma: common LangChain/FastAPI-compatible choice.
- FAISS: fast local vector search, common in Python.
- LanceDB: good local embedded vector database.
- SQLite vector extension: possible later, but adds setup complexity.

Recommended MVP options:

- Use Chroma or FAISS first in FastAPI.
- Use simple SQLite keyword/BM25 fallback if embeddings are unavailable.

Embedding options:

- OpenAI embeddings through user's account, if available.
- Local embeddings later through Ollama or Transformers.js.

### LLM And Codex Integration

Primary direction:

- OpenAI Codex CLI through the user's own account.
- Spawn CLI subprocesses from the FastAPI backend.
- Wrap all model calls behind an internal `LLMClient` interface.

Important packages:

- Python `subprocess` or `asyncio.create_subprocess_exec` for Codex CLI execution.
- Pydantic for output validation on the backend.
- `uuid` for document IDs, trace IDs, and job IDs.
- Zod can still be used in the frontend for validating UI-facing JSON payloads.

Recommended abstraction:

```ts
interface LLMClient {
  runJson<T>(task: string, prompt: string, schema: z.ZodSchema<T>): Promise<T>;
}
```

FastAPI/Python equivalent:

```py
class LLMClient:
    async def run_json(self, task: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
        ...
```

Error categories to support:

- `auth_lost`
- `rate_limit`
- `invalid_json`
- `timeout`
- `subprocess_crash`
- `empty_output`
- `unknown`

### Agent Orchestration

For the real Next.js/FastAPI app:

- Implement lightweight internal workflows in FastAPI first.
- Use explicit functions/classes per agent.
- Keep backend schemas strict with Pydantic.
- Keep frontend payload schemas strict with TypeScript and optional Zod.
- Add a lightweight Supervisor Agent as the central orchestration layer.
- Keep the Supervisor mostly deterministic/config-driven, not a costly LLM call for every request.

Only if Lab 3 strictly requires the original stack:

- LangGraph
- LangChain
- Python
- Gradio

Recommended approach:

- Build the real product architecture in Next.js + FastAPI.
- If the lab strictly requires LangGraph/Gradio, keep that as a separate compatibility prototype, not the product UI.

### Supervisor Agent

Add a lightweight Supervisor Agent above the specialist agents.

Purpose:

- Decide the high-level task route.
- Select the correct specialist agent.
- Select the LLM provider/fallback order for that task.
- Execute the specialist agent.
- Validate structured outputs.
- Retry or fall back when provider/model calls fail.
- Return the final response or a graceful error.

Recommended flow:

```text
User Request
  -> Supervisor Agent
     -> Router decision
     -> Select specialist agent
     -> Select LLM provider order
     -> Execute specialist agent
     -> Validate result
     -> Retry/fallback if needed
  -> Final Response
```

Specialist agents under Supervisor:

- General Agent
- RAG Agent
- Concept Spotter Agent
- Knowledge Graph Builder Agent
- Visual Sandbox Agent
- Mastery Evaluator Agent

Important design rule:

- Supervisor should not replace specialist agents.
- Supervisor should orchestrate and enforce policy.
- Use deterministic rules/config first.
- Only use an LLM inside Supervisor if routing cannot be solved reliably with rules.

### Advanced LLM Routing And Fallbacks

Add an LLM routing layer inspired by the deployment strategy notes on hybrid architecture, model tiering, caching, feature flags, and rollback/fallback design.

Goal:

- Keep Codex as the main high-quality provider.
- Add Gemini or other free/cheap providers for development/testing and low-risk tasks.
- Route by task complexity and provider availability.
- Fall back automatically on rate limits, auth failures, timeouts, invalid JSON, or provider crashes.

Recommended provider architecture:

```text
BaseLLMClient
  -> CodexCliClient
  -> GeminiClient
  -> OpenAIClient, optional
  -> MockLLMClient, for tests/offline mode

LLMRouterClient
  -> reads task type
  -> checks cache
  -> chooses provider order
  -> retries/fallbacks
  -> validates output
  -> logs result
```

All providers should expose the same interface:

```py
class BaseLLMClient:
    async def run_json(self, task: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
        ...
```

Recommended task routing:

```text
route_query               -> local rules, gemini, codex
general_chat              -> gemini, codex
rag_chat                  -> codex, gemini
extract_knowledge_graph   -> gemini, codex
generate_visual_spec      -> gemini, codex
evaluate_mastery_response -> gemini, codex
```

Fallback triggers:

- `rate_limit`
- `auth_lost`
- `timeout`
- `invalid_json`
- `subprocess_crash`
- `empty_output`
- `unknown`

Example provider flow:

```text
1. Check exact cache.
2. If cache hit, return cached JSON.
3. If cache miss, call first provider.
4. If provider succeeds and schema validates, store response in cache and return.
5. If provider fails, log error and try next provider.
6. If all providers fail, return graceful offline/error response.
```

Suggested `.env` configuration:

```env
ENABLE_LLM_FALLBACK=true
LLM_ROUTER_PROVIDER=local,gemini,codex
LLM_GENERAL_PROVIDER=gemini,codex
LLM_RAG_PROVIDER=codex,gemini
LLM_KG_PROVIDER=gemini,codex
LLM_VISUAL_PROVIDER=gemini,codex
LLM_EVAL_PROVIDER=gemini,codex

GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
```

Add SQLite tables for optimization and monitoring:

```text
llm_cache
  id
  task
  prompt_hash
  schema_name
  response_json
  provider
  created_at

llm_call_log
  id
  task
  provider
  success
  latency_ms
  error_category
  cache_hit
  created_at
```

Advanced routing tests to add:

- Gemini fails, Codex fallback succeeds.
- Codex rate-limited, Gemini fallback succeeds.
- Invalid JSON triggers repair retry.
- Cache hit avoids provider call.
- Task maps to expected provider order.
- All providers fail and return graceful error.

### Structured Output Validation

- Pydantic for backend LLM output schemas.
- TypeScript types and optional Zod for frontend payload validation.
- Use JSON schema-like prompts and repair retries.
- Every LLM-generated artifact should validate before being saved:
  - concept tags
  - visual specs
  - knowledge graph
  - mastery evaluations
  - quiz/flashcard outputs later

### Visual Sandbox Rendering

Recommended first renderers:

- KaTeX for formula walkthroughs.
- Plotly.js for function plots and distributions.
- Three.js with predefined scene templates.
- `@react-three/fiber` for React-native Three.js components.
- HTML Canvas for simple 2D animations.

Suggested packages:

- `katex`
- `react-katex`
- `plotly.js`
- `react-plotly.js`
- `three`
- `@react-three/fiber`
- `@react-three/drei`
- `framer-motion`, optional for UI transitions

Safety rule:

- The LLM should output structured visualization specs, not arbitrary executable JavaScript.
- Three.js scenes should be generated from trusted templates such as `molecule`, `pendulum`, `orbit`, `anatomy-part`, `vector-space`, or `process-flow`.

### Knowledge Graph Rendering

Recommended libraries:

- React Flow: easiest for interactive node/edge UI.
- Cytoscape.js: strong graph visualization and graph algorithms.
- vis-network: quick network graph rendering.
- D3 force: flexible but more manual work.

Recommended MVP choice:

- React Flow for simplicity and React integration.

Can wait:

- custom force layout engine
- bouncy physics
- label-aware collision

### Mastery Map Visualization

Use:

- React Flow nodes with custom styling.
- CSS colors for mastery score levels.
- Simple progress bars for Memory, Comprehension, Structure, and Application.
- Optional small chart library later if needed.

Possible chart tools:

- Recharts
- Nivo
- Chart.js

MVP recommendation:

- Use plain CSS progress bars first.

### Background Jobs

Use a simple local jobs table first.

Jobs to track:

- PDF extraction
- concept spotting
- knowledge graph generation
- visual generation
- mastery evaluation
- embedding/indexing

Possible later tools:

- `p-queue` for local queue control.
- `bottleneck` for rate limiting.
- custom retry timers for Codex/OpenAI rate limits.

MVP recommendation:

- Store job status in SQLite and run simple async workers in FastAPI.
- Use background tasks or a lightweight internal worker first.

### Testing

TypeScript app:

- Vitest
- Testing Library for React components
- Playwright for end-to-end desktop/web flows later
- Zod schema tests

FastAPI backend:

- pytest
- httpx test client
- Pydantic schema tests

Recommended MVP tests:

- PDF validation
- schema validation
- knowledge graph sanitization
- mastery score calculation
- monotone clamping
- Codex error classification
- router/workflow selection

### Observability For Lab 4

Use after the core app works:

- Langfuse self-hosted with Docker Compose
- PostgreSQL container
- local Langfuse web server on `http://localhost:3000`

FastAPI integration:

- Langfuse Python SDK
- Manual trace/span/generation logging around agent calls

LangGraph compatibility prototype, if used:

- `langfuse.callback.CallbackHandler`

Next.js frontend integration:

- Usually keep Langfuse writes in FastAPI, not the browser.
- Frontend can send feedback events to FastAPI, then FastAPI logs scores to Langfuse.

Track:

- route taken
- document ID
- concept ID
- model/task name
- token/cost metadata when available
- errors
- feedback score
- mastery evaluation result

### Environment And Secrets

Do not commit:

- `.env`
- Codex credentials
- user PDFs
- local SQLite database
- generated private artifacts

Suggested `.gitignore` entries:

```gitignore
.env
node_modules/
dist/
build/
.next/
app.db
*.sqlite
documents/
user-data/
venv/
__pycache__/
.pytest_cache/
uploads/
*.db
```

### Suggested Initial Dependency List

For the Next.js frontend:

```text
next
react
react-dom
typescript
tailwindcss
shadcn/ui
zod
uuid
pdfjs-dist
reactflow
katex
react-katex
plotly.js
react-plotly.js
three
@react-three/fiber
@react-three/drei
framer-motion
vitest
@testing-library/react
playwright
```

For the FastAPI backend:

```text
fastapi
uvicorn
pydantic
python-multipart
pytest
httpx
python-dotenv
pypdf
pymupdf
chromadb
faiss-cpu
langchain
langchain-community
langchain-openai
langfuse
```

For a separate Lab 3 prototype only if required:

```text
langgraph
langchain
langchain-community
langchain-openai
chromadb
faiss-cpu
gradio
pytest
python-dotenv
pypdf
```

For Lab 4 observability:

```text
langfuse
docker
docker-compose
postgres
```

## MVP: Keep And Build First

### 1. PDF Ingestion And Quality Check

- Accept PDF uploads.
- Verify the document has machine-readable text.
- Reject or warn on image-only scans.
- Enforce a maximum of 150 pages.
- Extract text page-by-page.
- Store the original PDF locally.
- Store extracted page text in the local database.

### 2. Concept Spotting

- Detect up to 4 important visualizable concepts per page.
- Each concept tag should include:
  - concept label
  - short explanation
  - page number
  - category/type if useful
- Start with page-level concept pills instead of exact pixel-perfect overlays.
- Clicking a concept should open or generate a visual sandbox.

### 3. Visual Sandbox

- This is the main exciting feature and should stay in the MVP.
- Clicking a concept should generate a structured visualization spec.
- Do not allow the LLM to generate arbitrary executable JavaScript directly.
- The LLM should output structured JSON, then the app renders it using predefined templates.
- Start with 2 or 3 visualization types:
  - KaTeX formula walkthrough
  - Plotly/function graph
  - simple Three.js template or simple 2D Canvas animation
- Each visual should include:
  - title
  - explanation
  - source page reference
  - structured rendering data

Example visualization spec:

```json
{
  "type": "plotly",
  "title": "Normal Distribution",
  "description": "Shows how probability density changes around the mean.",
  "sourcePages": [7],
  "plot": {
    "xRange": [-4, 4],
    "function": "normal_pdf",
    "parameters": {
      "mean": 0,
      "std": 1
    }
  }
}
```

### 4. Scoped PDF Chat

- Provide a chat interface for asking questions about the uploaded PDF.
- Answers should be grounded in the PDF.
- Include page references in answers.
- For Lab 3 compatibility, implement a minimal retrieval layer:
  - chunk page text
  - embed chunks
  - store in Chroma, FAISS, or equivalent
  - retrieve relevant chunks for chat answers
- The RAG agent should answer only from retrieved PDF context.
- If the answer is not in the PDF, say that the document does not provide the information.

### 5. Simple Knowledge Graph

- Keep the Knowledge Graph as data plus simple visualization.
- Do not build the custom animated graph engine yet.
- Generate 6-25 main concepts from the PDF.
- Generate typed relationship edges.
- Save the graph locally as `kg.json` and/or in SQLite.
- Use a library for rendering, such as:
  - React Flow
  - Cytoscape.js
  - vis-network
  - D3 force layout
- Clicking a node should show:
  - concept label
  - summary
  - page references
  - related concepts
  - mastery scores if available

Knowledge Graph node schema:

```json
{
  "id": "circulatory-system",
  "label": "Circulatory System",
  "summary": "The circulatory system transports blood, oxygen, and nutrients throughout the body.",
  "pages": [2, 3, 5],
  "evaluation": {
    "memory": 0,
    "comprehension": 0,
    "structure": 0,
    "application": 0
  }
}
```

Knowledge Graph edge schema:

```json
{
  "source": "heart",
  "target": "circulatory-system",
  "type": "composition",
  "description": "The heart is a major component of the circulatory system."
}
```

Supported edge types:

- `prerequisite`
- `composition`
- `causal`
- `specialisation`
- `parallel`
- `contrast`

Sanitization rules:

- Remove edges with unknown node IDs.
- Remove self-loops.
- Deduplicate duplicate edges.
- Validate all node IDs are unique.

### 6. Lightweight Mastery Map

- Keep basic mastery fields on each concept node.
- Track four dimensions:
  - Memory
  - Comprehension
  - Structure
  - Application
- Use a single weighted score for display.

Mastery score formula:

```ts
export function masteryScore(e: KGEvaluation): number {
  return Math.round(
    e.memory * 0.25 +
    e.comprehension * 0.30 +
    e.structure * 0.20 +
    e.application * 0.25
  );
}
```

Color levels:

- Grey `#b6b6ba`: score `< 1`, unstarted/no evidence.
- Blue `#7e9bc8`: score `< 25`, familiar/early recall.
- Violet `#8b78d9`: score `< 50`, developing understanding.
- Light green `#4fae84`: score `< 75`, competent/can apply.
- Deep emerald `#16a06d`: score `>= 75`, mastered.

Keep for MVP:

- Store four-axis scores per concept.
- Calculate unified mastery score.
- Color graph nodes by mastery score.
- Show a node detail panel with four bars and recommendations.
- Update scores after explicit evaluation events.

### 7. Simple Mastery Evaluator Agent

- Implement the evaluator as a simple explicit action first.
- Input:
  - concept information
  - current baseline scores
  - recent student interaction
- Output:
  - new four-axis scores
  - brief reasoning
  - recommended next action
- Use strict JSON schema validation.
- Apply monotone clamping so demonstrated mastery never decreases.

Monotone clamp rule:

```ts
function clampMonotone(prev: KGEvaluation, next: KGEvaluation): KGEvaluation {
  return {
    memory: Math.max(prev.memory, Math.min(100, Math.max(0, Math.round(next.memory)))),
    comprehension: Math.max(prev.comprehension, Math.min(100, Math.max(0, Math.round(next.comprehension)))),
    structure: Math.max(prev.structure, Math.min(100, Math.max(0, Math.round(next.structure)))),
    application: Math.max(prev.application, Math.min(100, Math.max(0, Math.round(next.application)))),
  };
}
```

Important label:

- Treat scores as highest demonstrated mastery, not guaranteed current ability.

### 8. LLM Integration Through Codex CLI

- Use a Bring-Your-Own-Account model.
- The user authenticates locally with their own OpenAI/Codex account.
- First version can require Codex CLI to be installed locally.
- Later versions can bundle platform-specific Codex CLI binaries.
- Implement a thin FastAPI backend abstraction so agents do not depend directly on CLI details.

Suggested FastAPI interface:

```py
from pydantic import BaseModel

class LLMClient:
    async def run_json(self, task: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
        ...
```

Suggested implementation:

```py
class CodexCliClient(LLMClient):
    async def run_json(self, task: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
        # spawn Codex CLI
        # capture stdout/stderr
        # parse JSON
        # validate with Pydantic
        # retry once with repair prompt if invalid
        # classify errors
        ...
```

Keep now:

- `codex login` setup flow.
- Codex subprocess wrapper.
- Pydantic schema validation in FastAPI.
- Optional Zod validation in Next.js for UI payloads.
- JSON repair retry.
- Error classification.

Verify before depending on:

- persistent Codex threads
- `threadId` reuse
- `outputSchema` support
- stable machine-readable subprocess output

### 9. Local Database

- Use SQLite as the local source of truth.
- Recommended stack for FastAPI:
  - SQLite
  - SQLAlchemy or SQLModel
  - Alembic migrations, optional
  - direct `sqlite3` is acceptable for MVP
- Use filesystem for large files and SQLite for metadata/state.

Store in filesystem:

- original PDFs
- cached rendered pages, if needed
- large visual assets, if needed
- exported reports
- optional human-readable `kg.json`

Store in SQLite:

- documents
- pages
- concept tags
- knowledge graph nodes and edges
- visual sandbox specs
- chat messages
- mastery scores
- evaluation journal
- background jobs

Minimal MVP tables:

- `documents`
- `pages`
- `concepts`
- `concept_edges`
- `visual_specs`
- `chat_messages`
- `mastery_scores`
- `evaluation_journal`
- `jobs`

Example local app data layout:

```text
AppData/
  VisualPDFTutor/
    app.db
    documents/
      doc_123/
        original.pdf
        kg.json
        page-cache/
        visual-specs/
```

### 10. Lab 3 Compatibility, Separate From Product UI

Lab 3 expects a multi-agent LangGraph/RAG chatbot with Gradio. The product target is **not Gradio**. If the course strictly requires the original lab stack, keep a separate lab prototype or compatibility branch that includes:

- Router Agent
- PDF RAG Agent
- Concept Spotter Agent
- Visualization Planner Agent
- Knowledge Graph Builder Agent
- Gradio UI for lab compliance only
- Unit tests for routing
- README with setup and architecture

Minimum Lab 3 deliverables:

- working multi-agent graph
- private/local document data source
- semantic router
- at least 6 pytest tests or equivalent tests
- interactive UI
- documentation

Do not let the Gradio prototype drive the main product UX. The main product should remain Next.js + FastAPI.

### 11. Lab 4 Compatibility

Lab 4 expects local observability with Langfuse. Add after the MVP is working:

- `docker-compose.yml` for Langfuse and PostgreSQL
- local Langfuse credentials in `.env`
- tracing around agent calls
- route metadata
- token/cost metadata where available
- feedback scores
- screenshots/PDF export for submission

## Wait List: Build Later

### 1. Custom Animated Knowledge Graph Engine

Wait on:

- radial clustering
- custom force-directed relaxation
- label-aware collision detection
- bouncy physics
- drag inertia
- spring-back snapping
- constantly shifting graph animation

Use a graph rendering library first.

### 2. Pixel-Perfect PDF Overlays

Wait on:

- exact word-to-pixel coordinate alignment
- overlay tags directly on text runs
- complex PDF canvas synchronization

Start with page-level or paragraph-level concept tags.

### 3. Full Study Suite

Wait on:

- flashcards
- FSRS spaced repetition
- full quiz engine
- Feynman interviewer
- discrimination quizzes with plausible distractors

Add these after visual sandbox and scoped chat are stable.

### 4. Full Mastery Engine Scheduler

Wait on:

- `summariseForEvaluator`
- chat-exit batching
- one in-flight and one pending evaluation per document
- automatic rate-limit sleep and resume
- background coalesced scheduler
- forgetting/decay model

Start with explicit evaluation after a completed interaction.

### 5. Complex Dynamic Visual Generation

Wait on:

- arbitrary generated JavaScript
- fully dynamic Three.js scenes
- complex Canvas simulations
- execution crash self-repair loops
- external authoritative citation lookup

Start with safe structured specs and known rendering templates.

### 6. Desktop Packaging

Wait on:

- polished Electron/Tauri installer
- bundled Codex platform binaries
- auto-updates
- production signing/notarization

Build as a local web app or development Electron shell first.

### 7. Advanced Langfuse Observability

Wait on:

- complete cost dashboards
- detailed human feedback loops
- mastery evaluation analytics
- full production-style monitoring

Add after core functionality works.

## Suggested Implementation Order

1. Create a monorepo or two-folder structure: `frontend/` for Next.js and `backend/` for FastAPI.
2. Add FastAPI health endpoint and Next.js shell layout.
3. Add SQLite database schema and migrations or initialization scripts.
4. Implement PDF upload API, page count check, machine-readable text check, and text extraction.
5. Store original PDFs and extracted pages locally.
6. Implement retrieval/chunking for scoped PDF chat.
7. Implement Codex CLI wrapper in FastAPI with Pydantic validation and JSON repair retry.
8. Implement concept spotting for one uploaded PDF.
9. Render PDF text/pages and concept tags in Next.js.
10. Implement visual sandbox JSON specs and 1-2 renderers.
11. Add Three.js/React Three Fiber template renderer for one high-impact scene type.
12. Implement minimal scoped PDF chat with page references.
13. Implement Knowledge Graph generation and sanitization.
14. Render the graph using React Flow or Cytoscape.js.
15. Add four-axis mastery fields and color-coded nodes.
16. Add simple explicit mastery evaluation.
17. Add backend pytest tests and frontend Vitest tests.
18. Add README with local run commands for frontend and backend.
19. Add Langfuse integration if needed for Lab 4 or debugging.

## Suggested Agents

### Router Agent

Routes user actions to the right workflow:

- PDF question
- concept spotting
- visualization generation
- knowledge graph generation
- mastery evaluation
- general help

### PDF RAG Agent

Answers questions using retrieved PDF context only.

### Concept Spotter Agent

Finds up to 4 useful visual concepts per page.

### Visualization Planner Agent

Chooses the best visualization type and produces a structured spec.

### Knowledge Graph Builder Agent

Extracts 6-25 concepts and typed edges from the document.

### Mastery Evaluator Agent

Updates four-axis demonstrated mastery scores from recent student evidence.

## Suggested Test Coverage

- Reject image-only or empty PDFs.
- Reject PDFs over 150 pages.
- Extract page text correctly.
- Concept spotting returns no more than 4 tags per page.
- Knowledge Graph schema validates.
- Knowledge Graph sanitizer removes bad edges.
- Visual spec schema validates.
- Router sends PDF questions to RAG.
- Router sends concept clicks to visualization workflow.
- Mastery score formula calculates correctly.
- Monotone clamp prevents score decreases.
- Codex wrapper handles invalid JSON.
- Codex wrapper classifies auth/rate-limit errors.

## Open Questions To Decide Later

- Final packaged app shell: Electron or Tauri after the local Next.js/FastAPI app works?
- Exact Codex CLI programmatic interface available in current version.
- Whether persistent Codex threads are officially supported and stable.
- Whether Lab 3 submission must strictly use LangGraph and Gradio, separate from the product stack.
- Whether to add vector RAG immediately or start with keyword/BM25 retrieval.
- Which visualization types should be implemented first.

# TODO: Local Visual PDF Study Companion

## Project Direction

Build a local-first desktop study companion that transforms text-based PDFs into interactive learning experiences. The MVP focuses on PDF ingestion, concept spotting, visual sandboxes, scoped PDF chat, a simple knowledge graph, and a lightweight mastery map.

The project should run locally on the user's computer and use the user's own OpenAI Codex CLI account where possible. The app should not require a paid hosted backend or proxy user documents through a developer-owned server.

## Recommended Tools And Technologies

### App Shell

Preferred MVP choices:

- Electron: best fit for a local desktop app with Node.js filesystem access and subprocess control.
- Next.js inside Electron: good if building a rich React UI and local app experience.

Alternative choices:

- Tauri: lighter than Electron, but Rust integration can add complexity.
- Gradio: fastest for Lab 3 prototype, but less ideal for the final desktop product.

Recommended direction:

- Start with Next.js + Electron if the goal is the real desktop app.
- Use Gradio only if a quick Lab 3-compatible prototype is needed.

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

### Desktop And Local System Access

- Electron main process for:
  - local file access
  - PDF storage
  - SQLite database access
  - spawning Codex CLI subprocesses
  - background jobs
- Electron preload script for safe IPC between frontend and backend.
- Avoid exposing raw Node.js APIs directly to the renderer.

Suggested Electron packages:

- `electron`
- `electron-builder`, later for packaging
- `concurrently`, useful during development

### PDF Processing

Recommended tools:

- `pdfjs-dist`: rendering PDF pages and extracting text in a web/JS stack.
- `pdf-parse`: simpler text extraction in Node.js if layout is not needed.
- `pypdf`, `PyMuPDF`, or `pdfplumber`: good alternatives if building a Python service/prototype.

MVP recommendation:

- Use `pdf-parse` or `pdfjs-dist` for page-level text extraction.
- Do not implement exact word-coordinate overlay in the first version.

Future tools for pixel-level overlays:

- `pdfjs-dist` text layer APIs
- canvas rendering
- bounding-box extraction from PDF.js text items

### Local Database

Recommended stack:

- SQLite
- `better-sqlite3`
- `drizzle-orm`
- Drizzle migrations

Why:

- local-first
- simple backup
- works offline
- easy to ship with Electron
- enough for documents, concepts, chat history, mastery scores, and jobs

Optional alternatives:

- Prisma + SQLite: good developer experience, heavier runtime.
- SQL.js: browser-only SQLite, but less ideal for desktop persistence.
- LowDB: okay for prototypes, but weaker for relational state.

### Vector Search / RAG

For Lab 3 compatibility, include a minimal retrieval layer.

Options:

- Chroma: common LangChain choice, easy for Python Lab 3 implementation.
- FAISS: fast local vector search, common in Python.
- LanceDB: good local embedded vector database.
- SQLite vector extension: possible later, but adds setup complexity.

Recommended MVP options:

- If Python/LangGraph prototype: Chroma or FAISS.
- If TypeScript/Electron app: LanceDB or local JSON/SQLite retrieval first, then add embeddings.

Embedding options:

- OpenAI embeddings through user's account, if available.
- Local embeddings later through Ollama or Transformers.js.

### LLM And Codex Integration

Primary direction:

- OpenAI Codex CLI through the user's own account.
- Spawn CLI subprocesses from Electron main process.
- Wrap all model calls behind an internal `LLMClient` interface.

Important packages:

- Node.js `child_process` or `execa` for subprocess execution.
- `zod` for output validation.
- `uuid` for document IDs, trace IDs, and job IDs.

Recommended abstraction:

```ts
interface LLMClient {
  runJson<T>(task: string, prompt: string, schema: z.ZodSchema<T>): Promise<T>;
}
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

For the real TypeScript app:

- Implement lightweight internal workflows first.
- Use explicit functions/classes per agent.
- Keep schemas strict with Zod.

For Lab 3 compatibility:

- LangGraph
- LangChain
- Python
- Gradio

Recommended approach:

- Build the real product architecture in TypeScript/Electron.
- If the lab strictly requires LangGraph, create a Python prototype or compatibility layer with the same conceptual agents.

### Structured Output Validation

- `zod` for all TypeScript schemas.
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
- HTML Canvas for simple 2D animations.

Suggested packages:

- `katex`
- `react-katex`
- `plotly.js`
- `react-plotly.js`
- `three`
- `@react-three/fiber`, optional later
- `@react-three/drei`, optional later

Safety rule:

- The LLM should output structured visualization specs, not arbitrary executable JavaScript.

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

- Store job status in SQLite and run simple async workers in Electron main process.

### Testing

TypeScript app:

- Vitest
- Testing Library for React components
- Playwright for end-to-end desktop/web flows later
- Zod schema tests

Python Lab prototype:

- pytest

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

Python/LangGraph integration:

- `langfuse.callback.CallbackHandler`

TypeScript/Electron integration:

- Langfuse SDK, if compatible with the app runtime
- Otherwise log structured events locally and export screenshots/metrics for the lab

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
```

### Suggested Initial Dependency List

For the TypeScript/Electron app:

```text
electron
next
react
react-dom
typescript
tailwindcss
zod
better-sqlite3
drizzle-orm
uuid
execa
pdfjs-dist
reactflow
katex
react-katex
plotly.js
react-plotly.js
three
vitest
@testing-library/react
```

For the Python Lab 3 prototype if needed:

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
- Implement a thin internal abstraction so agents do not depend directly on CLI details.

Suggested interface:

```ts
interface LLMClient {
  runJson<T>(task: string, prompt: string, schema: z.ZodSchema<T>): Promise<T>;
}
```

Suggested implementation:

```ts
class CodexCliClient implements LLMClient {
  async runJson<T>(task: string, prompt: string, schema: z.ZodSchema<T>): Promise<T> {
    // spawn Codex CLI
    // capture stdout/stderr
    // parse JSON
    // validate with Zod
    // retry once with repair prompt if invalid
    // classify errors
  }
}
```

Keep now:

- `codex login` setup flow.
- Codex subprocess wrapper.
- Zod schema validation.
- JSON repair retry.
- Error classification.

Verify before depending on:

- persistent Codex threads
- `threadId` reuse
- `outputSchema` support
- stable machine-readable subprocess output

### 9. Local Database

- Use SQLite as the local source of truth.
- Recommended stack for Electron/TypeScript:
  - `better-sqlite3`
  - `drizzle-orm`
  - Drizzle migrations
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

### 10. Lab 3 Compatibility

Lab 3 expects a multi-agent LangGraph/RAG chatbot with Gradio. If this project is used for Lab 3, include:

- Router Agent
- PDF RAG Agent
- Concept Spotter Agent
- Visualization Planner Agent
- Knowledge Graph Builder Agent
- Gradio or web UI
- Unit tests for routing
- README with setup and architecture

Minimum Lab 3 deliverables:

- working multi-agent graph
- private/local document data source
- semantic router
- at least 6 pytest tests or equivalent tests
- interactive UI
- documentation

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

1. Create project skeleton.
2. Add SQLite database and migrations.
3. Implement PDF upload, page count check, and text extraction.
4. Store documents and extracted pages locally.
5. Implement Codex CLI wrapper with Zod validation.
6. Implement concept spotting for one uploaded PDF.
7. Render concept tags in the UI.
8. Implement visual sandbox JSON specs and 1-2 renderers.
9. Implement minimal RAG/scoped chat with page references.
10. Implement Knowledge Graph generation and sanitization.
11. Render the graph using a library.
12. Add four-axis mastery fields and color-coded nodes.
13. Add simple explicit mastery evaluation.
14. Add tests.
15. Add README.
16. Add Langfuse integration for Lab 4, if needed.

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

- Final app shell: Electron, Tauri, Next.js local app, or Gradio first?
- Exact Codex CLI programmatic interface available in current version.
- Whether persistent Codex threads are officially supported and stable.
- Whether Lab 3 submission must strictly use LangGraph and Python, or whether TypeScript/Electron is acceptable.
- Whether to add vector RAG immediately or only for Lab compatibility.
- Which visualization types should be implemented first.

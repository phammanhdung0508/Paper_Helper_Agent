# Lab 4 Observability Export Guide

This guide explains how to generate the required PDF containing screenshots of the local Langfuse dashboard, a complete LangGraph trace, and the concepts mastery scores table for your Lab 4 submission.

## Step 1: Start the Local Langfuse Observability Stack
Make sure you have Docker installed and running. Spin up the self-hosted local Langfuse server and PostgreSQL DB by running the following command in the project root:
```bash
docker-compose up -d
```

## Step 2: Configure Observability Credentials
1. Open your browser and go to `http://localhost:3000`.
2. Click **Sign Up** to create an admin account.
3. Once logged in, go to **Settings** and generate **API Credentials** (API Keys).
4. Copy these keys and configure them in your `.env` file (copied from `.env.template` if not already present):
   ```env
   OPENAI_API_KEY=your-openai-api-key
   LANGFUSE_PUBLIC_KEY=pk-lf-your-local-public-key
   LANGFUSE_SECRET_KEY=sk-lf-your-local-secret-key
   LANGFUSE_HOST=http://localhost:3000
   ```

## Step 3: Generate Traces in the Application
1. Start the main application:
   ```bash
   python main.py
   ```
2. Open the UI (typically at `http://127.0.0.1:7860`).
3. Ingest a document (e.g., `lab3.pdf` or `lab4.pdf`). This creates the concept graph and maps nodes in the database.
4. Go to **Scoped Chat** and send a few messages (e.g., one greeting query which routes to the **General Agent**, and one query about hybrid work policy which routes to the **RAG Agent**).
5. Click **👍 Yes** or **👎 No** to log some helpfulness feedback.
6. Submit a mastery assessment answer for one of the concept nodes.

## Step 4: Capture Required Screenshots
Go back to your Langfuse dashboard at `http://localhost:3000` and capture the following screenshots:

1. **Langfuse Dashboard**: Capture the overview dashboard showing the metrics, trace counts, and helpfulness scores.
2. **Complete LangGraph Trace**: Under **Traces**, find the trace corresponding to your RAG/General chat query. Click on it and expand the tree showing the LangGraph execution flow (e.g., `router` node executing and then conditional routing to `rag_agent`/`general_agent`). Make sure the metadata tags like `session_id`, `user_id`, and `route_taken` are clearly visible in the trace side panel.
3. **Mastery Scores Table**: Take a screenshot of the concepts table inside the application UI showing the updated Mastery levels (Memory, Comprehension, Structure, Application) after your evaluation submissions.

## Step 5: Export to PDF for Submission
Combine your screenshots into a single PDF document:

- **Option A (Browser / Google Docs)**: Paste the captured screenshots into a Google Doc, add description headings, and click **File > Download > PDF Document (.pdf)**.
- **Option B (Markdown to PDF)**: Paste screenshots into a markdown file and use a tool like VS Code's "Markdown PDF" extension or `pandoc` with `wkhtmltopdf` to compile it.
- **Option C (LibreOffice)**: Paste the images into a Writer document and select **File > Export As > Export as PDF**.

Save this compiled PDF as `observability_export.pdf` in your project root or submit it alongside `lab4.pdf` as required by your instructor.

# Healthcare AI Chatbot

A production-grade, high-performance healthcare chatbot built with **FastAPI**, **PostgreSQL 15**, **React (Vite + TypeScript)**, and **Nginx**. Features OpenAI Tool-Calling against verified medical knowledge bases (MedlinePlus API & WHO), real-time Server-Sent Events (SSE) streaming, collapsible Thinking/Reasoning badges, performance metrics tracking (TTFT, Verification Latency, Total Time), multi-session history persistence, and multi-layer guardrails (PII redaction, intent classification, input moderation, and LLM-as-a-Judge hallucination verification).

---

## Key Features

- **Tool-Augmented Medical Knowledge Architecture (RAG)**:
  - **`search_knowledge_base`**: Vector search over granular local passages using Google AI Studio Gemini Embeddings (`gemini-embedding-2-preview`).
  - **`search_medlineplus_api`**: Live search against the NIH / MedlinePlus Developer Web Services API (`wsearch.nlm.nih.gov`) returning verified topic guides and direct URL citations.
- **PostgreSQL 15 Session Storage**:
  - Connection pooling with `asyncpg`.
  - Native `JSONB` storage for citations, thinking logs (`status_logs`), and timing metrics (`metadata`).
  - Automated SQLite-to-PostgreSQL migration on container startup.
- **Collapsible Thinking & Reasoning Process**:
  - Streams real-time pipeline status events (safety check, tool calls, chunk retrieval count, LLM generation, Judge verification).
  - Captures and extracts model reasoning tokens (`delta.reasoning_content`, `<think>...</think>`).
  - Rendered with Markdown and collapsed by default.
  - Persists across page reloads and session history navigation.
- **Performance & Latency Tracking**:
  - Calculates and displays real-time metrics per message turn:
    - **TTFT**: Time-To-First-Token latency.
    - **Verified**: Judge LLM hallucination audit duration.
    - **Total**: End-to-end processing time.
- **Modern React (Vite + TypeScript) Frontend**:
  - Dark-mode glassmorphism design system.
  - Token-by-token streaming response.
  - Dynamic sidebar auto-titling and session management (delete, edit past messages).
  - Persistent single medical disclaimer footer.
- **Multi-Layer Guardrails & Observability**:
  - **PII Redaction**: Automatic redaction of sensitive user identifiers.
  - **Intent Classifier**: Local routing for emergency symptom redirection and diagnostic refusal.
  - **Input Moderation**: Async API safety checks.
  - **Judge LLM Hallucination Verification**: Post-generation entailment evaluation checking sentence claims against retrieved chunks before final response approval.
  - **Portkey Observability**: Header metadata injection for full request trace tracking.

---

## REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness/readiness container healthcheck. |
| `GET` | `/api/sessions` | List active chat sessions. |
| `POST` | `/api/session` | Create a new chat session record. |
| `PATCH` | `/api/session/{session_id}` | Rename or update session title. |
| `DELETE` | `/api/session/{session_id}` | Permanently delete a session and its message history. |
| `GET` | `/api/session/{session_id}/history` | Fetch complete message history array for session. |
| `POST` | `/api/chat` | Submit chat query and receive SSE event stream. |
| `POST` | `/api/chat/edit` | Edit a past message, truncate subsequent history, and stream new response. |

---

## Deployment Script

| Script | Command | Purpose |
|---|---|---|
| **Deploy** | `powershell -ExecutionPolicy Bypass -File .\deploy.ps1` | Commits, pushes to main, SSHs into remote host (HP-AIO), pulls latest code, and rebuilds containers. |

---

## Quickstart Guide

### 1. Environment Setup
Copy the template environment file to `.env` and populate your API credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
BASE_URL=https://your-llm-endpoint.com/v1
API_KEY=your_openai_or_portkey_api_key
MODEL_NAME=gpt-4o-mini

GUARDRAIL_BASE_URL=https://your-moderation-endpoint.com/v1
GUARDRAIL_API_KEY=your_moderation_api_key
GUARDRAIL_MODEL_NAME=mistral-moderation-latest

JUDGE_BASE_URL=https://your-llm-endpoint.com/v1
JUDGE_API_KEY=your_judge_api_key
JUDGE_MODEL_NAME=gpt-4o-mini

EMBEDDING_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
EMBEDDING_API_KEY=your_gemini_api_key
EMBEDDING_MODEL_NAME=gemini-embedding-2-preview

DATABASE_URL=postgresql://postgres:postgrespassword@db:5432/healthchatbot
```

### 2. Launch with Docker Compose
Start PostgreSQL, FastAPI backend, and Nginx/React frontend:

```bash
docker compose up --build -d
```

Access the application at `http://localhost:8000`.

---

## Automated Verification & Testing

To run the guardrail test suite:

```bash
cd backend
pytest tests/test_guardrails.py -v
```

---

## Disclaimer & Limitations

- **Informational Health Education Only**: Designed for general medical health Q&A; does not substitute for professional medical advice, diagnosis, or treatment.

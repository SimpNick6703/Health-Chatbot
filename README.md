# Healthcare AI Chatbot

A high-performance healthcare chatbot providing general health Q&A, OpenAI Tool-Calling (Function Calling) against verified public-domain medical knowledge bases (MedlinePlus & WHO), live MedlinePlus Developer Web Services API integration, multi-session sidebar navigation, streaming token responses, and multi-layer guardrails (PII redaction, intent classification, input moderation, and LLM-as-a-Judge hallucination verification).

*Shared for evaluation only, all rights reserved.*

---

## Features

- **Tool-Calling Architecture (Function Calling)**:
  - **`search_knowledge_base`**: Dynamic vector search over granular ~300-character local knowledge passages using Google AI Studio Gemini Embeddings (`gemini-embedding-2-preview`) in cosine distance space.
  - **`search_medlineplus_api`**: Live search against the official NIH / MedlinePlus Developer Web Services API (`https://wsearch.nlm.nih.gov/ws/query?db=healthTopics&term={term}`) returning structured government health topic guides and official URLs.
  - **Performance**: Selective tool invocation avoids prompt bloat and delivers fast Time-To-First-Token (TTFT). Direct queries (greetings, emergency refusals) bypass tools entirely for instant (< 1s) responses.
- **Multi-Session Sidebar Navigation & History**:
  - **Chat History**: Sidebar listing of past active conversations with full message history restore on tap.
  - **Auto-Titling & Renaming**: Automatically titles sessions based on query topic strings; supports manual title editing.
  - **Soft Archiving**: Deleting a session sets `is_archived = 1` for full auditability against Portkey observability traces.
  - **Lazy Session Creation**: Prevents accumulation of empty session records in SQLite.
- **Multi-Layer Safety Guardrails**:
  - **PII Redaction**: Regex-based redaction of emails, phone numbers, Aadhaar, PAN, IP addresses, and vehicle numbers.
  - **Deterministic Intent Classification**: Instant local redirection for emergency symptoms and refusal of diagnostic/prescription queries.
  - **Input Moderation**: Async API safety checks with domain-specific ignored categories (`health`, `pii`).
  - **Hallucination Verification**: Post-generation LLM-as-a-Judge NLI evaluation checking sentence entailment against retrieved tool snippets before final response approval.
- **Collapsed Hallucination Response UX**:
  - If flagged by the Hallucination Detector, the generated response is **not deleted**.
  - The UI renders a warning banner (`Warning: Potential hallucination or unverified claim detected.`) and wraps the response inside a collapsed container:
    `st.expander("View unverified response (Use with caution)")`
- **Granular Ingestion & Content Caching**:
  - SHA-256 content hash caching in SQLite (`knowledge_cache`) to avoid redundant re-embedding API calls and honor developer rate limits.
- **Portkey Observability**: Injects `user=session_id` and custom header `x-portkey-metadata: {"_user": "<session_id>"}` across all LLM, embedding, and moderation clients.
- **Streamlit Dark Theme Frontend**:
  - Token-by-token SSE streaming.
  - Live status indicator widget (`Querying knowledge tools...` -> `Factually verified`).
  - **Horizontal Flexbox Citations**: Side-by-side citation cards.
  - **Clickable MedlinePlus Hyperlinks**: Direct links to `medlineplus.gov` opening in a new tab.
  - **Exact Chunk Excerpts**: Local KB citations display the exact text snippet retrieved.
  - Persistent medical disclaimer banner.

---

## REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness/readiness container healthcheck. |
| `GET` | `/api/sessions` | List active chat sessions (excludes 0-message empty chats). |
| `POST` | `/api/session` | Create a new chat session record. |
| `PATCH` | `/api/session/{session_id}` | Rename or update session title. |
| `DELETE` | `/api/session/{session_id}` | Soft-delete / archive a session. |
| `GET` | `/api/session/{session_id}/history` | Fetch complete message history array for session. |
| `POST` | `/api/chat` | Submit chat query and receive SSE event stream. |

---

## Prerequisites

- **Docker** & **Docker Compose** installed.
- OpenAI-compatible LLM endpoint API key.
- Google AI Studio API key (for Gemini embeddings).

---

## Quickstart Guide

### 1. Environment Setup
Copy the template environment file to `.env` and populate your API credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
ENVIRONMENT=development
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
```

### 2. Launch with Docker Compose
Start both backend (FastAPI) and frontend (Streamlit) services:

```bash
docker compose up --build -d
```

Access the web interface at `http://localhost:8501`.

---

## Example Queries by Topic

1. **Common Symptoms**: *"What should I do to care for a fever at home, and when should I see a doctor?"*
2. **General Diseases**: *"What is asthma, what causes it, and how is it managed?"*
3. **Healthy Lifestyle**: *"What are recommended sleep hygiene guidelines for adults?"*
4. **Nutrition & Diet**: *"How much daily sodium intake is recommended for heart health?"*
5. **Preventive Healthcare**: *"How often should adults get blood pressure and cholesterol screenings?"*
6. **First Aid**: *"How should I treat a minor first-degree burn at home?"*

---

## Automated Verification & Testing

To run the guardrail and security red-team test suite:

```bash
cd backend
pytest tests/test_guardrails.py -v
```

---

## Known Limitations

- **General Health Info Only**: Designed exclusively for informational health education; cannot substitute for professional clinical medical advice.
- **Session Memory**: Context window is limited to the last 6 conversation turns (`SESSION_MAX_TURNS`).

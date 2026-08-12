# Healthcare AI Chatbot — RAG, Guardrails & Medical Knowledge System

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=flat&logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg?style=flat&logo=typescript)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1.svg?style=flat&logo=postgresql)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=flat&logo=docker)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Evaluation-blue.svg)](#disclaimer--limitations)

A production-grade, high-performance **Healthcare AI Chatbot** combining Retrieval-Augmented Generation (RAG), OpenAI Tool Calling (Function Calling) against verified medical knowledge bases (NIH / MedlinePlus Developer Web Services API & WHO), real-time Server-Sent Events (SSE) streaming, model reasoning extraction, performance metrics tracking, and multi-layer safety guardrails.

> [!IMPORTANT]
> **Medical Disclaimer**: This application is designed exclusively for general health education and informational Q&A. It cannot substitute for professional clinical medical advice, diagnosis, or treatment. Always seek the advice of a qualified healthcare provider.

---

## 🚀 Key Technical Highlights

### 1. Tool-Augmented Retrieval-Augmented Generation (RAG)
- **`search_knowledge_base`**: Dynamic vector similarity search over granular local passages (~300 chars) using Google AI Studio Gemini Embeddings (`gemini-embedding-2-preview`).
- **`search_medlineplus_api`**: Live search against the NIH / MedlinePlus Developer Web Services API (`wsearch.nlm.nih.gov`) returning structured topic summaries and official government URLs.
- **Connection Pooling**: Reusable `httpx.AsyncClient` session with strict 5-second timeouts for fast external API fallback.

### 2. PostgreSQL 15 Session Storage & Migration
- **High-Performance Async I/O**: Asynchronous connection pooling managed via `asyncpg`.
- **Native JSONB Schema**: Stores citations, status logs, and timing metrics in structured `JSONB` columns.

> [!NOTE]
> **Automated Migration**: On startup, the backend automatically detects legacy SQLite `sessions.db` databases and migrates existing sessions and message histories into PostgreSQL without data loss.

### 3. Collapsible Model Reasoning & Performance Metrics
- **Reasoning Token Extractor**: Captures model reasoning (`delta.reasoning_content` or `<think>...</think>` tags) and streams pipeline execution status (`safety_check`, `tool_search`, `tool_exec`, `auditing`, `verified`).
- **Real-Time Latency Metrics**: Measures and persists turn-by-turn performance stats:
  - **TTFT**: Time-To-First-Token latency.
  - **Verified**: Judge LLM hallucination evaluation duration.
  - **Total**: End-to-end processing pipeline execution time.

### 4. Modern React (Vite + TypeScript) Frontend & Nginx Proxy
- **Glassmorphism UI**: Dark-mode interface with zero default browser styles.
- **Dynamic Sidebar History**: Auto-titles sessions on stream start and updates dynamically without requiring page reloads.
- **Message Editing**: Allows editing past turns with atomic history rollback and streaming response re-generation.

### 5. Multi-Layer Guardrails & Observability
- **PII Redactor**: Fast local regex scanner redacting emails, phone numbers, Aadhaar, PAN, IP addresses, and vehicle numbers.
- **Intent Classifier**: Instant local routing for emergency symptom redirection (911 / 112) and diagnostic/prescription query refusal.
- **Input Moderation**: Async API safety checks with domain-specific ignored categories (`health`, `pii`).
- **Judge LLM Hallucination Verification**: Post-generation NLI entailment evaluation checking sentence claims against retrieved chunks before final response approval.
- **Portkey AI Gateway**: Injects metadata headers (`x-portkey-metadata`) for full trace logging and user session analytics.

---

## 🛠️ REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness and readiness container check with PostgreSQL `SELECT 1` ping. |
| `GET` | `/api/sessions` | List active, non-archived chat sessions. |
| `POST` | `/api/session` | Create a new chat session record. |
| `PATCH` | `/api/session/{session_id}` | Update session title. |
| `DELETE` | `/api/session/{session_id}` | Soft-delete / archive a session and its message history. |
| `GET` | `/api/session/{session_id}/history` | Fetch complete message turn history for session. |
| `POST` | `/api/chat` | Submit user query and receive SSE event stream. |
| `POST` | `/api/chat/edit` | Edit a past message turn, rollback history, and stream new response. |

---

## ⚙️ Quickstart & Deployment

### 1. Environment Configuration

> [!WARNING]
> Ensure you populate all required API keys in `.env` before building the Docker containers.

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Configure `.env`:
```env
# Main LLM Endpoint
BASE_URL=https://your-llm-endpoint.com/v1
API_KEY=your_openai_or_portkey_api_key
MODEL_NAME=gpt-4o-mini

# Guardrail & Moderation
GUARDRAIL_BASE_URL=https://your-moderation-endpoint.com/v1
GUARDRAIL_API_KEY=your_moderation_api_key
GUARDRAIL_MODEL_NAME=mistral-moderation-latest

# Judge LLM (Hallucination Detection)
JUDGE_BASE_URL=https://your-llm-endpoint.com/v1
JUDGE_API_KEY=your_judge_api_key
JUDGE_MODEL_NAME=gpt-4o-mini

# Embeddings (Google AI Studio)
EMBEDDING_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
EMBEDDING_API_KEY=your_gemini_api_key
EMBEDDING_MODEL_NAME=gemini-embedding-2-preview

# Database
DATABASE_URL=postgresql://postgres:postgrespassword@db:5432/healthchatbot
```

### 2. Launching with Docker Compose

Build and launch all services (PostgreSQL 15, FastAPI Backend, React/Nginx Frontend):

```bash
docker compose up --build -d
```

Access the unified web application at **`http://localhost:8000`**.

---

## 🧪 Security & Guardrail Verification

> [!TIP]
> Run the automated red-team test suite to verify PII redaction, emergency classification, and jailbreak resistance.

```bash
cd backend
pytest tests/test_guardrails.py -v
```

---

## 📜 Disclaimer & Limitations

- **Informational Health Education Only**: This system is designed solely for informational medical Q&A and general health education.
- **Emergency Situations**: In case of a medical emergency, immediately contact your local emergency service (e.g., 911 or 112).

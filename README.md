# Healthcare AI Chatbot

A high-performance healthcare chatbot providing general health Q&A, RAG grounding against verified public-domain medical knowledge bases (MedlinePlus & WHO), streaming token responses, and multi-layer guardrails (PII redaction, intent classification, input moderation, and LLM-as-a-Judge hallucination verification).

*Shared for evaluation only, all rights reserved.*

---

## Features

- **Multi-Layer Safety Guardrails**:
  - **PII Redaction**: Regex-based redaction of emails, phone numbers, Aadhaar, PAN, IP addresses, and vehicle numbers.
  - **Deterministic Intent Classification**: Instant local redirection for emergency symptoms and refusal of diagnostic/prescription queries.
  - **Input Moderation**: Async API safety checks with domain-specific ignored categories (`health`, `pii`).
  - **Hallucination Verification**: Post-generation LLM-as-a-Judge NLI evaluation checking sentence entailment against retrieved RAG chunks before final response approval.
- **RAG Grounding & Ingestion Caching**:
  - Embedded via Google AI Studio Gemini Embeddings (`gemini-embedding-2-preview`).
  - SHA-256 content hash caching in SQLite (`knowledge_cache`) to avoid redundant re-embedding API calls and honor developer rate limits.
- **Portkey Observability**: Injects `user=session_id` and custom header `x-portkey-metadata: {"_user": "<session_id>", "environment": "<ENVIRONMENT>"}` across all API clients.
- **Streamlit Frontend**:
  - Token-by-token SSE streaming.
  - Live status indicator widget (`Checking for hallucination...` -> Green tick `✔` or Red cross `✖`).
  - One-tap "New Chat" session purge button.
  - Persistent medical disclaimer banner.

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
2. **General Diseases**: *"What are common symptoms and risk factors of Type 2 Diabetes?"*
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

## Deployment via SSH

To redeploy on a remote server (`HP-AIO`), execute the included PowerShell deployment script:

```powershell
.\deploy.ps1
```

---

## Known Limitations

- **General Health Info Only**: Designed exclusively for informational health education; cannot substitute for professional clinical medical advice.
- **Session Memory**: Context window is limited to the last 6 conversation turns (`SESSION_MAX_TURNS`).

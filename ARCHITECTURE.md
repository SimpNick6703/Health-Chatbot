# System Architecture — Healthcare AI Chatbot

## Overview
The Healthcare AI Chatbot is built using a decoupled FastAPI backend microservice and a Streamlit interactive frontend, containerized via Docker Compose.

```mermaid
flowchart TD
    User([User Client]) <--> UI[Streamlit Frontend :8501]
    UI <-->|SSE Stream / REST| API[FastAPI Backend :8000]

    subgraph Backend Pipeline
        API --> PII[PII Detector]
        PII --> Intent[Intent Classifier]
        Intent --> Mod[Input Moderation API]
        Mod --> RAG[RAG Retrieval Engine]
        RAG --> LLM[LLM Generator]
        LLM --> Judge[Hallucination Detector Judge]
    end

    subgraph Data & Storage
        RAG <--> Chroma[(ChromaDB Vector Store)]
        RAG <--> SQLite[(SQLite Session & Hash Cache)]
        Judge <--> SQLite
    end

    subgraph External APIs
        Mod <-->|httpx| Mistral[Mistral Moderation API]
        RAG <-->|OpenAI SDK| Gemini[Gemini Embedding API]
        LLM <-->|AsyncOpenAI| OpenAI[OpenAI / Portkey Gateway]
        Judge <-->|AsyncOpenAI| OpenAI
    end
```

---

## Tech Stack Rationale

| Component | Technology | Rationale |
|---|---|---|
| **Backend Framework** | FastAPI (Python 3.12) | Asynchronous non-blocking architecture, native SSE streaming support, Pydantic validation. |
| **Frontend UI** | Streamlit | Lightweight, interactive Python UI with real-time SSE streaming and status widgets. |
| **Vector Store** | ChromaDB | Lightweight, persistent vector database supporting custom embedding functions. |
| **Embeddings** | Gemini Embeddings (`gemini-embedding-2-preview`) | High accuracy semantic representation via Google AI Studio OpenAI-compatible API. |
| **Database** | SQLite (`aiosqlite`) | Zero-config persistent store for session turn history and SHA-256 RAG ingestion hash caching. |
| **Containerization** | Docker Compose | Two-service orchestration (`backend` + `frontend`) with readiness healthcheck gating. |

---

## Data Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as Streamlit UI
    participant Backend as FastAPI Router
    participant Guard as PII & Intent Guardrails
    participant RAG as ChromaDB / SQLite
    participant LLM as Main LLM
    participant Judge as Judge LLM

    User->>Frontend: Enter query / Click sample prompt
    Frontend->>Backend: POST /api/chat (session_id, query)
    Backend->>Guard: Redact PII & Classify Intent
    alt Non-Safe Intent (Emergency / Diagnosis)
        Guard-->>Backend: Refusal / Redirect script
        Backend-->>Frontend: Stream refusal & Complete
    else Safe Intent
        Backend->>Guard: Check Input Moderation
        Backend->>RAG: Retrieve Top K Chunks (Gemini Embeddings)
        RAG-->>Backend: Return Context Chunks
        Backend->>LLM: Stream Chat Completion (with Portkey headers)
        LLM-->>Backend: Stream Token Chunks
        Backend-->>Frontend: SSE Token Chunks
        Backend->>Frontend: SSE Status: checking_hallucination
        Backend->>Judge: Evaluate Entailment (LLM-as-a-Judge)
        alt Hallucination Detected
            Judge-->>Backend: is_hallucinated = True
            Backend-->>Frontend: SSE Error (Hallucination detected, response discarded)
        else Factually Grounded
            Judge-->>Backend: is_hallucinated = False
            Backend-->>Frontend: SSE Status: verified
            Backend-->>Frontend: SSE Token: Disclaimer Footer
            Backend-->>Frontend: SSE Done (sources)
        end
    end
```

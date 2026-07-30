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
        Mod --> ToolRound[LLM Tool Selection Round]
        ToolRound -->|Tool Call Requested| Exec[Tool Execution Dispatcher]
        Exec --> RAG[ChromaDB Vector Search]
        Exec --> Medline[MedlinePlus Web Services API]
        ToolRound -->|Direct Stream| LLM[LLM Token Generator]
        Exec --> LLM
        LLM --> Judge[Hallucination Detector Judge]
    end

    subgraph Data & Storage
        RAG <--> Chroma[(ChromaDB Vector Store)]
        API <--> SQLite[(SQLite Sessions & Hash Cache)]
        Judge <--> SQLite
    end

    subgraph External APIs
        Mod <-->|httpx| Mistral[Mistral Moderation API]
        RAG <-->|OpenAI SDK| Gemini[Gemini Embedding API]
        Medline <-->|httpx| NLM[NIH MedlinePlus API]
        LLM <-->|AsyncOpenAI| OpenAI[OpenAI / Portkey Gateway]
        Judge <-->|AsyncOpenAI| OpenAI
    end
```

---

## Tech Stack Rationale

| Component | Technology | Rationale |
|---|---|---|
| **Backend Framework** | FastAPI (Python 3.12) | Asynchronous non-blocking architecture, native SSE streaming support, Pydantic validation. |
| **Frontend UI** | Streamlit | Lightweight, interactive Python UI with real-time SSE streaming, dark theme, and compact session history sidebar. |
| **Tool Architecture** | OpenAI Function Calling | Selective tool invocation (`search_knowledge_base` and `search_medlineplus_api`) preventing prompt context bloat and speeding up TTFT. |
| **Vector Store** | ChromaDB | Lightweight, persistent vector database supporting Gemini Embeddings in cosine distance space over granular ~300-char passages. |
| **Live Health API** | MedlinePlus Web Services API | Official NIH / NLM web service (`https://wsearch.nlm.nih.gov/ws/query`) providing live topic summaries and clickable government URLs. |
| **Database** | SQLite (`aiosqlite`) | Zero-config persistent store for session history, titles, soft-archiving (`is_archived = 1`), and SHA-256 RAG hash caching. |
| **Containerization** | Docker Compose | Two-service orchestration (`backend` + `frontend`) with readiness healthcheck gating. |

---

## Data Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as Streamlit UI
    participant Backend as FastAPI Router
    participant Guard as PII & Guardrails
    participant Tools as Tool Dispatcher
    participant LLM as Main LLM
    participant Judge as Judge LLM

    User->>Frontend: Enter query / Select sidebar chat session
    Frontend->>Backend: POST /api/chat (session_id, query)
    Backend->>Guard: Redact PII & Classify Intent
    alt Non-Safe Intent (Emergency / Diagnosis)
        Guard-->>Backend: Refusal / Redirect script
        Backend-->>Frontend: Stream refusal & Complete
    else Safe Intent
        Backend->>Guard: Check Input Moderation
        Backend->>LLM: Tool Selection Completion (HEALTHCARE_TOOLS)
        alt LLM Requests Tool Execution
            LLM-->>Backend: tool_calls (search_knowledge_base / search_medlineplus_api)
            Backend->>Frontend: SSE Status: executing_tools
            Backend->>Tools: Execute search_knowledge_base / search_medlineplus_api
            Tools-->>Backend: Return retrieved chunks & direct URLs
        end
        Backend->>LLM: Stream Chat Completion (with Tool Messages & Portkey headers)
        LLM-->>Backend: Stream Token Chunks
        Backend-->>Frontend: SSE Token Chunks
        Backend->>Frontend: SSE Status: checking_hallucination
        Backend->>Judge: Evaluate Sentence Entailment (LLM-as-a-Judge)
        alt Hallucination Detected
            Judge-->>Backend: is_hallucinated = True
            Backend-->>Frontend: SSE Error (is_hallucinated=True, raw_response, citations)
            Frontend-->>User: Render Collapsed Warning Expander (View unverified response)
        else Factually Grounded
            Judge-->>Backend: is_hallucinated = False
            Backend-->>Frontend: SSE Status: verified
            Backend-->>Frontend: SSE Token: Disclaimer Footer
            Backend-->>Frontend: SSE Done (sources, citations)
            Frontend-->>User: Render Verified Response + Horizontal Citations
        end
    end
```

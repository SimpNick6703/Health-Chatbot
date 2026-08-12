# System Architecture — Healthcare AI Chatbot

## Overview
The Healthcare AI Chatbot is built using a decoupled FastAPI backend microservice, a modern React (Vite + TypeScript) frontend served via an Nginx reverse proxy, and a PostgreSQL 15 relational database, containerized via Docker Compose.

```mermaid
flowchart TD
    User([User Client]) <--> Nginx[Nginx Reverse Proxy :8000]
    Nginx <-->|Static Web Assets| React[React + Vite Frontend]
    Nginx <-->|SSE Stream / REST| API[FastAPI Backend :8000]

    subgraph Backend Pipeline
        API --> PII[PII Detector]
        PII --> Intent[Intent Classifier]
        Intent --> Mod[Input Moderation API]
        Mod --> ToolRound[LLM Tool Selection Round]
        ToolRound -->|Tool Call Requested| Exec[Tool Execution Dispatcher]
        Exec --> RAG[ChromaDB Vector Search]
        Exec --> Medline[MedlinePlus Web Services API]
        ToolRound -->|Direct Stream| LLM[LLM Token & Reasoning Generator]
        Exec --> LLM
        LLM --> Think[Reasoning Extractor]
        LLM --> Judge[Hallucination Detector Judge]
        Judge --> Metrics[Latency Metrics Tracker]
    end

    subgraph Data & Storage
        RAG <--> Chroma[(ChromaDB Vector Store)]
        API <--> Postgres[(PostgreSQL 15 Sessions & JSONB Metadata)]
        Judge <--> Postgres
    end

    subgraph External APIs
        Mod <-->|httpx| Mistral[Mistral Moderation API]
        RAG <-->|OpenAI SDK| Gemini[Gemini Embedding API]
        Medline <-->|httpx AsyncClient| NLM[NIH MedlinePlus API]
        LLM <-->|AsyncOpenAI| OpenAI[OpenAI / Portkey Gateway]
        Judge <-->|AsyncOpenAI| OpenAI
    end
```

---

## Tech Stack Rationale

| Component | Technology | Rationale |
|---|---|---|
| **Backend Framework** | FastAPI (Python 3.12) | Asynchronous non-blocking architecture, native SSE streaming support, Pydantic validation. |
| **Frontend UI** | React 18 (Vite + TypeScript) | High-performance SPA with real-time SSE streaming, collapsible thinking badge, dynamic session sidebar, dark theme glassmorphism. |
| **Reverse Proxy** | Nginx (Alpine) | Handles single-port routing (:8000), static file serving, and reverse proxying to backend FastAPI service. |
| **Database** | PostgreSQL 15 | Persistent session management, connection pooling via `asyncpg`, native `JSONB` storage for citations, status logs, and timing metrics. |
| **Tool Architecture** | OpenAI Function Calling | Selective tool invocation (`search_knowledge_base` and `search_medlineplus_api`) preventing prompt context bloat and speeding up TTFT. |
| **Vector Database** | ChromaDB | Local embedding vector store providing cosine similarity search over granular knowledge passages. |
| **Observability** | Portkey AI Gateway | Header metadata injection (`x-portkey-metadata`) for full trace logging and user session analytics. |

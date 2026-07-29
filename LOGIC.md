# Query Processing & Safety Logic Documentation

This document explains the end-to-end query processing pipeline, multi-layer guardrail design, prompt engineering strategy, and security verification approach.

---

## 1. Multi-Layer Guardrail Architecture

```mermaid
flowchart LR
    A[Raw Query] --> B[1. PII Redactor]
    B --> C[2. Intent Classifier]
    C --> D[3. Input Moderation]
    D --> E[4. RAG & LLM Generation]
    E --> F[5. Hallucination Detector]
    F --> G[6. Final Verified Output]
```

### Stage 1: PII Redaction (`PIIDetector`)
- **Execution**: Local regex scanner running in `< 1ms`.
- **Patterns**:
  - Email addresses: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
  - Phone numbers (Indian & International format): `(\+91[\-\s]?)?[6-9]\d{9}`
  - Aadhaar card numbers: `\d{4}[\s\-]?\d{4}[\s\-]?\d{4}`
  - PAN card numbers: `[A-Z]{5}\d{4}[A-Z]`
  - IP addresses: `(?:\d{1,3}\.){3}\d{1,3}`
  - Vehicle numbers: `[A-Z]{2}[\s\-]?\d{2}[\s\-]?[A-Z]{1,2}[\s\-]?\d{4}`
- **Behavior**: Replaces matches with explicit markers (`[EMAIL_REDACTED]`, `[PHONE_REDACTED]`, etc.) before any external API or storage call.

### Stage 2: Intent Classifier (`IntentClassifier`)
- **Execution**: Fast deterministic keyword matching.
- **Categories**:
  - **Emergency**: Triggers immediate redirect to 911 / 112 emergency service instructions.
  - **Diagnosis & Prescription**: Triggers structured refusal directing user to a licensed healthcare practitioner.
  - **Safe**: Passes to moderation and RAG processing.

### Stage 3: Input Moderation (`InputModerator`)
- **Execution**: Async `httpx` POST to external moderation API (`mistral-moderation-latest`).
- **Ignored Categories**: `{"health", "pii"}` (since health queries naturally discuss body symptoms).
- **Enforced Categories**: `sexual`, `violence_and_threats`, `selfharm`, `hate_and_discrimination`, `dangerous`, `criminal`, `jailbreaking`.
- **Portkey Metadata**: Passes `x-portkey-metadata` header containing `_user` and `environment`.

### Stage 4: Hallucination Detector (`HallucinationDetector`)
- **Execution**: Post-generation LLM-as-a-Judge NLI entailment verification.
- **Prompt Logic**: Evaluates whether all sentences in the generated LLM response are factually supported by the retrieved RAG context passages.
- **Interruption Behavior**: If `is_hallucinated == True`, stream is aborted, tokens are discarded on the client, and an error message (`"Hallucination detected, response discarded..."`) is rendered.

---

## 2. Ingestion & Content Caching Logic

To satisfy developer web service guidelines (MedlinePlus / NLM) and prevent redundant API calls:
1. When starting up, `rag_manager.ingest_knowledge_files` computes the SHA-256 hash of each file in `backend/knowledge/`.
2. Hashing is compared against the SQLite `knowledge_cache` table.
3. If content hash matches, ingestion skips re-embedding.
4. If changed or new, content is split into ~400-token passages, embedded via `gemini-embedding-2-preview`, updated in ChromaDB, and stored in `knowledge_cache`.

---

## 3. Portkey Observability Integration

Across all backend components:
- `llm_client.py`: Chat completions pass `user=session_id` and header `x-portkey-metadata: {"_user": "<session_id>", "environment": "<ENVIRONMENT>"}`.
- `guardrails.py`: Moderation and Judge LLM requests include the same metadata headers.
- `rag.py`: Embedding requests include user and metadata headers.

---

## 4. Security & Red-Team Testing Strategy

The test suite in `backend/tests/test_guardrails.py` uses test payloads adapted from security test suites (`prompt_injection.json`, `jailbreak.json`, `data_exfiltration.json`, `harmful_content.json`).

Tests verify:
- Complete PII pattern redaction.
- Instant emergency and diagnostic refusal.
- System prompt non-leakage under adversarial jailbreak attempts.
- In-scope medical question accuracy without false positive refusals.

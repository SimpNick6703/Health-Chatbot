# Healthcare AI Chatbot — v2 Implementation Plan

Upgrade the v1 prototype into a production-grade (v2) system. This involves migrating to FastMCP orchestration, replacing Streamlit with a custom React frontend with Vision capabilities, and implementing a robust PostgreSQL database.

## User Review Required

> [!IMPORTANT]  
> Please review the phases below. Once you approve, I will automatically begin execution starting with Phase 0.

## Open Questions

None currently. (Testing and local link clarifications have been successfully incorporated).

## Proposed Changes

### Phase 0: v1 Remediation (Critical Bug Fixes)
Before implementing v2 features, we must fix the following identified bugs in the v1 codebase:
- **PII Persistence Leak:** `session_store.save_turn()` is currently saving the raw `user_message`. It must save `cleaned_text` (the redacted version) to adhere to privacy rules.
- **Fail-Closed Safety & Bounded Retries:** `InputModerator.check_moderation` and `HallucinationDetector.detect_hallucination` currently catch `Exception` and fail *open*. Change them to retry with backoff, and if they still fail, fail *closed* (block the message) using a bounded retry budget (e.g., max 2 retries).
- **Session Titling Bug:** Fix the race condition where new sessions are invisible in the sidebar. Ensure the row is created *before* auto-titling attempts to fetch it.
- **Emergency Classifier False Positives:** Bare keywords in `EMERGENCY_KEYWORDS` block valid first-aid queries. Refine the classifier to distinguish first-person emergencies from third-person educational questions.
- **RAG Configuration:** Wire up `RAG_SIMILARITY_THRESHOLD` and `RAG_TOP_K` from `config.py`.
- **Streaming Failure Handling:** Prevent internal streaming exception messages (e.g., `[Error generating...]`) from being saved to the DB as valid turns.
- **Hallucination Check Bypass:** Enforce `response_format={"type": "json_object"}` on the Judge LLM to prevent JSON parsing errors. Do not skip the hallucination check if `source_chunks` is empty.
- **Minor Tweaks:** Add a leading `\b` to the Indian phone regex, add explicit `source_type` on `RetrievedChunk`, use `safety_identifier` for OpenAI, and tighten CORS.

---

### Phase 1: FastMCP Orchestration Upgrade
Replace the plain Python router with an MCP-based architecture.
- **FastMCP:** Introduce FastMCP for tool-calling orchestration.
- **In-Process Transport:** FastMCP must be configured to run in-process (stdio/library) to guarantee the near-zero overhead latency.
- **Tools:** Wrap existing query capabilities (`search_knowledge_base`, `search_medlineplus_api`) as FastMCP tools. 

---

### Phase 2: React Frontend & Vision Input
Upgrade UI to a custom React app with vision support, while maintaining strict guardrails.
- **Frontend Design Constraint:** Use standard clean semantic HTML and UI best-practices (strict WCAG not required). Use the **Stitch MCP** server and follow the **`/anti-ui-slop`** workflow skill.
- **Vision Pipeline:** Users can upload **up to 5 images** at once. Images will be uploaded directly to the Multimodal LLM (no separate OCR). Images are not persisted in the database.
- **Image Persistence UX:** The UI will use browser memory to display thumbnails during the live session. Reloading the page renders a placeholder (`[Image removed for privacy]`).
- **Vision Failure Path:** Gracefully refuse the upload if the vision model times out.
- **UI Input Control & Cancellation:** Lock chat input while a request is processing. Add a visible "Cancel" button to abort an ongoing streaming request, triggering a backend `asyncio` task cancellation to prevent runaway costs.
- **Message Editing:** Allow users to edit their past messages. The edited message re-runs the full guardrail pipeline. Handled as a single atomic database transaction to prevent orphaned data.
- **Streaming & Judge UX:** If the Hallucination Judge fails *after* streaming completes, transition the visible response bubble into a collapsed warning state.
- **Local KB Citations:** When generating UI citations for the local knowledge base, the citation link must point to `https://github.com/SimpNick6703/Health-Chatbot/tree/main/backend/knowledge`.

---

### Phase 3: PostgreSQL Database & Schema Design
Implement robust persistent storage.
- **PostgreSQL Migration:** Migrate to a local PostgreSQL container.
- **Driver & Pooling:** Use the **`asyncpg`** driver and establish a connection pool. Rewrite SQLite specific syntax.
- **Metadata JSONB:** Add a `metadata` `JSONB` column to the `messages` table storing Mistral moderation categories, TTFT, and Time-to-Verified metrics.
- **Persist Citations:** Add a `citations` `JSONB` column directly to the `messages` table. 

---

### Phase 4: Expanded Security & Performance Tracking
Track accurate metrics and render them.
- **Metric Tracking & Display:** Track **TTFT** (Time-To-First-Token) and **Time-to-Verified** (when the hallucination judge completes). Save these metrics in Postgres and explicitly render them in the React UI below each assistant message.

## Verification Plan

### Automated Tests
- Run `pytest tests/test_guardrails.py -v` after each phase to ensure the comprehensive functional guardrail regression suite passes, validating that fail-closed moderation and intent classification are never bypassed.
*(Note: Load and penetration testing are explicitly omitted for this local/showcase phase, as free-tier rate limits make load testing impractical).*

### Manual Verification
- Deploy via `deploy.ps1` and verify image upload handling, request cancellation, and message editing in the React UI.
- Reload a past session to ensure citations and hover-quotes are correctly re-rendered from Postgres.

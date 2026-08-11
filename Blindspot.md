### Blindspot Check: Health Chatbot Project

**1. User Experience & Interaction Design (Beyond Basic UI)**

*   **PRD:** Mentions "intuitive and user-friendly interface," "chat history sidebar," and "responsive design."
*   **Implementation Plan:** "Chat UI component," "sidebar for history," "basic UI for resource recommendations."
*   **Blindspot:**
    *   **Detailed Interaction Flows:** Beyond basic chat, how do complex interactions work? E.g., multi-turn symptom checking, disambiguating user input, how "follow-up questions" from Claude are presented and managed, how resource recommendations are displayed and interacted with (e.g., filtering, saving).
        *   *Answer:* Multi-turn context is strictly limited to the last 6 turns to maintain focus. The flow is a standard conversational interface. Resource recommendations (like MedlinePlus links) are rendered dynamically as horizontal citation pills with clickable URLs. 
    *   **Error States and Feedback:** What happens when the MedlinePlus API fails or returns no results? How are Claude API errors handled? What feedback does the user get for invalid input, network issues, or during long processing times?
        *   *Answer:* MedlinePlus API failures are caught and ignored (failing gracefully), allowing the local ChromaDB RAG to answer if possible. Network/API errors during streaming render an explicit `*Error: Connection lost*` message. Long processing times use a live status widget (`⚡ Querying knowledge tools...`).
    *   **Empty States:** What does the UI look like for a new user with no chat history? What if no resources are found?
        *   *Answer:* The empty state displays a welcome message, a medical disclaimer banner, and a grid of "Sample Prompts" (e.g., "Fever Care", "Asthma Overview") to bootstrap the conversation.
    *   **Accessibility (A11y):** While "user-friendly" is mentioned, there's no explicit mention of accessibility standards (WCAG) or implementation considerations (keyboard navigation, screen reader support, color contrast).
        *   *Open Question for User:* **Is WCAG compliance a strict requirement for the v2 React frontend, or should we just prioritize standard semantic HTML best-practices for now?**
    *   **Internationalization/Localization (i18n/l10n):** Is the chatbot intended for a single language/locale or multiple? This impacts text, date/time formats, resource recommendations, and potentially API choices.
        *   *Answer:* English-language support only (as explicitly scoped in the PRD Assumptions).

**2. Claude API Integration & Prompt Engineering Details**

*   **PRD:** "Leverage Claude API," "AI-driven empathy," "CBT techniques," "synthesize information."
*   **Implementation Plan:** "AI interaction layer (integrate Claude API)."
*   **Blindspot:**
    *   **Specific Prompt Strategies:** How will the prompts be structured to ensure "AI-driven empathy" and "CBT techniques"? Are there specific system prompts, few-shot examples, or fine-tuning approaches planned?
        *   *Answer:* The stack has pivoted from Claude/CBT to a general OpenAI-compatible Multimodal LLM (like `gpt-4o-mini`). The prompt strategy focuses purely on informational synthesis and explicit refusal of diagnostics, rather than CBT therapy.
    *   **Context Window Management:** The PRD mentions "multi-session memory," but for long, evolving conversations within a single session, how will the context window be managed for Claude to avoid exceeding limits and maintain coherence? Summarization strategies? Retrieval-Augmented Generation (RAG)?
        *   *Answer:* The conversation memory is rigidly bounded to the last 6 turns (`SESSION_MAX_TURNS`) to prevent context overflow and hallucination drift.
    *   **Hallucination Mitigation:** While Claude is advanced, how will the system specifically address potential AI hallucinations, especially in a health context where accuracy is critical?
        *   *Answer:* We use an LLM-as-a-Judge pattern. A secondary fast LLM evaluates the generated response against retrieved chunks for NLI entailment. If it fails, the response is wrapped in a "Collapsed Warning UX" (`View unverified response`).
    *   **Moderation and Safety:** How will user inputs be moderated for inappropriate content or safety concerns before being sent to Claude? How will Claude's responses be evaluated for safety and appropriateness before being shown to the user?
        *   *Answer:* Multi-layer: 1) Local regex PII redaction. 2) Local deterministic Intent Classification for emergencies. 3) Mistral Moderation API for harmful content. All are fail-closed.
    *   **Performance Optimization:** How will latency for Claude API calls be managed to provide a smooth user experience? Caching? Streaming responses?
        *   *Answer:* Responses are streamed token-by-token via Server-Sent Events (SSE). Tool orchestration uses FastMCP running in-process to eliminate HTTP hop overhead.

**3. MedlinePlus API Specifics & Data Handling**

*   **PRD:** "Symptom checker leveraging MedlinePlus API."
*   **Implementation Plan:** "Integrate MedlinePlus API."
*   **Blindspot:**
    *   **API Response Parsing & Mapping:** What specific data structures does MedlinePlus return? How will this data be parsed, validated, and mapped into a user-friendly format for Claude to synthesize or present directly?
        *   *Answer:* MedlinePlus returns XML/JSON which is parsed into strict `CitationItem` schemas (`title`, `url`, `snippet`). These are fed to the LLM via tool messages and rendered in the UI as clickable cards.
    *   **Rate Limits & Error Handling:** What are the MedlinePlus API rate limits, and how will the application handle them? What error codes can be expected, and how will they be communicated to the user or handled internally?
        *   *Answer:* Rate limits are respected by failing gracefully on 429s/500s. The system relies on bounded retries, and if it fails, the LLM falls back to the local ChromaDB RAG.
    *   **Data Freshness:** How often is MedlinePlus data updated, and is there any caching strategy needed to balance data freshness with API usage limits?
        *   *Answer:* The live API inherently provides fresh data. Caching is only applied to local static Markdown ingestion (via SHA-256 hashes in SQLite/Postgres).

**4. Data Management & Storage Details**

*   **PRD:** "Multi-session memory (session storage)."
*   **Implementation Plan:** "MongoDB for session storage," "user authentication" (implied for personalized sessions).
*   **Blindspot:**
    *   **Data Model Schema:** A detailed MongoDB schema for sessions, user data, conversation history, and resource recommendations is not specified. How will conversation turns be stored? What metadata will be associated with each session?
        *   *Answer:* We are using PostgreSQL with `asyncpg`, not MongoDB. The schema utilizes relational tables (`sessions`, `messages`) and a `JSONB` column on messages to store `citations` and metrics (TTFT, Time-to-Verified, Moderation Scores).
    *   **Data Security & Privacy (HIPAA/GDPR):** Given this is a "Health Chatbot," data security and privacy are paramount. Is the system designed to be HIPAA compliant? GDPR compliant? What are the specific encryption, access control, and data retention policies?
        *   *Answer:* Raw PII is redacted *before* storage or API transmission. Uploaded images (Vision feature) are never persisted. It is not currently certified for HIPAA compliance as it is a local/showcase app.
    *   **Backup & Recovery:** What are the backup and disaster recovery strategies for the MongoDB database?
        *   *Answer:* Handled via standard Docker volume backups for the Postgres container. Not a primary focus for this local showcase.
    *   **Scalability:** While MongoDB is scalable, are there specific sharding or replication strategies considered for future growth?
        *   *Answer:* Postgres connection pooling (`asyncpg.create_pool`) handles concurrency. Sharding is out of scope for v2.

**5. Resource Recommendation System Details**

*   **PRD:** "Local resource recommendations (mental health clinics, support groups, emergency services)."
*   **Implementation Plan:** "Basic UI for resource recommendations."
*   **Blindspot:**
    *   **Resource Database/Source:** Where will these "local resources" come from? Is there a separate database for them? A third-party API? How will this data be curated, updated, and maintained?
        *   *Open Question for User:* **Do you actually want to curate a local database of physical clinics/support groups, or is providing authoritative online links via MedlinePlus sufficient for v2?**
    *   **Location-Based Services:** How will "local" be determined? Will the user provide location information? How will privacy concerns related to location data be handled?
        *   *Answer:* Location features are out of scope. Emergency intent routes users to general numbers (e.g., 911 / 112).
    *   **Recommendation Algorithm:** How will resources be matched to user needs? Is it simple keyword matching, or a more sophisticated system based on Claude's understanding of the conversation?
        *   *Answer:* MedlinePlus uses semantic/keyword matching via their API. Local knowledge uses Cosine Similarity (Gemini Embeddings).

**6. Deployment, Operations & Monitoring**

*   **PRD:** Not explicitly covered, but implied by a production system.
*   **Implementation Plan:** Not explicitly covered beyond "React/Next.js frontend," "Node.js/Express backend."
*   **Blindspot:**
    *   **Cloud Provider & Services:** AWS, GCP, Azure? Specific services (e.g., EC2, Lambda, EKS, App Engine, Azure Web Apps, etc.) for hosting the frontend, backend, and database.
        *   *Answer:* Deployed locally/on a dedicated VM (HP-AIO) via Docker Compose.
    *   **CI/CD Pipeline:** How will code be built, tested, and deployed automatically?
        *   *Answer:* Handled via the automated PowerShell script (`deploy.ps1`).
    *   **Logging & Monitoring:** How will application logs be collected and analyzed? What metrics will be monitored (API latency, error rates, user engagement, Claude token usage, MedlinePlus usage)? Alerting strategy?
        *   *Answer:* Observability is natively handled by Portkey. We inject `x-portkey-metadata` headers linking logs to `session_id`. We also track TTFT and Time-to-Verified natively in Postgres.
    *   **Cost Management:** Especially important for API usage (Claude API, MedlinePlus). How will costs be tracked and optimized?
        *   *Answer:* Request Cancellation from the UI aborts backend `asyncio` tasks to immediately halt token generation and prevent runaway API costs.
    *   **Security Scanning & Vulnerability Management:** Regular scans for dependencies, code vulnerabilities, and infrastructure security.
        *   *Answer:* Out of scope for this specific showcase phase.

**7. Testing Strategy**

*   **PRD:** "Accurate and personalized information."
*   **Implementation Plan:** Not explicitly detailed.
*   **Blindspot:**
    *   **Unit/Integration/E2E Testing:** What frameworks and coverage targets for each layer (frontend components, backend APIs, database interactions)?
        *   *Answer:* Backend guardrails and intent classifiers are heavily tested via `pytest` (e.g., `test_guardrails.py`).
    *   **AI/LLM Specific Testing:** How will the "accuracy" and "personalization" of Claude's responses be systematically tested? How to test for harmful or biased outputs? Regression testing for prompt changes?
        *   *Answer:* The test suite specifically injects adversarial jailbreaks, PII arrays, and edge-case emergency prompts to ensure fail-closed logic holds.
    *   **Performance Testing:** Load testing for scalability.
        *   *Open Question for User:* **Do you need formal Load/Performance Testing (e.g., locust/k6) or Penetration Testing for v2, or is passing the guardrail regression suite sufficient?**
    *   **Security Testing:** Penetration testing, vulnerability scanning.
        *   *Answer:* (See above question).

---

**Final Clarifications (Resolved):**
1. **Accessibility (WCAG):** Strict compliance is not required for v2; the focus will be on standard semantic HTML and clean UI best-practices.
2. **Resource Database:** No custom local database of clinics will be curated. MedlinePlus authoritative links will be used. For local knowledge base citations, the UI will link to `https://github.com/SimpNick6703/Health-Chatbot/tree/main/backend/knowledge`.
3. **Performance & Security Testing:** Formal load and penetration testing are deferred. Passing the functional guardrail regression suite is considered sufficient for this local/showcase release.
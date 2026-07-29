"""Query processing router pipeline orchestrating guardrails, RAG retrieval, LLM streaming, and SSE event generation."""

import os
import json
import logging
from typing import List, Dict, Any, AsyncGenerator

from config import settings
from guardrails import pii_detector, intent_classifier, input_moderator, hallucination_detector
from rag import rag_manager
from llm_client import llm_client
from session import session_store

logger = logging.getLogger(__name__)

# Load system prompt at startup
SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "system.md")
SYSTEM_PROMPT_CONTENT: str = ""
if os.path.exists(SYSTEM_PROMPT_PATH):
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT_CONTENT = f.read()


def format_messages(
    system_prompt: str,
    history: List[Dict[str, str]],
    query: str,
    chunks: List[Any]
) -> List[Dict[str, str]]:
    """Format prompt messages array for LLM completion API.

    Args:
        system_prompt: System role prompt text.
        history: Conversation history list of dicts.
        query: Current user query text.
        chunks: Retrieved RAG context chunks.

    Returns:
        Formatted list of message dictionaries.
    """
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Append prior conversation turn history
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Construct user message with context chunks if available
    if chunks:
        context_str = "\n\n".join([
            f"[Source: {c.source}]\n{c.content}" for c in chunks
        ])
        user_content = (
            f"Context Chunks:\n{context_str}\n\n"
            f"User Question: {query}"
        )
    else:
        user_content = (
            f"Context Chunks: None available in knowledge base.\n\n"
            f"User Question: {query}"
        )

    messages.append({"role": "user", "content": user_content})
    return messages


async def process_query(session_id: str, user_message: str) -> AsyncGenerator[Dict[str, str], None]:
    """Execute main query processing pipeline and yield SSE event dictionary objects.

    Args:
        session_id: Active session identifier.
        user_message: Raw user query text.

    Yields:
        Dictionary objects representing SSE events (event, data).
    """
    # 1. PII Redaction
    cleaned_text, had_pii, pii_details = pii_detector.detect_and_redact(user_message)
    if had_pii:
        logger.info(f"Session {session_id}: PII detected and redacted.")

    # 2. Intent Classification
    intent = intent_classifier.classify(cleaned_text)
    logger.info(f"Session {session_id}: Intent classified as '{intent.category}'.")

    if intent.category != "safe" and intent.response:
        yield {"event": "token", "data": json.dumps({"token": intent.response})}
        yield {"event": "done", "data": json.dumps({"sources": []})}
        await session_store.save_turn(
            session_id=session_id,
            user_msg=user_message,
            assistant_msg=intent.response,
            intent=intent.category,
            flagged=True
        )
        return

    # 3. Input Moderation Check
    mod_result = await input_moderator.check_moderation(cleaned_text, session_id)
    if mod_result.blocked:
        logger.warning(f"Session {session_id}: Input blocked by moderation.")
        refusal = input_moderator.MODERATION_REFUSAL_RESPONSE
        yield {"event": "token", "data": json.dumps({"token": refusal})}
        yield {"event": "done", "data": json.dumps({"sources": []})}
        await session_store.save_turn(
            session_id=session_id,
            user_msg=user_message,
            assistant_msg=refusal,
            intent="moderated",
            flagged=True
        )
        return

    # 4. RAG Retrieval
    chunks = await rag_manager.retrieve(cleaned_text, session_id, top_k=settings.RAG_TOP_K)
    logger.info(f"Session {session_id}: Retrieved {len(chunks)} RAG chunks.")

    # 5. Build Conversation Context
    history = await session_store.get_history(session_id, limit=settings.SESSION_MAX_TURNS)
    messages = format_messages(SYSTEM_PROMPT_CONTENT, history, cleaned_text, chunks)

    # 6. Stream LLM Response
    collected_response: str = ""
    async for token in llm_client.generate_stream(messages, session_id):
        collected_response += token
        yield {"event": "token", "data": json.dumps({"token": token})}

    # 7. Hallucination Detection Verification Stage
    yield {"event": "status", "data": json.dumps({"stage": "checking_hallucination"})}

    chunk_texts = [c.content for c in chunks]
    is_hallucinated = await hallucination_detector.detect_hallucination(
        response_text=collected_response,
        source_chunks=chunk_texts,
        session_id=session_id
    )

    if is_hallucinated:
        logger.warning(f"Session {session_id}: Hallucination detected. Interrupting response.")
        error_msg = "Hallucination detected, response discarded. Please try again or ask something else."
        sources = list(set(c.source for c in chunks))
        await session_store.save_turn(
            session_id=session_id,
            user_msg=user_message,
            assistant_msg=error_msg,
            intent="safe",
            sources=sources,
            had_pii=had_pii,
            is_hallucinated=True,
            flagged=True
        )
        yield {"event": "error", "data": json.dumps({"type": "hallucination", "message": error_msg})}
        return

    # 8. Verification Complete
    yield {"event": "status", "data": json.dumps({"stage": "verified"})}

    # 9. Append Standard Disclaimer
    disclaimer = "\n\n*This is for informational purposes only. For medical advice or diagnosis, consult a professional.*"
    yield {"event": "token", "data": json.dumps({"token": disclaimer})}

    # 10. Persist Turn & Send Done Event
    final_answer = collected_response + disclaimer
    sources = list(set(c.source for c in chunks))
    await session_store.save_turn(
        session_id=session_id,
        user_msg=user_message,
        assistant_msg=final_answer,
        intent="safe",
        sources=sources,
        had_pii=had_pii,
        is_hallucinated=False,
        flagged=False
    )
    yield {"event": "done", "data": json.dumps({"sources": sources})}

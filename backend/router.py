import os
import json
import time
import logging
import asyncio
from typing import List, Dict, Any, AsyncGenerator, Optional

from config import settings
from guardrails import pii_detector, intent_classifier, input_moderator, hallucination_detector
from tools import get_openai_tools, execute_tool_call
from llm_client import llm_client
from session import session_store
from models import CitationItem, RetrievedChunk

logger = logging.getLogger(__name__)

# Load system prompt at startup
SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "system.md")
SYSTEM_PROMPT_CONTENT: str = ""
if os.path.exists(SYSTEM_PROMPT_PATH):
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT_CONTENT = f.read()


def format_system_messages(
    system_prompt: str,
    history: List[Dict[str, Any]],
    query: str,
    images: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Format base prompt messages array for LLM completion API.

    Args:
        system_prompt: System role prompt text.
        history: Conversation history list of dicts.
        query: Current user query text.

    Returns:
        Formatted list of message dictionaries.
    """
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    if not images:
        messages.append({"role": "user", "content": query})
    else:
        content_array = [{"type": "text", "text": query}]
        for img_data in images[:5]:
            content_array.append({
                "type": "image_url",
                "image_url": {"url": img_data}
            })
        messages.append({"role": "user", "content": content_array})

    return messages


async def process_query(
    session_id: str, 
    user_message: str, 
    images: Optional[List[str]] = None
) -> AsyncGenerator[Dict[str, str], None]:
    """Execute tool-augmented query pipeline and yield SSE event dictionary objects.

    Args:
        session_id: Active session identifier.
        user_message: Raw user query text.

    Yields:
        Dictionary objects representing SSE events (event, data).
    """
    t_start = time.perf_counter()
    first_token_time: Optional[float] = None

    # 0. Auto-title session if default
    try:
        sess_info = await session_store.get_session(session_id)
        is_new = not sess_info
        is_default_title = sess_info and (not sess_info.get("title") or sess_info.get("title") == "New Chat")
        
        if is_new or is_default_title:
            auto_title = user_message.strip()[:35] + ("..." if len(user_message.strip()) > 35 else "")
            if is_new:
                await session_store.create_session(session_id, title=auto_title)
            else:
                await session_store.update_session_title(session_id, auto_title)
    except Exception as exc:
        logger.error(f"Auto-titling failed for session {session_id}: {exc}")

    status_logs: List[str] = []

    # 1. PII Redaction & Moderation
    s1 = "Checking input safety and moderation rules..."
    status_logs.append(s1)
    yield {"event": "status", "data": json.dumps({"stage": "safety_check", "label": s1})}
    cleaned_text, had_pii, pii_details = pii_detector.detect_and_redact(user_message)
    if had_pii:
        logger.info(f"Session {session_id}: PII detected and redacted.")

    # 2. Intent Classification
    intent = intent_classifier.classify(cleaned_text)
    logger.info(f"Session {session_id}: Intent classified as '{intent.category}'.")

    if intent.category != "safe" and intent.response:
        yield {"event": "token", "data": json.dumps({"token": intent.response})}
        yield {"event": "done", "data": json.dumps({"sources": [], "citations": []})}
        await session_store.save_turn(
            session_id=session_id,
            user_msg=cleaned_text,
            assistant_msg=intent.response,
            intent=intent.category,
            status_logs=status_logs,
            flagged=True
        )
        return

    # 3. Input Moderation Check
    logger.info(f"Session {session_id}: Starting input moderation check.")
    mod_result = await input_moderator.check_moderation(cleaned_text, session_id)
    logger.info(f"Session {session_id}: Input moderation check finished. Blocked={mod_result.blocked}")
    if mod_result.blocked:
        logger.warning(f"Session {session_id}: Input blocked by moderation.")
        refusal = input_moderator.MODERATION_REFUSAL_RESPONSE
        yield {"event": "token", "data": json.dumps({"token": refusal})}
        yield {"event": "done", "data": json.dumps({"sources": [], "citations": []})}
        await session_store.save_turn(
            session_id=session_id,
            user_msg=cleaned_text,
            assistant_msg=refusal,
            intent="moderated",
            status_logs=status_logs,
            flagged=True
        )
        return

    # 4. Build Conversation Context & Tool Calling Round
    logger.info(f"Session {session_id}: Fetching history and building messages.")
    history = await session_store.get_history(session_id, limit=settings.SESSION_MAX_TURNS)
    messages = format_system_messages(SYSTEM_PROMPT_CONTENT, history, cleaned_text, images)

    s2 = "Searching health knowledge resources..."
    status_logs.append(s2)
    yield {"event": "status", "data": json.dumps({"stage": "tool_search", "label": s2})}
    tool_message = await llm_client.generate_tool_completion(messages, await get_openai_tools(), session_id)
    citations: List[CitationItem] = []
    tool_chunks: List[RetrievedChunk] = []

    if tool_message and getattr(tool_message, "tool_calls", None):
        tool_msg_dict = {
            "role": "assistant",
            "content": tool_message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in tool_message.tool_calls
            ]
        }
        messages.append(tool_msg_dict)

        for tc in tool_message.tool_calls:
            tool_name = tc.function.name
            readable_tool = "MedlinePlus API" if "medlineplus" in tool_name else "local knowledge base"
            s_exec = f"Executing search query on {readable_tool}..."
            status_logs.append(s_exec)
            yield {"event": "status", "data": json.dumps({"stage": "tool_exec", "label": s_exec})}
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}

            output_text, retrieved = await execute_tool_call(tool_name, args, session_id)
            tool_chunks.extend(retrieved)

            if retrieved:
                s_ret = f"Retrieved {len(retrieved)} verified context chunks."
                status_logs.append(s_ret)

            for chunk in retrieved:
                source_type = chunk.source_type
                title = chunk.heading or chunk.source
                snippet = chunk.snippet_text or chunk.content[:200]
                citations.append(CitationItem(
                    title=title,
                    source_type=source_type,
                    url=chunk.url,
                    snippet=snippet
                ))

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": output_text
            })

    # 5. Stream Final LLM Token Response
    s_gen = "Generating response..."
    status_logs.append(s_gen)
    yield {"event": "status", "data": json.dumps({"stage": "generating", "label": s_gen})}
    collected_response: str = ""
    try:
        async for token in llm_client.generate_stream(messages, session_id):
            if first_token_time is None:
                first_token_time = time.perf_counter()
            collected_response += token
            yield {"event": "token", "data": json.dumps({"token": token})}
    except asyncio.CancelledError:
        logger.info(f"Session {session_id}: Stream generation cancelled by client.")
        return
    except Exception as exc:
        logger.error(f"LLM streaming request failed: {exc}")
        if images:
            yield {"event": "error", "data": json.dumps({"message": "Unable to process uploaded images. Please try again."})}
        else:
            yield {"event": "error", "data": json.dumps({"message": "Connection lost or streaming error."})}
        return

    ttft_ms = int((first_token_time - t_start) * 1000) if first_token_time else 0

    # 6. Hallucination Detection Verification Stage
    s_audit = "Auditing answer quality with Judge LLM..."
    status_logs.append(s_audit)
    yield {"event": "status", "data": json.dumps({"stage": "auditing", "label": s_audit})}

    t_verify_start = time.perf_counter()
    chunk_texts = [c.content for c in tool_chunks]
    is_hallucinated = await hallucination_detector.detect_hallucination(
        response_text=collected_response,
        source_chunks=chunk_texts,
        session_id=session_id
    )
    t_verify_end = time.perf_counter()
    verification_ms = int((t_verify_end - t_verify_start) * 1000)

    total_ms = int((time.perf_counter() - t_start) * 1000)
    metrics = {
        "ttft_ms": ttft_ms,
        "verification_ms": verification_ms,
        "total_ms": total_ms
    }

    citations_payload = [c.model_dump() for c in citations]
    sources_payload = list(set(c.title for c in citations))

    if is_hallucinated:
        logger.warning(f"Session {session_id}: Hallucination detected.")
        warn_msg = "Potential hallucination or unverified claim detected."
        await session_store.save_turn(
            session_id=session_id,
            user_msg=cleaned_text,
            assistant_msg=collected_response,
            intent="safe",
            sources=citations_payload,
            status_logs=status_logs,
            metadata=metrics,
            had_pii=had_pii,
            is_hallucinated=True,
            flagged=True
        )
        yield {
            "event": "error",
            "data": json.dumps({
                "type": "hallucination",
                "is_hallucinated": True,
                "message": warn_msg,
                "raw_response": collected_response,
                "citations": citations_payload,
                "metrics": metrics
            })
        }
        return

    s_ver = "Response verified."
    status_logs.append(s_ver)
    yield {"event": "status", "data": json.dumps({"stage": "verified", "label": s_ver})}

    # 8. Persist Turn & Yield Done Event
    await session_store.save_turn(
        session_id=session_id,
        user_msg=cleaned_text,
        assistant_msg=collected_response,
        intent="safe",
        sources=citations_payload,
        status_logs=status_logs,
        metadata=metrics,
        had_pii=had_pii,
        is_hallucinated=False,
        flagged=False
    )
    yield {
        "event": "done",
        "data": json.dumps({
            "sources": sources_payload,
            "citations": citations_payload,
            "metrics": metrics
        })
    }

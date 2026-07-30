"""Streamlit frontend user interface for Healthcare AI Chatbot."""

import os
import json
import logging
import streamlit as st
import httpx
from httpx_sse import connect_sse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("frontend")

BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

# Page Config
st.set_page_config(
    page_title="Healthcare AI Assistant",
    page_icon="🏥",
    layout="wide"
)

# Custom CSS styling for dark theme presentation
st.markdown("""
<style>
    .disclaimer-banner {
        background-color: rgba(245, 158, 11, 0.12);
        border-left: 4px solid #f59e0b;
        padding: 12px 16px;
        border-radius: 6px;
        color: #fef08a;
        font-weight: 500;
        margin-bottom: 20px;
    }
    .source-tag {
        display: inline-block;
        background-color: #0369a1;
        color: #e0f2fe;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.82em;
        font-weight: 500;
        margin-right: 6px;
    }
</style>
""", unsafe_allow_html=True)


def get_new_session_id() -> str:
    """Request a new session ID from backend API.

    Returns:
        Session ID string or fallback local UUID string.
    """
    try:
        resp = httpx.post(f"{BACKEND_URL}/api/session", timeout=5.0)
        if resp.status_code == 201:
            return resp.json()["session_id"]
    except Exception as exc:
        logger.error(f"Failed to fetch session ID from backend: {exc}")

    import uuid
    return str(uuid.uuid4())


def delete_remote_session(session_id: str) -> None:
    """Send request to backend to purge session history.

    Args:
        session_id: Session ID to delete.
    """
    try:
        httpx.delete(f"{BACKEND_URL}/api/session/{session_id}", timeout=5.0)
    except Exception as exc:
        logger.error(f"Failed to delete remote session {session_id}: {exc}")


# Initialize Session State
if "session_id" not in st.session_state:
    st.session_state.session_id = get_new_session_id()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

# Sidebar UI
with st.sidebar:
    st.title("🏥 Healthcare AI")
    st.caption("Grounded Health Assistant & Guardrail System")

    st.markdown("---")

    if st.button("➕ Start New Chat", use_container_width=True):
        if st.session_state.session_id:
            delete_remote_session(st.session_state.session_id)
        st.session_state.session_id = get_new_session_id()
        st.session_state.messages = []
        st.session_state.pending_prompt = None
        st.rerun()

    st.markdown("### Sample Prompts")
    st.caption("Tap a button below for instant quick queries:")

    sample_prompts = {
        "🤒 Symptoms": "What should I do to care for a fever and when should I see a doctor?",
        "🩺 Conditions": "What are the common symptoms and risk factors of Type 2 Diabetes?",
        "🏃 Lifestyle": "What are the recommended sleep hygiene guidelines for adults?",
        "🥗 Nutrition": "How much sodium per day is recommended for heart health?",
        "💉 Prevention": "How often should adults get blood pressure and cholesterol screenings?",
        "🩹 First Aid": "How should I treat a minor first-degree burn at home?"
    }

    for label, prompt in sample_prompts.items():
        if st.button(label, use_container_width=True):
            st.session_state.pending_prompt = prompt

    st.markdown("---")
    st.caption(f"**Session ID:** `{st.session_state.session_id[:8]}...`")


# Main UI Header
st.title("Healthcare Information Assistant")

# Persistent Medical Disclaimer Banner
st.markdown(
    '<div class="disclaimer-banner">'
    '⚠️ <strong>Notice:</strong> This is for informational purposes only. For medical advice or diagnosis, consult a professional.'
    '</div>',
    unsafe_allow_html=True
)

# Render Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "sources" in msg and msg["sources"]:
            with st.expander("📚 Knowledge Sources"):
                for src in msg["sources"]:
                    st.markdown(f'<span class="source-tag">📄 {src}</span>', unsafe_allow_html=True)


# Determine prompt input (either typed or clicked from sidebar preset)
user_prompt = st.chat_input("Ask a general health question...")
if st.session_state.pending_prompt:
    user_prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None

if user_prompt:
    # Append user message to UI state
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # Assistant Response Placeholder
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        status_placeholder = st.empty()

        full_response: str = ""
        sources_list: list = []
        is_error: bool = False
        error_message: str = ""

        payload = {
            "session_id": st.session_state.session_id,
            "message": user_prompt
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                with connect_sse(
                    client, "POST", f"{BACKEND_URL}/api/chat", json=payload
                ) as event_source:
                    for sse in event_source.iter_sse():
                        event_type = sse.event
                        data = json.loads(sse.data) if sse.data else {}

                        if event_type == "token":
                            token = data.get("token", "")
                            full_response += token
                            message_placeholder.markdown(full_response + "▌")

                        elif event_type == "status":
                            stage = data.get("stage", "")
                            if stage == "checking_hallucination":
                                status_placeholder.info("🔍 Checking response against knowledge base for factual grounding...")
                            elif stage == "verified":
                                status_placeholder.success("✔ Factually verified against knowledge base.")

                        elif event_type == "error":
                            is_error = True
                            error_message = data.get(
                                "message",
                                "Hallucination detected, response discarded. Please try again or ask something else."
                            )
                            break

                        elif event_type == "done":
                            sources_list = data.get("sources", [])
                            break

        except Exception as exc:
            logger.error(f"SSE stream connection error: {exc}")
            is_error = True
            error_message = "Connection lost. Please check backend service."

        if is_error:
            message_placeholder.empty()
            status_placeholder.error(f"✖ {error_message}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"✖ *{error_message}*"
            })
        else:
            message_placeholder.markdown(full_response)
            status_placeholder.empty()

            if sources_list:
                with st.expander("📚 Knowledge Sources"):
                    for src in sources_list:
                        st.markdown(f'<span class="source-tag">📄 {src}</span>', unsafe_allow_html=True)

            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "sources": sources_list
            })

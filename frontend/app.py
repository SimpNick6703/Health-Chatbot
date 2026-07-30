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

# Custom CSS styling for dark theme presentation & horizontal citations
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
    .citation-container {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 12px;
    }
    .citation-card {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 0.88em;
        color: #e2e8f0;
        flex: 1 1 calc(50% - 10px);
        min-width: 280px;
    }
    .medline-link {
        color: #38bdf8 !important;
        text-decoration: none;
        font-weight: 600;
    }
    .medline-link:hover {
        text-decoration: underline;
    }
    .snippet-box {
        background-color: #0f172a;
        border-left: 3px solid #38bdf8;
        padding: 8px 12px;
        margin-top: 6px;
        border-radius: 4px;
        font-size: 0.86em;
        color: #cbd5e1;
        line-height: 1.4;
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
    """Send request to backend to archive session history.

    Args:
        session_id: Session ID to archive.
    """
    try:
        httpx.delete(f"{BACKEND_URL}/api/session/{session_id}", timeout=5.0)
    except Exception as exc:
        logger.error(f"Failed to archive remote session {session_id}: {exc}")


def render_citations_ui(citations: list) -> None:
    """Render horizontal citations flexbox with clickable links and exact snippet excerpts.

    Args:
        citations: List of CitationItem dicts.
    """
    if not citations:
        return

    with st.expander("📚 Knowledge Base Citations & Excerpts", expanded=False):
        cols = st.columns(min(len(citations), 2))
        for idx, cit in enumerate(citations):
            col = cols[idx % len(cols)]
            with col:
                title = cit.get("title", "Source")
                source_type = cit.get("source_type", "local_kb")
                url = cit.get("url")
                snippet = cit.get("snippet", "")

                if source_type == "medlineplus_api" and url:
                    st.markdown(
                        f"🌐 **[MedlinePlus: {title}]({url})**",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(f"📄 **{title}**")

                if snippet:
                    st.caption(f"*Excerpt:* {snippet}")


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
    st.caption("Tool-Augmented Health Assistant & Guardrail System")

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
        "🫁 Asthma": "What is asthma, what causes it, and how is it managed?",
        "🩺 Conditions": "What are common symptoms and risk factors of Type 2 Diabetes?",
        "🏃 Lifestyle": "What are recommended sleep hygiene guidelines for adults?",
        "🥗 Nutrition": "How much sodium per day is recommended for heart health?",
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
        if msg.get("is_hallucinated"):
            st.warning("⚠️ Potential hallucination or unverified claim detected.")
            with st.expander("⚠️ View unverified response (Use with caution)", expanded=False):
                st.markdown(msg["content"])
        else:
            st.markdown(msg["content"])

        if "citations" in msg and msg["citations"]:
            render_citations_ui(msg["citations"])


# Determine prompt input
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
        citations_list: list = []
        is_hallucinated: bool = False
        raw_response: str = ""
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
                            if stage == "executing_tools":
                                status_placeholder.info("⚡ Querying knowledge tools & MedlinePlus API...")
                            elif stage == "checking_hallucination":
                                status_placeholder.info("🔍 Verifying response factual consistency...")
                            elif stage == "verified":
                                status_placeholder.success("✔ Factually verified against knowledge base.")

                        elif event_type == "error":
                            if data.get("is_hallucinated"):
                                is_hallucinated = True
                                raw_response = data.get("raw_response", full_response)
                                citations_list = data.get("citations", [])
                            else:
                                is_error = True
                                error_message = data.get("message", "An error occurred.")
                            break

                        elif event_type == "done":
                            citations_list = data.get("citations", [])
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
        elif is_hallucinated:
            message_placeholder.empty()
            status_placeholder.warning("⚠️ Potential hallucination or unverified claim detected.")
            with st.expander("⚠️ View unverified response (Use with caution)", expanded=False):
                st.markdown(raw_response)

            render_citations_ui(citations_list)

            st.session_state.messages.append({
                "role": "assistant",
                "content": raw_response,
                "is_hallucinated": True,
                "citations": citations_list
            })
        else:
            message_placeholder.markdown(full_response)
            status_placeholder.empty()

            render_citations_ui(citations_list)

            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "is_hallucinated": False,
                "citations": citations_list
            })

"""Streamlit frontend user interface for Healthcare AI Chatbot."""

import os
import json
import logging
from typing import List, Dict, Any
import streamlit as st
import httpx
from httpx_sse import connect_sse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("frontend")

BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")

# Page Config
st.set_page_config(
    page_title="Healthcare AI Assistant",
    layout="wide"
)

# Custom CSS styling for dark theme presentation & aligned sidebar buttons
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
    div[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {
        align-items: center;
        gap: 6px;
        margin-bottom: 4px;
    }
    div[data-testid="stSidebar"] button {
        text-align: left;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    div[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) button {
        color: #f87171;
        border-color: #7f1d1d;
        text-align: center;
        font-size: 0.82em;
    }
    div[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] > div:nth-child(2) button:hover {
        background-color: #7f1d1d;
        color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)


def fetch_active_sessions() -> List[Dict[str, Any]]:
    """Fetch active chat sessions list from backend API.

    Returns:
        List of session objects.
    """
    try:
        resp = httpx.get(f"{BACKEND_URL}/api/sessions", timeout=4.0)
        if resp.status_code == 200:
            return resp.json().get("sessions", [])
    except Exception as exc:
        logger.error(f"Failed to fetch sessions from backend: {exc}")
    return []


def create_new_remote_session(title: str = "New Chat") -> str:
    """Create a new session on the backend.

    Args:
        title: Title string.

    Returns:
        New session ID.
    """
    try:
        resp = httpx.post(f"{BACKEND_URL}/api/session", json={"title": title}, timeout=5.0)
        if resp.status_code == 201:
            return resp.json()["session_id"]
    except Exception as exc:
        logger.error(f"Failed to create new session: {exc}")

    import uuid
    return str(uuid.uuid4())


def rename_remote_session(session_id: str, new_title: str) -> None:
    """Send patch request to rename session title.

    Args:
        session_id: Session ID.
        new_title: New title string.
    """
    try:
        httpx.patch(f"{BACKEND_URL}/api/session/{session_id}", json={"title": new_title}, timeout=5.0)
    except Exception as exc:
        logger.error(f"Failed to rename session {session_id}: {exc}")


def archive_remote_session(session_id: str) -> None:
    """Archive a chat session on backend.

    Args:
        session_id: Session ID to archive.
    """
    try:
        httpx.delete(f"{BACKEND_URL}/api/session/{session_id}", timeout=5.0)
    except Exception as exc:
        logger.error(f"Failed to archive session {session_id}: {exc}")


def fetch_remote_history(session_id: str) -> List[Dict[str, Any]]:
    """Fetch full message history for a session from backend API.

    Args:
        session_id: Target session ID.

    Returns:
        List of message dicts.
    """
    try:
        resp = httpx.get(f"{BACKEND_URL}/api/session/{session_id}/history", timeout=5.0)
        if resp.status_code == 200:
            raw_messages = resp.json().get("messages", [])
            messages = []
            for m in raw_messages:
                msg_dict = {
                    "role": m.get("role"),
                    "content": m.get("content"),
                    "is_hallucinated": m.get("is_hallucinated", False)
                }
                messages.append(msg_dict)
            return messages
    except Exception as exc:
        logger.error(f"Failed to fetch history for session {session_id}: {exc}")
    return []


def render_citations_ui(citations: list) -> None:
    """Render horizontal citations flexbox with clickable links and exact snippet excerpts.

    Args:
        citations: List of CitationItem dicts.
    """
    if not citations:
        return

    with st.expander("Knowledge Base Citations & Excerpts", expanded=False):
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
                        f"**[MedlinePlus: {title}]({url})**",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(f"**Source: {title}**")

                if snippet:
                    st.caption(f"*Excerpt:* {snippet}")


# Initialize Session State Variables
import uuid

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = fetch_remote_history(st.session_state.session_id)

if "editing_title" not in st.session_state:
    st.session_state.editing_title = False

if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

# Sidebar UI & Session Management
with st.sidebar:
    st.title("Healthcare AI")
    st.caption("Tool-Augmented Health Assistant & Guardrail System")

    st.markdown("---")

    if st.button("+ Start New Chat", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.editing_title = False
        st.session_state.pending_prompt = None
        st.rerun()

    st.markdown("---")
    st.markdown("### Chat History")

    raw_sessions = fetch_active_sessions()
    active_sessions = [s for s in raw_sessions if s.get("title") and s.get("title") != "New Chat"]

    if active_sessions:
        for s in active_sessions:
            s_id = s["session_id"]
            s_title = s["title"] or "Untitled Chat"
            is_active = (s_id == st.session_state.session_id)

            col1, col2 = st.columns([3.8, 1.2])

            with col1:
                label = f"[Active] {s_title}" if is_active else s_title
                if st.button(label, key=f"sess_btn_{s_id}", use_container_width=True):
                    if s_id != st.session_state.session_id:
                        st.session_state.session_id = s_id
                        st.session_state.messages = fetch_remote_history(s_id)
                        st.session_state.editing_title = False
                        st.session_state.pending_prompt = None
                        st.rerun()

            with col2:
                if st.button("Delete", key=f"del_btn_{s_id}", use_container_width=True):
                    archive_remote_session(s_id)
                    if s_id == st.session_state.session_id:
                        st.session_state.session_id = create_new_remote_session()
                        st.session_state.messages = []
                    st.rerun()
    else:
        st.caption("No past sessions found.")

    st.markdown("---")

    # Rename Current Session UI
    active_sess_obj = next((s for s in active_sessions if s["session_id"] == st.session_state.session_id), None)
    active_title = active_sess_obj["title"] if active_sess_obj else "New Chat"

    st.markdown(f"**Active Session:** `{active_title}`")
    if not st.session_state.editing_title:
        if st.button("Rename Chat", use_container_width=True):
            st.session_state.editing_title = True
            st.rerun()
    else:
        new_title_input = st.text_input("New title:", value=active_title, key="new_title_input")
        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save"):
                if new_title_input.strip():
                    rename_remote_session(st.session_state.session_id, new_title_input.strip())
                st.session_state.editing_title = False
                st.rerun()
        with col_cancel:
            if st.button("Cancel"):
                st.session_state.editing_title = False
                st.rerun()

    st.markdown("---")
    st.markdown("### Sample Prompts")
    st.caption("Tap a button below for instant quick queries:")

    sample_prompts = {
        "Fever Care": "What should I do to care for a fever and when should I see a doctor?",
        "Asthma Overview": "What is asthma, what causes it, and how is it managed?",
        "Diabetes Conditions": "What are common symptoms and risk factors of Type 2 Diabetes?",
        "Sleep Hygiene": "What are recommended sleep hygiene guidelines for adults?",
        "Sodium & Nutrition": "How much sodium per day is recommended for heart health?",
        "First Aid Burns": "How should I treat a minor first-degree burn at home?"
    }

    for label, prompt in sample_prompts.items():
        if st.button(label, use_container_width=True):
            st.session_state.pending_prompt = prompt


# Main UI Header
st.title("Healthcare Information Assistant")

# Persistent Medical Disclaimer Banner
st.markdown(
    '<div class="disclaimer-banner">'
    '<strong>Notice:</strong> This is for informational purposes only. For medical advice or diagnosis, consult a professional.'
    '</div>',
    unsafe_allow_html=True
)

# Render Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("is_hallucinated"):
            st.warning("Warning: Potential hallucination or unverified claim detected.")
            with st.expander("View unverified response (Use with caution)", expanded=False):
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
                                status_placeholder.info("Querying knowledge tools & MedlinePlus API...")
                            elif stage == "checking_hallucination":
                                status_placeholder.info("Verifying response factual consistency...")
                            elif stage == "verified":
                                status_placeholder.success("Factually verified against knowledge base.")

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
            status_placeholder.error(f"Error: {error_message}")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"*Error: {error_message}*"
            })
        elif is_hallucinated:
            message_placeholder.empty()
            status_placeholder.warning("Warning: Potential hallucination or unverified claim detected.")
            with st.expander("View unverified response (Use with caution)", expanded=False):
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

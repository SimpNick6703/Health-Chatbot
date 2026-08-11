"""FastAPI application entrypoint with REST and Server-Sent Events (SSE) streaming endpoints."""

import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config import settings
from models import ChatRequest, SessionResponse, SessionListResponse, SessionItem, UpdateSessionRequest
from session import session_store
from rag import rag_manager
from router import process_query

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for application startup and shutdown tasks."""
    logger.info("Initializing database schema...")
    await session_store.init_db()

    knowledge_dir = os.path.join(os.path.dirname(__file__), "knowledge")
    logger.info("Scanning and ingesting knowledge base documents...")
    await rag_manager.ingest_knowledge_files(
        knowledge_dir=knowledge_dir,
        get_cache_fn=session_store.get_cache_hash,
        update_cache_fn=session_store.update_cache_hash
    )
    logger.info("Application startup initialization complete.")
    yield
    logger.info("Application shutdown.")


app = FastAPI(
    title="Healthcare AI Chatbot API",
    description="FastAPI backend for Healthcare AI Chatbot with RAG, Guardrails, and Session Management",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend client
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", 
        "http://localhost:5173", 
        "http://localhost:8501", 
        "http://192.168.31.254:3000", 
        "http://192.168.31.254:8501"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """Liveness and readiness check endpoint for Docker container healthchecks."""
    return {"status": "healthy"}


@app.get("/api/sessions", response_model=SessionListResponse, status_code=status.HTTP_200_OK)
async def list_sessions() -> SessionListResponse:
    """Retrieve list of all active (non-archived) chat sessions."""
    sessions = await session_store.list_active_sessions()
    items = [SessionItem(**s) for s in sessions]
    return SessionListResponse(sessions=items)


@app.post("/api/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: Optional[UpdateSessionRequest] = None) -> SessionResponse:
    """Create a new chat session with an optional custom title."""
    title = request.title if request and request.title else "New Chat"
    session_id = await session_store.create_session(title=title)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return SessionResponse(session_id=session_id, title=title, created_at=now)


@app.patch("/api/session/{session_id}", status_code=status.HTTP_200_OK)
async def update_session_title(session_id: str, request: UpdateSessionRequest) -> Dict[str, str]:
    """Rename or update session title."""
    updated = await session_store.update_session_title(session_id, request.title)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found."
        )
    return {"status": "updated", "session_id": session_id, "title": request.title}


@app.delete("/api/session/{session_id}", status_code=status.HTTP_200_OK)
async def delete_session(session_id: str) -> Dict[str, str]:
    """Archive a chat session."""
    deleted = await session_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found."
        )
    return {"status": "archived", "session_id": session_id}


@app.get("/api/session/{session_id}/history", status_code=status.HTTP_200_OK)
async def get_session_history(session_id: str) -> Dict[str, Any]:
    """Retrieve full message turn history for a session."""
    history = await session_store.get_full_history(session_id)
    return {"session_id": session_id, "messages": history}


@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest) -> EventSourceResponse:
    """Submit a user chat query and return an SSE event stream."""
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message text cannot be empty."
        )

    generator = process_query(
        session_id=request.session_id,
        user_message=request.message
    )
    return EventSourceResponse(generator)

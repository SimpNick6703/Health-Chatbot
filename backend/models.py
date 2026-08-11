"""Pydantic models and data schemas for API requests, responses, and pipeline events."""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat message request payload from frontend."""

    session_id: str = Field(..., description="Unique identifier for the chat session.")
    message: str = Field(..., description="User message text.")


class SessionResponse(BaseModel):
    """Response payload when creating a new session."""

    session_id: str = Field(..., description="Newly created session identifier.")
    title: str = Field(default="New Chat", description="Session title.")
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")


class UpdateSessionRequest(BaseModel):
    """Request payload for updating session metadata."""

    title: str = Field(..., description="New session title.")


class SessionItem(BaseModel):
    """Model representing a single chat session item in listing."""

    session_id: str = Field(..., description="Session identifier.")
    title: str = Field(..., description="Session title.")
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")
    last_active_at: str = Field(..., description="ISO 8601 last active timestamp.")


class SessionListResponse(BaseModel):
    """Response payload for listing sessions."""

    sessions: List[SessionItem] = Field(default_factory=list, description="List of active chat sessions.")


class RetrievedChunk(BaseModel):
    """Model representing a chunk retrieved from vector database or API."""

    content: str = Field(..., description="Text content of the retrieved chunk.")
    source: str = Field(..., description="Filename or API source identifier.")
    source_type: Literal["local_kb", "medlineplus_api"] = Field(default="local_kb", description="Origin category.")
    score: float = Field(..., description="Similarity distance or relevance score.")
    heading: Optional[str] = Field(None, description="Section heading or topic title.")
    snippet_text: Optional[str] = Field(None, description="Granular text snippet excerpt.")
    url: Optional[str] = Field(None, description="Direct URL link if external API source.")


class CitationItem(BaseModel):
    """Structured citation item returned to frontend for UI rendering."""

    title: str = Field(..., description="Citation title or filename.")
    source_type: Literal["local_kb", "medlineplus_api"] = Field(..., description="Origin category.")
    url: Optional[str] = Field(None, description="Direct HTTP link if available.")
    snippet: str = Field(..., description="Exact text chunk snippet excerpt.")


class IntentResult(BaseModel):
    """Result from local intent classification guardrail."""

    category: Literal["emergency", "diagnosis", "prescription", "safe"] = Field(
        ..., description="Detected intent category."
    )
    response: Optional[str] = Field(
        None, description="Immediate refusal or redirect message if non-safe."
    )


class ModerationResult(BaseModel):
    """Result from input moderation API check."""

    blocked: bool = Field(..., description="Whether the content was flagged and blocked.")
    flagged_categories: List[str] = Field(
        default_factory=list, description="List of category names that triggered a flag."
    )
    category_scores: Dict[str, float] = Field(
        default_factory=dict, description="Raw category scores returned by moderation model."
    )


class StreamTokenEvent(BaseModel):
    """SSE event payload for streaming token chunks."""

    token: str = Field(..., description="Partial LLM text token.")


class StreamStatusEvent(BaseModel):
    """SSE event payload for status transitions."""

    stage: Literal["executing_tools", "checking_hallucination", "verified"] = Field(
        ..., description="Current processing stage identifier."
    )


class StreamDoneEvent(BaseModel):
    """SSE event payload emitted when stream completes successfully."""

    sources: List[str] = Field(default_factory=list, description="List of simple source titles.")
    citations: List[CitationItem] = Field(default_factory=list, description="Structured citation objects.")


class StreamErrorEvent(BaseModel):
    """SSE event payload emitted when a guardrail or hallucination error occurs."""

    type: str = Field(..., description="Category of error (e.g., hallucination, moderation).")
    message: str = Field(..., description="User-facing refusal or error message.")
    is_hallucinated: bool = Field(default=False, description="Whether hallucination check triggered.")
    raw_response: Optional[str] = Field(None, description="Unverified response text for collapsed UI container.")
    citations: List[CitationItem] = Field(default_factory=list, description="Associated citations if available.")

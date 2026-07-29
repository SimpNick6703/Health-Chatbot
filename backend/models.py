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
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")


class RetrievedChunk(BaseModel):
    """Model representing a chunk retrieved from ChromaDB."""

    content: str = Field(..., description="Text content of the retrieved chunk.")
    source: str = Field(..., description="Filename of the knowledge source document.")
    score: float = Field(..., description="Similarity distance or relevance score.")


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

    stage: Literal["checking_hallucination", "verified"] = Field(
        ..., description="Current processing stage identifier."
    )


class StreamDoneEvent(BaseModel):
    """SSE event payload emitted when stream completes successfully."""

    sources: List[str] = Field(..., description="List of knowledge source files used.")


class StreamErrorEvent(BaseModel):
    """SSE event payload emitted when a guardrail or error stops stream."""

    type: str = Field(..., description="Category of error (e.g., hallucination, moderation).")
    message: str = Field(..., description="User-facing refusal or error message.")

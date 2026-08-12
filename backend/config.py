"""Application configuration settings loaded from environment variables."""

from typing import Dict, Any
import json
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings class using pydantic-settings."""

    # LLM Settings
    BASE_URL: str = ""
    API_KEY: str = ""
    MODEL_NAME: str = "gpt-4o-mini"

    # Input Moderation Settings
    GUARDRAIL_BASE_URL: str = ""
    GUARDRAIL_API_KEY: str = ""
    GUARDRAIL_MODEL_NAME: str = "mistral-moderation-latest"

    # Judge LLM Settings
    JUDGE_BASE_URL: str = ""
    JUDGE_API_KEY: str = ""
    JUDGE_MODEL_NAME: str = "gpt-4o-mini"

    # Embedding Settings
    EMBEDDING_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = "gemini-embedding-2-preview"

    # Storage & Pipeline Settings
    CHROMA_PERSIST_DIR: str = "/data/chroma"
    SQLITE_PATH: str = "/data/sessions.db"
    DATABASE_URL: str = "postgresql://postgres:postgrespassword@db:5432/healthchatbot"
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.3
    SESSION_MAX_TURNS: int = 6

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def get_portkey_headers(self, session_id: str) -> Dict[str, str]:
        """Return headers dict containing Portkey observability metadata.

        Args:
            session_id: Unique identifier for current chat session.

        Returns:
            Dictionary containing x-portkey-metadata header.

        Examples:
            >>> settings = Settings()
            >>> headers = settings.get_portkey_headers("session-123")
            >>> "x-portkey-metadata" in headers
            True
        """
        metadata: Dict[str, str] = {
            "_user": session_id
        }
        return {"x-portkey-metadata": json.dumps(metadata)}


settings = Settings()

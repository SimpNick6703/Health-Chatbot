"""Async LLM client wrapper for streaming completions with Portkey observability headers."""

import json
import logging
from typing import List, Dict, AsyncGenerator
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Async wrapper for OpenAI-compatible chat completion LLM calls with streaming support."""

    def __init__(self) -> None:
        """Initialize AsyncOpenAI client targeting BASE_URL."""
        self.client = AsyncOpenAI(
            base_url=settings.BASE_URL,
            api_key=settings.API_KEY or "dummy_key"
        )

    async def generate_stream(
        self, messages: List[Dict[str, str]], session_id: str
    ) -> AsyncGenerator[str, None]:
        """Stream token chunks from chat completion endpoint.

        Args:
            messages: Formatted list of message dicts (system, user, assistant).
            session_id: Session ID for Portkey observability tracking.

        Yields:
            Raw text token strings as they arrive.
        """
        headers = settings.get_portkey_headers(session_id)

        try:
            stream = await self.client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=messages,
                stream=True,
                temperature=0.3,
                user=session_id,
                extra_headers=headers
            )

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content

        except Exception as exc:
            logger.error(f"LLM streaming request failed: {exc}")
            yield f"\n[Error generating response: {str(exc)}]"


llm_client = LLMClient()

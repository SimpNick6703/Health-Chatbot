"""Async LLM client wrapper for streaming completions and tool selection calls with Portkey observability headers."""

import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Async wrapper for OpenAI-compatible chat completion LLM calls with tool selection & streaming support."""

    def __init__(self) -> None:
        """Initialize AsyncOpenAI client targeting BASE_URL."""
        self.client = AsyncOpenAI(
            base_url=settings.BASE_URL,
            api_key=settings.API_KEY or "dummy_key",
            timeout=15.0
        )

    async def generate_tool_completion(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], session_id: str
    ) -> Any:
        """Execute non-streaming completion to allow model to select tool calls if needed.

        Args:
            messages: Conversation messages list.
            tools: OpenAI Function tool specs list.
            session_id: Session ID for Portkey headers.

        Returns:
            OpenAI ChatCompletion choice message object.
        """
        headers = settings.get_portkey_headers(session_id)

        try:
            res = await self.client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
                user=session_id,
                extra_headers=headers
            )
            return res.choices[0].message
        except Exception as exc:
            logger.error(f"LLM tool completion request failed: {exc}")
            return None

    async def generate_stream(
        self, messages: List[Dict[str, Any]], session_id: str
    ) -> AsyncGenerator[str, None]:
        """Stream token chunks from chat completion endpoint.

        Args:
            messages: Formatted list of message dicts (system, user, assistant, tool).
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
                    reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if reasoning:
                        yield f"<think>{reasoning}</think>"
                    if delta.content:
                        yield delta.content

        except Exception as exc:
            logger.error(f"LLM streaming request failed: {exc}")
            raise exc


llm_client = LLMClient()

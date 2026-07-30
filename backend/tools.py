"""OpenAI Tool (Function Calling) definitions and execution dispatcher for healthcare knowledge tools."""

import json
import logging
from typing import List, Dict, Any, Tuple

from rag import rag_manager
from medlineplus import medlineplus_client
from models import RetrievedChunk

logger = logging.getLogger(__name__)

# OpenAI Function Tool Schemas
HEALTHCARE_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the local curated healthcare vector database for factual information, "
                "symptoms, diseases, lifestyle guidelines, nutrition, and first-aid instructions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Specific health topic, disease name, or symptom keyword to search."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_medlineplus_api",
            "description": (
                "Search the official NIH / MedlinePlus Developer API for verified government "
                "health topic guides, clinical disease overviews, and official URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Medical term, symptom, or condition to look up in MedlinePlus."
                    }
                },
                "required": ["term"]
            }
        }
    }
]


async def execute_tool_call(
    tool_name: str, arguments: Dict[str, Any], session_id: str
) -> Tuple[str, List[RetrievedChunk]]:
    """Execute a function tool call requested by the LLM and return formatted text + retrieved chunk objects.

    Args:
        tool_name: Name of the tool requested (search_knowledge_base or search_medlineplus_api).
        arguments: Keyword argument dict passed by the LLM.
        session_id: Active session ID for Portkey tracking.

    Returns:
        Tuple of (formatted_tool_response_string, list_of_retrieved_chunks).
    """
    logger.info(f"Session {session_id}: Executing tool '{tool_name}' with args {arguments}")

    chunks: List[RetrievedChunk] = []

    if tool_name == "search_knowledge_base":
        query = arguments.get("query", "")
        chunks = await rag_manager.retrieve(query=query, session_id=session_id, top_k=3)
    elif tool_name == "search_medlineplus_api":
        term = arguments.get("term", "")
        chunks = await medlineplus_client.search_health_topics(query=term, max_results=2)

    if not chunks:
        return f"No results found for tool search '{tool_name}'.", []

    formatted_passages = []
    for c in chunks:
        source_info = f"Source: {c.source}"
        if c.url:
            source_info += f" | URL: {c.url}"
        formatted_passages.append(f"[{source_info}]\n{c.content}")

    return "\n---\n".join(formatted_passages), chunks

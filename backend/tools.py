"""OpenAI Tool (Function Calling) definitions and execution dispatcher using FastMCP in-process."""

import json
import logging
from typing import List, Dict, Any, Tuple
import asyncio

from fastmcp import FastMCP
from rag import rag_manager
from medlineplus import medlineplus_client
from models import RetrievedChunk

logger = logging.getLogger(__name__)

# Create the FastMCP instance
mcp = FastMCP("HealthcareTools")

@mcp.tool()
async def search_knowledge_base(query: str) -> str:
    """Search the local curated healthcare vector database for factual information, symptoms, diseases, lifestyle guidelines, nutrition, and first-aid instructions."""
    # The actual execution happens via execute_tool_call so we can capture the RetrievedChunks.
    # This definition allows FastMCP to automatically infer the schema.
    return ""

@mcp.tool()
async def search_medlineplus_api(term: str) -> str:
    """Search the official NIH / MedlinePlus Developer API for verified government health topic guides, clinical disease overviews, and official URLs."""
    return ""

# We will cache the tools to avoid regenerating on every request
_cached_tools: List[Dict[str, Any]] = []

async def get_openai_tools() -> List[Dict[str, Any]]:
    """Get the FastMCP tool definitions formatted as OpenAI schemas."""
    global _cached_tools
    if _cached_tools:
        return _cached_tools
        
    mcp_tools = await mcp.list_tools()
    tools = []
    
    for t in mcp_tools:
        mcp_t = t.to_mcp_tool().model_dump()
        tools.append({
            "type": "function",
            "function": {
                "name": mcp_t["name"],
                "description": mcp_t["description"],
                "parameters": mcp_t["inputSchema"]
            }
        })
        
    _cached_tools = tools
    return tools

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
    logger.info(f"Session {session_id}: Executing FastMCP tool '{tool_name}' with args {arguments}")

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

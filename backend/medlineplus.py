"""MedlinePlus Developer Web Service API client for live health topic searches."""

import re
import logging
import xml.etree.ElementTree as ET
from typing import List
import httpx

from models import RetrievedChunk

logger = logging.getLogger(__name__)

MEDLINEPLUS_API_URL: str = "https://wsearch.nlm.nih.gov/ws/query"


def strip_html_tags(text: str) -> str:
    """Strip HTML markup tags and clean whitespace.

    Args:
        text: Raw HTML or XML string.

    Returns:
        Clean plain text string.
    """
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return " ".join(clean.split())


class MedlinePlusClient:
    """Async client for querying the official MedlinePlus Web Services API (NIH/NLM)."""

    async def search_health_topics(
        self, query: str, max_results: int = 2
    ) -> List[RetrievedChunk]:
        """Search MedlinePlus Developer API for health topics matching the query.

        Args:
            query: Search term or user query.
            max_results: Maximum number of topic documents to return.

        Returns:
            List of RetrievedChunk objects containing topic summaries and URLs.
        """
        if not query.strip():
            return []

        params = {
            "db": "healthTopics",
            "term": query
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(MEDLINEPLUS_API_URL, params=params)
                response.raise_for_status()
                xml_data = response.text

            root = ET.fromstring(xml_data)
            chunks: List[RetrievedChunk] = []

            for doc in root.findall(".//document")[:max_results]:
                url = doc.attrib.get("url", "https://medlineplus.gov/")
                title = ""
                summary = ""

                for content in doc.findall("content"):
                    name = content.attrib.get("name")
                    text_val = content.text or ""

                    if name == "title":
                        title = strip_html_tags(text_val)
                    elif name == "FullSummary" or (name == "snippet" and not summary):
                        summary = strip_html_tags(text_val)

                if summary and title:
                    snippet = summary[:250] + ("..." if len(summary) > 250 else "")
                    source_label = f"MedlinePlus API ({title})"
                    content_text = f"Title: {title}\nSummary: {summary}\nURL: {url}"
                    chunks.append(RetrievedChunk(
                        content=content_text,
                        source=source_label,
                        source_type="medlineplus_api",
                        score=0.9,
                        heading=title,
                        snippet_text=snippet,
                        url=url
                    ))

            logger.info(f"Retrieved {len(chunks)} topic snippets from MedlinePlus API for term '{query}'.")
            return chunks

        except Exception as exc:
            logger.error(f"MedlinePlus API query failed: {exc}")
            return []


medlineplus_client = MedlinePlusClient()

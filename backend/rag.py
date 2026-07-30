"""RAG retrieval module using ChromaDB and async Gemini Embeddings with SQLite hash-caching."""

import os
import hashlib
import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from openai import AsyncOpenAI, OpenAI

from config import settings
from models import RetrievedChunk

logger = logging.getLogger(__name__)


class GeminiEmbeddingFunction(EmbeddingFunction):
    """Custom ChromaDB Embedding Function wrapping Google AI Studio Gemini Embeddings via OpenAI SDK."""

    def __init__(self, session_id: str = "rag_ingestion") -> None:
        """Initialize OpenAI client for Gemini Embeddings.

        Args:
            session_id: Session ID to attach to Portkey headers.
        """
        self.session_id = session_id
        self.client = OpenAI(
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY or "dummy_key"
        )

    def __call__(self, input: Documents) -> Embeddings:
        """Generate embeddings for input document chunks synchronously during ingestion.

        Args:
            input: List of text strings to embed.

        Returns:
            List of float vectors.
        """
        headers = settings.get_portkey_headers(self.session_id)
        embeddings: Embeddings = []
        for text in input:
            try:
                res = self.client.embeddings.create(
                    input=text,
                    model=settings.EMBEDDING_MODEL_NAME,
                    user=self.session_id,
                    extra_headers=headers
                )
                embeddings.append(res.data[0].embedding)
            except Exception as exc:
                logger.error(f"Gemini embedding call failed for chunk: {exc}")
                embeddings.append([0.0] * 3072)

        return embeddings


class RAGManager:
    """Manages knowledge ingestion, ChromaDB vector indexing, and async retrieval."""

    def __init__(self) -> None:
        """Initialize ChromaDB client and collection."""
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self.collection_name = "health_knowledge"
        self.embedding_fn = GeminiEmbeddingFunction()
        self.async_client = AsyncOpenAI(
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY or "dummy_key"
        )
        self.init_collection()

    def init_collection(self) -> None:
        """Get or create ChromaDB collection, resetting if dimension mismatch occurs."""
        try:
            self.collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
            if self.collection.count() > 0:
                try:
                    self.collection.query(query_texts=["health check"], n_results=1)
                except Exception as exc:
                    if "dimension" in str(exc).lower():
                        logger.warning(f"ChromaDB dimension mismatch ({exc}). Resetting collection...")
                        self.chroma_client.delete_collection(self.collection_name)
                        self.collection = self.chroma_client.get_or_create_collection(
                            name=self.collection_name,
                            embedding_function=self.embedding_fn,
                            metadata={"hnsw:space": "cosine"}
                        )
        except Exception as exc:
            logger.error(f"Error initializing ChromaDB collection: {exc}")
            self.collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file's contents.

        Args:
            file_path: Absolute or relative file path.

        Returns:
            Hex digest string of the file hash.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def chunk_text(self, text: str, max_chunk_chars: int = 350) -> List[Dict[str, str]]:
        """Split Markdown document into concise, topic-focused ~300-character passages.

        Args:
            text: Raw Markdown text.
            max_chunk_chars: Target maximum characters per chunk.

        Returns:
            List of dicts containing 'content', 'heading', and 'snippet'.
        """
        lines = text.split("\n")
        chunks: List[Dict[str, str]] = []
        current_heading = "General Overview"
        buffer: List[str] = []
        buffer_len = 0

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("# Source:") or stripped.startswith("# AI-curated"):
                continue

            if stripped.startswith("### ") or stripped.startswith("## ") or stripped.startswith("# "):
                if buffer:
                    chunk_str = " ".join(buffer)
                    chunks.append({
                        "content": f"{current_heading}: {chunk_str}",
                        "heading": current_heading,
                        "snippet": chunk_str[:250] + ("..." if len(chunk_str) > 250 else "")
                    })
                    buffer = []
                    buffer_len = 0
                current_heading = stripped.lstrip("#").strip()
                continue

            buffer.append(stripped)
            buffer_len += len(stripped)

            if buffer_len >= max_chunk_chars:
                chunk_str = " ".join(buffer)
                chunks.append({
                    "content": f"{current_heading}: {chunk_str}",
                    "heading": current_heading,
                    "snippet": chunk_str[:250] + ("..." if len(chunk_str) > 250 else "")
                })
                buffer = []
                buffer_len = 0

        if buffer:
            chunk_str = " ".join(buffer)
            chunks.append({
                "content": f"{current_heading}: {chunk_str}",
                "heading": current_heading,
                "snippet": chunk_str[:250] + ("..." if len(chunk_str) > 250 else "")
            })

        return chunks

    async def ingest_knowledge_files(
        self, knowledge_dir: str, get_cache_fn: Any, update_cache_fn: Any
    ) -> None:
        """Scan knowledge directory, check SHA-256 hashes against DB cache, and index new/modified files.

        Args:
            knowledge_dir: Path to directory containing .md knowledge files.
            get_cache_fn: Async function to fetch cached file hash from SQLite.
            update_cache_fn: Async function to update file hash in SQLite.
        """
        if not os.path.exists(knowledge_dir):
            logger.warning(f"Knowledge directory {knowledge_dir} does not exist.")
            return

        md_files = [
            f for f in os.listdir(knowledge_dir)
            if f.endswith(".md")
        ]

        for filename in md_files:
            file_path = os.path.join(knowledge_dir, filename)
            file_hash = self.compute_file_hash(file_path)
            cached_hash = await get_cache_fn(file_path)

            if cached_hash == file_hash:
                logger.info(f"Skipping indexing for {filename} (content hash unchanged).")
                continue

            logger.info(f"Ingesting & embedding updated knowledge file: {filename}")
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            chunk_objs = self.chunk_text(content)
            if not chunk_objs:
                continue

            documents = [c["content"] for c in chunk_objs]
            ids = [f"{filename}_chunk_{i}" for i in range(len(chunk_objs))]
            metadatas = [
                {"source": filename, "heading": c["heading"], "snippet": c["snippet"]}
                for c in chunk_objs
            ]

            try:
                self.collection.delete(where={"source": filename})
            except Exception:
                pass

            try:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
            except Exception as exc:
                if "dimension" in str(exc).lower():
                    logger.warning(f"ChromaDB collection dimension mismatch detected ({exc}). Recreating collection...")
                    self.chroma_client.delete_collection(self.collection_name)
                    self.collection = self.chroma_client.get_or_create_collection(
                        name=self.collection_name,
                        embedding_function=self.embedding_fn,
                        metadata={"hnsw:space": "cosine"}
                    )
                    self.collection.add(
                        documents=documents,
                        metadatas=metadatas,
                        ids=ids
                    )
                else:
                    raise exc

            await update_cache_fn(file_path, file_hash, len(chunk_objs))
            logger.info(f"Successfully indexed {len(chunk_objs)} granular chunks from {filename}.")

    async def retrieve(
        self, query: str, session_id: str, top_k: int = 3
    ) -> List[RetrievedChunk]:
        """Asynchronously retrieve relevant knowledge chunks from ChromaDB for a given query.

        Args:
            query: Redacted user query text.
            session_id: Session ID for Portkey tracking.
            top_k: Number of top chunks to retrieve.

        Returns:
            List of RetrievedChunk objects.
        """
        if not query.strip() or self.collection.count() == 0:
            return []

        headers = settings.get_portkey_headers(session_id)

        try:
            res = await self.async_client.embeddings.create(
                input=[query],
                model=settings.EMBEDDING_MODEL_NAME,
                user=session_id,
                extra_headers=headers
            )
            query_embedding = res.data[0].embedding

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            retrieved: List[RetrievedChunk] = []
            for doc, meta, dist in zip(documents, metadatas, distances):
                score = float(1.0 - dist) if dist is not None else 0.0
                retrieved.append(RetrievedChunk(
                    content=doc,
                    source=meta.get("source", "unknown"),
                    score=max(score, 0.0),
                    heading=meta.get("heading", ""),
                    snippet_text=meta.get("snippet", doc[:200])
                ))

            return retrieved
        except Exception as exc:
            logger.error(f"Async RAG retrieval failed: {exc}")
            return []


rag_manager = RAGManager()

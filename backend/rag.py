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
        if not input:
            return []

        headers = settings.get_portkey_headers(self.session_id)

        try:
            res = self.client.embeddings.create(
                input=input,
                model=settings.EMBEDDING_MODEL_NAME,
                user=self.session_id,
                extra_headers=headers
            )
            return [data.embedding for data in res.data]
        except Exception as exc:
            logger.error(f"Gemini embedding call failed: {exc}")
            return [[0.0] * 3072 for _ in input]


class RAGManager:
    """Manages knowledge ingestion, ChromaDB vector indexing, and async retrieval."""

    def __init__(self) -> None:
        """Initialize ChromaDB client and collection."""
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self.collection_name = "health_knowledge"
        self.embedding_fn = GeminiEmbeddingFunction()
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn
        )
        self.async_client = AsyncOpenAI(
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY or "dummy_key"
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

    def chunk_text(self, text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
        """Split text into overlapping character chunks cleanly on paragraph/sentence boundaries.

        Args:
            text: Raw text to split.
            chunk_size: Target maximum characters per chunk.
            overlap: Overlap characters between consecutive chunks.

        Returns:
            List of text chunks.
        """
        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current_chunk: List[str] = []
        current_length: int = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if current_length + len(para) > chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                last = current_chunk[-1] if current_chunk else ""
                current_chunk = [last] if len(last) < overlap else []
                current_length = sum(len(p) for p in current_chunk)

            current_chunk.append(para)
            current_length += len(para)

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

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

            chunks = self.chunk_text(content)
            if not chunks:
                continue

            ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

            try:
                self.collection.delete(where={"source": filename})
            except Exception:
                pass

            try:
                self.collection.add(
                    documents=chunks,
                    metadatas=metadatas,
                    ids=ids
                )
            except Exception as exc:
                if "dimension" in str(exc).lower():
                    logger.warning(f"ChromaDB collection dimension mismatch detected ({exc}). Recreating collection...")
                    self.chroma_client.delete_collection(self.collection_name)
                    self.collection = self.chroma_client.get_or_create_collection(
                        name=self.collection_name,
                        embedding_function=self.embedding_fn
                    )
                    self.collection.add(
                        documents=chunks,
                        metadatas=metadatas,
                        ids=ids
                    )
                else:
                    raise exc

            await update_cache_fn(file_path, file_hash, len(chunks))
            logger.info(f"Successfully indexed {len(chunks)} chunks from {filename}.")

    async def retrieve(
        self, query: str, session_id: str, top_k: int = 5
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
            # Asynchronously compute query embedding
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
                if score >= settings.RAG_SIMILARITY_THRESHOLD:
                    retrieved.append(RetrievedChunk(
                        content=doc,
                        source=meta.get("source", "unknown"),
                        score=score
                    ))

            return retrieved
        except Exception as exc:
            logger.error(f"Async RAG retrieval failed: {exc}")
            return []


rag_manager = RAGManager()

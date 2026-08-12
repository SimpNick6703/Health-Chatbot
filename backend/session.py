"""PostgreSQL session and knowledge cache store using asyncpg with automated SQLite migration."""

import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import asyncpg
import aiosqlite

from config import settings

logger = logging.getLogger(__name__)


class SessionStore:
    """Async PostgreSQL database store for chat sessions, messages, and RAG knowledge cache."""

    def __init__(self) -> None:
        """Initialize session store with connection pool set to None."""
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create PostgreSQL connection pool."""
        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=settings.DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    timeout=10.0
                )
                logger.info("PostgreSQL connection pool established successfully.")
            except Exception as exc:
                logger.error(f"Failed to establish PostgreSQL connection pool: {exc}")
                raise exc

    async def close(self) -> None:
        """Close PostgreSQL connection pool gracefully."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL connection pool closed.")

    async def init_db(self) -> None:
        """Create PostgreSQL database tables if they do not exist and trigger SQLite migration."""
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id VARCHAR(100) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL DEFAULT 'New Chat',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_active_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    is_archived BOOLEAN DEFAULT FALSE,
                    archived_at TIMESTAMPTZ
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(100) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    intent VARCHAR(50),
                    sources JSONB DEFAULT '[]'::jsonb,
                    status_logs JSONB DEFAULT '[]'::jsonb,
                    had_pii BOOLEAN DEFAULT FALSE,
                    is_hallucinated BOOLEAN DEFAULT FALSE,
                    flagged BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.execute("""
                ALTER TABLE messages ADD COLUMN IF NOT EXISTS status_logs JSONB DEFAULT '[]'::jsonb;
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_cache (
                    file_path VARCHAR(500) PRIMARY KEY,
                    content_hash VARCHAR(100) NOT NULL,
                    last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    chunk_count INT DEFAULT 0
                );
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
            """)

        logger.info("PostgreSQL database tables and indexes verified successfully.")
        await self.migrate_from_sqlite_if_needed()

    async def migrate_from_sqlite_if_needed(self) -> None:
        """Migrate existing chat sessions and messages from SQLite to PostgreSQL if Postgres is empty."""
        if not self.pool or not os.path.exists(settings.SQLITE_PATH):
            return

        async with self.pool.acquire() as conn:
            pg_count = await conn.fetchval("SELECT COUNT(*) FROM sessions")
            if pg_count > 0:
                logger.info("PostgreSQL already contains session records. Skipping SQLite data migration.")
                return

        logger.info(f"PostgreSQL database is empty. Starting automated migration from SQLite ({settings.SQLITE_PATH})...")
        try:
            async with aiosqlite.connect(settings.SQLITE_PATH) as sqlite_db:
                async with sqlite_db.execute("SELECT session_id, title, created_at, last_active_at, is_archived FROM sessions") as cursor:
                    sqlite_sessions = await cursor.fetchall()

                async with sqlite_db.execute("SELECT session_id, role, content, intent, sources, had_pii, is_hallucinated, flagged FROM messages ORDER BY id ASC") as cursor:
                    sqlite_messages = await cursor.fetchall()

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for s in sqlite_sessions:
                        session_id, title, created_at, last_active_at, is_archived = s
                        is_arch = bool(is_archived) if is_archived is not None else False
                        await conn.execute(
                            """
                            INSERT INTO sessions (session_id, title, created_at, last_active_at, is_archived)
                            VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, $3)
                            ON CONFLICT (session_id) DO NOTHING
                            """,
                            session_id, title or "New Chat", is_arch
                        )

                    for m in sqlite_messages:
                        session_id, role, content, intent, sources, had_pii, is_hallucinated, flagged = m
                        sources_json = sources if sources else "[]"
                        try:
                            json.loads(sources_json)
                        except Exception:
                            sources_json = "[]"

                        await conn.execute(
                            """
                            INSERT INTO messages (session_id, role, content, intent, sources, had_pii, is_hallucinated, flagged)
                            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                            """,
                            session_id, role, content, intent or "safe", sources_json,
                            bool(had_pii), bool(is_hallucinated), bool(flagged)
                        )

            logger.info(f"Successfully migrated {len(sqlite_sessions)} sessions and {len(sqlite_messages)} messages from SQLite to PostgreSQL.")
        except Exception as exc:
            logger.error(f"Error during SQLite to PostgreSQL migration: {exc}")

    async def list_active_sessions(self) -> List[Dict[str, Any]]:
        """Retrieve all active sessions containing at least 1 message turn."""
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.session_id, s.title, s.created_at, s.last_active_at
                FROM sessions s
                JOIN messages m ON s.session_id = m.session_id
                WHERE s.is_archived = FALSE AND s.title IS NOT NULL AND s.title != 'New Chat' AND s.title != ''
                GROUP BY s.session_id, s.title, s.created_at, s.last_active_at
                ORDER BY s.last_active_at DESC
                """
            )
            return [
                {
                    "session_id": r["session_id"],
                    "title": r["title"],
                    "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
                    "last_active_at": r["last_active_at"].isoformat() if hasattr(r["last_active_at"], "isoformat") else str(r["last_active_at"])
                } for r in rows
            ]

    async def update_session_title(self, session_id: str, title: str) -> bool:
        """Update session title."""
        if not self.pool:
            return False
        async with self.pool.acquire() as conn:
            res = await conn.execute(
                "UPDATE sessions SET title = $1 WHERE session_id = $2",
                title.strip(), session_id
            )
            return res != "UPDATE 0"

    async def create_session(self, session_id: str, title: str = "New Chat") -> None:
        """Create new session if it doesn't exist."""
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (session_id, title, created_at, last_active_at, is_archived)
                VALUES ($1, $2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, FALSE)
                ON CONFLICT (session_id) DO NOTHING
                """,
                session_id, title.strip()
            )

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch session metadata by session ID."""
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT session_id, title, created_at, last_active_at, is_archived FROM sessions WHERE session_id = $1",
                session_id
            )
            if not row:
                return None
            return {
                "session_id": row["session_id"],
                "title": row["title"],
                "created_at": str(row["created_at"]),
                "last_active_at": str(row["last_active_at"]),
                "is_archived": row["is_archived"]
            }

    async def get_history(self, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """Retrieve recent message history for context window."""
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content FROM messages
                WHERE session_id = $1
                ORDER BY id DESC LIMIT $2
                """,
                session_id, limit * 2
            )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def get_full_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve complete message history for session UI rendering."""
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, role, content, sources, status_logs, is_hallucinated, created_at FROM messages
                WHERE session_id = $1
                ORDER BY id ASC
                """,
                session_id
            )
        messages = []
        for r in rows:
            sources_val = r["sources"]
            if isinstance(sources_val, str):
                try:
                    sources_list = json.loads(sources_val)
                except Exception:
                    sources_list = []
            elif isinstance(sources_val, list):
                sources_list = sources_val
            else:
                sources_list = []

            status_logs_val = r["status_logs"]
            if isinstance(status_logs_val, str):
                try:
                    status_logs_list = json.loads(status_logs_val)
                except Exception:
                    status_logs_list = []
            elif isinstance(status_logs_val, list):
                status_logs_list = status_logs_val
            else:
                status_logs_list = []

            messages.append({
                "id": str(r["id"]),
                "role": r["role"],
                "content": r["content"],
                "sources": sources_list,
                "status_logs": status_logs_list,
                "is_hallucinated": bool(r["is_hallucinated"]),
                "created_at": str(r["created_at"])
            })
        return messages

    async def delete_messages_from_id(self, session_id: str, message_id: int) -> None:
        """Delete messages in a session from message_id onwards for editing."""
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM messages WHERE session_id = $1 AND id >= $2",
                session_id, message_id
            )

    async def save_turn(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        intent: str = "safe",
        sources: Optional[List[Any]] = None,
        status_logs: Optional[List[str]] = None,
        had_pii: bool = False,
        is_hallucinated: bool = False,
        flagged: bool = False
    ) -> None:
        """Persist user-assistant interaction turn."""
        if not self.pool:
            return
        sources_json = json.dumps(sources or [])
        status_logs_json = json.dumps(status_logs or [])
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO sessions (session_id, title, created_at, last_active_at, is_archived)
                    VALUES ($1, 'New Chat', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, FALSE)
                    ON CONFLICT(session_id) DO UPDATE SET last_active_at = CURRENT_TIMESTAMP
                    """,
                    session_id
                )
                await conn.execute(
                    """
                    INSERT INTO messages (session_id, role, content, intent, sources, status_logs, had_pii, is_hallucinated, flagged)
                    VALUES ($1, 'user', $2, $3, '[]'::jsonb, '[]'::jsonb, $4, FALSE, $5)
                    """,
                    session_id, user_msg, intent, had_pii, flagged
                )
                await conn.execute(
                    """
                    INSERT INTO messages (session_id, role, content, intent, sources, status_logs, had_pii, is_hallucinated, flagged)
                    VALUES ($1, 'assistant', $2, $3, $4::jsonb, $5::jsonb, FALSE, $6, $7)
                    """,
                    session_id, assistant_msg, intent, sources_json, status_logs_json, is_hallucinated, flagged
                )

    async def delete_session(self, session_id: str) -> bool:
        """Permanently delete session and messages."""
        if not self.pool:
            return False
        async with self.pool.acquire() as conn:
            res = await conn.execute("DELETE FROM sessions WHERE session_id = $1", session_id)
            return res != "DELETE 0"

    async def get_cache_hash(self, file_path: str) -> Optional[str]:
        """Fetch cached content SHA-256 hash for document."""
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            val = await conn.fetchval("SELECT content_hash FROM knowledge_cache WHERE file_path = $1", file_path)
            return val

    async def update_cache_hash(
        self, file_path: str, content_hash: str, chunk_count: int
    ) -> None:
        """Update or insert document content hash in knowledge_cache."""
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO knowledge_cache (file_path, content_hash, last_ingested_at, chunk_count)
                VALUES ($1, $2, CURRENT_TIMESTAMP, $3)
                ON CONFLICT(file_path) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    last_ingested_at = CURRENT_TIMESTAMP,
                    chunk_count = EXCLUDED.chunk_count
                """,
                file_path, content_hash, chunk_count
            )


session_store = SessionStore()

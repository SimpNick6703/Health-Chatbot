"""SQLite session and knowledge cache store using aiosqlite."""

import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import aiosqlite

from config import settings

logger = logging.getLogger(__name__)


class SessionStore:
    """Async SQLite database store for chat sessions, messages, and RAG knowledge cache."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize session store with database path."""
        self.db_path: str = db_path or settings.SQLITE_PATH

    async def init_db(self) -> None:
        """Create database tables if they do not already exist and run schema migrations."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New Chat',
                    created_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    is_archived INTEGER DEFAULT 0,
                    archived_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent TEXT,
                    sources TEXT,
                    had_pii INTEGER DEFAULT 0,
                    is_hallucinated INTEGER DEFAULT 0,
                    flagged INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_cache (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    last_ingested_at TEXT NOT NULL,
                    chunk_count INTEGER DEFAULT 0
                )
            """)

            # Schema migration check: Ensure title column exists in sessions table
            async with db.execute("PRAGMA table_info(sessions)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "title" not in columns:
                    logger.info("Migrating sessions table: adding 'title' column...")
                    await db.execute("ALTER TABLE sessions ADD COLUMN title TEXT DEFAULT 'New Chat'")

            await db.commit()
            logger.info("Database schema initialized successfully.")

    async def create_session(self, title: str = "New Chat") -> str:
        """Create a new chat session and store in database.

        Args:
            title: Initial session title string.

        Returns:
            Newly generated session_id UUID string.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (session_id, title, created_at, last_active_at, is_archived) VALUES (?, ?, ?, ?, 0)",
                (session_id, title, now, now)
            )
            await db.commit()

        logger.info(f"Created new chat session: {session_id} ('{title}')")
        return session_id

    async def list_active_sessions(self) -> List[Dict[str, Any]]:
        """Retrieve all active (non-archived) sessions that have at least 1 message turn.

        Returns:
            List of session dicts containing session_id, title, created_at, last_active_at.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT s.session_id, s.title, s.created_at, s.last_active_at
                FROM sessions s
                JOIN messages m ON s.session_id = m.session_id
                WHERE s.is_archived = 0 AND s.title IS NOT NULL AND s.title != 'New Chat' AND s.title != ''
                GROUP BY s.session_id
                ORDER BY s.last_active_at DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()

        return [
            {
                "session_id": row[0],
                "title": row[1],
                "created_at": row[2],
                "last_active_at": row[3]
            } for row in rows
        ]

    async def update_session_title(self, session_id: str, title: str) -> bool:
        """Update session title.

        Args:
            session_id: Target session ID.
            title: New title text.

        Returns:
            True if session existed and was updated.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE sessions SET title = ? WHERE session_id = ?",
                (title.strip(), session_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def create_session(self, session_id: str, title: str = "New Chat") -> None:
        """Create a new session if it doesn't exist."""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (session_id, title, created_at, last_active_at, is_archived)
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(session_id) DO NOTHING
                """,
                (session_id, title.strip(), now, now)
            )
            await db.commit()

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch session metadata by session ID.

        Args:
            session_id: Target session ID.

        Returns:
            Session dict or None if not found.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT session_id, title, created_at, last_active_at, is_archived FROM sessions WHERE session_id = ?",
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return {
                    "session_id": row[0],
                    "title": row[1],
                    "created_at": row[2],
                    "last_active_at": row[3],
                    "is_archived": row[4]
                }

    async def get_history(self, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """Retrieve recent conversation turn history for LLM context window.

        Args:
            session_id: Target chat session ID.
            limit: Maximum number of recent message turns to return.

        Returns:
            List of message dicts formatted as [{'role': 'user/assistant', 'content': ...}].
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT role, content FROM messages
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (session_id, limit * 2)
            ) as cursor:
                rows = await cursor.fetchall()

        history = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
        return history

    async def get_full_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve complete detailed message history for session UI rendering.

        Args:
            session_id: Target chat session ID.

        Returns:
            List of message dicts with role, content, sources, is_hallucinated, created_at.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT id, role, content, sources, is_hallucinated, created_at FROM messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,)
            ) as cursor:
                rows = await cursor.fetchall()

        messages = []
        for row in rows:
            sources_list = json.loads(row[3]) if row[3] else []
            messages.append({
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "sources": sources_list,
                "is_hallucinated": bool(row[4]),
                "created_at": row[5]
            })
        return messages

    async def delete_messages_from_id(self, session_id: str, message_id: int) -> None:
        """Atomically delete all messages in a session from a specific message ID onwards.
        Used for message editing to rollback conversation history.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM messages WHERE session_id = ? AND id >= ?",
                (session_id, message_id)
            )
            await db.commit()

    async def save_turn(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        intent: str = "safe",
        sources: Optional[List[Any]] = None,
        had_pii: bool = False,
        is_hallucinated: bool = False,
        flagged: bool = False
    ) -> None:
        """Persist a complete user-assistant interaction turn with observability metadata.

        Args:
            session_id: Active session ID.
            user_msg: Redacted user query message.
            assistant_msg: Final generated assistant response message.
            intent: Classified intent category string.
            sources: List of cited RAG knowledge source filenames.
            had_pii: Whether input contained PII.
            is_hallucinated: Whether response failed hallucination check.
            flagged: Whether turn was flagged by guardrails.
        """
        now = datetime.now(timezone.utc).isoformat()
        flagged_val = 1 if flagged else 0
        pii_val = 1 if had_pii else 0
        hallucinated_val = 1 if is_hallucinated else 0
        sources_str = json.dumps(sources or [])

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (session_id, title, created_at, last_active_at, is_archived)
                VALUES (?, 'New Chat', ?, ?, 0)
                ON CONFLICT(session_id) DO UPDATE SET last_active_at = excluded.last_active_at
                """,
                (session_id, now, now)
            )
            await db.execute(
                """
                INSERT INTO messages (session_id, role, content, intent, sources, had_pii, is_hallucinated, flagged, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, "user", user_msg, intent, "[]", pii_val, 0, flagged_val, now)
            )
            await db.execute(
                """
                INSERT INTO messages (session_id, role, content, intent, sources, had_pii, is_hallucinated, flagged, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, "assistant", assistant_msg, intent, sources_str, 0, hallucinated_val, flagged_val, now)
            )
            await db.commit()

    async def archive_session(self, session_id: str) -> bool:
        """Soft-delete / archive a session rather than purging its records.

        Args:
            session_id: Session ID to archive.

        Returns:
            True if session existed and was archived.
        """
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE sessions SET is_archived = 1, archived_at = ? WHERE session_id = ?",
                (now, session_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_session(self, session_id: str) -> bool:
        """Permanently delete a chat session and all its messages.

        Args:
            session_id: Session ID to delete.

        Returns:
            True if session existed and was deleted.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor = await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_cache_hash(self, file_path: str) -> Optional[str]:
        """Fetch cached content SHA-256 hash for a knowledge document file.

        Args:
            file_path: Relative or absolute file path.

        Returns:
            Stored hash string or None if not cached.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT content_hash FROM knowledge_cache WHERE file_path = ?",
                (file_path,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def update_cache_hash(
        self, file_path: str, content_hash: str, chunk_count: int
    ) -> None:
        """Update or insert document content hash in knowledge_cache table.

        Args:
            file_path: File path key.
            content_hash: SHA-256 hex string.
            chunk_count: Number of chunks indexed into vector DB.
        """
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO knowledge_cache (file_path, content_hash, last_ingested_at, chunk_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    last_ingested_at = excluded.last_ingested_at,
                    chunk_count = excluded.chunk_count
                """,
                (file_path, content_hash, now, chunk_count)
            )
            await db.commit()


session_store = SessionStore()

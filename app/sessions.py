"""
Sessions - Quan ly lich su hoi thoai.

Luu tru in-memory, co TTL va gioi han so luong tin nhan.
Thread-safe de dung voi Flask (multi-thread).
"""

from __future__ import annotations

import time
import uuid
from threading import Lock


class SessionStore:
    """In-memory session store cho lich su hoi thoai."""

    def __init__(self, max_turns: int = 20, ttl_seconds: int = 3600) -> None:
        self._store: dict[str, dict] = {}
        self._lock = Lock()
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def new_id() -> str:
        """Tao session ID moi."""
        return str(uuid.uuid4())

    def get_messages(self, session_id: str) -> list[dict]:
        """Lay lich su tin nhan cua session."""
        with self._lock:
            session = self._store.get(session_id)
            if not session:
                return []
            if time.time() - session["last_access"] > self.ttl_seconds:
                del self._store[session_id]
                return []
            session["last_access"] = time.time()
            return list(session["messages"])

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Them tin nhan vao session."""
        with self._lock:
            if session_id not in self._store:
                self._store[session_id] = {
                    "messages": [],
                    "created_at": time.time(),
                    "last_access": time.time(),
                }
            session = self._store[session_id]
            session["messages"].append({"role": role, "content": content})
            session["last_access"] = time.time()

            # Giu lai toi da max_turns * 2 tin nhan (user + assistant)
            limit = self.max_turns * 2
            if len(session["messages"]) > limit:
                session["messages"] = session["messages"][-limit:]

    def add_tool_exchange(
        self, session_id: str, assistant_msg: dict, tool_results: list[dict]
    ) -> None:
        """Luu tru tool call exchange (assistant message + tool results)."""
        with self._lock:
            if session_id not in self._store:
                self._store[session_id] = {
                    "messages": [],
                    "created_at": time.time(),
                    "last_access": time.time(),
                }
            session = self._store[session_id]
            session["messages"].append(assistant_msg)
            session["messages"].extend(tool_results)
            session["last_access"] = time.time()

    def clear(self, session_id: str) -> None:
        """Xoa session."""
        with self._lock:
            self._store.pop(session_id, None)

    def cleanup_expired(self) -> int:
        """Xoa cac session het han. Tra ve so session da xoa."""
        with self._lock:
            now = time.time()
            expired = [
                sid
                for sid, s in self._store.items()
                if now - s["last_access"] > self.ttl_seconds
            ]
            for sid in expired:
                del self._store[sid]
            return len(expired)

    def active_count(self) -> int:
        """So session dang hoat dong."""
        with self._lock:
            return len(self._store)

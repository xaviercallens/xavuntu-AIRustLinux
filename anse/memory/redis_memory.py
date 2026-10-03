"""
Redis Long-Term Memory Hub for AutoevolveAI / ANSE.

Persists full multi-turn conversations, user prompts, LLM thoughts, tool calls,
and outputs into persistent Redis data structures and streams when Redis is available.

Note: Persistence is guaranteed only when connected to a live Redis instance. When Redis
is unavailable, store_turn() will return False (when strict=False) or raise UnverifiedDataError
(when strict=True) to signal that the turn was NOT persisted.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from anse.infrastructure.fabrication import UnverifiedDataError

logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    step_index: int
    role: str  # "user" | "assistant" | "tool" | "system"
    content: str
    thinking: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""
    status: str = "DONE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationTurn:
        return cls(
            step_index=data.get("step_index", 0),
            role=data.get("role", "assistant"),
            content=data.get("content", ""),
            thinking=data.get("thinking", ""),
            tool_calls=data.get("tool_calls", []),
            timestamp=data.get("timestamp", ""),
            status=data.get("status", "DONE"),
        )


class RedisLongTermMemory:
    """
    Long-term persistent conversation and trace memory backed by Redis (when connected).
    Provides indexing, search, streaming, and full trajectory replay.

    When Redis is unavailable, store_turn() falls back to volatile behavior: returning False
    (if strict=False) or raising UnverifiedDataError (if strict=True) instead of persisting.
    Callers must check the return value or catch the exception to detect when writes fail.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        db: int = 0,
    ) -> None:
        self.host = str(host or os.getenv("REDIS_HOST") or "localhost")
        self.port = int(port or os.getenv("REDIS_PORT") or 6379)
        self.db = db
        self._client: Any = None
        self._connect()

    def _connect(self) -> None:
        try:
            import redis

            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_timeout=2.0,
            )
            self._client.ping()
            logger.info("Connected to Redis Long-Term Memory at %s:%d", self.host, self.port)
        except Exception as e:
            logger.error("Could not connect to Redis at %s:%d: %s", self.host, self.port, e)
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def store_turn(
        self,
        conversation_id: str,
        turn: ConversationTurn,
        publish_stream: bool = True,
        strict: bool = False,
    ) -> bool:
        """
        Store a single dialogue turn into Redis.

        Args:
            conversation_id: Unique conversation identifier
            turn: The conversation turn to store
            publish_stream: Whether to publish to the event stream
            strict: If True, raise UnverifiedDataError when Redis is unavailable.
                   If False (default), return False and log at ERROR level.

        Returns:
            True if successfully persisted to Redis, False otherwise.

        Raises:
            UnverifiedDataError: If strict=True and Redis is not connected.
        """
        turns_key = f"antigravity:conversation:{conversation_id}:turns"
        if not self._client:
            if strict:
                logger.error("Cannot store turn for conversation %s: Redis not connected, strict mode enabled", conversation_id)
                raise UnverifiedDataError(
                    f"Cannot persist turn for conversation {conversation_id}: Redis unavailable",
                    component="RedisLongTermMemory",
                    remedy="Ensure Redis is running and reachable, or pass strict=False to allow data loss"
                )
            else:
                logger.error("Cannot store turn for conversation %s: Redis not connected, data lost", conversation_id)
                return False

        pipe = self._client.pipeline()
        turn_json = json.dumps(turn.to_dict())

        # 1. Append to conversation turns list
        pipe.rpush(turns_key, turn_json)

        # 2. Add to global conversations set
        pipe.sadd("antigravity:conversations:all", conversation_id)

        # 3. Update conversation metadata hash
        meta_key = f"antigravity:conversation:{conversation_id}:meta"
        pipe.hincrby(meta_key, "total_turns", 1)
        if turn.role == "user":
            pipe.hincrby(meta_key, "user_turns", 1)
        elif turn.role == "assistant":
            pipe.hincrby(meta_key, "assistant_turns", 1)
        pipe.hset(meta_key, "last_updated", turn.timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ"))

        # 4. Publish to streaming event bus
        if publish_stream:
            stream_payload = {
                "conversation_id": conversation_id,
                "step_index": str(turn.step_index),
                "role": turn.role,
                "content_preview": (turn.content[:300] + "...") if len(turn.content) > 300 else turn.content,
                "has_tool_calls": "1" if turn.tool_calls else "0",
                "timestamp": turn.timestamp,
            }
            pipe.xadd("antigravity:stream:conversations", stream_payload, maxlen=100000)

        pipe.execute()
        return True

    def store_full_conversation(
        self,
        conversation_id: str,
        turns: list[ConversationTurn],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Atomically persist an entire conversation trajectory via pipelined batch."""
        if not self._client or not turns:
            return 0

        turns_key = f"antigravity:conversation:{conversation_id}:turns"
        meta_key = f"antigravity:conversation:{conversation_id}:meta"

        pipe = self._client.pipeline()
        pipe.delete(turns_key)

        user_count = 0
        assistant_count = 0

        for turn in turns:
            turn_json = json.dumps(turn.to_dict())
            pipe.rpush(turns_key, turn_json)
            if turn.role == "user":
                user_count += 1
            elif turn.role == "assistant":
                assistant_count += 1

        pipe.sadd("antigravity:conversations:all", conversation_id)

        meta_dict: dict[str, Any] = {
            "conversation_id": conversation_id,
            "total_turns": len(turns),
            "user_turns": user_count,
            "assistant_turns": assistant_count,
            "first_timestamp": turns[0].timestamp if turns else "",
            "last_timestamp": turns[-1].timestamp if turns else "",
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if metadata:
            meta_dict.update({k: str(v) for k, v in metadata.items()})

        pipe.hset(meta_key, mapping=meta_dict)

        # Store complete searchable document
        doc_key = f"antigravity:memory:long_term:{conversation_id}"
        doc_body = {
            "conversation_id": conversation_id,
            "metadata": meta_dict,
            "turns": [t.to_dict() for t in turns],
        }
        pipe.set(doc_key, json.dumps(doc_body))

        pipe.execute()
        return len(turns)

    def get_conversation_turns(self, conversation_id: str) -> list[ConversationTurn]:
        """Fetch all stored turns for a given conversation."""
        if not self._client:
            return []
        turns_key = f"antigravity:conversation:{conversation_id}:turns"
        raw_items = self._client.lrange(turns_key, 0, -1)
        turns = []
        for raw in raw_items:
            try:
                turns.append(ConversationTurn.from_dict(json.loads(raw)))
            except Exception:
                continue
        return turns

    def get_conversation_metadata(self, conversation_id: str) -> dict[str, str]:
        """Fetch metadata for a given conversation."""
        if not self._client:
            return {}
        meta_key = f"antigravity:conversation:{conversation_id}:meta"
        return dict(self._client.hgetall(meta_key))

    def list_all_conversations(self) -> list[str]:
        """List all indexed conversation IDs."""
        if not self._client:
            return []
        return sorted(list(self._client.smembers("antigravity:conversations:all")))

    def count_total_turns(self) -> int:
        """Count total dialogue turns recorded across all conversations in Redis."""
        if not self._client:
            return 0
        convs = self.list_all_conversations()
        total = 0
        for cid in convs:
            meta = self.get_conversation_metadata(cid)
            total += int(meta.get("total_turns", 0))
        return total

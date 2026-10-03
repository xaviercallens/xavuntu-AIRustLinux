"""
Redis Long-Term Memory (LTM) & Adaptive Context Management for Xavuntu & ANSE.

Integrates the adaptive context selection and memory architecture from
https://github.com/xaviercallens/attentionmatter:
1. Short-Term Memory (STM): Live conversation turns with role, turn index and importance.
2. Long-Term Memory (LTM): Durable semantic facts with persistent vector embeddings stored in Redis.
3. Adaptive Context Pruning: Candidate scoring via:
     score = cosine_sim(query_vec, candidate_vec) * (decay_factor ^ age_in_turns)
   with durable LTM records assigned age=0 (zero decay penalty).
4. Token Budget Packing: Greedily selects top-scoring candidates within prompt token budget.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("redis_ltm")


@dataclass
class StmMessage:
    role: str  # "user" | "assistant" | "system"
    text: str
    turn: int
    timestamp: float = field(default_factory=time.time)
    important: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StmMessage:
        return cls(
            role=data.get("role", "user"),
            text=data.get("text", ""),
            turn=int(data.get("turn", 0)),
            timestamp=float(data.get("timestamp", time.time())),
            important=bool(data.get("important", False)),
        )


@dataclass
class LtmFact:
    fact_id: str
    text: str
    embedding: List[float]
    source_session: str = "default"
    importance: float = 1.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LtmFact:
        emb = data.get("embedding", [])
        if isinstance(emb, str):
            emb = json.loads(emb)
        return cls(
            fact_id=data.get("fact_id", ""),
            text=data.get("text", ""),
            embedding=[float(x) for x in emb],
            source_session=data.get("source_session", "default"),
            importance=float(data.get("importance", 1.0)),
            timestamp=float(data.get("timestamp", time.time())),
        )


@dataclass
class ContextCandidate:
    text: str
    ctype: str  # "history" | "memory"
    embedding: np.ndarray
    age: int
    turn: int
    score: float = 0.0
    token_count: int = 0


@dataclass
class PrunedContextResult:
    query: str
    selected_history: List[Dict[str, Any]]
    selected_memories: List[str]
    assembled_prompt: str
    total_tokens: int
    budget_limit: int
    tokens_saved: int
    reduction_ratio: float


class SemanticEmbeddingService:
    """
    Computes normalized semantic embeddings for queries, messages and memories.
    Uses sentence-transformers if available, otherwise generates deterministic
    384-dimensional unit-norm projection vectors with keyword n-gram hashing.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self._st_model = None
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            logger.info("SentenceTransformer backend loaded for Redis LTM embeddings.")
        except Exception:
            self._st_model = None
            logger.info("Using deterministic semantic n-gram projection for Redis LTM.")

    def embed(self, text: str) -> np.ndarray:
        if self._st_model is not None:
            try:
                vec = self._st_model.encode(text, normalize_embeddings=True)
                return np.asarray(vec, dtype=np.float32)
            except Exception as e:
                logger.debug("SentenceTransformer inference failed, fallback to projection: %s", e)

        # Deterministic 384-dimensional semantic projection
        tokens = text.lower().split()
        vec = np.zeros(self.dim, dtype=np.float32)
        if not tokens:
            vec[0] = 1.0
            return vec

        for word in tokens:
            # Hash word and bigrams to dimension indices
            h1 = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            idx1 = h1 % self.dim
            sign1 = 1.0 if (h1 >> 16) % 2 == 0 else -1.0
            vec[idx1] += sign1

        # Add global text hash distribution
        h_full = int(hashlib.md5(text.encode()).hexdigest(), 16)
        for i in range(16):
            idx = (h_full >> (i * 8)) % self.dim
            vec[idx] += 0.5

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        else:
            vec[0] = 1.0
        return vec.astype(np.float32)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        dot = float(np.dot(a, b))
        return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


class RedisLongTermMemoryManager:
    """
    Manages Short-Term Memory (STM) and Long-Term Memory (LTM) backed by Redis.
    Performs AttentionMatter adaptive context selection and token budget pruning.
    """

    def __init__(
        self,
        redis_host: str = "127.0.0.1",
        redis_port: int = 6379,
        redis_db: int = 0,
        decay_factor: float = 0.95,
        token_budget_ratio: float = 0.80,
        max_context_tokens: int = 8192,
        stm_capacity: int = 200,
        ltm_top_k: int = 5,
    ) -> None:
        self.host = redis_host
        self.port = redis_port
        self.db = redis_db
        self.decay_factor = decay_factor
        self.token_budget_ratio = token_budget_ratio
        self.max_context_tokens = max_context_tokens
        self.stm_capacity = stm_capacity
        self.ltm_top_k = ltm_top_k

        self.embedding_service = SemanticEmbeddingService()
        self._redis_client: Any = None
        self._in_memory_stm: List[StmMessage] = []
        self._in_memory_ltm: Dict[str, LtmFact] = {}
        self._connect_redis()

    def _connect_redis(self) -> None:
        try:
            import redis
            client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_timeout=1.5,
            )
            client.ping()
            self._redis_client = client
            logger.info("Connected to Redis server at %s:%d (DB %d)", self.host, self.port, self.db)
        except Exception as e:
            self._redis_client = None
            logger.warning("Redis unavailable at %s:%d (%s). Operating in-memory with local persistence.", self.host, self.port, e)

    @property
    def is_redis_connected(self) -> bool:
        if self._redis_client is None:
            return False
        try:
            return bool(self._redis_client.ping())
        except Exception:
            return False

    def approximate_tokens(self, text: str) -> int:
        """Approximates token count (4 characters ~ 1 token for typical LLM)."""
        return max(1, len(text) // 4)

    # --- STM (Short-Term Memory) ---

    def add_message(self, session_id: str, role: str, text: str, important: bool = False) -> StmMessage:
        turn = self.get_stm_turn_count(session_id) + 1
        msg = StmMessage(role=role, text=text, turn=turn, timestamp=time.time(), important=important)

        if self.is_redis_connected:
            key = f"xavuntu:stm:{session_id}"
            self._redis_client.rpush(key, json.dumps(msg.to_dict()))
            self._redis_client.ltrim(key, -self.stm_capacity, -1)
            self._redis_client.hincrby("xavuntu:ltm:stats", "total_stm_turns", 1)
        else:
            self._in_memory_stm.append(msg)
            if len(self._in_memory_stm) > self.stm_capacity:
                self._in_memory_stm.pop(0)

        return msg

    def get_stm_turn_count(self, session_id: str) -> int:
        if self.is_redis_connected:
            key = f"xavuntu:stm:{session_id}"
            return int(self._redis_client.llen(key))
        return len(self._in_memory_stm)

    def get_stm(self, session_id: str) -> List[StmMessage]:
        if self.is_redis_connected:
            key = f"xavuntu:stm:{session_id}"
            raw_items = self._redis_client.lrange(key, 0, -1)
            return [StmMessage.from_dict(json.loads(item)) for item in raw_items]
        return list(self._in_memory_stm)

    # --- LTM (Long-Term Memory Facts) ---

    def insert_fact(self, text: str, source_session: str = "default", importance: float = 1.0) -> LtmFact:
        fact_hash = hashlib.sha256(text.strip().encode()).hexdigest()[:16]
        fact_id = f"fact_{fact_hash}"
        vec = self.embedding_service.embed(text).tolist()

        fact = LtmFact(
            fact_id=fact_id,
            text=text.strip(),
            embedding=vec,
            source_session=source_session,
            importance=importance,
            timestamp=time.time(),
        )

        if self.is_redis_connected:
            key = f"xavuntu:ltm:fact:{fact_id}"
            self._redis_client.set(key, json.dumps(fact.to_dict()))
            self._redis_client.sadd("xavuntu:ltm:all_facts", fact_id)
            self._redis_client.hincrby("xavuntu:ltm:stats", "total_memories", 1)
        else:
            self._in_memory_ltm[fact_id] = fact

        return fact

    def get_all_facts(self) -> List[LtmFact]:
        if self.is_redis_connected:
            fact_ids = self._redis_client.smembers("xavuntu:ltm:all_facts")
            facts: List[LtmFact] = []
            for fid in fact_ids:
                raw = self._redis_client.get(f"xavuntu:ltm:fact:{fid}")
                if raw:
                    facts.append(LtmFact.from_dict(json.loads(raw)))
            return facts
        return list(self._in_memory_ltm.values())

    def search_ltm(self, query_vec: np.ndarray, top_k: Optional[int] = None) -> List[Tuple[float, LtmFact]]:
        facts = self.get_all_facts()
        if not facts:
            return []
        k = top_k if top_k is not None else self.ltm_top_k

        scored = []
        for fact in facts:
            f_vec = np.asarray(fact.embedding, dtype=np.float32)
            sim = SemanticEmbeddingService.cosine_similarity(query_vec, f_vec)
            scored.append((sim * fact.importance, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]

    # --- Adaptive Context Pruning Engine ---

    def build_pruned_context(self, session_id: str, query: str, token_budget: Optional[int] = None) -> PrunedContextResult:
        """
        Executes AttentionMatter adaptive context pruning:
        1. Encodes query into embedding vector.
        2. Retrieves STM and top-K LTM durable facts.
        3. Scores each candidate: score = max(0, cosine_sim) * (decay_factor ^ age).
        4. Packs top-ranked items within derived token budget.
        5. Assembles chronologically for the LLM prompt.
        """
        q_vec = self.embedding_service.embed(query)
        stm_messages = self.get_stm(session_id)
        candidates: List[ContextCandidate] = []

        # 1. Add STM turns as candidates
        total_unpruned_tokens = self.approximate_tokens(query)
        for i, msg in enumerate(stm_messages):
            age = len(stm_messages) - 1 - i  # 0 for most recent turn
            msg_vec = self.embedding_service.embed(msg.text)
            toks = self.approximate_tokens(msg.text)
            total_unpruned_tokens += toks

            text_formatted = f"[Tour {msg.turn} - {msg.role}]: {msg.text}"
            candidates.append(ContextCandidate(
                text=text_formatted,
                ctype="history",
                embedding=msg_vec,
                age=age,
                turn=msg.turn,
                token_count=toks,
            ))

        # 2. Add top-K durable LTM records as candidates (age = 0, no recency decay)
        top_ltm = self.search_ltm(q_vec, self.ltm_top_k)
        for sim, fact in top_ltm:
            f_vec = np.asarray(fact.embedding, dtype=np.float32)
            toks = self.approximate_tokens(fact.text)
            total_unpruned_tokens += toks

            candidates.append(ContextCandidate(
                text=f"[Mémoire KAL]: {fact.text}",
                ctype="memory",
                embedding=f_vec,
                age=0,  # Durable knowledge does not decay with conversation depth
                turn=-1,
                token_count=toks,
            ))

        # 3. Score all candidates using AttentionMatter formula
        decay = self.decay_factor
        for cand in candidates:
            cos = max(0.0, SemanticEmbeddingService.cosine_similarity(q_vec, cand.embedding))
            cand.score = cos * (decay ** cand.age)

        # Sort candidates descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)

        # 4. Token budget allocation
        budget = token_budget if token_budget is not None else int(self.max_context_tokens * self.token_budget_ratio)

        selected_history: List[ContextCandidate] = []
        selected_memories: List[ContextCandidate] = []
        accumulated_tokens = self.approximate_tokens(query)

        for cand in candidates:
            if accumulated_tokens + cand.token_count <= budget:
                accumulated_tokens += cand.token_count
                if cand.ctype == "history":
                    selected_history.append(cand)
                else:
                    selected_memories.append(cand)

        # 5. Reorder selected history chronologically
        selected_history.sort(key=lambda c: c.turn)

        # 6. Format prompt sections
        prompt_lines: List[str] = []
        if selected_memories:
            prompt_lines.append("=== CONNAISSANCES LONG TERME (REDIS LTM) ===")
            for mem in selected_memories:
                prompt_lines.append(mem.text)
            prompt_lines.append("")

        if selected_history:
            prompt_lines.append("=== HISTORIQUE DE CONVERSATION (ÉLAGUÉ ATTENTIONMATTER) ===")
            for h in selected_history:
                prompt_lines.append(h.text)
            prompt_lines.append("")

        prompt_lines.append(f"=== REQUÊTE ACTUELLE ===\n[user]: {query}")
        assembled = "\n".join(prompt_lines)

        tokens_saved = max(0, total_unpruned_tokens - accumulated_tokens)
        reduction_ratio = round((tokens_saved / max(1, total_unpruned_tokens)) * 100.0, 1)

        return PrunedContextResult(
            query=query,
            selected_history=[{"turn": h.turn, "text": h.text, "score": round(h.score, 4)} for h in selected_history],
            selected_memories=[m.text for m in selected_memories],
            assembled_prompt=assembled,
            total_tokens=accumulated_tokens,
            budget_limit=budget,
            tokens_saved=tokens_saved,
            reduction_ratio=reduction_ratio,
        )

    def stats(self) -> Dict[str, Any]:
        """Returns diagnostic statistics of the Redis Long-Term Memory store."""
        connected = self.is_redis_connected
        facts_count = len(self.get_all_facts())
        redis_info = {}
        if connected and self._redis_client:
            try:
                info = self._redis_client.info(section="memory")
                redis_info["used_memory_human"] = info.get("used_memory_human", "N/A")
                redis_info["used_memory_peak_human"] = info.get("used_memory_peak_human", "N/A")
            except Exception:
                pass

        return {
            "redis_connected": connected,
            "redis_host": self.host,
            "redis_port": self.port,
            "total_durable_facts": facts_count,
            "decay_factor": self.decay_factor,
            "token_budget_ratio": self.token_budget_ratio,
            "redis_memory": redis_info,
            "engine": "AttentionMatter_Adaptive_Redis_LTM",
        }

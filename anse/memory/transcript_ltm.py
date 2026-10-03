"""Import Claude Code session transcripts into long-term memory.

Claude Code already persists every session as JSONL under
`~/.claude/projects/<slug>/<session-id>.jsonl`: user prompts, assistant
replies, tool calls and tool results. `docs/ROADMAP_V1_V2_COMPANION.md` §4.1
observes that a nightly importer over those files is sufficient to build
long-term memory with no live plumbing, and that is what this module is.

Two hard constraints, both taken from that roadmap's §4.5, both enforced here
rather than documented and hoped for:

1. **Scrubbing is a gate, not a pass.** Transcripts contain tokens, keys,
   absolute home paths and e-mail addresses. `scrub()` runs before anything is
   persisted, and `ScrubReport` records what it removed so a run that scrubbed
   nothing from a corpus full of secrets is visibly suspicious rather than
   silently clean.

2. **These records are retrieval-only.** Provider terms restrict using
   assistant outputs as training targets. Every record is therefore written
   with `trainable: False` and `usage: "retrieval_only"`, and
   `iter_training_candidates()` deliberately does not exist in this module.
   The defensible design the roadmap describes trains on *this project's own*
   artifacts -- diffs, test outcomes, verifier results, and the local model's
   own samples -- and uses assistant transcripts for retrieval and episode
   segmentation only. Changing that is a policy decision for the repository
   owner, not a code change to make casually.

Storage is dual, mirroring `anse/memory/harvester.py`: Redis for durable
key-addressed recall, Chroma for semantic retrieval. Redis being unreachable
raises; it does not silently degrade to a dict (the defect
`anse/memory/redis_memory.py` was found to have).
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CLAUDE_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_ANTIGRAVITY_ROOT = Path.home() / ".gemini" / "antigravity-cli" / "brain"
DEFAULT_TRANSCRIPT_ROOT = DEFAULT_CLAUDE_ROOT
REDIS_KEY_PREFIX = "anse:ltm:transcript"
CHROMA_COLLECTION = "claude_code_sessions"

# Ordered most-specific-first: a GitHub token would also match the generic
# high-entropy rule, and the specific label is more useful in the report.
_SCRUB_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{32,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("home_path", re.compile(r"/home/[A-Za-z0-9_.\-]+")),
)


@dataclass
class ScrubReport:
    """Counts per pattern. Visible so an implausibly clean run is noticeable."""

    replacements: dict[str, int] = field(default_factory=dict)

    def record(self, label: str, count: int) -> None:
        if count:
            self.replacements[label] = self.replacements.get(label, 0) + count

    @property
    def total(self) -> int:
        return sum(self.replacements.values())


def scrub(text: str, report: ScrubReport | None = None) -> str:
    """Remove credentials, e-mail addresses and absolute home paths."""
    cleaned = text
    for label, pattern in _SCRUB_PATTERNS:
        cleaned, count = pattern.subn(f"[REDACTED:{label}]", cleaned)
        if report is not None:
            report.record(label, count)
    return cleaned


@dataclass
class TranscriptTurn:
    """One turn of a session, already scrubbed."""

    session_id: str
    project_slug: str
    turn_index: int
    role: str
    text: str
    tool_names: list[str] = field(default_factory=list)
    timestamp: str | None = None
    # See module docstring: provider terms. Not a suggestion.
    trainable: bool = False
    usage: str = "retrieval_only"
    has_content: bool = True

    @property
    def record_id(self) -> str:
        return f"{self.session_id}:{self.turn_index}"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text_from_content(content: Any) -> tuple[str, list[str]]:
    """Flatten Claude Code's content field to text plus any tool names seen."""
    if isinstance(content, str):
        return content, []

    parts: list[str] = []
    tools: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and block.get("text"):
                parts.append(str(block["text"]))
            elif block_type == "thinking" and block.get("thinking"):
                parts.append(str(block["thinking"]))
            elif block_type == "tool_use":
                name = str(block.get("name", "unknown"))
                tools.append(name)
                parts.append(f"[tool_use:{name}] {json.dumps(block.get('input', {}))[:2000]}")
            elif block_type == "tool_result":
                raw = block.get("content")
                rendered = raw if isinstance(raw, str) else json.dumps(raw)[:2000]
                parts.append(f"[tool_result] {rendered}")
    return "\n".join(parts), tools


def parse_transcript(path: Path, scrub_report: ScrubReport | None = None) -> list[TranscriptTurn]:
    """Read one session JSONL (Claude Code or Antigravity) into scrubbed turns.

    Malformed lines are skipped with a warning rather than aborting the file --
    transcripts are append-only logs and a truncated final line is normal.
    """
    is_antigravity = (
        "brain" in path.parts
        or ".system_generated" in path.parts
        or path.name.startswith("transcript")
    )
    if is_antigravity and ".system_generated" in path.parts:
        session_id = path.parents[2].name
        project_slug = "antigravity"
    else:
        session_id = path.stem
        project_slug = path.parent.name
    turns: list[TranscriptTurn] = []

    with path.open(encoding="utf-8") as handle:
        for turn_index, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("%s line %d: %s", path.name, turn_index, exc)
                continue

            if not isinstance(event, dict):
                continue

            # Claude Code format
            if "message" in event and isinstance(event.get("message"), dict):
                message = event["message"]
                role = message.get("role")
                if role not in ("user", "assistant"):
                    continue

                text, tools = _text_from_content(message.get("content"))
                if not text.strip():
                    continue

                turns.append(
                    TranscriptTurn(
                        session_id=session_id,
                        project_slug=project_slug,
                        turn_index=turn_index,
                        role=str(role),
                        text=scrub(text, scrub_report),
                        tool_names=tools,
                        timestamp=event.get("timestamp"),
                    )
                )

            # Antigravity format
            elif "step_index" in event or "type" in event or "source" in event:
                type_name = str(event.get("type", ""))
                source = str(event.get("source", ""))
                step_idx = int(event.get("step_index", turn_index))
                timestamp = event.get("created_at")

                if type_name == "USER_INPUT" or source == "USER_EXPLICIT":
                    role = "user"
                    text = str(event.get("content", ""))
                    tools = []
                    has_content = True
                elif type_name == "PLANNER_RESPONSE":
                    role = "assistant"
                    content = str(event.get("content", ""))
                    thinking = str(event.get("thinking", ""))
                    tool_calls = event.get("tool_calls") or []
                    tools = [tc.get("name", "") for tc in tool_calls if isinstance(tc, dict)]
                    has_content = bool(content.strip())
                    parts = []
                    if content.strip():
                        parts.append(content.strip())
                    if thinking.strip():
                        parts.append(f"[thinking]\n{thinking.strip()}")
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            parts.append(f"[tool_call:{tc.get('name')}] {json.dumps(tc.get('args', {}))[:1000]}")
                    text = "\n".join(parts)
                elif type_name in ("GENERIC", "SYSTEM_MESSAGE") or source in ("SYSTEM", "MODEL"):
                    role = "tool" if type_name == "GENERIC" else "system"
                    text = str(event.get("content", ""))
                    tools = []
                    has_content = False
                else:
                    continue

                if not text.strip():
                    continue

                turns.append(
                    TranscriptTurn(
                        session_id=session_id,
                        project_slug=project_slug,
                        turn_index=step_idx,
                        role=role,
                        text=scrub(text, scrub_report),
                        tool_names=tools,
                        timestamp=timestamp,
                        has_content=has_content if role == "assistant" else (role == "user"),
                    )
                )

    return turns


# Must stay under the 4096-token runtime window Ollama gives the embedding model.
# ~4 chars/token holds for prose only: on 2026-09-28 a 6000-char chunk of agent
# transcript (sha256 hex, JSON, Lean Unicode) exceeded the window ("input length
# exceeds the context length") and aborted the whole ingest. 3500 chars stays under
# 4096 tokens even at ~1 char/token. Overlap keeps a sentence that straddles a
# boundary retrievable from at least one window.
EMBED_CHUNK_CHARS = 3500
EMBED_CHUNK_OVERLAP = 400


def _chunk_for_embedding(
    text: str,
    chunk_chars: int = EMBED_CHUNK_CHARS,
    overlap: int = EMBED_CHUNK_OVERLAP,
) -> list[str]:
    """Split a turn into windows that fit the embedding model's runtime context.

    Always returns at least one non-empty chunk, because the caller has already
    established the turn has text and the embedding function rejects empty input.
    """
    stripped = text.strip()
    if len(stripped) <= chunk_chars:
        return [stripped]

    chunks: list[str] = []
    start = 0
    while start < len(stripped):
        end = min(start + chunk_chars, len(stripped))
        window = stripped[start:end].strip()
        if window:
            chunks.append(window)
        if end >= len(stripped):
            break
        start = max(end - overlap, start + 1)
    return chunks or [stripped[:chunk_chars]]


def iter_transcripts(
    root: Path | str | Sequence[Path | str] | None = None,
) -> Iterator[Path]:
    """Yield every session JSONL under Claude Code and/or Antigravity roots."""
    if root is None:
        autoevolve_claude = DEFAULT_CLAUDE_ROOT / "-home-xavkal-xdev-AutoevolveAI"
        roots: list[Path] = []
        if autoevolve_claude.exists():
            roots.append(autoevolve_claude)
        roots.append(DEFAULT_ANTIGRAVITY_ROOT)
        roots.append(DEFAULT_CLAUDE_ROOT)
    elif isinstance(root, (list, tuple)):
        roots = [Path(r) for r in root]
    else:
        roots = [Path(root)]

    seen: set[Path] = set()
    for r in roots:
        if not r.exists():
            continue
        if "antigravity" in str(r) or "brain" in str(r):
            for session_dir in sorted(
                r.iterdir(),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            ):
                if session_dir.is_dir():
                    full = session_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
                    compact = session_dir / ".system_generated" / "logs" / "transcript.jsonl"
                    target = full if full.exists() else (compact if compact.exists() else None)
                    if target and target not in seen:
                        seen.add(target)
                        yield target
        else:
            for p in sorted(
                r.rglob("*.jsonl"),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            ):
                if p not in seen:
                    seen.add(p)
                    yield p


class TranscriptLTM:
    """Dual-write long-term memory: Redis for recall, Chroma for retrieval."""

    def __init__(
        self,
        redis_url: str | None = None,
        chroma_directory: Path | str | None = None,
        collection: str = CHROMA_COLLECTION,
        enable_chroma: bool = True,
    ) -> None:
        import redis

        self.redis_url = redis_url or os.environ.get(
            "ANSE_REDIS_URL", "redis://localhost:6379/0"
        )
        # from_url does not connect; ping() is what proves the backend is there.
        self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        self._redis.ping()

        self._collection = None
        if enable_chroma and chroma_directory is not None:
            import chromadb

            from anse.memory.ollama_embeddings import OllamaEmbeddingFunction

            directory = Path(chroma_directory)
            directory.mkdir(parents=True, exist_ok=True)
            self._embedding_function = OllamaEmbeddingFunction()
            client = chromadb.PersistentClient(path=str(directory))
            self._collection = client.get_or_create_collection(
                name=collection,
                embedding_function=self._embedding_function,
                metadata={"hnsw:space": "cosine"},
            )

    def already_indexed(self, record_id: str) -> bool:
        """True if the first chunk of this turn is already in Chroma."""
        if self._collection is None:
            return False
        existing = self._collection.get(ids=[f"{record_id}:0"], limit=1)
        return bool(existing.get("ids"))

    def store_turns(self, turns: Sequence[TranscriptTurn], batch_size: int = 32) -> int:
        """Write a sequence of turns to Redis (pipelined) and Chroma (batched).

        Returns the number of chunks written to Chroma.
        """
        if not turns:
            return 0

        pipe = self._redis.pipeline()
        for turn in turns:
            key = f"{REDIS_KEY_PREFIX}:{turn.record_id}"
            pipe.hset(
                key,
                mapping={
                    "session_id": turn.session_id,
                    "project_slug": turn.project_slug,
                    "turn_index": str(turn.turn_index),
                    "role": turn.role,
                    "text": turn.text,
                    "tool_names": json.dumps(turn.tool_names),
                    "timestamp": turn.timestamp or "",
                    "trainable": "0",
                    "usage": turn.usage,
                },
            )
            pipe.sadd(f"{REDIS_KEY_PREFIX}:sessions", turn.session_id)
        pipe.execute()

        chunks_written = 0
        if self._collection is not None:
            batch_ids: list[str] = []
            batch_docs: list[str] = []
            batch_metas: list[dict[str, Any]] = []

            for turn in turns:
                # System notifications and pure internal tool executions carry no semantic query value
                if turn.role in ("system", "tool") or not turn.text.strip():
                    continue
                if turn.role == "assistant" and not turn.has_content:
                    continue
                if self.already_indexed(turn.record_id):
                    continue

                chunks = _chunk_for_embedding(turn.text)
                base = {
                    "session_id": turn.session_id,
                    "project_slug": turn.project_slug,
                    "role": turn.role,
                    "turn_index": turn.turn_index,
                    "tool_names": ",".join(turn.tool_names),
                    "trainable": False,
                    "usage": turn.usage,
                    "chunks": len(chunks),
                }
                for i, chunk in enumerate(chunks):
                    batch_ids.append(f"{turn.record_id}:{i}")
                    batch_docs.append(chunk)
                    batch_metas.append({**base, "chunk_index": i})

                if len(batch_ids) >= batch_size:
                    self._collection.upsert(
                        ids=batch_ids,
                        documents=batch_docs,
                        metadatas=batch_metas,
                    )
                    chunks_written += len(batch_ids)
                    batch_ids, batch_docs, batch_metas = [], [], []

            if batch_ids:
                self._collection.upsert(
                    ids=batch_ids,
                    documents=batch_docs,
                    metadatas=batch_metas,
                )
                chunks_written += len(batch_ids)

        return chunks_written

    def store_turn(self, turn: TranscriptTurn) -> None:
        """Write one turn to Redis, and to Chroma when enabled."""
        self.store_turns([turn])

    def turn_count(self) -> int:
        """Number of turn records currently in Redis."""
        return len(list(self._redis.scan_iter(match=f"{REDIS_KEY_PREFIX}:*:*", count=1000)))

    def session_ids(self) -> set[str]:
        return set(self._redis.smembers(f"{REDIS_KEY_PREFIX}:sessions"))

    def search(self, question: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Semantic search over stored turns."""
        if self._collection is None:
            raise RuntimeError("Chroma is not enabled on this TranscriptLTM instance")
        results = self._collection.query(query_texts=[question], n_results=n_results)
        ids = results.get("ids") or [[]]
        if not ids[0]:
            return []
        return [
            {
                "id": ids[0][i],
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
            for i in range(len(ids[0]))
        ]


def import_all(
    root: Path | str | Sequence[Path | str] | None = None,
    redis_url: str | None = None,
    chroma_directory: Path | str | None = None,
    limit_files: int | None = None,
) -> dict[str, Any]:
    """Import every available transcript. Returns a report of what was stored."""
    scrub_report = ScrubReport()
    ltm = TranscriptLTM(
        redis_url=redis_url,
        chroma_directory=chroma_directory,
        enable_chroma=chroma_directory is not None,
    )

    files_read = 0
    turns_stored = 0
    chunks_stored = 0
    for path in iter_transcripts(root):
        if limit_files is not None and files_read >= limit_files:
            break
        turns = parse_transcript(path, scrub_report)
        chunks_stored += ltm.store_turns(turns)
        turns_stored += len(turns)
        files_read += 1

    return {
        "files_read": files_read,
        "turns_stored": turns_stored,
        "chunks_stored": chunks_stored,
        "sessions": len(ltm.session_ids()),
        "scrub": {"total_replacements": scrub_report.total, "by_pattern": scrub_report.replacements},
        "usage_policy": "retrieval_only -- not training targets (see module docstring)",
    }

#!/usr/bin/env python3
"""
Sync all Antigravity conversations, user prompts, and LLM outputs to Redis Long-Term Memory.

Parses local transcript logs from ~/.gemini/antigravity-cli/brain/ and streams/persists
every interaction, thought, tool execution, and response to Redis.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from anse.memory.redis_memory import ConversationTurn, RedisLongTermMemory  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BRAIN_DIR = Path.home() / ".gemini" / "antigravity-cli" / "brain"


def parse_transcript_file(transcript_path: Path) -> list[ConversationTurn]:
    """Parse JSONL transcript into a sequence of ConversationTurns."""
    turns: list[ConversationTurn] = []
    if not transcript_path.exists():
        return turns

    with transcript_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            step_index = int(data.get("step_index", len(turns)))
            step_type = data.get("type", "")
            source = data.get("source", "")
            created_at = data.get("created_at", "")
            status = data.get("status", "DONE")

            # Determine role
            if step_type == "USER_INPUT" or source == "USER_EXPLICIT":
                role = "user"
                content = str(data.get("content", ""))
                thinking = ""
                tool_calls = []
            elif source == "MODEL" or step_type in ("PLANNER_RESPONSE", "GENERIC"):
                role = "assistant"
                content = str(data.get("content", ""))
                thinking = str(data.get("thinking", ""))
                tool_calls = data.get("tool_calls", [])
            else:
                role = "system"
                content = str(data.get("content", ""))
                thinking = ""
                tool_calls = []

            turns.append(
                ConversationTurn(
                    step_index=step_index,
                    role=role,
                    content=content,
                    thinking=thinking,
                    tool_calls=tool_calls,
                    timestamp=created_at,
                    status=status,
                )
            )

    return turns


def sync_all_conversations(
    brain_dir: Path | None = None,
    host: str | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    brain = brain_dir or DEFAULT_BRAIN_DIR
    if not brain.exists():
        raise FileNotFoundError(f"Brain directory not found at {brain}")

    memory = RedisLongTermMemory(host=host, port=port)
    if not memory.is_connected:
        raise ConnectionError(f"Could not connect to Redis server at {memory.host}:{memory.port}")

    conv_dirs = [
        d for d in brain.iterdir()
        if d.is_dir() and (d / ".system_generated" / "logs").exists()
    ]
    logger.info("Found %d conversation directories in %s", len(conv_dirs), brain)

    synced_conversations = 0
    total_turns_synced = 0
    total_user_prompts = 0
    total_llm_outputs = 0

    t0 = time.perf_counter()

    for d in sorted(conv_dirs, key=lambda x: x.name):
        cid = d.name
        log_dir = d / ".system_generated" / "logs"
        full_transcript = log_dir / "transcript_full.jsonl"
        compact_transcript = log_dir / "transcript.jsonl"

        target_file = full_transcript if full_transcript.exists() else compact_transcript
        if not target_file.exists():
            continue

        turns = parse_transcript_file(target_file)
        if not turns:
            continue

        # Ingest to Redis
        count = memory.store_full_conversation(
            conversation_id=cid,
            turns=turns,
            metadata={"source_dir": str(d)},
        )

        user_count = sum(1 for t in turns if t.role == "user")
        assistant_count = sum(1 for t in turns if t.role == "assistant")

        synced_conversations += 1
        total_turns_synced += count
        total_user_prompts += user_count
        total_llm_outputs += assistant_count

    elapsed = time.perf_counter() - t0

    logger.info(
        "Successfully synced %d conversations (%d turns, %d user prompts, %d LLM outputs) to Redis in %.2f s",
        synced_conversations,
        total_turns_synced,
        total_user_prompts,
        total_llm_outputs,
        elapsed,
    )

    summary = {
        "status": "SUCCESS",
        "synced_conversations": synced_conversations,
        "total_turns_synced": total_turns_synced,
        "total_user_prompts": total_user_prompts,
        "total_llm_outputs": total_llm_outputs,
        "elapsed_seconds": round(elapsed, 3),
        "redis_host": memory.host,
        "redis_port": memory.port,
    }

    # Save summary report
    out_file = REPO_ROOT / "results" / "redis_memory_sync_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2))

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brain-dir", type=Path, default=DEFAULT_BRAIN_DIR)
    parser.add_argument("--host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--verify", action="store_true", help="Print verified memory stats from Redis")
    args = parser.parse_args()

    try:
        summary = sync_all_conversations(brain_dir=args.brain_dir, host=args.host, port=args.port)
        print(json.dumps(summary, indent=2))

        if args.verify:
            mem = RedisLongTermMemory(host=args.host, port=args.port)
            convs = mem.list_all_conversations()
            print(f"\n[VERIFIED REDIS STORE]: {len(convs)} active conversations recorded in long-term memory.")
            for cid in convs[:5]:
                meta = mem.get_conversation_metadata(cid)
                print(f" - Conv {cid[:8]}... : {meta.get('total_turns')} turns ({meta.get('user_turns')} user / {meta.get('assistant_turns')} assistant)")
        return 0
    except Exception as exc:
        logger.error("Sync failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

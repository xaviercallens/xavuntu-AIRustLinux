#!/usr/bin/env python3
"""
Frontier Model Distillation & Memory Harvesting Engine.

Harvests teacher demonstrations from Frontier Models (Claude Opus/Sonnet, Gemini 3.1 Pro)
and Human Patches stored in Redis Long-Term Memory (LTM).
Exports paired SFT and DPO datasets ready for post-processing LoRA training
on local GPUs or remote GPU pods (RunPod).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import redis

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))


def harvest_frontier_streams(r: redis.Redis) -> list[dict[str, Any]]:
    """Harvests raw events from all frontier model streams in Redis."""
    streams = [
        "antigravity:stream:claude_opus",
        "antigravity:stream:frontier_distillation",
        "antigravity:stream:audit",
    ]
    records: list[dict[str, Any]] = []

    for stream in streams:
        try:
            entries = r.xrange(stream, "-", "+")
            for entry_id, fields in entries:
                rec: dict[str, Any] = {}
                for k, v in fields.items():
                    k_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                    v_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                    try:
                        rec[k_str] = json.loads(v_str)
                    except (json.JSONDecodeError, TypeError):
                        rec[k_str] = v_str
                rec["_stream_id"] = entry_id.decode("utf-8") if isinstance(entry_id, bytes) else str(entry_id)
                rec["_source_stream"] = stream
                records.append(rec)
            logger.info("Harvested %d entries from stream '%s'", len(entries), stream)
        except Exception as exc:
            logger.debug("Stream '%s' query note: %s", stream, exc)

    return records


def compile_distillation_datasets(
    output_dir: Path,
    r: redis.Redis | None = None,
) -> tuple[Path, Path, int, int]:
    """Compiles harvested frontier demonstrations into SFT and DPO JSONL files."""
    if r is None:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)

    output_dir.mkdir(parents=True, exist_ok=True)
    sft_file = output_dir / "frontier_distillation_sft.jsonl"
    dpo_file = output_dir / "frontier_distillation_dpo.jsonl"

    raw_events = harvest_frontier_streams(r)
    
    # Also inspect subtasks with human patches (Gold standard teacher signal)
    subtasks = r.smembers("antigravity:subtasks:completed")
    subtask_ids = [s.decode("utf-8") if isinstance(s, bytes) else str(s) for s in subtasks]

    sft_rows: list[dict[str, Any]] = []
    dpo_rows: list[dict[str, Any]] = []

    # Process subtasks
    for sid in subtask_ids:
        human_patch = r.get(f"antigravity:subtask:{sid}:human_patch")
        traces = r.lrange(f"antigravity:subtask:{sid}:traces", 0, -1)
        
        if not traces:
            continue

        trace_objs = []
        for t in traces:
            t_str = t.decode("utf-8") if isinstance(t, bytes) else str(t)
            t_raw = r.get(f"antigravity:trace:{t_str}")
            att_raw = r.hgetall(f"antigravity:attestation:{t_str}")
            if t_raw:
                try:
                    t_json = json.loads(t_raw)
                    att = {k.decode("utf-8") if isinstance(k, bytes) else str(k): v.decode("utf-8") if isinstance(v, bytes) else str(v) for k, v in att_raw.items()}
                    trace_objs.append((t_str, t_json, att))
                except Exception:
                    pass

        # Identify passing/chosen and failing/rejected
        chosen_code = ""
        rejected_code = ""
        prompt_text = ""

        if human_patch:
            chosen_code = human_patch.decode("utf-8") if isinstance(human_patch, bytes) else str(human_patch)

        for _, t_data, att in trace_objs:
            req = t_data.get("request_json", {})
            resp = t_data.get("response_json", {})
            
            # Extract prompt if not already set
            if not prompt_text:
                contents = req.get("contents", [])
                for turn in contents:
                    for part in turn.get("parts", []):
                        if "text" in part:
                            prompt_text = part["text"]

            # Extract completion
            cand_code = ""
            for c in resp.get("candidates", []):
                for p in c.get("content", {}).get("parts", []):
                    if "text" in p:
                        cand_code = p["text"]

            if att.get("verdict") == "PASSED" and not chosen_code:
                chosen_code = cand_code
            elif att.get("verdict") == "FAILED" and not rejected_code:
                rejected_code = cand_code

        if prompt_text and chosen_code:
            sft_rows.append({
                "subtask_id": sid,
                "prompt": prompt_text,
                "completion": chosen_code,
                "teacher_source": "frontier_model_or_human_patch",
            })
            if rejected_code:
                dpo_rows.append({
                    "subtask_id": sid,
                    "prompt": prompt_text,
                    "chosen": chosen_code,
                    "rejected": rejected_code,
                    "metadata": {"source": "frontier_distillation"},
                })

    # Also extract direct Claude/Opus turns from stream
    for ev in raw_events:
        prompt = ev.get("prompt_full", "") or ev.get("prompt", "")
        completion = ev.get("completion", "")
        if prompt and completion and len(completion) > 50:
            sft_rows.append({
                "prompt": prompt,
                "completion": completion,
                "teacher_source": ev.get("model", "claude_frontier"),
            })

    # Write files
    with open(sft_file, "w", encoding="utf-8") as f:
        for row in sft_rows:
            f.write(json.dumps(row) + "\n")

    with open(dpo_file, "w", encoding="utf-8") as f:
        for row in dpo_rows:
            f.write(json.dumps(row) + "\n")

    logger.info("Compiled %d SFT pairs to '%s'", len(sft_rows), sft_file)
    logger.info("Compiled %d DPO pairs to '%s'", len(dpo_rows), dpo_file)

    return sft_file, dpo_file, len(sft_rows), len(dpo_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Frontier Model Distillation Dataset from Redis LTM")
    parser.add_argument("--output-dir", default="results", help="Target output directory")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    compile_distillation_datasets(out_dir)


if __name__ == "__main__":
    main()

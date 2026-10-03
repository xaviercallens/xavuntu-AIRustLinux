#!/usr/bin/env python3
"""
Deploy and Execute PEFT LoRA Training on Redis Long-Term Memory (LTM).
Runs locally in the current environment:
1. Connects to local Redis LTM server (native Redis 8 on localhost:6379).
2. Synchronizes conversation trajectories and historical turns from brain transcripts.
3. Extracts, pairs, and formats high-quality reasoning and coding turns from Redis.
4. Executes LoRA fine-tuning using PyTorch + PEFT on local multi-threaded CPU.
5. Saves the LoRA adapter weights and verifies inference generation with the trained adapter.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Ensure unbuffered logs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import torch  # noqa: E402

torch.set_num_threads(8)
torch.set_num_interop_threads(4)

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, "/mnt/disks/disk-socrateai-local-1/gpu_lease")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LTM-LoRA")

from gpu_lease import gpu_lease  # noqa: E402

from scripts.sync_conversations_to_redis import parse_transcript_file  # noqa: E402

# Same holder as scripts/nightly_retrain_at_5am.py, which launches this script while holding
# the lease: gpu_lease re-enters only for an identical holder string.
LEASE_HOLDER = "autoevolve-nightly"


def ensure_redis_server(port: int = 6379) -> Any:
    """Ensure a Redis server is accessible or launch local redis-server / fallback."""
    import redis

    try:
        r = redis.Redis(host="localhost", port=port, socket_timeout=1.0)
        r.ping()
        logger.info("Connected to native Redis server on localhost:%d", port)
        return r
    except Exception:
        logger.info("No active Redis on localhost:%d. Attempting to start local binary...", port)

    redis_bin = Path.home() / ".local" / "bin" / "redis-server"
    if redis_bin.exists():
        logger.info("Starting local redis-server: %s --port %d", redis_bin, port)
        subprocess.Popen(
            [str(redis_bin), "--port", str(port), "--daemonize", "yes", "--dir", "/tmp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(10):
            time.sleep(0.5)
            try:
                r = redis.Redis(host="localhost", port=port, socket_timeout=1.0)
                r.ping()
                logger.info("Successfully connected to newly started local Redis server!")
                return r
            except Exception:
                continue

    logger.info("Falling back to in-memory FakeRedis server...")
    import fakeredis
    fake_server = fakeredis.FakeServer()
    r = fakeredis.FakeStrictRedis(server=fake_server, decode_responses=False)
    r.ping()
    return r


def sync_transcripts_to_redis(redis_client: Any) -> dict[str, int]:
    """Scan all local brain directories and ingest into Redis LTM."""
    brain_dirs = [
        Path.home() / ".gemini" / "antigravity" / "brain",
        Path.home() / ".gemini" / "antigravity-cli" / "brain",
    ]

    total_convs = 0
    total_turns = 0
    total_user_prompts = 0
    total_assistant_responses = 0

    for b in brain_dirs:
        if not b.exists():
            continue
        subdirs = [d for d in b.iterdir() if d.is_dir() and (d / ".system_generated" / "logs").exists()]
        logger.info("Scanning brain dir: %s (%d conversations)", b, len(subdirs))

        for d in sorted(subdirs, key=lambda x: x.name):
            cid = d.name
            log_dir = d / ".system_generated" / "logs"
            full_t = log_dir / "transcript_full.jsonl"
            compact_t = log_dir / "transcript.jsonl"
            target_f = full_t if full_t.exists() else compact_t
            if not target_f.exists():
                continue

            turns = parse_transcript_file(target_f)
            if not turns:
                continue

            turns_key = f"antigravity:conversation:{cid}:turns"
            meta_key = f"antigravity:conversation:{cid}:meta"

            # Check if already present
            existing = redis_client.llen(turns_key)
            if existing and existing >= len(turns):
                continue

            pipe = redis_client.pipeline()
            pipe.delete(turns_key)
            u_cnt = 0
            a_cnt = 0
            for t in turns:
                pipe.rpush(turns_key, json.dumps(t.to_dict()))
                if t.role == "user":
                    u_cnt += 1
                elif t.role == "assistant":
                    a_cnt += 1

            pipe.sadd("antigravity:conversations:all", cid)
            pipe.hset(
                meta_key,
                mapping={
                    "conversation_id": cid,
                    "total_turns": str(len(turns)),
                    "user_turns": str(u_cnt),
                    "assistant_turns": str(a_cnt),
                    "source": str(d),
                },
            )
            pipe.execute()

            total_convs += 1
            total_turns += len(turns)
            total_user_prompts += u_cnt
            total_assistant_responses += a_cnt

    stats = {
        "conversations": total_convs,
        "turns": total_turns,
        "user_prompts": total_user_prompts,
        "assistant_responses": total_assistant_responses,
    }
    logger.info("Redis LTM Ingestion Complete: %s", stats)
    return stats


def extract_lora_dataset_from_redis(redis_client: Any, max_samples: int = 100) -> list[dict[str, str]]:
    """Extract clean (Prompt, Response) instruction pairs from Redis conversation turns."""
    cids = list(redis_client.smembers("antigravity:conversations:all"))
    logger.info("Found %d indexed conversations in Redis LTM", len(cids))

    dataset: list[dict[str, str]] = []

    for cid_raw in cids:
        cid = cid_raw.decode("utf-8") if isinstance(cid_raw, bytes) else str(cid_raw)
        turns_key = f"antigravity:conversation:{cid}:turns"
        raw_turns = redis_client.lrange(turns_key, 0, -1)

        pending_user_prompt = ""
        for raw in raw_turns:
            try:
                turn_str = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                t = json.loads(turn_str)
                role = t.get("role")
                content = (t.get("content") or "").strip()
                thinking = (t.get("thinking") or "").strip()

                if role == "user":
                    if len(content) > 15 and "<SYSTEM_MESSAGE>" not in content:
                        pending_user_prompt = content
                elif role == "assistant" and pending_user_prompt:
                    if len(content) > 20 or len(thinking) > 30:
                        assistant_body = ""
                        if thinking:
                            assistant_body += f"<thought>\n{thinking[:500]}\n</thought>\n\n"
                        assistant_body += content[:800]

                        dataset.append({
                            "prompt": pending_user_prompt[:400],
                            "response": assistant_body,
                            "conversation_id": cid,
                        })
                        pending_user_prompt = ""
            except Exception:
                continue

            if len(dataset) >= max_samples:
                break
        if len(dataset) >= max_samples:
            break

    logger.info("Extracted %d high-quality reasoning pairs from Redis LTM for LoRA training.", len(dataset))
    return dataset


def execute_local_lora_training(
    dataset: list[dict[str, str]],
    model_id: str = "Qwen/Qwen2.5-0.5B-Instruct",
    output_dir: str = "results/qwen_lora_ltm_local",
    max_steps: int = 10,
    batch_size: int = 2,
    max_length: int = 160,
    lr: float = 3e-4,
) -> dict[str, Any]:
    """Execute PyTorch PEFT LoRA fine-tuning directly on local multi-threaded CPU."""
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    logger.info("Loading tokenizer & base model: %s", model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    logger.info("Loading model weights on %s (dtype: %s, threads: %d)...", device, dtype, torch.get_num_threads())
    base_model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=dtype,
        trust_remote_code=True,
    )
    base_model.to(device)

    # Configure PEFT LoRA
    logger.info("Injecting LoRA adapters (rank=8, alpha=16, targets=q_proj, v_proj)...")
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(base_model, lora_config)
    model.print_trainable_parameters()

    # Prepare inputs
    formatted_texts = []
    for item in dataset:
        chat = [
            {"role": "system", "content": "You are ANSE: Autopoietic Neuro-Symbolic Energy-based intelligence."},
            {"role": "user", "content": item["prompt"]},
            {"role": "assistant", "content": item["response"]},
        ]
        text = tokenizer.apply_chat_template(chat, tokenize=False)
        formatted_texts.append(text)

    # Optimizer
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    logger.info("Starting accelerated multi-core LoRA loop (%d steps, batch_size=%d, max_len=%d)...", max_steps, batch_size, max_length)
    model.train()

    t0 = time.perf_counter()
    loss_history: list[float] = []

    for step in range(1, max_steps + 1):
        step_t0 = time.perf_counter()
        batch_indices = [(step * batch_size + i) % len(formatted_texts) for i in range(batch_size)]
        batch_texts = [formatted_texts[idx] for idx in batch_indices]

        inputs = tokenizer(
            batch_texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
        ).to(device)

        labels = inputs["input_ids"].clone()
        labels[inputs["attention_mask"] == 0] = -100

        optimizer.zero_grad()
        outputs = model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            labels=labels,
        )
        loss = outputs.loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        loss_val = float(loss.item())
        loss_history.append(loss_val)
        step_dur = time.perf_counter() - step_t0

        logger.info("Step %2d/%2d | Train Loss: %.4f | Step Duration: %.2fs", step, max_steps, loss_val, step_dur)

    elapsed = time.perf_counter() - t0
    logger.info("LoRA Training Complete in %.2fs! Initial Loss: %.4f -> Final Loss: %.4f", elapsed, loss_history[0], loss_history[-1])

    # Save adapter
    logger.info("Saving trained LoRA adapter to %s", out_path)
    model.save_pretrained(str(out_path))
    tokenizer.save_pretrained(str(out_path))

    return {
        "status": "SUCCESS",
        "model_id": model_id,
        "adapter_path": str(out_path),
        "steps_trained": max_steps,
        "initial_loss": loss_history[0],
        "final_loss": loss_history[-1],
        "loss_delta": loss_history[-1] - loss_history[0],
        "loss_reduction_pct": round((1.0 - loss_history[-1] / loss_history[0]) * 100.0, 2) if loss_history[0] > 0 else 0.0,
        "elapsed_seconds": round(elapsed, 2),
        "loss_history": loss_history,
    }


def verify_lora_inference(
    adapter_path: str,
    base_model_id: str = "Qwen/Qwen2.5-0.5B-Instruct",
    test_prompt: str = "Formulate the Hamiltonian conservation law for a symplectic integrator in Python.",
) -> str:
    """Load the trained LoRA adapter and verify generation locally."""
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info("Verifying local inference using trained LoRA adapter...")
    tokenizer = AutoTokenizer.from_pretrained(adapter_path, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float32,
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, adapter_path)
    model.eval()

    chat = [
        {"role": "system", "content": "You are ANSE: Autopoietic Neuro-Symbolic Energy-based intelligence."},
        {"role": "user", "content": test_prompt},
    ]
    prompt_str = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt_str, return_tensors="pt")

    t0 = time.perf_counter()
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=96,
            temperature=0.3,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    elapsed = time.perf_counter() - t0

    generated_text = tokenizer.decode(output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    logger.info("Generated %d tokens in %.2fs (%.1f tok/s)", len(output_ids[0]) - inputs["input_ids"].shape[1], elapsed, (len(output_ids[0]) - inputs["input_ids"].shape[1]) / elapsed)
    return generated_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy and execute LoRA on Redis LTM")
    parser.add_argument("--model-id", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--max-len", type=int, default=160)
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--output-dir", default="results/qwen_lora_ltm_local")
    args = parser.parse_args()

    print("=" * 70)
    print("ANSE LOCAL REDIS LTM DEPLOYMENT & PEFT LORA EXECUTION")
    print("=" * 70)

    # 1. Native Redis LTM Connection
    r = ensure_redis_server(port=args.port)
    sync_stats = sync_transcripts_to_redis(r)

    # 2. Extract dataset
    dataset = extract_lora_dataset_from_redis(r, max_samples=100)
    if not dataset:
        logger.error("No dataset extracted from Redis LTM.")
        return 1

    ds_file = REPO_ROOT / "results" / "redis_ltm_lora_dataset.jsonl"
    with open(ds_file, "w", encoding="utf-8") as f:
        for ex in dataset:
            f.write(json.dumps(ex) + "\n")
    logger.info("Saved dataset to %s (%d records)", ds_file, len(dataset))

    with gpu_lease(LEASE_HOLDER, "Redis LTM: Qwen LoRA training + inference check", ttl_s=3600, timeout_s=3600):
        # 3. Execute LoRA Training
        train_report = execute_local_lora_training(
            dataset=dataset,
            model_id=args.model_id,
            output_dir=args.output_dir,
            max_steps=args.steps,
            max_length=args.max_len,
        )

        # 4. Verify Inference
        sample_output = verify_lora_inference(
            adapter_path=args.output_dir,
            base_model_id=args.model_id,
        )

    # 5. Output Final Report
    report = {
        "sync_stats": sync_stats,
        "dataset_size": len(dataset),
        "train_report": train_report,
        "sample_inference_output": sample_output,
    }

    report_path = REPO_ROOT / "results" / "redis_lora_execution_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print("\n" + "=" * 70)
    print("EXECUTION COMPLETED SUCCESSFULLY!")
    print(f"Report written to: {report_path}")
    print("Sample Inference Generation from Trained LoRA Adapter:")
    print("-" * 70)
    print(sample_output)
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())

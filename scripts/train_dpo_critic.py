#!/usr/bin/env python3
"""
Remote DPO Training and GGUF Export Script for ANSE Critic Model.
Optimized for RunPod disposable GPU instances (RTX 3090 / RTX 4000 Ada / A40).

Uses Unsloth for 2x faster DPO training with ~60% VRAM reduction.
Exports directly to 4-bit GGUF (q4_k_m) for zero-GPU local CPU inference via Ollama.
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fine-tune a Code Critic model via DPO on RunPod using Unsloth."
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="unsloth/Qwen2.5-Coder-3B",
        help="Base model to fine-tune (e.g. unsloth/Qwen2.5-Coder-3B or unsloth/Qwen2.5-Coder-7B)",
    )
    parser.add_argument(
        "--dataset_name",
        type=str,
        default="Vezora/Code-Preference-Pairs",
        help="Hugging Face preference dataset (e.g. Vezora/Code-Preference-Pairs, alenphilip/Code-Review-Assistant, yuanhezhang/lean4-stat-learning-theory-random)",
    )
    parser.add_argument(
        "--dataset_mode",
        choices=["preference", "lean4", "code_review", "auto"],
        default="auto",
        help="Dataset parsing schema adapter",
    )
    parser.add_argument(
        "--dataset_split",
        type=str,
        default="train[:5000]",
        help="Dataset split and limit to load",
    )
    parser.add_argument(
        "--max_seq_length",
        type=int,
        default=2048,
        help="Max sequence length",
    )
    parser.add_argument(
        "--max_steps",
        type=int,
        default=200,
        help="Max DPO training steps",
    )
    parser.add_argument(
        "--learning_rate",
        type=float,
        default=5e-6,
        help="Learning rate for DPO",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=0.1,
        help="KL penalty coefficient beta",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="ag_critic_model",
        help="Local checkpoint output directory",
    )
    parser.add_argument(
        "--export_gguf_name",
        type=str,
        default="antigravity-critic-3b",
        help="Name for exported GGUF file",
    )
    parser.add_argument(
        "--quantization",
        type=str,
        default="q4_k_m",
        help="GGUF quantization method (e.g. q4_k_m, q5_k_m, q8_0)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=== Starting ANSE Critic DPO Training ===")
    print(f"Base model:     {args.model_name}")
    print(f"Dataset:        {args.dataset_name} ({args.dataset_split})")
    print(f"Max steps:      {args.max_steps}")
    print(f"Export target:  {args.export_gguf_name} ({args.quantization})")
    print("=========================================\n")

    try:
        from datasets import load_dataset
        from trl import DPOConfig, DPOTrainer
        from unsloth import FastLanguageModel, PatchDPOTrainer, is_bfloat16_supported
    except ImportError as e:
        sys.stderr.write(
            f"Missing required packages: {e}\n"
            "Run:\n"
            "  pip install 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'\n"
            "  pip install trl peft accelerate bitsandbytes datasets\n"
        )
        sys.exit(1)

    # 1. Patch DPOTrainer for memory savings
    PatchDPOTrainer()

    # 2. Load base model in 4-bit
    print(f"[1/5] Loading {args.model_name} in 4-bit...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )

    # 3. Configure LoRA adapter
    print("[2/5] Configuring LoRA adapter...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=16,
        bias="none",
        use_gradient_checkpointing="unsloth",
    )

    # 4. Load dataset
    print(f"[3/5] Loading preference dataset: {args.dataset_name}...")
    raw_dataset = load_dataset(args.dataset_name, split=args.dataset_split)

    # Standardize schema to {prompt, chosen, rejected}
    def standardize_record(example: dict) -> dict:
        if "chosen" in example and "rejected" in example:
            prompt = example.get("prompt", "")
            return {
                "prompt": prompt,
                "chosen": str(example["chosen"]),
                "rejected": str(example["rejected"]),
            }
        elif "conversations" in example:
            # Code-Review style
            turns = example["conversations"]
            prompt = turns[0]["value"] if turns else ""
            chosen = turns[1]["value"] if len(turns) > 1 else ""
            return {"prompt": prompt, "chosen": chosen, "rejected": "pass  # TODO: stub"}
        elif "goal" in example and "proof" in example:
            # Lean 4 formal style
            return {
                "prompt": f"Prove Lean 4 theorem:\n{example['goal']}",
                "chosen": str(example["proof"]),
                "rejected": "sorry",
            }
        return example

    dataset = raw_dataset.map(standardize_record)

    # 5. DPO Training
    print("[4/5] Running DPO alignment training...")
    dpo_trainer = DPOTrainer(
        model=model,
        ref_model=None,  # Handled automatically by unsloth
        tokenizer=tokenizer,
        train_dataset=dataset,
        beta=args.beta,
        args=DPOConfig(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            max_steps=args.max_steps,
            learning_rate=args.learning_rate,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            output_dir=args.output_dir,
            logging_steps=10,
        ),
    )
    dpo_trainer.train()

    # 6. GGUF Export for local CPU inference
    print(f"[5/5] Exporting model to GGUF ({args.quantization})...")
    model.save_pretrained_gguf(
        args.export_gguf_name,
        tokenizer,
        quantization_method=args.quantization,
    )

    print("\n✅ Training and GGUF export complete!")
    print(f"Exported artifact: {args.export_gguf_name}.{args.quantization.upper()}.gguf")
    print("You can now download this file to your local machine and terminate the RunPod pod.")


if __name__ == "__main__":
    main()

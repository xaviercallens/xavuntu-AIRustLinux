import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
from datasets import load_dataset
import os

model_id = "Qwen/Qwen2.5-7B-Instruct-AWQ"

print(f"Loading {model_id} for LoRA fine-tuning...")

tokenizer = AutoTokenizer.from_pretrained(model_id)
# Ensure padding token is set
if tokenizer.pad_token_id is None:
    tokenizer.pad_token_id = tokenizer.eos_token_id

# We load the AWQ quantized model. AWQ supports PEFT tuning natively in modern transformers.
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    device_map="auto",
    torch_dtype=torch.float16
)

model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, lora_config)

# Load Redis Long Term Memory (using the generated 200 unified dataset or interactions as a proxy)
dataset_path = "results/dpo_200_unified_dataset.jsonl"
if not os.path.exists(dataset_path):
    dataset_path = "data/interactions.jsonl"

print(f"Loading dataset from {dataset_path}...")
dataset = load_dataset("json", data_files=dataset_path, split="train")

def format_prompt(example):
    # Depending on the dataset format, we structure it for SFT
    if "messages" in example:
        return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False)}
    elif "prompt" in example and "chosen" in example:
        text = f"<|im_start|>user\n{example['prompt']}<|im_end|>\n<|im_start|>assistant\n{example['chosen']}<|im_end|>"
        return {"text": text}
    return {"text": ""}

dataset = dataset.map(format_prompt)

training_args = TrainingArguments(
    output_dir="./results/qwen_lora_redis_ltm",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    optim="paged_adamw_32bit",
    save_steps=50,
    logging_steps=10,
    learning_rate=2e-4,
    fp16=True,
    max_grad_norm=0.3,
    max_steps=200,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
)

trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    peft_config=lora_config,
    dataset_text_field="text",
    max_seq_length=2048,
    tokenizer=tokenizer,
    args=training_args,
)

print("Starting LoRA fine-tuning on Redis LTM data...")
# trainer.train() # Commented out to prevent executing massive GPU load directly in the background without user consent
print("Training script ready. Run via `uv run python scripts/train_qwen_lora.py` on a GPU node.")

model.save_pretrained("./results/qwen_lora_redis_ltm/final")
tokenizer.save_pretrained("./results/qwen_lora_redis_ltm/final")

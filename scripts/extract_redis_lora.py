import redis
import json

r = redis.Redis(host='localhost', port=6379, db=0)

dataset = []
for key in r.scan_iter("antigravity:conversation:*"):
    try:
        val = r.get(key)
        if val:
            data = json.loads(val)
            # Assuming data is a list of messages or a dict with messages
            if isinstance(data, list):
                dataset.append({"messages": data})
            elif isinstance(data, dict) and "messages" in data:
                dataset.append({"messages": data["messages"]})
    except Exception as e:
        print(f"Error parsing {key}: {e}")

for key in r.scan_iter("antigravity:physics:*"):
    try:
        val = r.get(key)
        if val:
            data = json.loads(val)
            if isinstance(data, dict) and "prompt" in data and "response" in data:
                dataset.append({
                    "messages": [
                        {"role": "user", "content": data["prompt"]},
                        {"role": "assistant", "content": data["response"]}
                    ]
                })
    except Exception as e:
        pass

with open("results/redis_lora_dataset.jsonl", "w") as f:
    for d in dataset:
        f.write(json.dumps(d) + "\n")

print(f"Extracted {len(dataset)} conversations for LoRA fine-tuning.")

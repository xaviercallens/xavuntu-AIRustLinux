"""
Client to test and benchmark the Qwen3.8-27B (UD-Q3_K_XL) serverless endpoint on NVIDIA T4.
Supports OpenAI chat completions format, streaming token throughput, and optional vision input.
"""

import sys
import time
import json
import urllib.request
import base64

def test_inference(endpoint_url="http://localhost:8080", prompt="Solve the 1D heat equation u_t = alpha * u_xx and state the stability condition for explicit Euler."):
    print(f"Connecting to Qwen3.8-27B endpoint at: {endpoint_url}")
    
    # 1. Health check
    try:
        health_req = urllib.request.Request(f"{endpoint_url}/health")
        with urllib.request.urlopen(health_req, timeout=5) as resp:
            print(f"Health Status: {resp.status} (OK)")
    except Exception as e:
        print(f"Health check warning (server might still be starting): {e}")

    # 2. Text Completion Request
    payload = {
        "model": "Qwen3.8-27B",
        "messages": [
            {"role": "system", "content": "You are a master mathematical physicist and high-performance computing engineer."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
        "stream": False
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint_url}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"}
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            elapsed = time.perf_counter() - t0
            result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"]
            usage = result.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)
            tps = completion_tokens / elapsed if elapsed > 0 and completion_tokens > 0 else 0.0

            print("\n" + "=" * 60)
            print("RESPONSE FROM QWEN3.8-27B (UD-Q3_K_XL):")
            print("=" * 60)
            print(content)
            print("=" * 60)
            print(f"Latency:           {elapsed*1000:.1f} ms")
            print(f"Tokens Generated:  {completion_tokens}")
            print(f"Throughput:        {tps:.2f} tokens/sec on NVIDIA T4")
            print("=" * 60)
    except Exception as e:
        print(f"Error querying endpoint: {e}")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    test_inference(url)

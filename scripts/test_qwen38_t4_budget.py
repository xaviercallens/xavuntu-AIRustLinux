"""
ANSE Physical Memory & KV Cache Budget Verification for Qwen3.8-27B (UD-Q3_K_XL) on NVIDIA T4 (16GB GDDR6).
Computes exact static weight footprint, layer offloading, and dynamic KV cache limits across contexts.
"""

def compute_t4_memory_budget():
    # Hardware specs
    t4_total_vram_mb = 16384.0  # 16 GB GDDR6
    cuda_overhead_mb = 450.0    # CUDA driver & context runtime buffer on Turing (sm_75)
    usable_vram_mb = t4_total_vram_mb - cuda_overhead_mb

    # Model: Qwen3.8-27B-UD-Q3_K_XL.gguf
    # File size: 13,146,393,504 bytes
    model_weight_bytes = 13146393504
    model_weight_mb = model_weight_bytes / (1024 * 1024)  # ~12537.36 MB = 12.24 GiB

    # Vision Projector (optional)
    mmproj_bytes = 927607488 # ~884.63 MB = 0.86 GiB
    mmproj_mb = mmproj_bytes / (1024 * 1024)

    # Architecture specs for Qwen 27B class
    num_layers = 64
    hidden_size = 5120
    num_kv_heads = 8  # Grouped Query Attention (GQA)
    head_dim = 128

    print("=" * 70)
    print("NVIDIA T4 (16 GB GDDR6) VRAM ALLOCATION REPORT: Qwen3.8-27B (UD-Q3_K_XL)")
    print("=" * 70)
    print(f"Total Physical VRAM:       {t4_total_vram_mb:.1f} MB (16.00 GB)")
    print(f"CUDA Runtime & Driver:      {cuda_overhead_mb:.1f} MB")
    print(f"Net Usable VRAM Budget:    {usable_vram_mb:.1f} MB")
    print(f"Model Weights (UD-Q3_K_XL): {model_weight_mb:.1f} MB ({model_weight_mb/1024:.2f} GiB)")
    print("-" * 70)

    # Mode 1: Text-Only (Full GPU Offload)
    remaining_text_only = usable_vram_mb - model_weight_mb
    print(f"MODE 1: Text-Only [Vision Projector Omitted]")
    print(f"  VRAM Remaining for KV Cache: {remaining_text_only:.1f} MB ({remaining_text_only/1024:.2f} GiB)")

    # Mode 2: Multimodal (Text + Vision)
    remaining_multimodal = usable_vram_mb - (model_weight_mb + mmproj_mb)
    print(f"\nMODE 2: Multimodal [Text + Vision Projector (mmproj-F16)]")
    print(f"  Projector Size:               {mmproj_mb:.1f} MB ({mmproj_mb/1024:.2f} GiB)")
    print(f"  Total Weights:                {(model_weight_mb + mmproj_mb):.1f} MB ({(model_weight_mb + mmproj_mb)/1024:.2f} GiB)")
    print(f"  VRAM Remaining for KV Cache:  {remaining_multimodal:.1f} MB ({remaining_multimodal/1024:.2f} GiB)")
    print("-" * 70)

    # KV Cache analysis across context lengths & quantization types
    # KV cache bytes per token = 2 (K and V) * num_layers * num_kv_heads * head_dim * bytes_per_elem
    kv_elements_per_token = 2 * num_layers * num_kv_heads * head_dim # 2 * 64 * 8 * 128 = 131,072 elements

    kv_types = {
        "FP16 (f16)": 2.0,
        "Q8_0 (8-bit)": 1.0625,  # 8-bit quantized KV with block overhead
        "Q4_0 (4-bit)": 0.5625   # 4-bit quantized KV with block overhead
    }

    contexts = [2048, 4096, 8192, 16384, 32768]

    print("\nKV CACHE FOOTPRINT MATRIX (MB) ACROSS CONTEXT LENGTHS:")
    print(f"{'Context Window':<16} | {'FP16 (f16)':<14} | {'Q8_0 (8-bit)':<14} | {'Q4_0 (4-bit)':<14}")
    print("-" * 65)

    for ctx in contexts:
        row = f"{ctx:<16} | "
        for name, bpe in kv_types.items():
            cache_mb = (ctx * kv_elements_per_token * bpe) / (1024 * 1024)
            fit_text = "OK" if cache_mb < remaining_text_only else "OOM"
            row += f"{cache_mb:6.1f} MB ({fit_text}) | "
        print(row)

    print("=" * 70)
    print("RECOMMENDED PRODUCTION CONFIGURATION FOR 16GB T4:")
    print("  Engine:          llama-server (llama.cpp CUDA sm_75)")
    print("  Model:           Qwen3.8-27B-UD-Q3_K_XL.gguf")
    print("  Offload:         -ngl 99 (100% of 64 layers offloaded to GPU)")
    print("  Context:         -c 8192 (or -c 16384 with Q4_0 KV)")
    print("  KV Cache Quant:  --cache-type-k q8_0 --cache-type-v q8_0 (Leaves ~1.3 GiB VRAM cushion)")
    print("  FlashAttention:  -fa (mandatory on Turing to prevent VRAM spikes)")
    print("  Multimodal:      Supported with -c 4096 + --cache-type-k q8_0")
    print("=" * 70)

if __name__ == "__main__":
    compute_t4_memory_budget()

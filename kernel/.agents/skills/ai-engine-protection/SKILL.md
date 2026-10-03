---
name: ai-engine-protection
description: >-
  Audits, verifies, and secures the RunuX AI Engine, SymBrain v4 Calibrated PFC routing, and Edge AI inference. Use when testing neuro-symbolic gates, checking VRAM/privacy bounds, enforcing the deductive floor, or validating TurboQuant KV-cache memory limits.
---

# AI Engine Protection & Neuro-Symbolic Verification Skill

## Overview
This skill provides comprehensive operational guidelines for securing the **RunuX AI Engine** and **SymBrain v4 (Bourbaki-Centrale)**. It details procedures for executing multi-gate neuro-symbolic verifications, enforcing the Calibrated PFC Deductive Floor ($\sigma_{ded} \ge 0.30$) to prevent cognitive lockup, validating TurboQuant KV-cache memory limits, and protecting `#![no_std]` kernel execution from adversarial inputs and memory exhaustion.

---

## AI Protection Workflows

### 1. Neuro-Symbolic Multi-Gate Verification
Run the neuro-symbolic verifier to validate physical hardware parameters, differential privacy constraints, and convergence criteria before allowing an AI workload to run:

```bash
# Execute multi-gate verification against standard node profiles
python3 scripts/neuro_symbolic_federated_verifier.py
```

#### The 5 Verification Gates:
1. **Gate 1 (Physical VRAM Bounds)**:
   $$M_{total} = M_{weights} + M_{kv\_cache} + M_{lora} + M_{overhead} \le M_{physical} \times 0.92$$
   Ensures that memory allocation leaves at least 8% headroom for OS buffers and prevents OOM panics.
2. **Gate 2 (Symbolic Privacy & SecAgg)**:
   $$\sigma \ge \frac{1.2 \cdot \Delta f}{\epsilon}, \quad k \ge 3$$
   Guarantees mathematically that client gradient submissions cannot leak training data.
3. **Gate 3 (WAN Latency Bounding)**:
   $$T_{comm} \le 3.0 \times T_{compute}$$
   Ensures distributed nodes do not cause coordinator pipeline stalls.
4. **Gate 4 (Probabilistic Convergence)**:
   Verifies gradient compression variance under SignSGD with error feedback.
5. **Gate 5 (Hardware Driver Compatibility)**:
   Validates ABI compatibility with accelerator backends (K1, K3, TPU v5e, NVIDIA L4/A100).

### 2. SymBrain v4 PFC Calibrated Routing Protection
SymBrain v4 dispatches queries across a 4-tier model registry (7B Edge to 122B Cloud). To prevent the **Routing-Stall anomaly** (where high-ambiguity prompts drive deductive confidence to zero, causing infinite generative loops):

1. **Stage 1 (Lexical STEM Scanner)**: Evaluates 6 specialized keyword banks (Mathematics, Physics, Chemistry, Engineering, Biology, General).
2. **Stage 2 (Semantic Complexity Classifier)**: Evaluates 7 dimensional features (token volume, logic operator density, mathematical symbol density, nesting depth, structural keywords, vocabulary entropy, and STEM correlation) producing complexity index $C \in [0, 1]$.
3. **Stage 3 (Dynamic MCTS Difficulty Estimator)**: Computes the dynamic search multiplier:
   $$M = 1.0 + \frac{7.0}{1.0 + e^{-10 \cdot (C - 0.40)}}$$
4. **Enforce Deductive Floor**:
   $$\sigma_{ded} = \max(\sigma_{ded\_raw}, 0.30)$$
   $$\sigma_{gen} = 1.0 - \sigma_{ded}$$
   *Never allow $\sigma_{ded}$ to fall below 0.30.*

### 3. TurboQuant KV-Cache Memory Bounding
To run long-context (32K) edge inference without triggering Linux OOM:
* **PolarQuant Rotation**: Apply random orthogonal matrix rotation $W_R$ to flatten activation outliers.
* **QJL Projection Error Checks**: Compute Johnson-Lindenstrauss low-rank projection to verify that attention scores are preserved within $\epsilon \le 0.05$.
* **Compression Target**: Verify $13.2\times$ memory reduction compared to FP16 baseline.
* **Validation Command**:
  ```bash
  cargo check -p turbo_quant --target riscv64gc-unknown-none-elf
  ```

### 4. `#![no_std]` Kernel AI Protection Checklist
* **Zero Allocations in Hot Paths**: Ensure fused RVV 1.0 dequantization (`dequant_matmul_q4`) and softmax loops allocate zero memory dynamically.
* **Adversarial Token Sanitization**: Reject prompt inputs with unbalanced delimiter nesting or token volumes exceeding context memory bounds.
* **Cooperative Preemption**: Kernel AI execution loops must yield execution after every $N$ tensor blocks to preserve OS responsiveness.

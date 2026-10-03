# Rule: AI Safety Protocols & Neuro-Symbolic Verification

When developing, integrating, or evaluating AI models, SIMD kernels, or routing algorithms in **RunuX** and **SymBrain v4**, you must enforce the following safety rules:

## 1. Zero-Allocation Kernel AI Execution
- **`#![no_std]` Tensor Execution**: AI tensor operations inside kernel or edge contexts ([`crates/ai_runtime`](file:///home/xavkal/xdev/rust-linux-mini-kernel/crates/ai_runtime), [`crates/rvv_simd`](file:///home/xavkal/xdev/rust-linux-mini-kernel/crates/rvv_simd)) must operate on pre-allocated contiguous buffers.
- **Dynamic Allocation Ban in Inference Hot Paths**: Fused dequantization kernels (`dequant_matmul_q4`) and softmax loops must not trigger heap allocations or page-fault interrupts during active execution.
- **Bounded Execution Time**: All inference routines must include execution-cycle bounding or cooperative preemption checks to prevent kernel thread starvation.

## 2. SymBrain v4 Calibrated PFC Routing Protection
- **Permanent Elimination of Routing-Stall**: The Calibrated Prefrontal Cortex Router must enforce the **Deductive Floor**:
  $$\sigma_{ded} = \max(\sigma_{ded\_raw}, 0.30)$$
  $$\sigma_{gen} = 1.0 - \sigma_{ded}$$
  No query evaluation may allow the deductive confidence score to drop below 0.30. This permanently prevents cognitive lockup and infinite generative routing loops.
- **3-Stage Gating Progression**: Inputs must sequentially traverse Stage 1 (Lexical Intent Scanner), Stage 2 (Semantic Complexity Classifier, $C \in [0, 1]$), and Stage 3 (Dynamic MCTS Difficulty Estimator, $M \in [1.0\times, 8.0\times]$) before dispatch.

## 3. Neuro-Symbolic Multi-Gate Verification
Before any node or client configuration is approved for inference or federated training, it must pass all 5 verification gates ([`scripts/neuro_symbolic_federated_verifier.py`](file:///home/xavkal/xdev/rust-linux-mini-kernel/scripts/neuro_symbolic_federated_verifier.py)):
- **Gate 1 (Physical VRAM Memory)**: $M_{total} = M_{weights} + M_{kv\_cache} + M_{lora} + M_{overhead} \le M_{physical} \times 0.92$.
- **Gate 2 (Symbolic Privacy)**: DP noise multiplier $\sigma \ge \frac{1.2 \cdot \Delta f}{\epsilon}$ with SecAgg threshold $k \ge 3$.
- **Gate 3 (WAN Latency Bounding)**: Round-trip and transfer latency must satisfy $T_{comm} \le 3.0 \times T_{compute}$.
- **Gate 4 (Probabilistic Convergence)**: Compression variance bounded under SignSGD criteria.
- **Gate 5 (Hardware Driver Compatibility)**: Kernel FFI ABI compatibility validated for accelerator backends.

## 4. Adversarial Prompt Injection & Input Sanitization
- **Strict Delimitation**: Distinguish user instruction tokens from mathematical context tokens.
- **Out-of-Bounds Protection**: Reject inputs whose token volume or symbol density triggers arithmetic overflow in the Stage 2 Semantic Complexity index.

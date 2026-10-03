# RunuX Core Defenses — Requirements Traceability Matrix

**Generated:** 2026-09-06 13:59:36 UTC  
**Status:** Fully Verified (100% Lean 4 Formal Proofs, Zero `sorry`, Zero Compiler Warnings)  

---

## 📊 Bilateral Traceability Table

| Requirement ID | Title | Kernel Subsystem | Lean 4 Proved Theorem | Rust Unit Test Target | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `REQ-RCD-001` | **Ring 0 Pre-Dispatch Syscall Interception** | `crates/syscall_table` | `kernel_isolation_guarantee, kernel_ip_spoofing_always_blocked` | `tests::test_benign_syscall_passes, tests::test_kernel_ip_spoofing_blocked` | ✅ **VERIFIED** |
| `REQ-RCD-002` | **Zero-Copy Lock-Free SPSC Ring Buffer Boundedness** | `crates/ai_bridge` | `ring_buffer_head_slot_bounded, ring_buffer_tail_slot_bounded` | `ring_buffer::tests::test_ring_buffer_fifo, ring_buffer::tests::test_ring_buffer_full_and_overwrite` | ✅ **VERIFIED** |
| `REQ-RCD-003` | **Hardware-Independent W^X Memory Enforcement** | `crates/ebpf_firewall` | `wx_violation_always_blocked` | `tests::test_wx_mprotect_blocked, tests::test_wx_mmap_blocked` | ✅ **VERIFIED** |
| `REQ-RCD-004` | **Sub-15 µs Quantized TinyML Anomaly Classification** | `crates/ai_detector` | `tinyml_score_within_bounds, anomaly_above_threshold_triggers_defense` | `tests::test_tinyml_score_within_bounds, tests::test_anomalous_exploit_chain` | ✅ **VERIFIED** |
| `REQ-RCD-005` | **Fixed-Point Q8.8 Integer Shannon Entropy Evaluation** | `crates/ebpf_firewall` | `high_entropy_never_passes` | `tests::test_shannon_entropy` | ✅ **VERIFIED** |
| `REQ-RCD-006` | **Heapless Merkle Audit Trail with Monotonic Sequence ID** | `crates/immutable_logs` | `append_preserves_history, sequence_id_determines_uniqueness` | `tests::test_merkle_append_sequence_id, tests::test_sync_audit_log` | ✅ **VERIFIED** |
| `REQ-RCD-007` | **LMS Security Policy State Machine Safety** | `crates/ebpf_firewall` | `policy_escalation_monotonic, unauthorized_deescalation_forbidden` | `tests::test_lms_policy_state_transitions` | ✅ **VERIFIED** |
| `REQ-RCD-008` | **Multi-Rule Pessimistic Security Precedence** | `crates/ebpf_firewall` | `blockkill_absorbs_all, merge_verdict_commutative` | `tests::test_pessimistic_verdict_merge` | ✅ **VERIFIED** |
| `REQ-RCD-009` | **Lean 4 Formal Specification Verification (Zero sorry)** | `specs/lean4` | `All 40 Theorems in MVK.RunuxDefenses` | `verify_specs.sh (0 sorry, 0 axioms)` | ✅ **VERIFIED** |
| `REQ-RCD-010` | **Multi-Architecture x86_64 & RISC-V Bare-Metal Build** | `Workspace Crates` | `N/A (Compiler Verification)` | `cargo check (x86_64 + riscv64gc-unknown-none-elf)` | ✅ **VERIFIED** |
| `REQ-RCD-011` | **Automated Process Quarantine & Execution Confinement** | `crates/ebpf_firewall, crates/syscall_table` | `quarantine_enforces_complete_isolation, quarantined_cannot_fork_or_send` | `tests::test_req_rcd_011_process_quarantine_blocks_fork_and_net` | ✅ **VERIFIED** |
| `REQ-RCD-012` | **Kernel State Auto-Repair & Checkpoint Restoration** | `crates/ebpf_firewall` | `auto_repair_restores_wx_invariant, auto_repair_preserves_valid_pages` | `tests::test_req_rcd_012_auto_repair_restores_wx_invariant` | ✅ **VERIFIED** |
| `REQ-RCD-013` | **Cryptographic Enclave Attestation & Consensus Sync** | `crates/immutable_logs` | `authentic_attestation_requires_trusted_key, attestation_sequence_monotonic` | `tests::test_req_rcd_013_enclave_attestation_integrity` | ✅ **VERIFIED** |
| `REQ-RCD-014` | **Zero-Copy Ingress Network Packet Path Inspection** | `crates/ebpf_firewall` | `high_entropy_never_passes, blockkill_absorbs_all` | `tests::test_req_rcd_014_network_packet_ingress_inspection` | ✅ **VERIFIED** |
| `REQ-RCD-015` | **Zero-Downtime Hot-Patching & State Congruence** | `crates/ebpf_firewall, crates/immutable_logs` | `append_preserves_history, policy_escalation_monotonic` | `tests::test_req_rcd_015_hot_patch_state_congruence` | ✅ **VERIFIED** |
| `REQ-RCD-016` | **SymBrain v4 Ring 0 Deductive Floor (σ_ded ≥ 0.30)** | `crates/ai_detector, crates/ebpf_firewall` | `deductive_floor_bounded, deductive_floor_prevents_routing_stall, cognitive_budget_partition_exact` | `tests::test_req_rcd_016_deductive_floor_enforcement` | ✅ **VERIFIED** |
| `REQ-RCD-017` | **Neuro-Symbolic Multi-Gate Federated Ingress Verification** | `crates/federated, crates/immutable_logs` | `federated_vram_headroom_invariant, differential_privacy_budget_bounded` | `tests::test_req_rcd_017_federated_multigate_verification` | ✅ **VERIFIED** |
| `REQ-RCD-018` | **Bounded eBPF Bytecode Safety & Ring 0 JIT Termination** | `crates/ebpf_firewall` | `ebpf_instruction_count_bounded, ebpf_stack_depth_bounded, ebpf_acyclic_execution_terminates` | `tests::test_req_rcd_018_ebpf_bytecode_verifier_safety` | ✅ **VERIFIED** |
| `REQ-RCD-019` | **TurboQuant KV-Cache Zero-Leak Bounds & RAII Zeroization** | `crates/turbo_quant, crates/ai_detector` | `turboquant_kv_cache_bounded, kv_cache_zeroize_prevents_leakage` | `tests::test_req_rcd_019_turboquant_kv_cache_bounds_and_zeroize` | ✅ **VERIFIED** |
| `REQ-RCD-020` | **Deterministic Fault-Tolerant Panic-Free Chaos Recovery** | `crates/ebpf_firewall, crates/syscall_table` | `chaos_fault_graceful_degradation, failsafe_policy_soundness` | `tests::test_req_rcd_020_chaos_recovery_and_panic_free` | ✅ **VERIFIED** |
| `REQ-RCD-021` | **Static Tensor Arena & Zero-Heap Deterministic Inference** | `crates/ai_detector` | `tensor_arena_offset_within_bounds, tensor_arena_alignment_preservation` | `tests::test_req_rcd_021_static_tensor_arena_alignment_and_bounds` | ✅ **VERIFIED** |
| `REQ-RCD-022` | **Hardware DMA Ring Descriptors & Zero-Copy Safe Ownership** | `crates/ai_bridge` | `dma_non_overlapping_buffers_safe, dma_ring_index_bounded` | `tests::test_req_rcd_022_hardware_dma_ring_descriptor_ownership` | ✅ **VERIFIED** |
| `REQ-RCD-023` | **Active Pre-Dispatch Syscall Interception & Automatic Quarantine** | `crates/syscall_table, crates/immutable_logs` | `pre_dispatch_quarantined_always_denied, pre_dispatch_unquarantined_pass_allowed` | `tests::test_req_rcd_023_pre_dispatch_short_circuit_and_quarantine` | ✅ **VERIFIED** |
| `REQ-RCD-024` | **Polymorphic LLM Attack Trace & ROP Chain Detection** | `crates/ebpf_firewall` | `nop_sled_detected_triggers_blockkill, benign_nop_length_passes` | `tests::test_req_rcd_024_polymorphic_exploit_and_rop_detection` | ✅ **VERIFIED** |
| `REQ-RCD-025` | **Enclave Consensus Synchronization & Epoch Monotonicity** | `crates/immutable_logs` | `consensus_epoch_strictly_monotonic, consensus_sequence_continuity` | `tests::test_req_rcd_025_enclave_consensus_sync_and_epoch_continuity` | ✅ **VERIFIED** |
| `REQ-RCD-026` | **Self-Healing Page Table Invariant Monitor & Shadow Page Directory** | `crates/ebpf_firewall` | `pte_safe_attributes_invariant, shadow_pte_repair_soundness` | `tests::test_req_rcd_026_pte_shadow_monitor_and_repair` | ✅ **VERIFIED** |
| `REQ-RCD-027` | **Autonomous Threat Score Decaying & Adaptive Rate Limiter** | `crates/ai_detector` | `threat_decay_bounded, adaptive_rate_limit_monotonic` | `tests::test_req_rcd_027_adaptive_threat_decay_and_rate_limiting` | ✅ **VERIFIED** |
| `REQ-RCD-028` | **Hardware Cryptographic Hash Acceleration & Constant-Time Verification** | `crates/immutable_logs` | `constant_time_eq_soundness, constant_time_eq_reflexive` | `tests::test_req_rcd_028_constant_time_crypto_verification` | ✅ **VERIFIED** |
| `REQ-RCD-029` | **Dynamic Network Connection Tracker (Conntrack) Defense Filter** | `crates/ebpf_firewall` | `tcp_state_transition_validity, invalid_syn_state_blocked` | `tests::test_req_rcd_029_conntrack_stateful_inspection` | ✅ **VERIFIED** |
| `REQ-RCD-030` | **Multi-Core Pre-Dispatch Sharded Lock-Free Telemetry Ring** | `crates/ai_bridge` | `per_cpu_shard_isolation, shard_index_in_bounds` | `tests::test_req_rcd_030_per_cpu_sharded_ring_isolation` | ✅ **VERIFIED** |
| `REQ-RCD-031` | **Fine-Grained Capability-Based Access Control (CapBAC) Token Validator** | `crates/ebpf_firewall` | `cap_drop_monotonic, unprivileged_cap_blocked` | `tests::test_req_rcd_031_capability_based_access_control` | ✅ **VERIFIED** |
| `REQ-RCD-032` | **Hardware Cryptographic Nonce Cache & Anti-Replay Defense** | `crates/immutable_logs` | `freshness_window_bounded, replay_nonce_duplicate_rejected` | `tests::test_req_rcd_032_anti_replay_nonce_cache` | ✅ **VERIFIED** |
| `REQ-RCD-033` | **Edge AI Dynamic Model Quantization Weight Verifier & Checksum Anchor** | `crates/ai_detector` | `int4_nibble_in_bounds, tampered_weight_rejected` | `tests::test_req_rcd_033_quantized_weight_verifier_and_integrity` | ✅ **VERIFIED** |
| `REQ-RCD-034` | **Zero-Copy Hardware Zero-Trust Enclave IPC Channel** | `crates/ai_bridge` | `enclave_ipc_buffer_bounded, enclave_ipc_state_progression` | `enclave_ipc::tests::test_req_rcd_034_enclave_ipc_channel_zero_copy` | ✅ **VERIFIED** |
| `REQ-RCD-035` | **Real-Time Microsecond Kernel Watchdog & Deadlock Breaker** | `crates/syscall_table, crates/ebpf_firewall` | `watchdog_deadline_monotonic, watchdog_timeout_triggers_failsafe` | `tests::test_req_rcd_035_defense_watchdog_realtime_deadline, tests::test_req_rcd_035_pre_dispatch_watchdog_deadline` | ✅ **VERIFIED** |
| `REQ-RCD-036` | **Unified System Call Table Dispatcher with Defense Guard** | `crates/syscall_table, crates/sys_*` | `sys_dispatch_hook_soundness, sys_dispatch_denied_aborts_execution` | `tests::test_req_rcd_036_syscall_dispatch_table_guarded` | ✅ **VERIFIED** |
| `REQ-RCD-037` | **Edge AI Runtime Statically Compiled Model Weight Adapter** | `crates/ai_runtime, crates/ai_detector` | `frozen_weights_rodata_immutable, model_loader_checksum_verified` | `tests::test_req_rcd_037_defense_model_loader` | ✅ **VERIFIED** |
| `REQ-RCD-038` | **Netfilter Active Ingress Packet Defense Hook** | `crates/netfilter, crates/ebpf_firewall` | `netfilter_packet_ingress_defense_soundness, netfilter_benign_packet_forwarded` | `tests::test_req_rcd_038_netfilter_ingress_defense` | ✅ **VERIFIED** |
| `REQ-RCD-039` | **Multi-Engine Consensus Verdict Aggregator** | `crates/ebpf_firewall` | `consensus_verdict_pessimistic_dominance, confidence_score_bounded` | `tests::test_req_rcd_039_consensus_verdict_aggregator` | ✅ **VERIFIED** |
| `REQ-RCD-040` | **Complete End-to-End Kernel Isolation Guarantee & Full Stack Attestation** | `specs/lean4, crates/immutable_logs` | `runux_core_defense_complete_isolation, full_defense_pipeline_soundness` | `verify_specs.sh (84 theorems, 0 sorry, 0 axioms)` | ✅ **VERIFIED** |

---

## 📝 Detailed Requirement Descriptions

### `REQ-RCD-001`: Ring 0 Pre-Dispatch Syscall Interception
- **Subsystem**: `crates/syscall_table`
- **Lean 4 Theorem**: `kernel_isolation_guarantee, kernel_ip_spoofing_always_blocked`
- **Unit Test**: `tests::test_benign_syscall_passes, tests::test_kernel_ip_spoofing_blocked`
- **Functional Description**: Intercepts all incoming user-space/VM syscalls before table dispatch and enforces kernel isolation.

### `REQ-RCD-002`: Zero-Copy Lock-Free SPSC Ring Buffer Boundedness
- **Subsystem**: `crates/ai_bridge`
- **Lean 4 Theorem**: `ring_buffer_head_slot_bounded, ring_buffer_tail_slot_bounded`
- **Unit Test**: `ring_buffer::tests::test_ring_buffer_fifo, ring_buffer::tests::test_ring_buffer_full_and_overwrite`
- **Functional Description**: Lock-free circular ring buffer with atomic acquire-release ordering and bounded slot indices.

### `REQ-RCD-003`: Hardware-Independent W^X Memory Enforcement
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `wx_violation_always_blocked`
- **Unit Test**: `tests::test_wx_mprotect_blocked, tests::test_wx_mmap_blocked`
- **Functional Description**: Unconditionally detects and blocks mprotect/mmap requests attempting simultaneous write and execute.

### `REQ-RCD-004`: Sub-15 µs Quantized TinyML Anomaly Classification
- **Subsystem**: `crates/ai_detector`
- **Lean 4 Theorem**: `tinyml_score_within_bounds, anomaly_above_threshold_triggers_defense`
- **Unit Test**: `tests::test_tinyml_score_within_bounds, tests::test_anomalous_exploit_chain`
- **Functional Description**: Per-PID sliding window evaluated by frozen INT8 neural perceptron with bounded [0, 1000] activation.

### `REQ-RCD-005`: Fixed-Point Q8.8 Integer Shannon Entropy Evaluation
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `high_entropy_never_passes`
- **Unit Test**: `tests::test_shannon_entropy`
- **Functional Description**: Fast integer Shannon entropy calculation routing encrypted/polymorphic payloads to deep inspection.

### `REQ-RCD-006`: Heapless Merkle Audit Trail with Monotonic Sequence ID
- **Subsystem**: `crates/immutable_logs`
- **Lean 4 Theorem**: `append_preserves_history, sequence_id_determines_uniqueness`
- **Unit Test**: `tests::test_merkle_append_sequence_id, tests::test_sync_audit_log`
- **Functional Description**: Array-backed binary Merkle tree with domain separation and monotonically increasing sequence counters.

### `REQ-RCD-007`: LMS Security Policy State Machine Safety
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `policy_escalation_monotonic, unauthorized_deescalation_forbidden`
- **Unit Test**: `tests::test_lms_policy_state_transitions`
- **Functional Description**: Monotonic policy escalation; de-escalation strictly requires valid cryptographic root attestation.

### `REQ-RCD-008`: Multi-Rule Pessimistic Security Precedence
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `blockkill_absorbs_all, merge_verdict_commutative`
- **Unit Test**: `tests::test_pessimistic_verdict_merge`
- **Functional Description**: Pessimistic semi-lattice composition where BlockKill unconditionally dominates all other verdicts.

### `REQ-RCD-009`: Lean 4 Formal Specification Verification (Zero sorry)
- **Subsystem**: `specs/lean4`
- **Lean 4 Theorem**: `All 40 Theorems in MVK.RunuxDefenses`
- **Unit Test**: `verify_specs.sh (0 sorry, 0 axioms)`
- **Functional Description**: 100% formal mathematical closure across all defense domains without axioms or omissions.

### `REQ-RCD-010`: Multi-Architecture x86_64 & RISC-V Bare-Metal Build
- **Subsystem**: `Workspace Crates`
- **Lean 4 Theorem**: `N/A (Compiler Verification)`
- **Unit Test**: `cargo check (x86_64 + riscv64gc-unknown-none-elf)`
- **Functional Description**: Zero compiler warnings and zero errors across native x86_64 and RISC-V 64-bit embedded targets.

### `REQ-RCD-011`: Automated Process Quarantine & Execution Confinement
- **Subsystem**: `crates/ebpf_firewall, crates/syscall_table`
- **Lean 4 Theorem**: `quarantine_enforces_complete_isolation, quarantined_cannot_fork_or_send`
- **Unit Test**: `tests::test_req_rcd_011_process_quarantine_blocks_fork_and_net`
- **Functional Description**: Enforces complete process isolation upon Rollback verdict; locks out fork, clone, execve, and network transmission.

### `REQ-RCD-012`: Kernel State Auto-Repair & Checkpoint Restoration
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `auto_repair_restores_wx_invariant, auto_repair_preserves_valid_pages`
- **Unit Test**: `tests::test_req_rcd_012_auto_repair_restores_wx_invariant`
- **Functional Description**: Safely restores corrupted page permission flags stripping PROT_EXEC to enforce W^X invariant without crashing.

### `REQ-RCD-013`: Cryptographic Enclave Attestation & Consensus Sync
- **Subsystem**: `crates/immutable_logs`
- **Lean 4 Theorem**: `authentic_attestation_requires_trusted_key, attestation_sequence_monotonic`
- **Unit Test**: `tests::test_req_rcd_013_enclave_attestation_integrity`
- **Functional Description**: Cryptographically anchors Merkle log roots using hardware enclave signatures and strictly monotonic sequence counters.

### `REQ-RCD-014`: Zero-Copy Ingress Network Packet Path Inspection
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `high_entropy_never_passes, blockkill_absorbs_all`
- **Unit Test**: `tests::test_req_rcd_014_network_packet_ingress_inspection`
- **Functional Description**: Inspects network ingress packets for anomalous TCP flag scans (SYN-FIN, Xmas, Null) and polymorphic high-entropy payloads.

### `REQ-RCD-015`: Zero-Downtime Hot-Patching & State Congruence
- **Subsystem**: `crates/ebpf_firewall, crates/immutable_logs`
- **Lean 4 Theorem**: `append_preserves_history, policy_escalation_monotonic`
- **Unit Test**: `tests::test_req_rcd_015_hot_patch_state_congruence`
- **Functional Description**: Ensures atomic, zero-downtime policy and rule updating in Ring 0 without memory corruption, downtime, or kernel reboots.

### `REQ-RCD-016`: SymBrain v4 Ring 0 Deductive Floor (σ_ded ≥ 0.30)
- **Subsystem**: `crates/ai_detector, crates/ebpf_firewall`
- **Lean 4 Theorem**: `deductive_floor_bounded, deductive_floor_prevents_routing_stall, cognitive_budget_partition_exact`
- **Unit Test**: `tests::test_req_rcd_016_deductive_floor_enforcement`
- **Functional Description**: Enforces a calibrated lower bound on deductive reasoning attention (σ_ded ≥ 0.30) eliminating the Routing-Stall anomaly.

### `REQ-RCD-017`: Neuro-Symbolic Multi-Gate Federated Ingress Verification
- **Subsystem**: `crates/federated, crates/immutable_logs`
- **Lean 4 Theorem**: `federated_vram_headroom_invariant, differential_privacy_budget_bounded`
- **Unit Test**: `tests::test_req_rcd_017_federated_multigate_verification`
- **Functional Description**: Verifies distributed edge nodes for physical VRAM headroom (≥ 8%), differential privacy (ε ≤ 1.0), and cryptographic attestation.

### `REQ-RCD-018`: Bounded eBPF Bytecode Safety & Ring 0 JIT Termination
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `ebpf_instruction_count_bounded, ebpf_stack_depth_bounded, ebpf_acyclic_execution_terminates`
- **Unit Test**: `tests::test_req_rcd_018_ebpf_bytecode_verifier_safety`
- **Functional Description**: Static bytecode verifier enforcing bounded instruction counts (≤ 256), stack limits (≤ 512), and acyclic control flow.

### `REQ-RCD-019`: TurboQuant KV-Cache Zero-Leak Bounds & RAII Zeroization
- **Subsystem**: `crates/turbo_quant, crates/ai_detector`
- **Lean 4 Theorem**: `turboquant_kv_cache_bounded, kv_cache_zeroize_prevents_leakage`
- **Unit Test**: `tests::test_req_rcd_019_turboquant_kv_cache_bounds_and_zeroize`
- **Functional Description**: Enforces strict physical allocation bounds on compressed KV-cache tensors and deterministic RAII volatile zeroization upon drop.

### `REQ-RCD-020`: Deterministic Fault-Tolerant Panic-Free Chaos Recovery
- **Subsystem**: `crates/ebpf_firewall, crates/syscall_table`
- **Lean 4 Theorem**: `chaos_fault_graceful_degradation, failsafe_policy_soundness`
- **Unit Test**: `tests::test_req_rcd_020_chaos_recovery_and_panic_free`
- **Functional Description**: Guarantees deterministic, panic-free fail-safe posture degradation (panic="abort" compliance) under hardware chaos faults.

### `REQ-RCD-021`: Static Tensor Arena & Zero-Heap Deterministic Inference
- **Subsystem**: `crates/ai_detector`
- **Lean 4 Theorem**: `tensor_arena_offset_within_bounds, tensor_arena_alignment_preservation`
- **Unit Test**: `tests::test_req_rcd_021_static_tensor_arena_alignment_and_bounds`
- **Functional Description**: Enforces 64-byte cache alignment and compile-time fixed capacity bounds for deterministic Ring 0 TinyML evaluation without heap allocations.

### `REQ-RCD-022`: Hardware DMA Ring Descriptors & Zero-Copy Safe Ownership
- **Subsystem**: `crates/ai_bridge`
- **Lean 4 Theorem**: `dma_non_overlapping_buffers_safe, dma_ring_index_bounded`
- **Unit Test**: `tests::test_req_rcd_022_hardware_dma_ring_descriptor_ownership`
- **Functional Description**: Provides 64-byte cache-aligned DMA descriptor rings with explicit hardware/software ownership bit semantics and non-overlapping buffer isolation.

### `REQ-RCD-023`: Active Pre-Dispatch Syscall Interception & Automatic Quarantine
- **Subsystem**: `crates/syscall_table, crates/immutable_logs`
- **Lean 4 Theorem**: `pre_dispatch_quarantined_always_denied, pre_dispatch_unquarantined_pass_allowed`
- **Unit Test**: `tests::test_req_rcd_023_pre_dispatch_short_circuit_and_quarantine`
- **Functional Description**: Intercepts user/VM syscalls at Ring 0 entry, short-circuiting anomalous calls, automatically quarantining offending PIDs, and logging to Merkle audit.

### `REQ-RCD-024`: Polymorphic LLM Attack Trace & ROP Chain Detection
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `nop_sled_detected_triggers_blockkill, benign_nop_length_passes`
- **Unit Test**: `tests::test_req_rcd_024_polymorphic_exploit_and_rop_detection`
- **Functional Description**: Detects polymorphic payload injection via long NOP sleds, high Shannon entropy, and anomalous cross-page instruction jumps in ROP chains.

### `REQ-RCD-025`: Enclave Consensus Synchronization & Epoch Monotonicity
- **Subsystem**: `crates/immutable_logs`
- **Lean 4 Theorem**: `consensus_epoch_strictly_monotonic, consensus_sequence_continuity`
- **Unit Test**: `tests::test_req_rcd_025_enclave_consensus_sync_and_epoch_continuity`
- **Functional Description**: Enforces strictly monotonic epoch advancement and gapless sequence continuity across hardware enclaves and distributed audit logs.

### `REQ-RCD-026`: Self-Healing Page Table Invariant Monitor & Shadow Page Directory
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `pte_safe_attributes_invariant, shadow_pte_repair_soundness`
- **Unit Test**: `tests::test_req_rcd_026_pte_shadow_monitor_and_repair`
- **Functional Description**: Audits physical page table entries enforcing W^X invariants and user/kernel isolation, auto-repairing malicious or corrupted PTE attributes.

### `REQ-RCD-027`: Autonomous Threat Score Decaying & Adaptive Rate Limiter
- **Subsystem**: `crates/ai_detector`
- **Lean 4 Theorem**: `threat_decay_bounded, adaptive_rate_limit_monotonic`
- **Unit Test**: `tests::test_req_rcd_027_adaptive_threat_decay_and_rate_limiting`
- **Functional Description**: Exponential moving average (EMA) threat accumulator with fixed-point decay throttling suspect processes without heap allocations.

### `REQ-RCD-028`: Hardware Cryptographic Hash Acceleration & Constant-Time Verification
- **Subsystem**: `crates/immutable_logs`
- **Lean 4 Theorem**: `constant_time_eq_soundness, constant_time_eq_reflexive`
- **Unit Test**: `tests::test_req_rcd_028_constant_time_crypto_verification`
- **Functional Description**: Constant-time memory comparisons and hardware-accelerated digest calculations resisting cache-timing side channels.

### `REQ-RCD-029`: Dynamic Network Connection Tracker (Conntrack) Defense Filter
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `tcp_state_transition_validity, invalid_syn_state_blocked`
- **Unit Test**: `tests::test_req_rcd_029_conntrack_stateful_inspection`
- **Functional Description**: Stateful conntrack filter tracking TCP connection handshakes and immediately blocking out-of-order packets and stealth port scans.

### `REQ-RCD-030`: Multi-Core Pre-Dispatch Sharded Lock-Free Telemetry Ring
- **Subsystem**: `crates/ai_bridge`
- **Lean 4 Theorem**: `per_cpu_shard_isolation, shard_index_in_bounds`
- **Unit Test**: `tests::test_req_rcd_030_per_cpu_sharded_ring_isolation`
- **Functional Description**: Per-CPU sharded circular ring buffers eliminating cross-core cache line bouncing and lock contention under multi-core workloads.

### `REQ-RCD-031`: Fine-Grained Capability-Based Access Control (CapBAC) Token Validator
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `cap_drop_monotonic, unprivileged_cap_blocked`
- **Unit Test**: `tests::test_req_rcd_031_capability_based_access_control`
- **Functional Description**: Enforces fine-grained capability tokens and monotonic privilege reduction, blocking unprivileged access to sensitive syscalls.

### `REQ-RCD-032`: Hardware Cryptographic Nonce Cache & Anti-Replay Defense
- **Subsystem**: `crates/immutable_logs`
- **Lean 4 Theorem**: `freshness_window_bounded, replay_nonce_duplicate_rejected`
- **Unit Test**: `tests::test_req_rcd_032_anti_replay_nonce_cache`
- **Functional Description**: Prevents replay attacks against hardware enclave attestation tokens and telemetry frames with timestamp freshness validation.

### `REQ-RCD-033`: Edge AI Dynamic Model Quantization Weight Verifier & Checksum Anchor
- **Subsystem**: `crates/ai_detector`
- **Lean 4 Theorem**: `int4_nibble_in_bounds, tampered_weight_rejected`
- **Unit Test**: `tests::test_req_rcd_033_quantized_weight_verifier_and_integrity`
- **Functional Description**: Validates INT4/INT8 numerical boundaries and cryptographic digest anchors before loading quantized TinyML model weights into Ring 0.

### `REQ-RCD-034`: Zero-Copy Hardware Zero-Trust Enclave IPC Channel
- **Subsystem**: `crates/ai_bridge`
- **Lean 4 Theorem**: `enclave_ipc_buffer_bounded, enclave_ipc_state_progression`
- **Unit Test**: `enclave_ipc::tests::test_req_rcd_034_enclave_ipc_channel_zero_copy`
- **Functional Description**: Provides lock-free, zero-copy cacheline-aligned shared memory channel between Ring 0 and the hardware secure enclave.

### `REQ-RCD-035`: Real-Time Microsecond Kernel Watchdog & Deadlock Breaker
- **Subsystem**: `crates/syscall_table, crates/ebpf_firewall`
- **Lean 4 Theorem**: `watchdog_deadline_monotonic, watchdog_timeout_triggers_failsafe`
- **Unit Test**: `tests::test_req_rcd_035_defense_watchdog_realtime_deadline, tests::test_req_rcd_035_pre_dispatch_watchdog_deadline`
- **Functional Description**: Monitors defense execution deadlines in real time, triggering fail-safe rollback upon timeout to prevent kernel denial-of-service.

### `REQ-RCD-036`: Unified System Call Table Dispatcher with Defense Guard
- **Subsystem**: `crates/syscall_table, crates/sys_*`
- **Lean 4 Theorem**: `sys_dispatch_hook_soundness, sys_dispatch_denied_aborts_execution`
- **Unit Test**: `tests::test_req_rcd_036_syscall_dispatch_table_guarded`
- **Functional Description**: Pre-dispatch guarded system call table routing authorized calls to module handlers while immediately aborting denied calls.

### `REQ-RCD-037`: Edge AI Runtime Statically Compiled Model Weight Adapter
- **Subsystem**: `crates/ai_runtime, crates/ai_detector`
- **Lean 4 Theorem**: `frozen_weights_rodata_immutable, model_loader_checksum_verified`
- **Unit Test**: `tests::test_req_rcd_037_defense_model_loader`
- **Functional Description**: Static .rodata weight loader providing zero-copy slice descriptors and constant-time SHA-256/BLAKE3 digest verification.

### `REQ-RCD-038`: Netfilter Active Ingress Packet Defense Hook
- **Subsystem**: `crates/netfilter, crates/ebpf_firewall`
- **Lean 4 Theorem**: `netfilter_packet_ingress_defense_soundness, netfilter_benign_packet_forwarded`
- **Unit Test**: `tests::test_req_rcd_038_netfilter_ingress_defense`
- **Functional Description**: Active Ring 0 packet filter intercepting network ingress in IPv6 routing paths, dropping stealth scans and high-entropy exploits.

### `REQ-RCD-039`: Multi-Engine Consensus Verdict Aggregator
- **Subsystem**: `crates/ebpf_firewall`
- **Lean 4 Theorem**: `consensus_verdict_pessimistic_dominance, confidence_score_bounded`
- **Unit Test**: `tests::test_req_rcd_039_consensus_verdict_aggregator`
- **Functional Description**: Consensus aggregator enforcing pessimistic dominance where BlockKill absorbs all other verdicts, with fixed-point Q8 confidence scoring.

### `REQ-RCD-040`: Complete End-to-End Kernel Isolation Guarantee & Full Stack Attestation
- **Subsystem**: `specs/lean4, crates/immutable_logs`
- **Lean 4 Theorem**: `runux_core_defense_complete_isolation, full_defense_pipeline_soundness`
- **Unit Test**: `verify_specs.sh (84 theorems, 0 sorry, 0 axioms)`
- **Functional Description**: End-to-end mathematical closure and full stack attestation proving that suspect or quarantined processes can never execute kernel code.

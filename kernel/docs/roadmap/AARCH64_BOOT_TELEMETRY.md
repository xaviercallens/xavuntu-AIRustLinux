# AArch64 Boot Telemetry — Clean-Room GCP Verification

**Status: real, reproducible, narrow.** Companion to
[`RISCV_BOOT_TELEMETRY.md`](RISCV_BOOT_TELEMETRY.md) and
[`X86_64_BOOT_TELEMETRY.md`](X86_64_BOOT_TELEMETRY.md) — same method,
same scope limits, this time for `examples/aarch64_qemu_harness`
([#73](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/73)),
a from-scratch third architecture (no AArch64 code existed in this repo
before that PR). **Not** a comparison against Linux or a feature-parity
claim — this harness has no scheduler, no drivers beyond a serial UART
poke, no filesystem, and no userspace.

## What was run, and where

- **Instance:** a fresh GCP `e2-micro` VM (`us-central1-a`, Debian 12,
  10GB `pd-standard` disk — always-free tier), created solely for this
  verification and deleted afterward. `/dev/kvm` was not used (no
  aarch64-on-aarch64 hardware acceleration is possible from an x86_64
  host regardless); every boot below is QEMU TCG emulation.
- **Software installed:** `qemu-system-arm` (provides
  `qemu-system-aarch64`) via `apt-get` (real root, standard package),
  plus stable Rust via `rustup` with the `aarch64-unknown-none` target
  added.
- **Source:** `git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git`
  over HTTPS at commit `fc98869` (merge of
  [#73](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/73)).
- **Correctness check:** `bash scripts/aarch64_boot_test.sh --timeout 15`,
  unmodified — `PASS`.
- **Telemetry:** `bash scripts/aarch64_boot_bench.sh --runs 30 --timeout 15`.

## Results (n=30, 2026-09-27)

| Metric | Value |
|---|---|
| Pass rate | 30/30 |
| Mean boot time | 0.0392 s |
| Stddev | 0.0011 s |
| 95% CI (normal approx.) | [0.0388 s, 0.0395 s] |
| Min / Max | 0.0376 s / 0.0415 s |

Raw per-run CSV: [`boot_telemetry/aarch64_boot_bench_2026-09-27.csv`](boot_telemetry/aarch64_boot_bench_2026-09-27.csv).

**This is the fastest of the three harnesses** (0.039s vs. RISC-V's
0.062s and x86_64's 0.552s) — it has the simplest boot path of the
three: QEMU's aarch64 `-kernel` loader starts the raw ELF directly with
no firmware stage at all (no OpenSBI handshake like RISC-V, no
BIOS+GRUB+ISO9660 like x86_64). This is a boot-*path* difference, not a
claim about the kernel code being "better," and says so explicitly, the
same as the other two telemetry docs.

**Host environment:** AMD EPYC 7B12 (x86_64, cross-emulating aarch64
via TCG — no native ARM hardware was used), QEMU 7.2.22, Debian 12
bookworm. Re-run `scripts/aarch64_boot_bench.sh` yourself for your own
machine's numbers.

## Downloadable artifact

The exact binary measured above — `aarch64_qemu_harness`,
`aarch64-unknown-none`, release profile, built at commit `fc98869` —
is attached to the
[boot-verified release](https://github.com/xaviercallens/rust-linux-mini-kernel/releases)
along with this CSV. SHA-256:
`06010355af0ca8db4f72740c7681b395262251e0f1eee1bd3cd965a9e6f7c8d9`.
Boot it directly, no packaging needed (unlike the x86_64 binary):

```bash
qemu-system-aarch64 -machine virt -cpu cortex-a72 -nographic -nic none \
  -kernel aarch64-qemu-harness-v11.3.7
```

No standing cloud service was left running: the GCP VM was deleted
after these artifacts were captured. No public SSH access to any
project infrastructure exists; see `SECURITY.md`.

## What this does and doesn't show

- **Does show:** `examples/aarch64_qemu_harness` performs a genuine
  exception-level descent (defensively handling EL3/EL2/EL1 starting
  states), reaches EL1, and calls real `kernel_types::SafePageFrame`
  logic — both the valid-pointer and null-rejection paths — over a real
  PL011 UART, then shuts down cleanly via PSCI `SYSTEM_OFF`. This works
  outside the original development environment, consistently across 30
  runs, on a from-scratch architecture port with zero prior AArch64
  code in this repository to build on.
- **Doesn't show:** performance or feature comparability with Linux
  (not attempted), behavior on physical ARM64 hardware (QEMU/TCG
  cross-emulation only — no native ARM silicon was used anywhere in
  this verification), or anything about subsystem init beyond the one
  type exercised — there is no real GIC, no real page tables, no
  scheduler (see `ROADMAP.md` T3/M3).

## Reproduce this yourself

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel
sudo apt-get install -y qemu-system-arm
rustup target add aarch64-unknown-none
bash scripts/aarch64_boot_test.sh                          # correctness, single run
bash scripts/aarch64_boot_bench.sh --runs 30 --timeout 15   # telemetry, n=30
```

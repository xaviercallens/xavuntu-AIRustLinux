# RISC-V Boot Telemetry — Clean-Room GCP Verification

**Status: real, reproducible, narrow.** This documents one measurement —
QEMU boot latency of `examples/riscv_qemu_harness` — run on a machine
neither developing nor previously touching this repo. It is **not** a
comparison against Linux or any claim of feature parity: RunuX's RISC-V
harness has no scheduler, no drivers, no filesystem, and no userspace, so
there is no comparable workload to benchmark it against yet. See
[`README.md`](../../README.md) → *Measured Status* for what else does and
doesn't exist.

## What was run, and where

- **Instance:** a fresh GCP `e2-micro` VM (`us-central1-a`, Debian 12,
  10GB `pd-standard` disk — inside Google's always-free tier), created
  solely for this verification and deleted afterward.
- **Software installed:** `qemu-system-misc` via `apt-get` (real root,
  standard package, no workarounds), stable Rust via `rustup` with the
  `riscv64gc-unknown-none-elf` target added.
- **Source:** `git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git`
  over HTTPS (no local state, no cached artifacts) at commit
  `55b7803` (merge of [#69](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/69)).
- **Correctness check:** `bash scripts/riscv_boot_test.sh --timeout 15`,
  unmodified, run first — `PASS`.
- **Telemetry:** `bash scripts/riscv_boot_bench.sh --runs 30 --timeout 15`
  (new script, added in this PR), which builds once and then boots the
  harness 30 times, timing each run from QEMU launch to the kernel's own
  clean shutdown (SiFive test-finisher device, exit code 0) and
  re-checking the full banner sequence every time.

## Results (n=30, 2026-09-27)

| Metric | Value |
|---|---|
| Pass rate | 30/30 |
| Mean boot time | 0.0617 s |
| Stddev | 0.0015 s |
| 95% CI (normal approx.) | [0.0611 s, 0.0622 s] |
| Min / Max | 0.0593 s / 0.0643 s |

Raw per-run CSV: [`boot_telemetry/riscv_boot_bench_2026-09-27.csv`](boot_telemetry/riscv_boot_bench_2026-09-27.csv).

**Host environment** (affects absolute numbers, not the pass/fail
result): AMD EPYC 7B12, QEMU 7.2.22, Debian 12 bookworm, x86_64 host
emulating riscv64. Re-run `scripts/riscv_boot_bench.sh` yourself to get
numbers for your own machine — this is a measurement of one machine, not
a portable performance claim.

## Downloadable artifact

The exact binary measured above — `riscv_qemu_harness`,
`riscv64gc-unknown-none-elf`, release profile, built at commit `55b7803`
— is attached to the
[boot-verified release](https://github.com/xaviercallens/rust-linux-mini-kernel/releases)
along with this CSV, for anyone to boot locally with their own QEMU
(`qemu-system-riscv64 -machine virt -nographic -bios default -kernel
riscv_qemu_harness`) without needing a Rust toolchain. SHA-256:
`240f35e471efc5acb8e6aed14b8fb38a7374b7039c5f8e98fc0aaeb1b8c0e69e`.

No standing cloud service was left running: the GCP VM was deleted after
these artifacts were captured. There is no public SSH access to any
project infrastructure — this is intentional; see `SECURITY.md`.

## What this does and doesn't show

- **Does show:** the boot path in `arch/riscv64` + `examples/riscv_qemu_harness`
  is real, works outside the original development environment, and boots
  in ~62ms under QEMU on commodity cloud hardware, consistently across 30 runs.
- **Doesn't show:** performance or feature comparability with Linux (not
  attempted — see the framing note above), behavior on physical RISC-V
  hardware (QEMU only), or anything about the subsystem-init stubs
  (`riscv_arch_init`/`riscv_irq_init`/`riscv_pgtable_init` print banners
  but don't yet wire real PLIC/Sv39 state — see `ROADMAP.md` T3/M3).

## Reproduce this yourself

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel
sudo apt-get install -y qemu-system-misc   # or brew install qemu on macOS
rustup target add riscv64gc-unknown-none-elf
bash scripts/riscv_boot_test.sh                          # correctness, single run
bash scripts/riscv_boot_bench.sh --runs 30 --timeout 15   # telemetry, n=30
```

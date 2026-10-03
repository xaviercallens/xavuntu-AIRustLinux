# x86_64 Boot Telemetry — Clean-Room GCP Verification

**Status: real, reproducible, narrow.** Companion to
[`RISCV_BOOT_TELEMETRY.md`](RISCV_BOOT_TELEMETRY.md) — same method, same
scope limits, this time for `examples/x86_64_qemu_harness` (genuine
64-bit long mode via GRUB Multiboot2, not the older
`examples/demo_kernel` 32-bit trick). **Not** a comparison against
Linux or a feature-parity claim — this harness has no scheduler, no
drivers beyond a serial UART poke, no filesystem, and no userspace.

## What was run, and where

- **Instance:** a fresh GCP `e2-micro` VM (`us-central1-a`, Debian 12,
  10GB `pd-standard` disk — always-free tier), created solely for this
  verification and deleted afterward. `/dev/kvm` was **not** present
  (this shared-core tier has no nested virtualization), so every boot
  below used QEMU's software TCG emulation, not hardware-accelerated
  KVM — the numbers reflect that.
- **Software installed:** `qemu-system-x86`, `grub-pc-bin`,
  `grub-common`, `xorriso`, `mtools` via `apt-get` (real root, standard
  packages, no workarounds — unlike the rootless extraction this took
  in my own sandbox to figure the recipe out), plus stable Rust via
  `rustup`.
- **Source:** `git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git`
  over HTTPS at commit `ed73aa8` (merge of
  [#71](https://github.com/xaviercallens/rust-linux-mini-kernel/pull/71)).
- **Correctness check:** `bash scripts/x86_64_boot_test.sh --timeout 20`,
  unmodified — `PASS`.
- **Telemetry:** `bash scripts/x86_64_boot_bench.sh --runs 30 --timeout 20`.

## Results (n=30, 2026-09-27)

| Metric | Value |
|---|---|
| Pass rate | 30/30 |
| Mean boot time | 0.5518 s |
| Stddev | 0.1375 s |
| 95% CI (normal approx.) | [0.5026 s, 0.6010 s] |
| Min / Max | 0.5121 s / 1.2722 s |

Raw per-run CSV: [`boot_telemetry/x86_64_boot_bench_2026-09-27.csv`](boot_telemetry/x86_64_boot_bench_2026-09-27.csv).
Run 2 (1.27s) is a clear outlier — likely one-time VM scheduling jitter
or cold cache, not a steady-state number; it is left in the raw data
rather than dropped.

**Why this is ~9x slower than the RISC-V harness (0.062s):** the
x86_64 path boots through full SeaBIOS POST, then GRUB parsing an
ISO9660 filesystem and loading the kernel, versus RISC-V's OpenSBI
loading a raw ELF directly via `-kernel`. This is a boot-*path*
difference (BIOS+GRUB+ISO vs. direct load), not a claim about the
kernel code itself, and neither number says anything about Linux.

**Host environment:** AMD EPYC 7B12, QEMU 7.2.22 (TCG, no KVM),
Debian 12 bookworm. Re-run `scripts/x86_64_boot_bench.sh` yourself for
your own machine's numbers, ideally with `/dev/kvm` available for a
hardware-accelerated comparison point.

## Downloadable artifact

The exact binary measured above — `x86_64_qemu_harness`,
`x86_64-unknown-linux-gnu`, release profile, built at commit `ed73aa8`
— is attached to the
[boot-verified release](https://github.com/xaviercallens/rust-linux-mini-kernel/releases)
along with this CSV. SHA-256:
`7a6e4e50e64f1f5004c06b560638d79044529c20e3a7425c157e8aa4682d6c29`.
Booting it requires packaging into a GRUB ISO first (see
`scripts/x86_64_boot_test.sh` for the exact recipe) — unlike the
RISC-V binary, it can't be handed straight to `-kernel`.

No standing cloud service was left running: the GCP VM was deleted
after these artifacts were captured. No public SSH access to any
project infrastructure exists; see `SECURITY.md`.

## What this does and doesn't show

- **Does show:** `examples/x86_64_qemu_harness` performs a genuine
  32-bit-protected-mode → long-mode CPU transition (PAE, `EFER.LME`,
  `CR0.PG`, a real GDT far-jump) and, once in 64-bit mode, calls real
  `kernel_types::SafePageFrame` logic — both the valid-pointer and
  null-rejection paths — not just print statements. This works outside
  the original development environment, consistently across 30 runs.
- **Doesn't show:** performance or feature comparability with Linux
  (not attempted), behavior on physical x86_64 hardware (QEMU/TCG
  only, no KVM available on this VM tier), or anything about
  subsystem init beyond the one type exercised — there is no IDT, no
  APIC, no real drivers, no scheduler (see `ROADMAP.md` T3/M3).

## Reproduce this yourself

```bash
git clone https://github.com/xaviercallens/rust-linux-mini-kernel.git
cd rust-linux-mini-kernel
sudo apt-get install -y qemu-system-x86 grub-pc-bin grub-common xorriso mtools
bash scripts/x86_64_boot_test.sh                          # correctness, single run
bash scripts/x86_64_boot_bench.sh --runs 30 --timeout 20   # telemetry, n=30
```

# Reddit + Hacker News launch kit

Nothing here has been posted. A human posts it, from their own account.
Every number below is copied from README → Measured Status; re-check it
against `python3 scripts/metrics.py measure` before posting, since numbers
drift.

## Ground rules (these decide whether it lands or gets removed)

1. **Disclose up front that AI agents wrote much of this code.** The whole
   story of the repo is that it was audited and found to contain
   hallucinated claims. Hiding the AI involvement and being found out is the
   worst outcome; leading with it is the hook.
2. **Lead with what you can try, not what you built.** Show HN requires
   something people can run; the 60-second quick-start is that.
3. **State the limits in the first paragraph.** Boot harness, not an OS. No
   scheduler, drivers, or userspace. 141 of 316 crates are placeholders.
4. **Never ask for upvotes, never share the link asking friends to upvote.**
   Both sites detect and penalize vote rings. Ask for feedback, not votes.
5. **Reply to every comment for the first ~3 hours, no defensiveness.**
   "You're right, that's a real gap, tracked in #N" is the winning answer.
6. **One site per day, and read each community's current rules/sidebar
   first.** Rules change and I cannot verify them from here.
7. **Reddit self-promotion norms:** most communities expect you to be a
   participant, not only a poster of your own links. Comment helpfully in
   those communities for a few days first if the account is new.

## Sequence

| Day | Where | Angle |
|---|---|---|
| 1 (Tue–Thu, ~8–10am US Eastern) | Hacker News, Show HN | Try it: boots on 3 architectures |
| 2 | r/rust | The `unsafe`/`static mut` audit + no_std multi-arch harness |
| 2–3 | r/osdev | The boot code itself: long-mode switch, AArch64 EL descent |
| 3–4 | r/RISCV, r/aarch64 (only if rules allow project posts) | One arch each, short |
| Week 2 | Hacker News (only if there's a real reason) or Lean Zulip | Negative-results story (TPU findings) |

Timing advice is a common heuristic, not a guarantee.

## Hacker News

**Title** (Show HN titles: plain, factual, no hype, no all-caps, ≤80 chars):

> Show HN: A Rust kernel harness that boots on x86_64, RISC-V and AArch64

**URL:** `https://github.com/xaviercallens/rust-linux-mini-kernel`

**First comment (post it yourself immediately; HN convention):**

> I've been building RunuX, a Rust reimplementation of pieces of Linux kernel subsystems, largely with AI coding agents. Last month I audited it and found many of its own claims were false ("297/297 modules, zero warnings" — 141 of 316 crates are placeholder stubs; "zero sorry" in the Lean specs — 245 are open; demo GIFs captioned as live recordings were hand-drawn). I corrected them and built tooling so it can't happen quietly again (a metrics ratchet, a proof oracle, a PR guard).
>
> The part you can try: prebuilt images for three architectures, no toolchain needed. The README quick-start is three curls and one QEMU command each. x86_64 goes through GRUB Multiboot2 and does a real 32→64-bit long-mode switch; RISC-V boots via OpenSBI; AArch64 is a from-scratch port (EL2→EL1 descent, PSCI shutdown). Each boot was also re-run 30 times on a fresh GCP VM (x86_64 mean 0.55s under TCG emulation, no KVM).
>
> What it is not: a usable OS. There's no scheduler, no drivers, no userspace, and the boot code exercises only a small slice of real crate code (`kernel_types::SafePageFrame`). I make no performance comparison with Linux.
>
> I also probed a Google Cloud TPU VM's PCI topology and found a bug in my own probe that could have corrupted the NIC carrying my SSH session (caught in review, fixed, disclosed in the docs). A custom GCE boot image currently gets to SeaBIOS but not past GRUB; that's documented as an open failure.
>
> Feedback I'd most like: does it boot on your hardware or hypervisor (including failures), and where the "measured status" table is still overclaiming.

**If it gets no traction:** don't repost. HN allows one resubmission of a
substantially different angle after a while; the TPU negative-results
writeup is that angle.

## Reddit

Use a text or link post per each subreddit's rules. Titles should be
specific and modest.

### r/rust

**Title:** I audited my own AI-assisted `no_std` Rust kernel project and found most of its claims were wrong. Here's the tooling and a 3-arch boot harness

**Body:**

> RunuX is a Rust reimplementation of pieces of Linux kernel subsystems (`#![no_std]`, `#[repr(C)]` FFI types). Much of it was written with AI coding agents, which is why I audited it: 141 of 316 crates were ≤25-line placeholders, the "zero warnings" came from blanket `#[allow(clippy::all)]` in 284 crates, and only 111 of 722 `unsafe` blocks had a `// SAFETY:` comment.
>
> What I built in response: a metrics ratchet that fails CI on regression, and an oracle that rejects a "fix" that adds `sorry`/`allow`/`todo!` or silently weakens a theorem.
>
> Rust-specific things you might find useful or want to critique: a from-scratch `arch/aarch64` in `no_std` with hand-written EL3/EL2→EL1 entry; an x86_64 Multiboot2 entry that builds page tables and switches to long mode in `global_asm!`; a generic `PciConfigBackend` trait so the same enumeration code runs against real port I/O or a replayed fixture without `dyn` or `alloc`.
>
> Try it (no toolchain): quick-start at the top of the README. Limits: boot harness only, no scheduler/drivers/userspace.
>
> Repo: https://github.com/xaviercallens/rust-linux-mini-kernel — there are `agent-ready` and `good first issue` items if you want to help remove `static mut` or document `unsafe` blocks; each has an oracle command.

### r/osdev

**Title:** Multiboot2 → long mode on x86_64, plus a from-scratch AArch64 and RISC-V harness, all in Rust `no_std`

**Body:**

> Small Rust `no_std` harnesses that boot on x86_64 (GRUB Multiboot2, PAE + EFER.LME + CR0.PG, far jump to a 64-bit segment), RISC-V (OpenSBI → S-mode, Sv39 setup still stubbed), and AArch64 (EL3/EL2→EL1 descent, PL011, PSCI SYSTEM_OFF). Prebuilt images you can run under QEMU are linked from the README quick-start.
>
> Honest limits: no IDT/APIC on x86_64, no real GIC or page tables on AArch64, no scheduler or userspace. One known real-world failure: on Google Compute Engine a custom image reaches SeaBIOS and then hangs after "Booting from Hard Disk 0..." (Google's SeaBIOS fork 1.8.2-google; mainline 1.16.3 boots the same image). If anyone knows what that fork does differently with INT13h extended reads, I'd love a pointer.
>
> Code is AI-assisted; I say so in the README.

### r/RISCV and r/aarch64 (only if the sidebar allows project posts)

> Short post: one architecture, the exact `qemu-system-*` command, the expected `[SUCCESS]` line, and the limits. Ask whether it boots on real boards (VisionFive, Pi, etc.) and what breaks.

## Expected hard questions, and honest answers

| Question | Answer |
|---|---|
| "Isn't this just AI slop?" | Much of it was AI-written. That's why there's an audit, a paper on what failed, and oracles that CI re-runs. Judge the evidence table, not the origin. |
| "Why not contribute to Rust-for-Linux?" | Different goal: this is a research testbed for verifiable AI-agent contributions plus Lean specs, not a Linux upstream candidate. |
| "Does it run anything?" | No. Boot harness only. That's stated in the README and the first HN comment. |
| "Benchmarks vs Linux?" | None, and none claimed. Boot-time numbers are QEMU TCG emulation on a small VM and only measure the harness. |
| "Why does the Lean tree have 245 `sorry`?" | Measured, not hidden: `scripts/metrics.py measure`. Only `RunuxDefenses.lean` (84 theorems) is fully closed. |
| "Is the TinyML detector any good?" | No. Replay on real traces showed its weights are untrained. See `ML_WORKLOAD_FIREWALL_REPLAY.md`. |
| "Did it boot on real hardware?" | Not on physical boards. QEMU and GCP VMs only. On GCE a custom image fails past GRUB, documented. |

## Before you post: checklist

- [ ] `python3 scripts/metrics.py measure` and refresh any numbers above
- [ ] Re-run the README quick-start from a clean directory
- [ ] Repo has no open PRs with stale claims; latest release is current
- [ ] You have ~3 hours free to answer comments
- [ ] Post from your own account; do not ask anyone to upvote

# Security Policy

## Status

RunuX is a research project, **not production software**. Do not deploy it
where a vulnerability could harm anyone. See README → *Measured Status*.

## Reporting a vulnerability

Report privately via **GitHub → Security → "Report a vulnerability"**
(private vulnerability reporting). Please do not open a public issue for:

- memory-safety bugs (undefined behavior, unsound `unsafe`, aliasing violations);
- bypasses of the Ring 0 defense pipeline, the eBPF firewall, or the TinyML classifier;
- ways to get a malicious change past CI (`scripts/pr_guard.py`, `scripts/check_unit.py`,
  the metrics ratchet) or to make an AI agent workflow in `.github/workflows/`
  act on attacker-controlled instructions (prompt injection);
- leaked credentials or sensitive data in the repository or its history.

Include what you did, what happened, and a minimal reproduction. Expect an
acknowledgment within 7 days. This is a volunteer project, so there is no bug
bounty.

## In scope and especially welcome

- **AI-assisted and AI-agent attacks** on the defense pipeline: adaptive
  black-box evasion of the classifier, attacks at machine speed, and
  fingerprinting of the defense stack by timing. See
  `docs/roadmap/AI_AGENT_DEFENSE_PLAN.md`.
- **Prompt injection against the contribution workflows**, e.g. an issue or PR
  crafted to make the triage bot or a maintainer-launched agent do something
  outside its task.
- **Unsound `unsafe`**, e.g. `crates/ai_detector::activation_slice`
  (`&self -> &mut`), which is already known and tracked publicly.

## Past incidents (disclosed)

- 2026-09: a Zenodo API token was committed in `paper/upload_to_zenodo.py`
  (public since 2026-05-30). The file was removed in v11.3.0 and the token is
  being rotated. Two files that exposed internal infrastructure hostnames
  were purged from all history via a rewrite; tags and branches were
  force-updated.

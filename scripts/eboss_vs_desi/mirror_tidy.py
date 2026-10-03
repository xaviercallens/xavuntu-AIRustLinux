"""Move the stale (pre-round-2) mirror copies on disk 2 aside so only the fresh cp -r copies sit in the tree."""
from __future__ import annotations

import shutil
from pathlib import Path

BASE = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/cosmo3/eboss_vs_desi")
STALE = BASE / "stale_prior_mirror_not_regenerated"


def main() -> int:
    STALE.mkdir(exist_ok=True)
    moved: list[str] = []
    for sub, keep in (("results", "eboss_vs_desi"), ("papers", "eboss_vs_desi")):
        for p in sorted((BASE / sub).iterdir()):
            if p.name == keep:
                continue
            dest = STALE / sub
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dest / p.name))
            moved.append(f"{sub}/{p.name}")
    top = BASE / "EBOSS_VS_DESI_LITERATURE_REVIEW_2026.md"
    if top.exists():
        shutil.move(str(top), str(STALE / top.name))
        moved.append(top.name)
    (BASE / "MIRROR_README.txt").write_text(
        "Mirror of the eboss_vs_desi problem, written by the round-2 fix stage on 2026-09-27 with cp -r:\n"
        "  results/eboss_vs_desi/  <- worktree results/eboss_vs_desi/\n"
        "  papers/eboss_vs_desi/   <- worktree papers/eboss_vs_desi/\n"
        "  docs/literature/EBOSS_VS_DESI_LITERATURE_REVIEW_2026.md\n"
        "stale_prior_mirror_not_regenerated/ holds copies from an earlier mirror of the interrupted run;\n"
        "they were not regenerated and must not be trusted.\n")
    print(f"moved {len(moved)} stale entries:", ", ".join(moved))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

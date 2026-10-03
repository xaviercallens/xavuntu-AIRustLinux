"""Fix round: compare the regenerated chains / summaries with the pre-fix-round copies.

The pre-fix-round outputs were copied to /tmp/dr2_fixround_oldchains/ before
mcmc_fit.py and grid_posterior.py were re-run from the current files. Writes
results/desi_dr2_bao/fixround_rerun_check.json with np.array_equal per chain,
the sha256 of every old and new file, the script sha256s, and a diff of the
summary JSONs ignoring generated_at timestamps.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "desi_dr2_bao"
OLD = Path("/tmp/dr2_fixround_oldchains")
CHAINS = ("DR2_LCDM", "DR2_wCDM", "DR1_LCDM", "DR1_wCDM", "DR2_LCDM_radiation", "DR2_wCDM_radiation")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def strip_ts(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: strip_ts(v) for k, v in obj.items() if k not in ("generated_at", "timestamp_utc")}
    if isinstance(obj, list):
        return [strip_ts(v) for v in obj]
    return obj


def diff_paths(a: Any, b: Any, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            out += diff_paths(a.get(k), b.get(k), f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff_paths(x, y, f"{path}[{i}]")
        return out
    return [] if a == b else [path]


def main() -> int:
    chains: dict[str, Any] = {}
    for n in CHAINS:
        o, c = np.load(OLD / "chains" / f"{n}.npz"), np.load(RES / "chains" / f"{n}.npz")
        chains[n] = {"samples_array_equal": bool(np.array_equal(o["samples"], c["samples"])),
                     "tau_array_equal": bool(np.array_equal(o["tau"], c["tau"])),
                     "old_sha256": sha(OLD / "chains" / f"{n}.npz"), "new_sha256": sha(RES / "chains" / f"{n}.npz")}
    summaries: dict[str, Any] = {}
    for f in ("mcmc_summary.json", "grid_summary.json"):
        o, c = json.loads((OLD / f).read_text()), json.loads((RES / f).read_text())
        d = diff_paths(strip_ts(o), strip_ts(c))
        summaries[f] = {"identical_ignoring_timestamps": not d, "differing_paths": d[:50],
                        "old_sha256": sha(OLD / f), "new_sha256": sha(RES / f)}
    out = {"purpose": "fix round: regenerate chains and grid from the current scripts and compare with the pre-fix-round outputs",
           "scripts_sha256": {s: sha(ROOT / "scripts" / "desi_dr2_bao" / s)
                              for s in ("mcmc_fit.py", "grid_posterior.py", "dr2_model.py")},
           "chains": chains, "summaries": summaries,
           "all_identical": all(v["samples_array_equal"] and v["tau_array_equal"] for v in chains.values())
           and all(v["identical_ignoring_timestamps"] for v in summaries.values())}
    (RES / "fixround_rerun_check.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "chains"}, indent=1))
    print({n: v["samples_array_equal"] for n, v in chains.items()})
    return 0 if out["all_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

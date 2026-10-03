#!/usr/bin/env python3
"""Fetch the real Laya System-1 checkpoint so `LayaSystemOneDecisionEngine` stops falling
back to heuristics.

Laya is a real, published model: "the open-source, Jev-compatible System-1 decision model"
by Convai Innovations (github.com/receptron/laya — the Node/TS runtime and export script;
huggingface.co/convaiinnovations/laya — the actual weights, Apache-2.0). The Python
reference implementation this repo's `anse/v5/laya_system_one.py` already imports
(`rl_agent_api.RLAgent`, `rl_common.build_model`) ships INSIDE that Hugging Face repo, next
to the checkpoint — not as a separate pip package. `checkpoints/` is gitignored (804 MB of
weights), so this script is how a fresh checkout gets it, same idea as `tools/
setup_v2_env.sh` for the v2 venv.

Before this script runs, `LayaSystemOneDecisionEngine` reports `is_loaded=False` with
"Laya model weights not found", and 5 tests fail as a result (`tests/v5/
test_anse_v5.py::TestLayaSystemOne::{test_laya_model_loaded_on_cpu,test_laya_triage_choice}`,
3 more in `tests/web/test_anse_v5_ui.py::TestAnseV5ApiEndpoints`) -- this has been true of
every release from v13.2.0 through v13.4.1. After it runs, real calibrated inference:
measured 2026-09-28, CPU, `triage_hypothesis` on a symplectic-form theorem statement ->
choice "sound" at p=0.8163 in 873 ms; `score_hypothesis` on a SIMD kernel description ->
2.97/4 ("optimized") in 551 ms. All 7 Laya tests pass.

Usage:
    .venv/bin/python scripts/setup_laya_checkpoint.py                 # English checkpoint (~840 MB)
    .venv/bin/python scripts/setup_laya_checkpoint.py --variant multilingual
    .venv/bin/python scripts/setup_laya_checkpoint.py --verify-only   # just check what's there
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LAYA_DIR = REPO_ROOT / "checkpoints" / "laya"
HF_REPO = "convaiinnovations/laya"

# Files the Python reference implementation (anse/v5/laya_system_one.py) actually needs.
# email_utils.py and eval/* are not required at runtime but are small and document the
# model's own reported benchmark, so they are fetched too.
REQUIRED_FILES = ("model.safetensors", "rl_agent_config.json", "rl_agent_api.py", "rl_common.py")
PATTERNS_BY_VARIANT: dict[str, list[str]] = {
    "english": [
        "README.md", "model.safetensors", "encoder/*", "tokenizer/*",
        "rl_agent_config.json", "rl_common.py", "rl_agent_api.py", "email_utils.py",
        "eval/results.json", "eval/results.md",
    ],
    "multilingual": [
        "multilingual/model.safetensors", "multilingual/encoder/*", "multilingual/tokenizer/*",
        "multilingual/rl_agent_config.json", "rl_common.py", "rl_agent_api.py",
    ],
    "typed-decisions": [
        "typed-decisions/model.safetensors", "typed-decisions/encoder/*", "typed-decisions/tokenizer/*",
        "typed-decisions/rl_agent_config.json", "rl_common.py", "rl_agent_api.py",
    ],
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(model_dir: Path) -> bool:
    missing = [f for f in REQUIRED_FILES if not (model_dir / f).exists()]
    if missing:
        print(f"MISSING at {model_dir}: {missing}")
        return False
    size_mb = (model_dir / "model.safetensors").stat().st_size / (1 << 20)
    print(f"OK: {model_dir} has all required files. model.safetensors = {size_mb:.0f} MiB")
    return True


def download(model_dir: Path, variant: str) -> None:
    from huggingface_hub import snapshot_download

    patterns = PATTERNS_BY_VARIANT[variant]
    print(f"Downloading {HF_REPO} (variant={variant}) to {model_dir} ...")
    snapshot_download(HF_REPO, local_dir=str(model_dir), allow_patterns=patterns)
    manifest = {
        "hf_repo": HF_REPO,
        "variant": variant,
        "license": "apache-2.0",
        "files_sha256": {f: sha256_of(model_dir / f) for f in REQUIRED_FILES if (model_dir / f).exists()},
    }
    (model_dir / "DOWNLOAD_MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_LAYA_DIR)
    ap.add_argument("--variant", choices=sorted(PATTERNS_BY_VARIANT), default="english")
    ap.add_argument("--verify-only", action="store_true", help="check the checkpoint is present, download nothing")
    args = ap.parse_args()

    if args.verify_only:
        return 0 if verify(args.model_dir) else 1

    args.model_dir.mkdir(parents=True, exist_ok=True)
    download(args.model_dir, args.variant)
    return 0 if verify(args.model_dir) else 1


if __name__ == "__main__":
    sys.exit(main())

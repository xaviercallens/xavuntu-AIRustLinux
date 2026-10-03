"""Step 4+5 of the Laya cold-start validation: held-out evaluation with a shuffled-label control.

Compares, on the same group-held-out rows with their REAL labels:
  (a) the unmodified base checkpoint,
  (b) the head fine-tune on real training labels (one run per seed),
  (c) the identical fine-tune on label-permuted training rows (one run per seed).
Metrics reuse ``rl_common``: ``auroc`` on p(true), ``ece_score``; accuracy is argmax == label;
``heldout_loss`` is ``-proper_reward`` (lower is better). Base and the promoted (b) run are scored
through the reference ``DecisionModel.forward``; the other runs through the cached-encoder replay,
whose agreement with the reference path is measured on the base model and reported.

Writes ``checkpoints/laya_coldstart_v1/`` (self-contained, loadable like the base), and
``results/laya_coldstart/report.json`` + ``README.md``.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import torch  # noqa: E402
from common import (  # noqa: E402
    CACHE_DIR,
    FINETUNED_DIR,
    LAYA_DIR,
    OUT_DIR,
    SPLIT_PATH,
    elapsed,
    encode_noul_record,
    encoder_features,
    full_forward_logits,
    head_logits_from_features,
    load_base_model,
    load_cfg,
    load_tokenizer,
    read_dataset,
    read_split,
    rl_common,
    set_cpu_threads,
)

BASE_FILES = ["rl_agent_config.json", "rl_common.py", "rl_agent_api.py", "README.md", "DOWNLOAD_MANIFEST.json"]
BASE_DIRS = ["encoder", "tokenizer"]


def metrics(logits: torch.Tensor, labels: np.ndarray, srcs: list[str]) -> dict[str, Any]:
    p = torch.softmax(logits, -1).numpy()
    p_true = p[:, 1]
    pred = logits.argmax(-1).numpy()
    correct = (pred == labels).astype(float)
    conf = p.max(-1)
    target = np.stack([1 - labels, labels], -1).astype(np.float32)
    rew = rl_common.proper_reward(torch.tensor(p), torch.tensor(target), torch.full((len(labels),), 2),
                                  torch.ones_like(torch.tensor(p), dtype=torch.bool)).numpy()

    def block(sel: np.ndarray) -> dict[str, Any]:
        n = int(sel.sum())
        maj = float(max(labels[sel].mean(), 1 - labels[sel].mean())) if n else float("nan")
        return {"n": n, "pos": int(labels[sel].sum()), "accuracy": round(float(correct[sel].mean()), 4),
                "majority_class_accuracy": round(maj, 4),
                "auroc": round(rl_common.auroc(p_true[sel], labels[sel]), 4),
                "ece": round(rl_common.ece_score(conf[sel], correct[sel]), 4),
                "heldout_loss": round(float(-rew[sel].mean()), 4),
                "mean_p_true": round(float(p_true[sel].mean()), 4)}

    out = {"overall": block(np.ones(len(labels), dtype=bool))}
    for s in sorted(set(srcs)):
        out[s] = block(np.array([x == s for x in srcs]))
    return out


def load_run(cfg: dict[str, Any], run_dir: Path) -> tuple[torch.nn.Module, dict[str, Any]]:
    from safetensors.torch import load_file

    model = load_base_model(cfg)
    delta = load_file(str(run_dir / "trainable.safetensors"))
    missing, unexpected = model.load_state_dict(delta, strict=False)
    assert not unexpected, unexpected
    assert set(delta) <= set(model.state_dict()), "run weights do not match the architecture"
    with open(run_dir / "summary.json") as f:
        summary = json.load(f)
    return model, summary


def write_promoted_checkpoint(model: torch.nn.Module, summary: dict[str, Any]) -> None:
    from safetensors.torch import save_file

    if FINETUNED_DIR.resolve() == LAYA_DIR.resolve():
        raise SystemExit("refusing to write over the base checkpoint directory")
    FINETUNED_DIR.mkdir(parents=True, exist_ok=True)
    for name in BASE_FILES:
        if (LAYA_DIR / name).exists():
            shutil.copy2(LAYA_DIR / name, FINETUNED_DIR / name)
    for name in BASE_DIRS:
        if (FINETUNED_DIR / name).exists():
            shutil.rmtree(FINETUNED_DIR / name)
        shutil.copytree(LAYA_DIR / name, FINETUNED_DIR / name)
    sd = {k: v.detach().contiguous() for k, v in model.state_dict().items()}
    save_file(sd, str(FINETUNED_DIR / "model.safetensors"))
    with open(FINETUNED_DIR / "COLDSTART_PROVENANCE.json", "w") as f:
        json.dump({"status": "cold-start validation only, NOT a promoted checkpoint",
                   "base": str(LAYA_DIR / "model.safetensors"), "trained_parts": summary["trainable_keys"][:3] + ["..."],
                   "training": {k: summary[k] for k in ("labels", "seed", "epochs", "batch_size", "lr", "n_train_rows")},
                   "split": str(SPLIT_PATH), "todo_item": 24}, f, indent=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real-runs", nargs="+", default=["real_s0"])
    ap.add_argument("--shuffled-runs", nargs="+", default=["shuffled_s0"])
    args = ap.parse_args()
    set_cpu_threads()
    t_all = time.time()
    cfg, tok = load_cfg(), load_tokenizer()
    recs, split = read_dataset(), read_split()
    by_uid = {r["uid"]: r for r in recs}
    held = [by_uid[u] for u in split["heldout_uids"]]
    items = [encode_noul_record(r, tok, cfg, flipped=False) for r in held]
    keep = [i for i, it in enumerate(items) if it is not None]
    held, items = [held[i] for i in keep], [items[i] for i in keep]
    labels = np.array([r["qs"][0]["y"] for r in held])
    srcs = [r["src"] for r in held]
    pad = tok.pad_token_id
    timings: dict[str, float] = {}

    # (a) base, reference path + cached path (agreement check)
    t0 = time.time()
    base = load_base_model(cfg)
    base_logits = full_forward_logits(base, items, pad)
    timings["base_full_forward_s"] = elapsed(t0)
    t0 = time.time()
    feats = [f.to(torch.float16).float() for f in encoder_features(base, items, pad)]
    timings["heldout_encoder_cache_s"] = elapsed(t0)
    with torch.no_grad():
        cached_logits = torch.cat([head_logits_from_features(base, feats[s:s + 8], items[s:s + 8], pad)[0][:, :2]
                                   for s in range(0, len(items), 8)], 0)
    path_diff = float((base_logits - cached_logits).abs().max())
    print(f"base: reference vs cached-path max |dlogit| = {path_diff:.2e}")
    table: dict[str, Any] = {"base": metrics(base_logits, labels, srcs)}
    summaries: dict[str, Any] = {}

    def cached_eval(model: torch.nn.Module) -> torch.Tensor:
        model.eval()
        with torch.no_grad():
            return torch.cat([head_logits_from_features(model, feats[s:s + 8], items[s:s + 8], pad)[0][:, :2]
                              for s in range(0, len(items), 8)], 0)

    for kind, names in (("finetuned", args.real_runs), ("shuffled_control", args.shuffled_runs)):
        for name in names:
            run_dir = CACHE_DIR / "runs" / name
            if not (run_dir / "trainable.safetensors").exists():
                table[f"{kind}:{name}"] = {"status": "BLOCKED", "error": f"missing {run_dir}"}
                continue
            t0 = time.time()
            model, summary = load_run(cfg, run_dir)
            summaries[name] = summary
            table[f"{kind}:{name}"] = metrics(cached_eval(model), labels, srcs)
            timings[f"eval_{name}_s"] = elapsed(t0)
            if kind == "finetuned" and name == args.real_runs[0]:
                t0 = time.time()
                write_promoted_checkpoint(model, summary)
                reloaded = load_base_model(cfg, weights=FINETUNED_DIR / "model.safetensors")
                ref_logits = full_forward_logits(reloaded, items, pad)
                table[f"{kind}:{name}"]["reference_path"] = metrics(ref_logits, labels, srcs)["overall"]
                table[f"{kind}:{name}"]["reference_vs_cached_max_dlogit"] = float(
                    (ref_logits - cached_eval(model)).abs().max())
                timings["promoted_checkpoint_write_and_reference_eval_s"] = elapsed(t0)

    def pick(prefix: str, key: str) -> list[float]:
        return [v["overall"][key] for k, v in table.items() if k.startswith(prefix) and "overall" in v]

    ft_auc, sh_auc, ft_acc, sh_acc = (pick("finetuned:", "auroc"), pick("shuffled_control:", "auroc"),
                                      pick("finetuned:", "accuracy"), pick("shuffled_control:", "accuracy"))
    base_auc, base_acc = table["base"]["overall"]["auroc"], table["base"]["overall"]["accuracy"]
    spread = max([max(x) - min(x) for x in (ft_auc, sh_auc) if len(x) > 1] + [0.0])
    beats_auc = bool(ft_auc and sh_auc and min(ft_auc) > max(base_auc, max(sh_auc)) + spread)
    beats_acc = bool(ft_acc and sh_acc and min(ft_acc) > max(base_acc, max(sh_acc)) + spread)
    verdict = {"finetuned_auroc": ft_auc, "shuffled_auroc": sh_auc, "base_auroc": base_auc,
               "finetuned_accuracy": ft_acc, "shuffled_accuracy": sh_acc, "base_accuracy": base_acc,
               "seed_spread_auroc_or_acc": round(spread, 4), "n_seeds": len(ft_auc),
               "finetuned_beats_base_and_control_on_auroc": beats_auc,
               "finetuned_beats_base_and_control_on_accuracy": beats_acc,
               "signal": "YES" if (beats_auc and beats_acc) else "NO / INCONCLUSIVE"}
    timings["evaluate_total_s"] = elapsed(t_all)
    report = {"what": "Laya cold-start validation (TODO 24): head-only fine-tune from the real base checkpoint, "
                      "group-held-out evaluation, shuffled-label control. CPU only.",
              "dataset_counts": split["dataset_counts"], "train_counts": split["train_counts"],
              "heldout_counts": split["heldout_counts"], "split": {k: split[k] for k in ("seed", "fraction", "heldout_groups")},
              "n_train_rows": len(split["train_uids"]), "n_heldout_rows": len(items),
              "training_runs": summaries, "heldout_table": table,
              "base_reference_vs_cached_path_max_dlogit": path_diff, "timings_s": timings, "verdict": verdict}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "report.json", "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps({k: v["overall"] for k, v in table.items() if "overall" in v}, indent=1))
    print(json.dumps(verdict, indent=1))
    print("wrote", OUT_DIR / "report.json")


if __name__ == "__main__":
    main()

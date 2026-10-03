"""Step 3 of the Laya cold-start validation: head-only fine-tune from the real base checkpoint.

Starts from ``checkpoints/laya/model.safetensors`` (strict load), freezes the encoder and trains
only ``head`` + ``type_emb`` + ``scorer`` with the model family's own strictly-proper objective,
``-proper_reward(...).mean()`` from ``rl_common``. Because the encoder is frozen and run in eval
mode, its hidden states are computed once per (record, option order) and cached; the head is then
trained on the cached states through exactly the same ops as ``DecisionModel.forward``.

``--labels shuffled`` permutes ``y`` across the training rows (the label-control pattern of
``anse/v2/label_control.py``) and is evaluated on the untouched held-out labels by evaluate.py.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import torch  # noqa: E402
from common import (  # noqa: E402
    CACHE_DIR,
    TRAINABLE_PARTS,
    elapsed,
    encode_noul_record,
    encoder_features,
    freeze_for_head_tune,
    head_logits_from_features,
    load_base_model,
    load_cfg,
    load_tokenizer,
    read_dataset,
    read_split,
    rl_common,
    set_cpu_threads,
)

FEATURE_CACHE = CACHE_DIR / "train_features.pt"


def build_or_load_cache(model: torch.nn.Module, tok: Any, cfg: dict[str, Any], train_recs: list[dict[str, Any]]) -> dict[str, Any]:
    """{uid: {"items": [canonical, flipped], "feats": [tensor, tensor]}} for every training record."""
    if FEATURE_CACHE.exists():
        cache = torch.load(FEATURE_CACHE)
        if set(cache) == {r["uid"] for r in train_recs}:
            print(f"loaded encoder feature cache {FEATURE_CACHE} ({len(cache)} records)")
            return cache
        print("cache uid set differs from the current split; rebuilding")
    t0 = time.time()
    uids, items = [], []
    for r in train_recs:
        pair = [encode_noul_record(r, tok, cfg, flipped=False), encode_noul_record(r, tok, cfg, flipped=True)]
        if any(it is None for it in pair):
            print(f"  [drop] options did not fit for {r['uid']}")
            continue
        for it in pair:
            uids.append(r["uid"])
            items.append(it)
    feats = encoder_features(model, items, tok.pad_token_id)
    cache: dict[str, Any] = {}
    for uid, it, f in zip(uids, items, feats, strict=True):
        cache.setdefault(uid, {"items": [], "feats": []})
        cache[uid]["items"].append(it)
        cache[uid]["feats"].append(f.to(torch.float16))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(cache, FEATURE_CACHE)
    print(f"encoder feature cache built for {len(cache)} records x 2 orders in {elapsed(t0)}s")
    return cache


def relabel(items: list[dict[str, Any]], y: int) -> list[dict[str, Any]]:
    """Rewrite target/label of the (canonical, flipped) item pair for label y; the state text is untouched."""
    out = []
    for it in items:
        order = it["order"] if "order" in it else [0, 1]
        target = [1.0 if i == y else 0.0 for i in range(2)]
        new = dict(it)
        new["target"] = [target[i] for i in order]
        new["label"] = order.index(y)
        out.append(new)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", choices=["real", "shuffled"], default="real")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--threads", type=int, default=6)
    args = ap.parse_args()
    set_cpu_threads(args.threads)
    t_start = time.time()
    cfg, tok = load_cfg(), load_tokenizer()
    recs = read_dataset()
    split = read_split()
    by_uid = {r["uid"]: r for r in recs}
    train_recs = [by_uid[u] for u in split["train_uids"]]

    model = load_base_model(cfg)
    trainable = freeze_for_head_tune(model)
    n_train = sum(p.numel() for n, p in model.named_parameters() if p.requires_grad)
    n_total = sum(p.numel() for p in model.parameters())
    print(f"trainable params {n_train:,} of {n_total:,} ({', '.join(TRAINABLE_PARTS)})")

    t0 = time.time()
    cache = build_or_load_cache(model, tok, cfg, train_recs)
    cache_s = elapsed(t0)
    uids = [u for u in split["train_uids"] if u in cache]
    ys = {u: by_uid[u]["qs"][0]["y"] for u in uids}
    if args.labels == "shuffled":
        perm = [ys[u] for u in uids]
        random.Random(1000 + args.seed).shuffle(perm)
        ys = dict(zip(uids, perm, strict=True))
        agree = sum(int(ys[u] == by_uid[u]["qs"][0]["y"]) for u in uids)
        print(f"shuffled labels: {agree}/{len(uids)} rows keep their real label by chance")

    rl_common.seed_all(args.seed)
    rng = random.Random(args.seed)
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.01)
    pad_id = tok.pad_token_id
    curve: list[dict[str, float]] = []
    for ep in range(args.epochs):
        model.train()
        te = time.time()
        order = list(uids)
        rng.shuffle(order)
        tot, n_items, n_correct = 0.0, 0, 0
        for s in range(0, len(order), args.batch_size):
            batch_uids = order[s:s + args.batch_size]
            items, feats = [], []
            for u in batch_uids:
                k = rng.randrange(2)  # option order augmentation, as encode_record(train=True) does
                items.append(relabel([cache[u]["items"][k]], ys[u])[0])
                feats.append(cache[u]["feats"][k].float())
            logits, mask, target, qtype = head_logits_from_features(model, feats, items, pad_id)
            probs = torch.softmax(logits.masked_fill(~mask, -1e4), -1)
            loss = -rl_common.proper_reward(probs, target, qtype, mask).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            tot += float(loss) * len(items)
            n_items += len(items)
            n_correct += int((logits.argmax(-1) == torch.tensor([it["label"] for it in items])).sum())
        row = {"epoch": ep + 1, "train_loss": round(tot / max(1, n_items), 4),
               "train_acc": round(n_correct / max(1, n_items), 4), "seconds": elapsed(te)}
        curve.append(row)
        print(json.dumps(row), flush=True)

    run_dir = CACHE_DIR / "runs" / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    from safetensors.torch import save_file

    sd = {k: v.detach().contiguous() for k, v in model.state_dict().items() if k in set(trainable)}
    save_file(sd, str(run_dir / "trainable.safetensors"))
    summary = {"run_name": args.run_name, "labels": args.labels, "seed": args.seed, "epochs": args.epochs,
               "batch_size": args.batch_size, "lr": args.lr, "n_train_rows": len(uids),
               "trainable_params": n_train, "total_params": n_total, "loss_curve": curve,
               "seconds_feature_cache": cache_s, "seconds_train_epochs": round(sum(r["seconds"] for r in curve), 1),
               "seconds_total": elapsed(t_start), "trainable_keys": trainable}
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=1)
    print("saved", run_dir)


if __name__ == "__main__":
    main()

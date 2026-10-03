"""Shared helpers for the Laya cold-start validation (TODO 24).

CPU only by construction: ``CUDA_VISIBLE_DEVICES`` is cleared before torch is imported so
nothing here can compete with the GPU jobs. The model, tokenizer and record encoding come
from the reference implementation shipped with the checkpoint (``checkpoints/laya/rl_common.py``);
nothing about the tokenization or marker scheme is reinvented here.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ["CUDA_VISIBLE_DEVICES"] = ""

import torch  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LAYA_DIR = REPO / "checkpoints" / "laya"
OUT_DIR = REPO / "results" / "laya_coldstart"
FINETUNED_DIR = REPO / "checkpoints" / "laya_coldstart_v1"
DATASET_PATH = OUT_DIR / "dataset.jsonl"
SPLIT_PATH = OUT_DIR / "split.json"
CACHE_DIR = Path("/tmp/laya_coldstart_cache")

if str(LAYA_DIR) not in sys.path:
    sys.path.insert(0, str(LAYA_DIR))

import rl_common  # noqa: E402  (checkpoints/laya/rl_common.py)

TRAINABLE_PARTS = ("head", "type_emb", "scorer")


def set_cpu_threads(n: int = 6) -> None:
    torch.set_num_threads(n)


def load_cfg() -> dict[str, Any]:
    with open(LAYA_DIR / "rl_agent_config.json") as f:
        return json.load(f)


def load_tokenizer() -> Any:
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(str(LAYA_DIR / "tokenizer"))


def load_base_model(cfg: dict[str, Any], weights: Path | None = None) -> torch.nn.Module:
    """Architecture from the encoder config, weights from a safetensors file (strict)."""
    from safetensors.torch import load_file

    model = rl_common.build_model(cfg, encoder_dir=str(LAYA_DIR / "encoder"))
    state = load_file(str(weights or (LAYA_DIR / "model.safetensors")))
    model.load_state_dict(state, strict=True)
    model.encoder.config.reference_compile = False
    model.eval()
    return model


def freeze_for_head_tune(model: torch.nn.Module) -> list[str]:
    """Freeze everything except head + type_emb + scorer. Returns the trainable parameter names."""
    trainable: list[str] = []
    for name, p in model.named_parameters():
        keep = name.split(".")[0] in TRAINABLE_PARTS
        p.requires_grad_(keep)
        if keep:
            trainable.append(name)
    return trainable


def read_dataset(path: Path = DATASET_PATH) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_split(path: Path = SPLIT_PATH) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def encode_noul_record(rec: dict[str, Any], tok: Any, cfg: dict[str, Any], flipped: bool) -> dict[str, Any] | None:
    """One record -> one model item, in canonical ([false, true]) or flipped option order.

    Canonical order goes through ``rl_common.encode_record`` unchanged. The flipped order mirrors
    the ``train=True`` branch of that function (which draws the order from an RNG) so both orders
    can be cached deterministically for the frozen encoder.
    """
    if not flipped:
        items = rl_common.encode_record(rec, tok, cfg, rng=None, train=False)
        return items[0] if items else None
    q = rec["qs"][0]
    k = len(rl_common.render_options(q))
    order = list(range(k))[::-1]
    ids, markers = rl_common.build_sequence(tok, rec["state"], q, cfg["max_len"], cfg["head_max_len"], option_order=order)
    if len(markers) != k:
        return None
    target = [1.0 if i == q["y"] else 0.0 for i in range(k)]
    target = [target[i] for i in order]
    return {"ids": ids, "markers": markers, "qtype": rl_common.QTYPES[q["t"]], "target": target,
            "label": order.index(q["y"]), "episode": 0, "ep_step": 0, "ep_len": 1, "src": rec.get("src", ""),
            "q_index": 0, "order": order}


@torch.no_grad()
def encoder_features(model: torch.nn.Module, items: list[dict[str, Any]], pad_id: int, batch_size: int = 8,
                     log_every: int = 10) -> list[torch.Tensor]:
    """Frozen-encoder hidden states per item (unpadded, fp32). Encoder in eval mode (no dropout)."""
    model.eval()
    out: list[torch.Tensor] = []
    t0 = time.time()
    order = sorted(range(len(items)), key=lambda i: len(items[i]["ids"]))
    feats: dict[int, torch.Tensor] = {}
    for bi, s in enumerate(range(0, len(order), batch_size)):
        sel = [items[i] for i in order[s:s + batch_size]]
        b = rl_common.collate_items([sel], pad_id)
        h = model.encoder(input_ids=b["input_ids"], attention_mask=b["attention_mask"]).last_hidden_state
        for r, i in enumerate(order[s:s + batch_size]):
            n = len(items[i]["ids"])
            feats[i] = h[r, :n].clone()
        if log_every and bi % log_every == 0:
            print(f"  encoder features {s + len(sel)}/{len(items)} ({time.time() - t0:.0f}s)", flush=True)
    for i in range(len(items)):
        out.append(feats[i])
    return out


def head_logits_from_features(model: torch.nn.Module, feats: list[torch.Tensor], items: list[dict[str, Any]],
                              pad_id: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Replays ``DecisionModel.forward`` from cached encoder states: type_emb -> head layers -> scorer.

    Returns (logits, marker_mask, target, qtype) for the batch; logits are already masked to -1e4
    off-option exactly like the reference forward.
    """
    b = rl_common.collate_items([items], pad_id)
    n, seq_len = b["input_ids"].shape
    d = feats[0].shape[-1]
    h = torch.zeros((n, seq_len, d), dtype=feats[0].dtype)
    for i, f in enumerate(feats):
        h[i, :f.shape[0]] = f
    h = h + model.type_emb(b["qtype"])[:, None, :]
    if model.head is not None:
        pad = ~b["attention_mask"].bool()
        for layer in model.head.layers:
            h = layer(h, src_key_padding_mask=pad)
    idx = b["marker_pos"].clamp(min=0)[:, :, None].expand(-1, -1, h.size(-1))
    m = torch.gather(h, 1, idx)
    logits = model.scorer(m).squeeze(-1).float()
    logits = logits.masked_fill(~b["marker_mask"], -1e4)
    return logits, b["marker_mask"], b["target"], b["qtype"]


@torch.no_grad()
def full_forward_logits(model: torch.nn.Module, items: list[dict[str, Any]], pad_id: int, batch_size: int = 8) -> torch.Tensor:
    """Reference path: ``DecisionModel.forward`` end to end (encoder included). Used for every reported number."""
    model.eval()
    chunks: list[torch.Tensor] = []
    for s in range(0, len(items), batch_size):
        b = rl_common.collate_items([items[s:s + batch_size]], pad_id)
        logits, _act = model(b["input_ids"], b["attention_mask"], b["marker_pos"], b["marker_mask"], b["qtype"])
        chunks.append(logits[:, :2].float())
    return torch.cat(chunks, 0)


def elapsed(t0: float) -> float:
    return round(time.time() - t0, 1)

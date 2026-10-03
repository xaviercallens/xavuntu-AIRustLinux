"""Step 1+2 of the Laya cold-start validation: labeled records from REAL verifier verdicts, group split.

Every label is a verifier verdict already on disk (cosmo3 pipeline step pass/fail; Lean kernel
compile + axiom audit). No model opinion, no invented labels.

State design note (hardness): ``clean`` is computed by ``scripts/hardness/build_ladder.py`` as
``rc == 0 and "sorryAx" not in axioms and set(axioms) <= TRUSTED``. Putting ``axioms`` in the
state would therefore hand the model the label verbatim, so it is deliberately left out. The
state carries the theorem statement (from ``ladder.json``) and, when the run recorded it, the
generated proof head (``retrieval_ab.json`` only; ``baseline.json`` did not store proof text).
"""
from __future__ import annotations

import collections
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATASET_PATH, OUT_DIR, REPO, SPLIT_PATH  # noqa: E402

COSMO3_EPISODES = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake/episodes/cosmo3_2026-09-27.jsonl")
HARDNESS_DIR = REPO / "results" / "hardness"
NOUL_CRIT = {"true": "the verifier accepted it", "false": "the verifier rejected it"}
HELDOUT_FRACTION = 0.2
SPLIT_SEED = 0
PROOF_HEAD_CHARS = 600
_CURVE_ID = re.compile(r"^t(\d)_(\w+?)_([TF])$")


def cosmo3_records() -> list[dict[str, Any]]:
    if not COSMO3_EPISODES.exists():
        print(f"[skip] cosmo3 episodes missing: {COSMO3_EPISODES}")
        return []
    out: list[dict[str, Any]] = []
    with open(COSMO3_EPISODES) as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            md = row.get("metadata", {})
            passed = bool(row.get("converged")) and md.get("tests_passed", 0) == md.get("tests_total", 1)
            state = {"step": md.get("step"), "input_summary": row.get("task"), "command": md.get("verifier"),
                     "evidence_path": md.get("evidence_path"), "iteration": row.get("iteration")}
            out.append({"uid": f"cosmo3:{i}", "src": "cosmo3_episode", "group": row["task"], "state": state,
                        "qs": [{"t": "noul", "ins": "Did this pipeline step pass its verifier?", "crit": NOUL_CRIT,
                                "y": int(passed)}]})
    return out


def hardness_group(item_id: str) -> str:
    m = _CURVE_ID.match(item_id)
    return m.group(2) if m else item_id


def hardness_records(path: Path, src: str, statements: dict[str, str]) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"[skip] {src} missing: {path}")
        return []
    with open(path) as f:
        data = json.load(f)
    runs = data.get("runs", []) if isinstance(data, dict) else data
    out: list[dict[str, Any]] = []
    skipped = collections.Counter()
    for i, r in enumerate(runs):
        if r.get("truth") not in (True, "True"):
            skipped[f"truth={r.get('truth')!r}"] += 1
            continue
        if "clean" not in r:
            skipped["no_clean_field"] += 1
            continue
        state: dict[str, Any] = {"tier": r["tier"], "id": r["id"], "prover": r["model"],
                                 "statement": statements.get(r["id"], "")}
        if "proof_head" in r:
            state["proof_head"] = str(r["proof_head"])[:PROOF_HEAD_CHARS]
        elif r.get("extracted") is False or r.get("extracted") == "False":
            state["proof_head"] = "(no proof extracted from the prover output)"
        out.append({"uid": f"{src}:{i}", "src": src, "group": hardness_group(r["id"]), "state": state,
                    "qs": [{"t": "noul", "ins": "Did this Lean proof compile and use only trusted axioms?",
                            "crit": NOUL_CRIT, "y": int(bool(r["clean"]) and str(r["clean"]) != "False")}]})
    print(f"[{src}] kept {len(out)} of {len(runs)} runs; skipped {dict(skipped)}")
    return out


def load_statements() -> dict[str, str]:
    p = HARDNESS_DIR / "ladder.json"
    if not p.exists():
        print("[warn] ladder.json missing: hardness states will have no theorem statement")
        return {}
    with open(p) as f:
        items = json.load(f)
    return {it["id"]: (it.get("defs", "") + "\n" + it["statement"]).strip() for it in items}


def split_family(src: str) -> str:
    """Both hardness files contain the same theorems, so they must be split as one family."""
    return "cosmo3" if src == "cosmo3_episode" else "hardness"


def group_split(records: list[dict[str, Any]], fraction: float, seed: int) -> dict[str, Any]:
    """Held-out groups chosen per family until >= fraction of that family's rows are held out.

    Pre-registered rule: shuffle the family's groups with the seed and take them in order; if the
    held-out side would end up with a single class, the first not-yet-taken group that carries the
    missing class is added (a one-class held-out set cannot measure AUROC at all).
    """
    rng = random.Random(seed)
    heldout_groups: dict[str, list[str]] = {}
    for fam in sorted({split_family(r["src"]) for r in records}):
        rows = [r for r in records if split_family(r["src"]) == fam]
        by_group: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for r in rows:
            by_group[r["group"]].append(r)
        groups = sorted(by_group)
        rng.shuffle(groups)
        quota = fraction * len(rows)
        taken: list[str] = []
        n = 0
        for g in groups:
            if n >= quota:
                break
            taken.append(g)
            n += len(by_group[g])
        labels = {r["qs"][0]["y"] for g in taken for r in by_group[g]}
        for missing in (0, 1):
            if missing not in labels:
                for g in groups:
                    if g not in taken and any(r["qs"][0]["y"] == missing for r in by_group[g]):
                        taken.append(g)
                        break
        heldout_groups[fam] = sorted(taken)
    held = {r["uid"] for r in records if r["group"] in set(heldout_groups[split_family(r["src"])])}
    train_uids = [r["uid"] for r in records if r["uid"] not in held]
    heldout_uids = [r["uid"] for r in records if r["uid"] in held]
    train_groups = {(split_family(r["src"]), r["group"]) for r in records if r["uid"] not in held}
    heldout_pairs = {(split_family(r["src"]), r["group"]) for r in records if r["uid"] in held}
    assert not (train_groups & heldout_pairs), "a group leaked across the split"
    return {"seed": seed, "fraction": fraction, "heldout_groups": heldout_groups,
            "train_uids": train_uids, "heldout_uids": heldout_uids}


def class_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for r in records:
        c = out.setdefault(r["src"], {"rows": 0, "pos": 0, "neg": 0, "groups": 0})
        c["rows"] += 1
        c["pos" if r["qs"][0]["y"] == 1 else "neg"] += 1
    for src in out:
        out[src]["groups"] = len({r["group"] for r in records if r["src"] == src})
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    statements = load_statements()
    records: list[dict[str, Any]] = []
    records += cosmo3_records()
    records += hardness_records(HARDNESS_DIR / "baseline.json", "hardness_baseline", statements)
    records += hardness_records(HARDNESS_DIR / "retrieval_ab.json", "hardness_retrieval_ab", statements)
    srcs = {r["src"] for r in records}
    if "cosmo3_episode" not in srcs or "hardness_baseline" not in srcs:
        raise SystemExit("BLOCKED: the two mandatory sources (cosmo3 episodes, hardness baseline) are not both present")
    counts = class_counts(records)
    print("dataset counts:", json.dumps(counts, indent=1))
    with open(DATASET_PATH, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    split = group_split(records, HELDOUT_FRACTION, SPLIT_SEED)
    by_uid = {r["uid"]: r for r in records}
    split["train_counts"] = class_counts([by_uid[u] for u in split["train_uids"]])
    split["heldout_counts"] = class_counts([by_uid[u] for u in split["heldout_uids"]])
    split["dataset_counts"] = counts
    with open(SPLIT_PATH, "w") as f:
        json.dump(split, f, indent=1)
    print("train rows:", len(split["train_uids"]), json.dumps(split["train_counts"]))
    print("held-out rows:", len(split["heldout_uids"]), json.dumps(split["heldout_counts"]))
    print("held-out groups:", json.dumps(split["heldout_groups"]))
    print("wrote", DATASET_PATH, "and", SPLIT_PATH)


if __name__ == "__main__":
    main()

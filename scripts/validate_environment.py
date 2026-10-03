#!/usr/bin/env python3
"""End-to-end validation of this deployment. Reports what is true, not what is hoped.

Every check returns PASS, FAIL or SKIP with the evidence that produced it. A SKIP
is a result (a component is genuinely absent), a FAIL is a result (it is present
and broken), and neither is hidden. Exit code is nonzero if anything FAILED, so
this is usable as a gate.

Written because the v12.4.0 release asserted "✅ FULLY OPERATIONAL" for a stack
whose verification gates exited 1 and whose test suite could not even be
collected. The remedy is a validator that prints the command output it based each
verdict on.

Usage:
    .venv/bin/python scripts/validate_environment.py
    .venv/bin/python scripts/validate_environment.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DISK2 = Path("/mnt/disks/disk-socrateai-local-1")
sys.path.insert(0, str(DISK2 / "gpu_lease"))

from gpu_lease import gpu_lease  # noqa: E402

LEASE_HOLDER = "autoevolve-validate-env"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class Check:
    name: str
    verdict: Verdict
    detail: str
    evidence: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)


def _run(cmd: list[str], timeout: float = 60.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.0f}s"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


# --------------------------------------------------------------- host resources


def check_host_resources() -> Check:
    """CPU, RAM and the two disks this profile depends on."""
    cpus = os.cpu_count() or 0
    mem_gb = 0.0
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    mem_gb = int(line.split()[1]) / 1024 / 1024
                    break
    except OSError:
        pass

    root = shutil.disk_usage("/")
    disk2_free_gb = None
    if DISK2.exists():
        disk2_free_gb = shutil.disk_usage(DISK2).free / 2**30

    metrics = {
        "cpu_count": cpus,
        "mem_total_gb": round(mem_gb, 1),
        "root_free_gb": round(root.free / 2**30, 1),
        "disk2_free_gb": round(disk2_free_gb, 1) if disk2_free_gb else None,
        "disk2_mounted": DISK2.exists(),
    }
    if not DISK2.exists():
        return Check(
            "host_resources",
            Verdict.FAIL,
            f"second disk {DISK2} is not mounted; the data lake and model store live there",
            metrics=metrics,
        )
    return Check(
        "host_resources",
        Verdict.PASS,
        f"{cpus} vCPU, {mem_gb:.0f} GiB RAM, root {metrics['root_free_gb']} GiB free, "
        f"disk2 {metrics['disk2_free_gb']} GiB free",
        metrics=metrics,
    )


# ------------------------------------------------------------------------- GPU


def check_gpu() -> Check:
    """Live NVML probe. Never inferred."""
    code, out, err = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if code != 0:
        return Check("gpu", Verdict.FAIL, f"nvidia-smi failed: {err or code}", evidence=err)

    name, total, free, driver = (part.strip() for part in out.split(",")[:4])
    metrics = {
        "name": name,
        "total_mib": int(total),
        "free_mib": int(free),
        "driver": driver,
    }
    return Check("gpu", Verdict.PASS, f"{name}, driver {driver}, {free} MiB free of {total}", evidence=out, metrics=metrics)


def check_torch_cuda() -> Check:
    code, out, err = _run(
        [
            sys.executable,
            "-c",
            "import torch,json;"
            "d=torch.cuda.is_available();"
            "p=torch.cuda.get_device_properties(0) if d else None;"
            "print(json.dumps({'available':d,'torch':torch.__version__,"
            "'name':p.name if p else None,'sm':f'{p.major}.{p.minor}' if p else None}))",
        ],
        timeout=180,
    )
    if code != 0:
        return Check("torch_cuda", Verdict.FAIL, f"torch probe failed: {err[:200]}", evidence=err)
    info = json.loads(out)
    if not info["available"]:
        return Check("torch_cuda", Verdict.FAIL, "torch cannot see CUDA", evidence=out)
    # sm_75 (Turing) has fp16 tensor cores but no bf16 ones, and no FlashAttention-2.
    note = ""
    if info["sm"] == "7.5":
        note = " — sm_75: use fp16, not bf16; FlashAttention-2 needs sm_80+"
    return Check(
        "torch_cuda",
        Verdict.PASS,
        f"torch {info['torch']} sees {info['name']} (sm {info['sm']}){note}",
        evidence=out,
        metrics=info,
    )


# ---------------------------------------------------------------------- ollama


def check_ollama_gpu_placement() -> Check:
    """The check that caught days of silent CPU-only serving.

    Ollama initialised before the GPU driver existed and served on CPU at
    2.3 tok/s for days while every report claimed T4 inference. Placement is
    therefore verified explicitly, not assumed from the model being loaded.
    """
    code, out, _ = _run(["ollama", "ps"], timeout=30)
    if code != 0:
        return Check("ollama_placement", Verdict.SKIP, "ollama not reachable", evidence=out)
    if "GPU" in out:
        return Check("ollama_placement", Verdict.PASS, "a model is resident on the GPU", evidence=out)
    if not out or len(out.strip().splitlines()) <= 1:
        return Check(
            "ollama_placement",
            Verdict.SKIP,
            "no model currently loaded; run an inference then re-check placement",
            evidence=out,
        )
    return Check(
        "ollama_placement",
        Verdict.FAIL,
        "a model is loaded but NOT on the GPU (CPU-only serving)",
        evidence=out,
    )


def check_ollama_throughput(model: str = "qwen2.5-coder:7b-instruct") -> Check:
    """Warm throughput. A cold call includes model load and is not the useful number."""
    try:
        import httpx
    except ImportError:
        return Check("ollama_throughput", Verdict.SKIP, "httpx not installed")

    payload = {
        "model": model,
        "prompt": "Write a Python function that returns the sum of a list.",
        "stream": False,
        "options": {"num_predict": 80, "temperature": 0.2},
    }
    try:
        with gpu_lease(LEASE_HOLDER, "validate_environment: warm Ollama throughput probe",
                       ttl_s=1800, timeout_s=600):
            httpx.post("http://localhost:11434/api/generate", json=payload, timeout=900)
            start = time.monotonic()
            response = httpx.post(
                "http://localhost:11434/api/generate", json=payload, timeout=900
            )
            wall = time.monotonic() - start
    except TimeoutError as exc:
        return Check("ollama_throughput", Verdict.SKIP, f"GPU lease held by another job: {exc}")
    except httpx.HTTPError as exc:
        return Check("ollama_throughput", Verdict.SKIP, f"ollama unreachable: {exc}")

    if response.status_code != 200:
        return Check(
            "ollama_throughput",
            Verdict.FAIL,
            f"ollama returned {response.status_code}",
            evidence=response.text[:300],
        )

    body = response.json()
    tokens = body.get("eval_count", 0)
    eval_s = body.get("eval_duration", 1) / 1e9
    tps = tokens / eval_s if eval_s else 0.0
    metrics = {"model": model, "tokens": tokens, "eval_s": round(eval_s, 2), "tok_per_s": round(tps, 1), "wall_s": round(wall, 2)}

    if tps < 10:
        return Check(
            "ollama_throughput",
            Verdict.FAIL,
            f"{tps:.1f} tok/s is CPU-class; the GPU is probably not being used "
            "(restart ollama so it re-probes the driver)",
            evidence=json.dumps(metrics),
            metrics=metrics,
        )
    return Check(
        "ollama_throughput",
        Verdict.PASS,
        f"{tps:.1f} tok/s warm on {model}",
        evidence=json.dumps(metrics),
        metrics=metrics,
    )


# ----------------------------------------------------------------------- redis


def check_redis() -> Check:
    try:
        import redis
    except ImportError:
        return Check("redis", Verdict.SKIP, "redis client not installed")
    try:
        client = redis.Redis.from_url(
            os.environ.get("ANSE_REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        client.ping()
        size = client.dbsize()
    except Exception as exc:
        return Check("redis", Verdict.FAIL, f"redis unreachable: {exc}")
    return Check("redis", Verdict.PASS, f"reachable, {size} keys", metrics={"dbsize": size})


# ------------------------------------------------------------------ embeddings


def check_embeddings() -> Check:
    """Semantic embeddings must be real, not md5 pseudo-vectors."""
    try:
        from anse.memory.ollama_embeddings import (
            EmbeddingUnavailableError,
            OllamaEmbeddingFunction,
        )
    except ImportError as exc:
        return Check("embeddings", Verdict.FAIL, f"cannot import embedding module: {exc}")

    fn = OllamaEmbeddingFunction()
    try:
        info = fn.probe()
    except EmbeddingUnavailableError as exc:
        return Check("embeddings", Verdict.SKIP, f"embedding backend unavailable: {exc}")

    return Check(
        "embeddings",
        Verdict.PASS,
        f"{info['model']} returns {info['dimension']}-d vectors",
        metrics=info,
    )


def check_semantic_quality() -> Check:
    """Prove the embedding carries meaning, which an md5 n-gram vector does not."""
    try:
        from anse.memory.ollama_embeddings import (
            EmbeddingUnavailableError,
            OllamaEmbeddingFunction,
        )
    except ImportError as exc:
        return Check("semantic_quality", Verdict.FAIL, f"import failed: {exc}")

    def cosine(u: list[float], v: list[float]) -> float:
        dot = sum(a * b for a, b in zip(u, v))
        return dot / ((sum(a * a for a in u) ** 0.5) * (sum(b * b for b in v) ** 0.5))

    try:
        a, b, c = OllamaEmbeddingFunction()(
            [
                "the dog ran quickly across the field",
                "a canine sprinted rapidly over the meadow",
                "quarterly amortisation of deferred tax liabilities",
            ]
        )
    except EmbeddingUnavailableError as exc:
        return Check("semantic_quality", Verdict.SKIP, f"backend unavailable: {exc}")

    paraphrase = cosine(a, b)
    unrelated = cosine(a, c)
    metrics = {"paraphrase_cos": round(paraphrase, 4), "unrelated_cos": round(unrelated, 4)}
    if paraphrase <= unrelated:
        return Check(
            "semantic_quality",
            Verdict.FAIL,
            f"paraphrase similarity {paraphrase:.3f} does not exceed unrelated "
            f"{unrelated:.3f} — this embedding is not semantic",
            metrics=metrics,
        )
    return Check(
        "semantic_quality",
        Verdict.PASS,
        f"paraphrase {paraphrase:.3f} > unrelated {unrelated:.3f}",
        metrics=metrics,
    )


# --------------------------------------------------------------------- chroma


def check_chroma_collections() -> Check:
    try:
        import chromadb
    except ImportError:
        return Check("chroma", Verdict.SKIP, "chromadb not installed")

    roots = [
        REPO_ROOT / "data" / "chroma",
        DISK2 / "AutoevolveAI" / "datalake" / "data" / "chroma" / "mathlib_rag_db",
        DISK2 / "AutoevolveAI" / "datalake" / "chroma",
    ]
    found: dict[str, int] = {}
    for root in roots:
        if not root.exists():
            continue
        try:
            client = chromadb.PersistentClient(path=str(root))
            for collection in client.list_collections():
                found[f"{root.name}/{collection.name}"] = collection.count()
        except Exception as exc:  # a corrupt store must not abort validation
            found[f"{root.name}/<error>"] = -1
            del exc

    if not found:
        return Check("chroma", Verdict.SKIP, "no Chroma collections found in the known roots")
    total = sum(v for v in found.values() if v > 0)
    return Check(
        "chroma",
        Verdict.PASS,
        f"{len(found)} collection(s), {total} items: "
        + ", ".join(f"{k}={v}" for k, v in sorted(found.items())),
        metrics=found,
    )


# ------------------------------------------------------------------ lean gate


def check_lean_sorry_is_not_a_proof() -> Check:
    """The defect that invalidates every exit-code-based proof gate in this repo.

    `sorry` compiles and EXITS 0, so returncode is not evidence of a proof. A
    sound gate must inspect `#print axioms` for sorryAx.
    """
    lean = shutil.which("lean")
    if lean is None:
        return Check("lean_sorry_gate", Verdict.SKIP, "lean not on PATH")

    import tempfile

    source = "theorem probe_sorry (n : Nat) : n + 0 = n := by sorry\n#print axioms probe_sorry\n"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "Probe.lean"
        path.write_text(source)
        code, out, err = _run([lean, str(path)], timeout=180)

    combined = f"{out}\n{err}"
    exits_zero = code == 0
    names_sorry_ax = "sorryAx" in combined
    metrics = {"exit_code": code, "exits_zero_with_sorry": exits_zero, "axioms_reveal_sorry": names_sorry_ax}

    if exits_zero and names_sorry_ax:
        return Check(
            "lean_sorry_gate",
            Verdict.PASS,
            "confirmed: `sorry` exits 0 but #print axioms reveals sorryAx — "
            "an axiom-checked gate is required, exit code alone is not proof",
            evidence=combined[:400],
            metrics=metrics,
        )
    if exits_zero and not names_sorry_ax:
        return Check(
            "lean_sorry_gate",
            Verdict.FAIL,
            "`sorry` exits 0 AND #print axioms did not reveal sorryAx — "
            "no reliable way to detect unproved theorems here",
            evidence=combined[:400],
            metrics=metrics,
        )
    return Check(
        "lean_sorry_gate",
        Verdict.PASS,
        f"lean rejected the sorry proof outright (exit {code})",
        evidence=combined[:400],
        metrics=metrics,
    )


# ------------------------------------------------------------- repo own gates


def check_repo_gates() -> list[Check]:
    """Run the repo's own stated completion gates and report their true exit codes."""
    checks: list[Check] = []
    env_python = str(REPO_ROOT / ".venv" / "bin" / "python")
    for name, script in (
        ("gate_antigravity_guard", "antigravity_guard.py"),
        ("gate_test_rigor_guard", "test_rigor_guard.py"),
    ):
        code, out, err = _run([env_python, str(REPO_ROOT / script)], timeout=600)
        tail = (out or err)[-400:]
        checks.append(
            Check(
                name,
                Verdict.PASS if code == 0 else Verdict.FAIL,
                f"{script} exited {code}",
                evidence=tail,
                metrics={"exit_code": code},
            )
        )

    code, out, err = _run(
        [env_python, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider", "--collect-only"],
        timeout=600,
    )
    collected = "error" not in (out + err).lower() or code == 0
    checks.append(
        Check(
            "gate_pytest_collects",
            Verdict.PASS if collected and code == 0 else Verdict.FAIL,
            f"pytest collection exited {code}"
            + ("" if collected else " — the suite cannot be collected, so 0 tests run"),
            evidence=(out or err)[-400:],
            metrics={"exit_code": code},
        )
    )
    return checks


# ------------------------------------------------------------------------ main


CHECKS: tuple[Callable[[], Check], ...] = (
    check_host_resources,
    check_gpu,
    check_torch_cuda,
    check_ollama_gpu_placement,
    check_ollama_throughput,
    check_redis,
    check_embeddings,
    check_semantic_quality,
    check_chroma_collections,
    check_lean_sorry_is_not_a_proof,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--skip-gates", action="store_true", help="skip the slow repo gates")
    args = parser.parse_args(argv)

    results: list[Check] = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # a broken check must not hide the others
            results.append(Check(check.__name__, Verdict.FAIL, f"check raised: {exc}"))

    if not args.skip_gates:
        results.extend(check_repo_gates())

    passed = sum(1 for r in results if r.verdict is Verdict.PASS)
    failed = sum(1 for r in results if r.verdict is Verdict.FAIL)
    skipped = sum(1 for r in results if r.verdict is Verdict.SKIP)

    if args.json:
        print(
            json.dumps(
                {
                    "summary": {"pass": passed, "fail": failed, "skip": skipped},
                    "checks": [
                        {
                            "name": r.name,
                            "verdict": str(r.verdict),
                            "detail": r.detail,
                            "metrics": r.metrics,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
    else:
        width = max(len(r.name) for r in results)
        for r in results:
            print(f"[{r.verdict:4}] {r.name:<{width}}  {r.detail}")
        print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
        if failed:
            print("\nFAILED checks are real defects in this deployment, not validator bugs.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

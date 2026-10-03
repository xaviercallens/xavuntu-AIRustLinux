#!/usr/bin/env python3
"""Publish the cosmology synthesis paper and its data to Zenodo and Hugging Face.

Tokens are read from a KEY=VALUE file (``ZENODO_TOKEN``, ``HUGGINGFACE_TOKEN``) or the
environment, and are never printed. ``--dry-run`` builds the bundle and the metadata and
stops before any network write. A Zenodo publish mints a permanent DOI, so the default is
to create the deposition as a draft; ``--publish`` is required to make it public.

Usage:
    .venv/bin/python scripts/publish_cosmo_synthesis.py --token-file ~/.token_workflow_token --dry-run
    .venv/bin/python scripts/publish_cosmo_synthesis.py --token-file ~/.token_workflow_token --publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
BUNDLE_DIR = Path("/mnt/disks/disk-socrateai-local-1/SocrateAI-storage/lab-archive/cosmology_bao_2026-09")
RUNS = ["bao_flcdm", "desi_dr2_bao", "bao_bbn_h0", "eboss_vs_desi", "cosmo_synthesis", "cosmo3_learning"]
LEAN = ["BAO_FlatLCDM", "DESI_DR2_wCDM", "BAO_BBN_H0", "BAO_Consistency"]
PAPER_PDF = REPO / "papers" / "cosmo_synthesis" / "cosmo_synthesis.pdf"
HF_REPO = "callensxavier/autoevolve-bao-cosmology-reproductions"
ZENODO = "https://zenodo.org/api"


def load_tokens(path: Path | None) -> dict[str, str]:
    out = {k: os.environ[k] for k in ("ZENODO_TOKEN", "HUGGINGFACE_TOKEN") if os.environ.get(k)}
    if path and path.exists():
        for raw in path.read_text().splitlines():
            line = raw.strip().removeprefix("export ")
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def bundle_members() -> list[Path]:
    members: list[Path] = []
    for run in RUNS:
        for sub in ("results", "scripts", "papers"):
            d = REPO / sub / run
            if d.exists():
                members += [p for p in d.rglob("*") if p.is_file() and p.suffix not in {".aux", ".log", ".out", ".pyc"}]
    members += [REPO / "formal" / "ANSE" / f"{m}.lean" for m in LEAN]
    members += [REPO / "docs" / "literature" / f"{n}_LITERATURE_REVIEW_2026.md"
                for n in ("BAO_FLCDM", "DESI_DR2_BAO", "BAO_BBN_H0", "EBOSS_VS_DESI")]
    members += [REPO / "LL.md", REPO / "scripts" / "cosmo3_retrofit.py"]
    return sorted(p for p in set(members) if p.exists())


def build_bundle() -> tuple[Path, Path]:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    members = bundle_members()
    manifest = {str(p.relative_to(REPO)): {"sha256": sha256(p), "bytes": p.stat().st_size} for p in members}
    manifest_path = BUNDLE_DIR / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=1))
    tar_path = BUNDLE_DIR / "autoevolve_bao_cosmology_2026-09.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for p in members:
            tar.add(p, arcname=str(p.relative_to(REPO)))
        tar.add(manifest_path, arcname="MANIFEST.json")
    return tar_path, manifest_path


def zenodo_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    return {"metadata": {
        "title": meta["title"],
        "upload_type": "publication",
        "publication_type": "preprint",
        "description": meta["description"],
        "creators": [{"name": "Callens, Xavier", "affiliation": "SocrateAI Lab"}],
        "keywords": ["BAO", "DESI DR2", "cosmology", "reproducibility", "preregistration",
                     "Lean 4", "formal verification", "AI agents"],
        "license": "cc-by-4.0",
        "related_identifiers": [
            {"identifier": "https://github.com/xaviercallens/AutoevolveAI", "relation": "isSupplementTo", "scheme": "url"},
            {"identifier": "https://github.com/xaviercallens/rusty-SUNDIALS", "relation": "isSupplementTo", "scheme": "url"},
            {"identifier": f"https://huggingface.co/datasets/{HF_REPO}", "relation": "isSupplementedBy", "scheme": "url"},
        ],
        "notes": meta.get("notes", ""),
    }}


def zenodo_request(method: str, url: str, token: str, data: bytes | None = None,
                   content_type: str = "application/json") -> dict[str, Any]:
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=600) as r:
        body = r.read()
        return json.loads(body) if body else {}


def publish_zenodo(token: str, files: list[Path], meta: dict[str, Any], publish: bool) -> dict[str, Any]:
    dep = zenodo_request("POST", f"{ZENODO}/deposit/depositions", token, b"{}")
    bucket = dep["links"]["bucket"]
    for f in files:
        with open(f, "rb") as fh:
            zenodo_request("PUT", f"{bucket}/{f.name}", token, fh.read(), "application/octet-stream")
    dep = zenodo_request("PUT", f"{ZENODO}/deposit/depositions/{dep['id']}", token,
                         json.dumps(zenodo_metadata(meta)).encode())
    if publish:
        dep = zenodo_request("POST", f"{ZENODO}/deposit/depositions/{dep['id']}/actions/publish", token)
    return {"id": dep.get("id"), "doi": dep.get("doi") or dep.get("metadata", {}).get("prereserve_doi", {}).get("doi"),
            "state": dep.get("state"), "submitted": dep.get("submitted"),
            "html": dep.get("links", {}).get("html")}


def publish_hf(token: str, tar_path: Path, manifest: Path, card: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(HF_REPO, repo_type="dataset", exist_ok=True)
    api.upload_file(path_or_fileobj=card.encode(), path_in_repo="README.md", repo_id=HF_REPO, repo_type="dataset")
    for f in (tar_path, manifest, PAPER_PDF):
        api.upload_file(path_or_fileobj=str(f), path_in_repo=f.name, repo_id=HF_REPO, repo_type="dataset")
    episodes = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/datalake/episodes/cosmo3_2026-09-27.jsonl")
    if episodes.exists():
        api.upload_file(path_or_fileobj=str(episodes), path_in_repo="jepa_episodes/cosmo3_2026-09-27.jsonl",
                        repo_id=HF_REPO, repo_type="dataset")
    return f"https://huggingface.co/datasets/{HF_REPO}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", type=Path)
    ap.add_argument("--meta", type=Path, default=REPO / "papers" / "cosmo_synthesis" / "publication_meta.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--publish", action="store_true", help="make the Zenodo record public (mints the DOI)")
    ap.add_argument("--skip-zenodo", action="store_true")
    ap.add_argument("--skip-hf", action="store_true")
    ap.add_argument("--no-rebuild", action="store_true",
                    help="reuse the existing bundle so every upload carries the same sha256")
    ap.add_argument("--publish-id", type=int,
                    help="publish an existing Zenodo draft deposition by id (no new deposition)")
    args = ap.parse_args()

    if args.publish_id:
        toks = load_tokens(args.token_file)
        dep = zenodo_request("POST", f"{ZENODO}/deposit/depositions/{args.publish_id}/actions/publish",
                             toks["ZENODO_TOKEN"])
        print(json.dumps({"id": dep.get("id"), "doi": dep.get("doi"), "state": dep.get("state"),
                          "submitted": dep.get("submitted"), "html": dep.get("links", {}).get("html")}, indent=2))
        return 0

    meta = json.loads(args.meta.read_text())
    if args.no_rebuild:
        tar_path = BUNDLE_DIR / "autoevolve_bao_cosmology_2026-09.tar.gz"
        manifest = BUNDLE_DIR / "MANIFEST.json"
    else:
        tar_path, manifest = build_bundle()
    report: dict[str, Any] = {"bundle": str(tar_path), "bundle_sha256": sha256(tar_path),
                              "bundle_bytes": tar_path.stat().st_size, "manifest": str(manifest),
                              "files_in_manifest": len(json.loads(manifest.read_text())),
                              "paper_pdf_sha256": sha256(PAPER_PDF)}
    if args.dry_run:
        report["zenodo_metadata"] = zenodo_metadata(meta)
        print(json.dumps(report, indent=2))
        return 0
    toks = load_tokens(args.token_file)
    if not args.skip_zenodo:
        report["zenodo"] = publish_zenodo(toks["ZENODO_TOKEN"], [PAPER_PDF, tar_path, manifest], meta, args.publish)
    if not args.skip_hf:
        report["huggingface"] = publish_hf(toks["HUGGINGFACE_TOKEN"], tar_path, manifest, meta["hf_card"])
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

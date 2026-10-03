#!/usr/bin/env python3
"""Create (or update) a Zenodo *draft* deposition. Never publishes.

Publishing mints a permanent DOI and cannot be undone, so it is left to a
human clicking "Publish" in the Zenodo web UI after reviewing the draft.

Token: $ZENODO_TOKEN, else ~/.zenodo_token. Never hard-code tokens here.
TLS verification stays on.

Usage:
    scripts/publish/zenodo_draft.py --metadata publish/zenodo_metadata.json \
        --file paper/claims_vs_evidence.pdf --file ... [--deposition-id ID]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

API = "https://zenodo.org/api/deposit/depositions"


def token() -> str:
    t = os.environ.get("ZENODO_TOKEN")
    if not t:
        p = Path.home() / ".zenodo_token"
        t = p.read_text().strip() if p.exists() else ""
    if not t:
        sys.exit("ERROR: set ZENODO_TOKEN or create ~/.zenodo_token")
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", required=True)
    ap.add_argument("--file", action="append", default=[])
    ap.add_argument("--deposition-id", help="update an existing draft instead of creating one")
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {token()}"}
    metadata = json.loads(Path(args.metadata).read_text())

    if args.deposition_id:
        dep = requests.get(f"{API}/{args.deposition_id}", headers=headers, timeout=60)
    else:
        dep = requests.post(API, headers=headers, json={}, timeout=60)
    dep.raise_for_status()
    dep = dep.json()
    if dep.get("submitted"):
        sys.exit(f"ERROR: deposition {dep['id']} is already published; create a new version instead")

    bucket = dep["links"]["bucket"]
    for f in args.file:
        p = Path(f)
        with p.open("rb") as fh:
            r = requests.put(f"{bucket}/{p.name}", data=fh, headers=headers, timeout=300)
        r.raise_for_status()
        print(f"uploaded {p.name} ({p.stat().st_size} bytes)")

    r = requests.put(f"{API}/{dep['id']}", headers=headers, json={"metadata": metadata}, timeout=60)
    r.raise_for_status()
    d = r.json()
    print(json.dumps({
        "deposition_id": d["id"],
        "state": d.get("state"),
        "submitted": d.get("submitted"),
        "reserved_doi": d["metadata"].get("prereserve_doi", {}).get("doi"),
        "review_url": d["links"].get("html"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

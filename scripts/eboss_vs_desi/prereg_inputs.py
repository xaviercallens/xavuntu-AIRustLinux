"""Pre-registration inputs for the eboss_vs_desi problem (no fitting).

Computes, from data files and published numbers only:
  1. sha256 of every data file the planned fit will read;
  2. the literature-only expectation band for the DESI DR2 vs SDSS parameter
     tension, using the published (Omega_m, h r_d) means/errors of both
     surveys. The SDSS (Omega_m, h r_d) correlation coefficient is NOT
     published in the fetched sources, so the band is scanned over it.

Writes results/eboss_vs_desi/prereg_inputs.json. Does not read or produce
any fit output of this problem.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import stats

DATA_DIR = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
OUT = Path(__file__).resolve().parents[2] / "results" / "eboss_vs_desi" / "prereg_inputs.json"

SDSS_FILES: list[str] = [
    "sdss_MGS_prob.txt",
    "sdss_DR12_LRG_BAO_DMDH.dat",
    "sdss_DR12_LRG_BAO_DMDH_covtot.txt",
    "sdss_DR16_LRG_BAO_DMDH.dat",
    "sdss_DR16_LRG_BAO_DMDH_covtot.txt",
    "sdss_DR16_ELG_BAO_DVtable.txt",
    "sdss_DR16_QSO_BAO_DMDH.txt",
    "sdss_DR16_QSO_BAO_DMDH_covtot.txt",
    "sdss_DR16_LYAUTO_BAO_DMDHgrid.txt",
    "sdss_DR16_LYxQSO_BAO_DMDHgrid.txt",
]
DESI_FILES: list[str] = [
    "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_mean.txt",
    "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_cov.txt",
]
EXCLUDED_FILES: list[str] = [
    # DESI DR1 + eBOSS combined Lya: contains DESI data -> must NOT enter the SDSS side.
    "desi_2024_eboss_gaussian_bao_Lya_GCcomb_mean.txt",
    "desi_2024_eboss_gaussian_bao_Lya_GCcomb_cov.txt",
]

# Published values (see docs/literature/EBOSS_VS_DESI_LITERATURE_REVIEW_2026.md)
DESI_DR2 = {"om": 0.2975, "om_sig": 0.0086, "rdh": 101.54, "rdh_sig": 0.73, "r": -0.92}
SDSS = {"om": 0.299, "om_sig": 0.016, "rdh": 100.4, "rdh_sig": 1.3}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cov2(s1: float, s2: float, r: float) -> np.ndarray:
    return np.array([[s1 * s1, r * s1 * s2], [r * s1 * s2, s2 * s2]])


def pte_to_sigma(chi2: float, dof: int) -> float:
    pte = float(stats.chi2.sf(chi2, dof))
    return float(stats.norm.isf(pte / 2.0))


def tension(r_sdss: float, scale: float = 1.0) -> dict[str, float]:
    """eq.(18) tension; `scale` multiplies every DESI distance ratio, which maps
    exactly to h r_d -> h r_d / scale at fixed Omega_m (errors scale likewise)."""
    rdh_desi = DESI_DR2["rdh"] / scale
    d = np.array([DESI_DR2["om"] - SDSS["om"], rdh_desi - SDSS["rdh"]])
    c = cov2(DESI_DR2["om_sig"], DESI_DR2["rdh_sig"] / scale, DESI_DR2["r"]) + cov2(
        SDSS["om_sig"], SDSS["rdh_sig"], r_sdss
    )
    chi2 = float(d @ np.linalg.solve(c, d))
    return {"r_sdss": r_sdss, "scale": scale, "chi2_2dof": chi2,
            "pte": float(stats.chi2.sf(chi2, 2)), "n_sigma": pte_to_sigma(chi2, 2)}


R_SCAN: list[float] = [float(r) for r in np.round(np.arange(-0.95, 0.951, 0.05), 2)]
SHIFT_SCALES: list[float] = [0.97, 0.95, 0.93, 0.90, 1.03, 1.05, 1.07, 1.10]


def injected_shift_table() -> list[dict[str, float]]:
    """Expected N_sigma for the negative control 'all DESI ratios x scale',
    minimised over the unpublished SDSS correlation (worst case for the control)."""
    rows = []
    for s in SHIFT_SCALES:
        ns = [tension(r, s)["n_sigma"] for r in R_SCAN]
        rows.append({"scale": s, "n_sigma_min_over_r": float(min(ns)),
                     "n_sigma_max_over_r": float(max(ns))})
    return rows


def main() -> int:
    files = {}
    for name in SDSS_FILES + DESI_FILES + EXCLUDED_FILES:
        p = DATA_DIR / name
        files[name] = {"sha256": sha256(p), "bytes": p.stat().st_size}
    scan = [tension(r) for r in R_SCAN]
    shift_rows = injected_shift_table()
    nsig = [s["n_sigma"] for s in scan]
    one_d = {
        "om": abs(DESI_DR2["om"] - SDSS["om"]) / np.hypot(DESI_DR2["om_sig"], SDSS["om_sig"]),
        "rdh": abs(DESI_DR2["rdh"] - SDSS["rdh"]) / np.hypot(DESI_DR2["rdh_sig"], SDSS["rdh_sig"]),
    }
    out = {
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "data_dir": str(DATA_DIR),
        "files": files,
        "literature_expectation": {
            "inputs": {"desi_dr2": DESI_DR2, "sdss": SDSS},
            "one_d_sigma": {k: float(v) for k, v in one_d.items()},
            "two_d_scan_over_unpublished_sdss_correlation": scan,
            "two_d_n_sigma_min": float(min(nsig)),
            "two_d_n_sigma_max": float(max(nsig)),
        },
        "negative_control_injected_scale_expectation": shift_rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps({"files": {k: v["sha256"] for k, v in files.items()},
                      "one_d_sigma": out["literature_expectation"]["one_d_sigma"],
                      "two_d_n_sigma_range": [min(nsig), max(nsig)],
                      "injected_scale": shift_rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

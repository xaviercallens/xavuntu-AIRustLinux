#!/usr/bin/env python3
"""Flat-LambdaCDM BAO consistency fit against real DESI DR1 combined data.

Two independently-coded prediction methods must agree (the same discipline as
Elenchus's ratchet: an independent second path catching a bug the first path
would hide):
  Method A: astropy.cosmology.FlatLambdaCDM (H0 fixed at 100 so only Om0
            varies; the fitted r_d*h parameter absorbs the H0/r_d degeneracy
            that BAO alone cannot break -- exactly DESI's own parametrization).
  Method B: a from-scratch numpy/scipy.integrate.quad implementation of
            E(z) = sqrt(Om*(1+z)^3 + (1-Om)) and the comoving-distance
            integral, with no astropy dependency.

Fit: scipy.optimize.minimize on the real 12x12 DESI DR1 covariance (real
matrix, not diagonal -- DM/DH within a redshift bin are correlated).
Cross-check: an independent grid search over the same chi^2.

External validation target (not used as a fit input): DESI DR1's own quoted
flat-LCDM result, Om = 0.295 +/- 0.015, rd*h = (101.8 +/- 1.3) Mpc
(arXiv:2404.03002, quoted directly from the fetched paper text).

Run with the venv-pta interpreter (has astropy + scipy together):
    /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python3 fit_desi_bao.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from astropy.cosmology import FlatLambdaCDM
from scipy.integrate import quad
from scipy.optimize import minimize

DATA_DIR = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
MEAN_FILE = DATA_DIR / "desi_2024_gaussian_bao_ALL_GCcomb_mean.txt"
COV_FILE = DATA_DIR / "desi_2024_gaussian_bao_ALL_GCcomb_cov.txt"
C_KM_S = 299792.458  # exact, CODATA

DESI_PAPER_OM = (0.295, 0.015)
DESI_PAPER_RDH = (101.8, 1.3)  # Mpc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_data() -> tuple[list[float], list[float], list[str], np.ndarray]:
    zs, vals, kinds = [], [], []
    for line in MEAN_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        z, v, kind = line.split()
        zs.append(float(z))
        vals.append(float(v))
        kinds.append(kind)
    cov = np.loadtxt(COV_FILE)
    assert cov.shape == (len(zs), len(zs)), f"cov shape {cov.shape} != {len(zs)} data points"
    return zs, vals, kinds, cov


# ---------------------------------------------------------------- Method A --
def predict_astropy(zs: list[float], kinds: list[str], om: float, rd_h: float) -> np.ndarray:
    cosmo = FlatLambdaCDM(H0=100.0, Om0=om)  # H0=100 isolates the h-dependence into rd_h
    out = []
    for z, kind in zip(zs, kinds):
        dm100 = cosmo.comoving_distance(z).value  # Mpc, at H0=100 (i.e. this is D_M*h)
        h100 = cosmo.H(z).value  # km/s/Mpc, at H0=100 (i.e. this is H(z)/h)
        dm_over_rd = dm100 / rd_h
        dh_over_rd = C_KM_S / (h100 * rd_h)
        if kind == "DM_over_rs":
            out.append(dm_over_rd)
        elif kind == "DH_over_rs":
            out.append(dh_over_rd)
        elif kind == "DV_over_rs":
            dv_over_rd = (z * dm_over_rd**2 * dh_over_rd) ** (1.0 / 3.0)
            out.append(dv_over_rd)
        else:
            raise ValueError(f"unknown observable kind: {kind}")
    return np.array(out)


# ---------------------------------------------------------------- Method B --
def e_of_z(z: float, om: float) -> float:
    return np.sqrt(om * (1.0 + z) ** 3 + (1.0 - om))


def comoving_distance_h100(z: float, om: float) -> float:
    """D_C(z) in Mpc, for H0 = 100 km/s/Mpc exactly (independent of astropy)."""
    integral, _ = quad(lambda zp: 1.0 / e_of_z(zp, om), 0.0, z)
    return (C_KM_S / 100.0) * integral


def predict_manual(zs: list[float], kinds: list[str], om: float, rd_h: float) -> np.ndarray:
    out = []
    for z, kind in zip(zs, kinds):
        dm100 = comoving_distance_h100(z, om)
        h100 = 100.0 * e_of_z(z, om)
        dm_over_rd = dm100 / rd_h
        dh_over_rd = C_KM_S / (h100 * rd_h)
        if kind == "DM_over_rs":
            out.append(dm_over_rd)
        elif kind == "DH_over_rs":
            out.append(dh_over_rd)
        elif kind == "DV_over_rs":
            out.append((z * dm_over_rd**2 * dh_over_rd) ** (1.0 / 3.0))
        else:
            raise ValueError(f"unknown observable kind: {kind}")
    return np.array(out)


def chi2(theta: np.ndarray, zs, vals, kinds, cov_inv, predictor) -> float:
    om, rd_h = theta
    if not (0.01 < om < 0.99) or rd_h <= 0:
        return 1e12
    model = predictor(zs, kinds, om, rd_h)
    resid = np.array(vals) - model
    return float(resid @ cov_inv @ resid)


def grid_search(zs, vals, kinds, cov_inv, predictor,
                 om_range=(0.20, 0.40), rdh_range=(90.0, 115.0), n=141) -> tuple[float, float, float]:
    """Independent cross-check: brute-force grid, no gradient/optimizer machinery shared with minimize()."""
    oms = np.linspace(*om_range, n)
    rdhs = np.linspace(*rdh_range, n)
    best = (None, None, np.inf)
    for om in oms:
        for rd_h in rdhs:
            c2 = chi2(np.array([om, rd_h]), zs, vals, kinds, cov_inv, predictor)
            if c2 < best[2]:
                best = (om, rd_h, c2)
    return best


def main() -> int:
    zs, vals, kinds, cov = load_data()
    cov_inv = np.linalg.inv(cov)
    n_data = len(vals)
    n_params = 2

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "data_provenance": {
            "mean_file": str(MEAN_FILE),
            "mean_file_sha256": sha256(MEAN_FILE),
            "cov_file": str(COV_FILE),
            "cov_file_sha256": sha256(COV_FILE),
            "n_data_points": n_data,
            "redshift_bins": zs,
            "observable_kinds": kinds,
        },
        "external_validation_target": {
            "source": "DESI DR1 2024 VI, arXiv:2404.03002, quoted from fetched paper text",
            "Om_m": DESI_PAPER_OM,
            "rd_h_Mpc": DESI_PAPER_RDH,
        },
    }

    for name, predictor in [("astropy_H0trick", predict_astropy), ("manual_quad", predict_manual)]:
        x0 = np.array([0.3, 100.0])
        opt = minimize(chi2, x0, args=(zs, vals, kinds, cov_inv, predictor), method="Nelder-Mead",
                        options={"xatol": 1e-6, "fatol": 1e-8, "maxiter": 5000})
        om_fit, rdh_fit = opt.x
        c2_fit = opt.fun
        dof = n_data - n_params
        result[f"fit_{name}"] = {
            "Om_m": round(float(om_fit), 5),
            "rd_h_Mpc": round(float(rdh_fit), 4),
            "chi2": round(float(c2_fit), 4),
            "dof": dof,
            "chi2_per_dof": round(float(c2_fit) / dof, 4),
            "optimizer_converged": bool(opt.success),
        }

    om_grid, rdh_grid, c2_grid = grid_search(zs, vals, kinds, cov_inv, predict_astropy)
    result["cross_check_grid_search"] = {
        "Om_m": round(float(om_grid), 4),
        "rd_h_Mpc": round(float(rdh_grid), 3),
        "chi2": round(float(c2_grid), 4),
        "note": "independent brute-force grid, no optimizer machinery shared with minimize()",
    }

    a, b = result["fit_astropy_H0trick"], result["fit_manual_quad"]
    result["method_agreement"] = {
        "Om_m_diff": round(abs(a["Om_m"] - b["Om_m"]), 6),
        "rd_h_diff_Mpc": round(abs(a["rd_h_Mpc"] - b["rd_h_Mpc"]), 6),
        "agrees_to_1e-3": abs(a["Om_m"] - b["Om_m"]) < 1e-3 and abs(a["rd_h_Mpc"] - b["rd_h_Mpc"]) < 1e-2,
    }

    om_dev_sigma = abs(a["Om_m"] - DESI_PAPER_OM[0]) / DESI_PAPER_OM[1]
    rdh_dev_sigma = abs(a["rd_h_Mpc"] - DESI_PAPER_RDH[0]) / DESI_PAPER_RDH[1]
    result["deviation_from_published_result"] = {
        "Om_m_sigma": round(float(om_dev_sigma), 3),
        "rd_h_sigma": round(float(rdh_dev_sigma), 3),
        "within_2_sigma_both": bool(om_dev_sigma < 2 and rdh_dev_sigma < 2),
    }

    out_path = Path("results/bao_flcdm/desi_dr1_flcdm_fit.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

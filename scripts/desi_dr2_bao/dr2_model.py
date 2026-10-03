#!/usr/bin/env python3
"""Shared model code for the DESI DR2 BAO fit (problem slug: desi_dr2_bao).

Reuses the parser of scripts/bao_flcdm/fit_desi_bao.py unchanged (load_data),
re-pointing its MEAN_FILE/COV_FILE module globals, as the preregistration
(results/desi_dr2_bao/preregistration.json, "model.parent_import") requires.
The parent main() is never called: it writes into results/bao_flcdm.

Generalization (only E(z) changes):
    E(z)^2 = Om (1+z)^3 + Or (1+z)^4 + (1 - Om - Or) (1+z)^{3(1+w)}
Primary model: Or = 0.  w = -1 is flat LCDM.

Three prediction paths, cross-checked against each other in controls.py:
  quad   : scipy.integrate.quad per redshift (the parent's Method B, generalized)
  astropy: FlatLambdaCDM / FlatwCDM with H0 = 100 (the parent's Method A)
  gl     : vectorized fixed-order Gauss-Legendre on [0, z] (speed path for
           emcee; validated against quad at the prior-box corners)
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize

# ---- parent import shim (preregistered): Python 3.10 lacks datetime.UTC ----
if not hasattr(_dt, "UTC"):
    _dt.UTC = _dt.timezone.utc  # type: ignore[attr-defined]
sys.dont_write_bytecode = True  # never refresh scripts/bao_flcdm/__pycache__
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "bao_flcdm"))
import fit_desi_bao as parent  # noqa: E402

C_KM_S: float = parent.C_KM_S
DATA_DIR: Path = parent.DATA_DIR
DR1_MEAN: Path = DATA_DIR / "desi_2024_gaussian_bao_ALL_GCcomb_mean.txt"
DR1_COV: Path = DATA_DIR / "desi_2024_gaussian_bao_ALL_GCcomb_cov.txt"
DR2_MEAN: Path = DATA_DIR / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_mean.txt"
DR2_COV: Path = DATA_DIR / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_cov.txt"

RESULTS = REPO / "results" / "desi_dr2_bao"
PREREG = RESULTS / "preregistration.json"
PREREG_SHA256_EXPECTED = "723cd27d3e5e198eb415ce3f585c4dfcdd3fa1af658660c8b764bf3476fd32a4"

PRIOR_OM = (0.01, 0.99)
PRIOR_HRD = (10.0, 1000.0)
PRIOR_W = (-3.0, 1.0)

GL_ORDER = 96
_GL_X, _GL_W = np.polynomial.legendre.leggauss(GL_ORDER)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def check_provenance() -> dict[str, object]:
    """Verify preregistration and data sha256 against the preregistered values."""
    prereg_sha = sha256(PREREG)
    prereg = json.loads(PREREG.read_text())
    out: dict[str, object] = {"preregistration_sha256": prereg_sha,
                              "preregistration_sha256_matches": prereg_sha == PREREG_SHA256_EXPECTED}
    files_ok = True
    for key, info in prereg["data_files"].items():
        actual = sha256(Path(info["path"]))
        ok = actual == info["sha256"]
        files_ok = files_ok and ok
        out[f"{key}_sha256_matches"] = ok
    out["all_data_sha256_match"] = files_ok
    return out


class Dataset:
    """z, values, kinds, covariance as parsed by the parent's load_data()."""

    def __init__(self, mean_file: Path, cov_file: Path, label: str) -> None:
        parent.MEAN_FILE = mean_file
        parent.COV_FILE = cov_file
        zs, vals, kinds, cov = parent.load_data()
        self.label = label
        self.z = np.array(zs, dtype=float)
        self.vals = np.array(vals, dtype=float)
        self.kinds = list(kinds)
        self.cov = np.array(cov, dtype=float)
        self.cov_inv = np.linalg.inv(self.cov)
        self.n = len(zs)

    def with_values(self, vals: np.ndarray) -> "Dataset":
        new = object.__new__(Dataset)
        new.label, new.z, new.kinds = self.label, self.z.copy(), list(self.kinds)
        new.cov, new.cov_inv, new.n = self.cov.copy(), self.cov_inv.copy(), self.n
        new.vals = np.asarray(vals, dtype=float).copy()
        return new

    def with_cov(self, cov: np.ndarray) -> "Dataset":
        new = self.with_values(self.vals)
        new.cov = np.asarray(cov, dtype=float).copy()
        new.cov_inv = np.linalg.inv(new.cov)
        return new

    def with_z_kinds(self, z: np.ndarray, kinds: list[str]) -> "Dataset":
        new = self.with_values(self.vals)
        new.z = np.asarray(z, dtype=float).copy()
        new.kinds = list(kinds)
        return new


def load_dr1() -> Dataset:
    return Dataset(DR1_MEAN, DR1_COV, "DR1")


def load_dr2() -> Dataset:
    return Dataset(DR2_MEAN, DR2_COV, "DR2")


# ------------------------------------------------------------------ E(z) ---
def e_of_z(z: np.ndarray | float, om: np.ndarray | float, w: np.ndarray | float = -1.0,
           orad: float = 0.0) -> np.ndarray:
    zp1 = 1.0 + np.asarray(z, dtype=float)
    ode = 1.0 - om - orad
    return np.sqrt(om * zp1**3 + orad * zp1**4 + ode * zp1 ** (3.0 * (1.0 + w)))


def _assemble(z: np.ndarray, kinds: list[str], dm100: np.ndarray, e: np.ndarray,
              hrd: np.ndarray | float) -> np.ndarray:
    """Build observables. dm100/e have shape (..., n); hrd broadcast over leading axes."""
    hrd_arr = np.asarray(hrd, dtype=float)[..., None] if np.ndim(hrd) else float(hrd)
    dm = dm100 / hrd_arr
    dh = C_KM_S / (100.0 * e) / hrd_arr
    out = np.empty(np.broadcast(dm, dh).shape)
    for i, kind in enumerate(kinds):
        if kind == "DM_over_rs":
            out[..., i] = dm[..., i]
        elif kind == "DH_over_rs":
            out[..., i] = dh[..., i]
        elif kind == "DV_over_rs":
            out[..., i] = np.cbrt(z[i] * dm[..., i] ** 2 * dh[..., i])
        else:
            raise ValueError(f"unknown observable kind: {kind}")
    return out


def predict_quad(ds: Dataset, om: float, hrd: float, w: float = -1.0, orad: float = 0.0) -> np.ndarray:
    """Parent Method B generalized to wCDM (+ optional radiation)."""
    dm100 = np.array([(C_KM_S / 100.0) * quad(lambda zp: 1.0 / float(e_of_z(zp, om, w, orad)),
                                                0.0, zi, epsabs=0.0, epsrel=1e-12, limit=200)[0]
                      for zi in ds.z])
    e = e_of_z(ds.z, om, w, orad)
    return _assemble(ds.z, ds.kinds, dm100, e, hrd)


def predict_astropy(ds: Dataset, om: float, hrd: float, w: float = -1.0) -> np.ndarray:
    """Parent Method A generalized: FlatLambdaCDM (w=-1) or FlatwCDM, H0=100, Tcmb0=0."""
    from astropy.cosmology import FlatLambdaCDM, FlatwCDM
    cosmo = FlatLambdaCDM(H0=100.0, Om0=om) if w == -1.0 else FlatwCDM(H0=100.0, Om0=om, w0=w)
    assert cosmo.Ogamma0 == 0.0 and cosmo.Onu0 == 0.0, "astropy path must carry no radiation"
    dm100 = np.array([cosmo.comoving_distance(zi).value for zi in ds.z])
    e = np.array([cosmo.efunc(zi) for zi in ds.z])
    return _assemble(ds.z, ds.kinds, dm100, e, hrd)


def predict_gl(ds: Dataset, om: np.ndarray | float, hrd: np.ndarray | float,
               w: np.ndarray | float = -1.0, orad: float = 0.0) -> np.ndarray:
    """Vectorized Gauss-Legendre path. Parameters may be arrays of shape (m,)."""
    om_a = np.atleast_1d(np.asarray(om, dtype=float))
    w_a = np.broadcast_to(np.atleast_1d(np.asarray(w, dtype=float)), om_a.shape)
    hrd_a = np.broadcast_to(np.atleast_1d(np.asarray(hrd, dtype=float)), om_a.shape)
    z = ds.z
    # nodes on [0, z_i]: zp = z_i/2 (x+1); shape (n, G)
    zp = 0.5 * z[:, None] * (_GL_X[None, :] + 1.0)
    inv_e = 1.0 / e_of_z(zp[None, :, :], om_a[:, None, None], w_a[:, None, None], orad)
    integral = 0.5 * z[None, :] * np.einsum("mng,g->mn", inv_e, _GL_W)
    dm100 = (C_KM_S / 100.0) * integral
    e = e_of_z(z[None, :], om_a[:, None], w_a[:, None], orad)
    out = _assemble(z, ds.kinds, dm100, e, hrd_a)
    return out[0] if np.ndim(om) == 0 else out


# ------------------------------------------------------------- chi2 & fit --
def chi2_vals(ds: Dataset, model: np.ndarray) -> np.ndarray | float:
    r = ds.vals - model
    return np.einsum("...i,ij,...j->...", r, ds.cov_inv, r)


def in_prior(om: float, hrd: float, w: float = -1.0) -> bool:
    return (PRIOR_OM[0] < om < PRIOR_OM[1] and PRIOR_HRD[0] < hrd < PRIOR_HRD[1]
            and PRIOR_W[0] <= w <= PRIOR_W[1])


Predictor = Callable[..., np.ndarray]


def fit_chi2_min(ds: Dataset, model: str = "lcdm", predictor: Predictor = predict_gl,
                 x0: tuple[float, ...] | None = None, orad: float = 0.0,
                 max_restarts: int = 5) -> dict[str, object]:
    """Nelder-Mead (parent's tolerances), restarted from its own optimum until chi2 stops falling."""
    if model == "lcdm":
        def f(t: np.ndarray) -> float:
            om, hrd = float(t[0]), float(t[1])
            if not in_prior(om, hrd):
                return 1e12
            return float(chi2_vals(ds, predictor(ds, om, hrd, -1.0, orad) if orad else predictor(ds, om, hrd)))
        start = np.array(x0 if x0 is not None else (0.3, 100.0))
    elif model == "wcdm":
        def f(t: np.ndarray) -> float:
            om, w, hrd = float(t[0]), float(t[1]), float(t[2])
            if not in_prior(om, hrd, w):
                return 1e12
            return float(chi2_vals(ds, predictor(ds, om, hrd, w, orad) if orad else predictor(ds, om, hrd, w)))
        start = np.array(x0 if x0 is not None else (0.3, -1.0, 100.0))
    else:
        raise ValueError(model)
    opt = minimize(f, start, method="Nelder-Mead",
                   options={"xatol": 1e-8, "fatol": 1e-10, "maxiter": 20000, "maxfev": 40000})
    best_x, best_f, n_restart = opt.x, float(opt.fun), 0
    for _ in range(max_restarts):
        opt2 = minimize(f, best_x, method="Nelder-Mead",
                        options={"xatol": 1e-8, "fatol": 1e-10, "maxiter": 20000, "maxfev": 40000})
        n_restart += 1
        improved = float(opt2.fun) < best_f - 1e-12
        if float(opt2.fun) <= best_f:
            best_x, best_f = opt2.x, float(opt2.fun)
        if not improved:
            break
    names = ["Om", "h_rd"] if model == "lcdm" else ["Om", "w", "h_rd"]
    npar = len(names)
    return {"params": {k: float(v) for k, v in zip(names, best_x)}, "x": [float(v) for v in best_x],
            "chi2": best_f, "dof": ds.n - npar, "restarts": n_restart}


def model_vector(ds: Dataset, model: str, x: np.ndarray | list[float], orad: float = 0.0) -> np.ndarray:
    if model == "lcdm":
        return predict_gl(ds, float(x[0]), float(x[1]), -1.0, orad)
    return predict_gl(ds, float(x[0]), float(x[2]), float(x[1]), orad)


def fisher_cov(ds: Dataset, model: str, x: np.ndarray | list[float], rel_step: float = 1e-4,
               orad: float = 0.0) -> np.ndarray:
    """(J^T C^-1 J)^-1 with central-difference Jacobian of the model vector."""
    x = np.asarray(x, dtype=float)
    cols = []
    for k in range(len(x)):
        h = rel_step * max(abs(x[k]), 1e-3)
        xp, xm = x.copy(), x.copy()
        xp[k] += h
        xm[k] -= h
        cols.append((model_vector(ds, model, xp, orad) - model_vector(ds, model, xm, orad)) / (2 * h))
    jac = np.array(cols).T
    return np.linalg.inv(jac.T @ ds.cov_inv @ jac)


def omega_rad_from_astropy() -> float:
    """Preregistered: FlatLambdaCDM(H0=68, Om0=0.3, Tcmb0=Planck18.Tcmb0, Neff=3.044, m_nu=0)."""
    import astropy.units as u
    from astropy.cosmology import FlatLambdaCDM, Planck18
    c = FlatLambdaCDM(H0=68.0, Om0=0.3, Tcmb0=Planck18.Tcmb0, Neff=3.044, m_nu=0.0 * u.eV)
    return float(c.Ogamma0 + c.Onu0)

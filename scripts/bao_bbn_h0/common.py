"""Shared model code for the bao_bbn_h0 fit (inverse distance ladder).

Model (fixed by results/bao_bbn_h0/preregistration.json):
  flat LCDM, parameters theta = (H0, omega_b, Omega_m); Omega_m includes the one
  massive 0.06 eV neutrino (DESI convention). N_eff = 3.044, T_cmb = 2.7255 K.
  r_d from Aubourg et al. 2015 (arXiv:1411.1074) eq. 16 with
  omega_cb = Omega_m h^2 - 0.0107*sum_mnu (Aubourg's omega_nu, used only inside r_d).
  BBN prior omega_b ~ N(0.02218, 0.00055) (arXiv:2503.14738 eq. 14).
  Flat priors H0 U[20,100], omega_b U[0.005,0.1], Omega_m U[0.01,0.99].

Two background predictors, coded independently:
  * predict_astropy: astropy FlatLambdaCDM(m_nu=[0.06,0,0], Neff=3.044); Om0 is
    Omega_m minus ONLY the massive-nu share of astropy's Onu0 (astropy's Onu0 also
    carries the two massless species, which are radiation).
  * predict_manual / predict_manual_vec: photons from first principles
    (scipy.constants), massless-nu share of N_eff as radiation (2/3 of N_eff, as
    astropy splits N_eff evenly), 0.06 eV nu counted as pure matter inside Omega_m.
    Distances by 64-node Gauss-Legendre quadrature (vectorised over walkers).

Degrees of freedom (fixed before any chi2 was printed):
  BAO+BBN DR2: 13 + 1 - 3 = 11;  DR1: 12 + 1 - 3 = 10;
  G1 (Om, hr_d) DR2: 13 - 2 = 11;  G2 DR1: 12 - 2 = 10;
  N2 (EdS, H0 and omega_b free): 13 + 1 - 2 = 12;  N1 scrambled: 11.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import emcee
import numpy as np
from astropy.cosmology import FlatLambdaCDM
from scipy import constants as sc
from scipy.integrate import quad
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "bao_bbn_h0"
PREREG = RESULTS / "preregistration.json"
DATA = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
DR2_MEAN = DATA / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_mean.txt"
DR2_COV = DATA / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_cov.txt"
DR1_MEAN = DATA / "desi_2024_gaussian_bao_ALL_GCcomb_mean.txt"
DR1_COV = DATA / "desi_2024_gaussian_bao_ALL_GCcomb_cov.txt"

C_KM_S = sc.c / 1000.0
T_CMB = 2.7255
NEFF = 3.044
MNU = 0.06
OMEGA_NU_AUBOURG = 0.0107 * MNU
BBN_MEAN = 0.02218
BBN_SIGMA = 0.00055
PRIOR_H0 = (20.0, 100.0)
PRIOR_WB = (0.005, 0.1)
PRIOR_OM = (0.01, 0.99)
PRIOR_HRD = (10.0, 1000.0)
NU_PER_SPECIES = (7.0 / 8.0) * (4.0 / 11.0) ** (4.0 / 3.0)  # 0.2271073...

GL_X, GL_W = np.polynomial.legendre.leggauss(64)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class BAOData:
    name: str
    z: np.ndarray
    vals: np.ndarray
    kinds: list[str]
    cov: np.ndarray
    cov_inv: np.ndarray
    mean_path: Path
    cov_path: Path


def load_bao(mean_path: Path, cov_path: Path, name: str) -> BAOData:
    zs: list[float] = []
    vals: list[float] = []
    kinds: list[str] = []
    for line in mean_path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        z, v, k = s.split()
        if k not in ("DM_over_rs", "DH_over_rs", "DV_over_rs"):
            raise ValueError(f"unknown observable {k}")
        zs.append(float(z))
        vals.append(float(v))
        kinds.append(k)
    cov = np.loadtxt(cov_path)
    if cov.shape != (len(zs), len(zs)):
        raise ValueError(f"cov shape {cov.shape} vs {len(zs)} points")
    return BAOData(name, np.array(zs), np.array(vals), kinds, cov, np.linalg.inv(cov), mean_path, cov_path)


def load_dr2() -> BAOData:
    return load_bao(DR2_MEAN, DR2_COV, "DESI_DR2")


def load_dr1() -> BAOData:
    return load_bao(DR1_MEAN, DR1_COV, "DESI_DR1")


# ----------------------------------------------------------------- r_d -------
def rd_aubourg16(omega_cb: np.ndarray | float, omega_b: np.ndarray | float) -> np.ndarray:
    """Aubourg+2015 eq. 16 [Mpc], CAMB convention."""
    return 55.154 * np.exp(-72.3 * (OMEGA_NU_AUBOURG + 0.0006) ** 2) / (
        np.asarray(omega_cb) ** 0.25351 * np.asarray(omega_b) ** 0.12807
    )


def rd_aubourg16_neff(omega_cb: np.ndarray | float, omega_b: np.ndarray | float, neff: float) -> np.ndarray:
    """Eq. 16 rescaled with Aubourg eq. 17 N_eff slope 1/[1+(N_eff-3.046)/30.60] (S1 only)."""
    return rd_aubourg16(omega_cb, omega_b) / (1.0 + (neff - 3.046) / 30.60)


def rd_desi_eq2(omega_m_incl_nu: np.ndarray | float, omega_b: np.ndarray | float, neff: float) -> np.ndarray:
    """DESI DR2 eq. 2 power law [Mpc]; pivot 0.1432 is nu-inclusive (S2 only)."""
    return 147.05 * (np.asarray(omega_b) / 0.02236) ** -0.13 * (np.asarray(omega_m_incl_nu) / 0.1432) ** -0.23 * (neff / 3.04) ** -0.1


def omega_cb_of(h: np.ndarray | float, om: np.ndarray | float) -> np.ndarray:
    return np.asarray(om) * np.asarray(h) ** 2 - OMEGA_NU_AUBOURG


class RdCambTable:
    """Amendment-1 primary r_d: bicubic spline of ln r_drag(CAMB) in (ln omega_b, ln omega_cdm)
    at each h node, linear in h between nodes. Measured h dependence at fixed physical densities
    (results/bao_bbn_h0/fixround_diagnostics.json, vs the h=0.6 node): <= 1.8e-5 in the core region,
    maximum 2.1e-4 at the h=0.2 node in a far corner (omega_b 0.0093, omega_cdm 0.27), not at the
    22 refilled h=0.99 nodes. A single probe near Planck values gave ~3e-7 over h=0.5-0.9.
    Returns NaN outside the table (callers map that to zero posterior support)."""

    def __init__(self, path: Path) -> None:
        from scipy.interpolate import RectBivariateSpline

        z = np.load(path)
        self.lnwb = z["ln_omega_b"]
        self.lnwc = z["ln_omega_cdm"]
        self.h = z["h"]
        self.omega_nu = float(z["omega_nu_camb"])
        tab = z["rdrag"]
        if not np.all(np.isfinite(tab)):
            raise ValueError("CAMB table has non-finite nodes")
        self.splines = [RectBivariateSpline(self.lnwb, self.lnwc, np.log(tab[k]), kx=3, ky=3) for k in range(len(self.h))]

    def __call__(self, wb: np.ndarray | float, wc: np.ndarray | float, h: np.ndarray | float) -> np.ndarray:
        wb, wc, h = np.broadcast_arrays(np.atleast_1d(wb).astype(float), np.atleast_1d(wc).astype(float),
                                        np.atleast_1d(h).astype(float))
        out = np.full(wb.shape, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            x, y = np.log(wb), np.log(wc)
        ok = (x >= self.lnwb[0]) & (x <= self.lnwb[-1]) & (y >= self.lnwc[0]) & (y <= self.lnwc[-1]) \
            & (h >= self.h[0]) & (h <= self.h[-1])
        if not np.any(ok):
            return out
        hk = np.clip(np.searchsorted(self.h, h[ok]) - 1, 0, len(self.h) - 2)
        vals = np.array([s.ev(x[ok], y[ok]) for s in self.splines])  # (nh, n)
        idx = np.arange(int(ok.sum()))
        h0, h1 = self.h[hk], self.h[hk + 1]
        wgt = (h[ok] - h0) / (h1 - h0)
        out[ok] = np.exp((1 - wgt) * vals[hk, idx] + wgt * vals[hk + 1, idx])
        return out


RD_TABLE = RESULTS / "rd_camb_table.npz"
_RD_CAMB: RdCambTable | None = None


def rd_camb(h: np.ndarray, om: np.ndarray, wb: np.ndarray) -> np.ndarray:
    """Exact-CAMB r_drag [Mpc] for (h, Omega_m incl. nu, omega_b); omega_cdm = Om h^2 - omega_b - omega_nu(CAMB)."""
    global _RD_CAMB
    if _RD_CAMB is None:
        _RD_CAMB = RdCambTable(RD_TABLE)
    wc = np.asarray(om) * np.asarray(h) ** 2 - np.asarray(wb) - _RD_CAMB.omega_nu
    return _RD_CAMB(wb, wc, h)


# ----------------------------------------------------------- background ------
def omega_gamma_h2() -> float:
    """Photon density omega_gamma = Omega_gamma h^2 from first principles."""
    a_rad = 4.0 * sc.Stefan_Boltzmann / sc.c  # J m^-3 K^-4
    rho_gamma = a_rad * T_CMB**4 / sc.c**2  # kg m^-3
    mpc = sc.parsec * 1e6
    h100_si = 100.0 * 1000.0 / mpc  # s^-1
    rho_crit_h2 = 3.0 * h100_si**2 / (8.0 * np.pi * sc.G)
    return float(rho_gamma / rho_crit_h2)


OMEGA_GAMMA_H2 = omega_gamma_h2()


def omega_r_h2(neff: float = NEFF, radiation: bool = True) -> float:
    """Photons + massless share (2/3 of N_eff) of neutrinos."""
    if not radiation:
        return 0.0
    return OMEGA_GAMMA_H2 * (1.0 + NU_PER_SPECIES * neff * 2.0 / 3.0)


def _e_of_z(z: np.ndarray, om: np.ndarray, orad: np.ndarray) -> np.ndarray:
    zp = 1.0 + z
    return np.sqrt(om * zp**3 + orad * zp**4 + (1.0 - om - orad))


def distances_manual_vec(
    z: np.ndarray, h: np.ndarray, om: np.ndarray, neff: float = NEFF, radiation: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """D_M and D_H in Mpc, shapes (nw, nz). h, om shape (nw,)."""
    h = np.atleast_1d(h)[:, None, None]
    om = np.atleast_1d(om)[:, None, None]
    orad = omega_r_h2(neff, radiation) / h**2
    zz = z[None, :, None] * 0.5 * (GL_X[None, None, :] + 1.0)
    integ = np.sum(GL_W[None, None, :] / _e_of_z(zz, om, orad), axis=2) * 0.5 * z[None, :]
    dh0 = C_KM_S / (100.0 * h[:, :, 0])
    dm = dh0 * integ
    dh = dh0 / _e_of_z(z[None, :], om[:, :, 0], orad[:, :, 0])
    return dm, dh


def obs_from_distances(dm: np.ndarray, dh: np.ndarray, z: np.ndarray, kinds: list[str], rd: np.ndarray) -> np.ndarray:
    rd = np.atleast_1d(rd)[:, None]
    out = np.empty_like(dm)
    for j, k in enumerate(kinds):
        if k == "DM_over_rs":
            out[:, j] = dm[:, j]
        elif k == "DH_over_rs":
            out[:, j] = dh[:, j]
        else:
            out[:, j] = (z[j] * dm[:, j] ** 2 * dh[:, j]) ** (1.0 / 3.0)
    return out / rd


def predict_manual_vec(
    d: BAOData, h0: np.ndarray, wb: np.ndarray, om: np.ndarray,
    rd_fn: str = "aub16", neff: float = NEFF, radiation: bool = True,
) -> np.ndarray:
    h = np.atleast_1d(h0) / 100.0
    om = np.atleast_1d(om)
    wb = np.atleast_1d(wb)
    dm, dh = distances_manual_vec(d.z, h, om, neff, radiation)
    if rd_fn == "aub16":
        rd = rd_aubourg16(omega_cb_of(h, om), wb)
    elif rd_fn == "aub16_neff":
        rd = rd_aubourg16_neff(omega_cb_of(h, om), wb, neff)
    elif rd_fn == "desi_eq2":
        rd = rd_desi_eq2(om * h**2, wb, neff)
    elif rd_fn == "camb":
        if neff != NEFF:
            raise ValueError("CAMB table is built at N_eff=3.044 only")
        rd = rd_camb(h, om, wb)
    else:
        raise ValueError(rd_fn)
    return obs_from_distances(dm, dh, d.z, d.kinds, rd)


def predict_manual_quad(d: BAOData, h0: float, wb: float, om: float) -> np.ndarray:
    """Scalar, scipy.quad version of the manual predictor (for P4)."""
    h = h0 / 100.0
    orad = omega_r_h2() / h**2
    rd = float(rd_aubourg16(omega_cb_of(h, om), wb))
    out = []
    for z, k in zip(d.z, d.kinds):
        integ, _ = quad(lambda x: 1.0 / float(_e_of_z(np.array(x), np.array(om), np.array(orad))), 0.0, z,
                        epsabs=0, epsrel=1e-12)
        dm = C_KM_S / h0 * integ
        dh = C_KM_S / h0 / float(_e_of_z(np.array(z), np.array(om), np.array(orad)))
        if k == "DM_over_rs":
            v = dm
        elif k == "DH_over_rs":
            v = dh
        else:
            v = (z * dm**2 * dh) ** (1.0 / 3.0)
        out.append(v / rd)
    return np.array(out)


def astropy_cosmo(h0: float, om: float) -> tuple[FlatLambdaCDM, float]:
    """astropy cosmology with Om0 = Omega_m - (massive-nu share of Onu0)."""
    probe = FlatLambdaCDM(H0=h0, Om0=0.3, Tcmb0=T_CMB, Neff=NEFF, m_nu=[MNU, 0.0, 0.0])
    massless = 2.0 * probe.Ogamma0 * NU_PER_SPECIES * NEFF / 3.0
    onu_massive = float(probe.Onu0 - massless)
    cosmo = FlatLambdaCDM(H0=h0, Om0=om - onu_massive, Tcmb0=T_CMB, Neff=NEFF, m_nu=[MNU, 0.0, 0.0])
    return cosmo, onu_massive


def predict_astropy(d: BAOData, h0: float, wb: float, om: float) -> np.ndarray:
    cosmo, _ = astropy_cosmo(h0, om)
    rd = float(rd_aubourg16(omega_cb_of(h0 / 100.0, om), wb))
    dm = cosmo.comoving_transverse_distance(d.z).value
    dh = C_KM_S / cosmo.H(d.z).value
    return obs_from_distances(dm[None, :], dh[None, :], d.z, d.kinds, np.array([rd]))[0]


# ---------------------------------------------------------- likelihoods -------
def chi2_vec(d: BAOData, vals: np.ndarray, model: np.ndarray) -> np.ndarray:
    r = vals[None, :] - model
    return np.einsum("wi,ij,wj->w", r, d.cov_inv, r)


def make_logpost(
    d: BAOData, vals: np.ndarray | None = None, bbn: tuple[float, float] | None = (BBN_MEAN, BBN_SIGMA),
    rd_fn: str = "aub16", neff: float = NEFF, radiation: bool = True,
) -> Callable[[np.ndarray], np.ndarray]:
    """Vectorised log posterior over theta rows (H0, omega_b, Omega_m)."""
    v = d.vals if vals is None else vals

    def logpost(theta: np.ndarray) -> np.ndarray:
        theta = np.atleast_2d(theta)
        h0, wb, om = theta[:, 0], theta[:, 1], theta[:, 2]
        ok = (
            (h0 > PRIOR_H0[0]) & (h0 < PRIOR_H0[1]) & (wb > PRIOR_WB[0]) & (wb < PRIOR_WB[1])
            & (om > PRIOR_OM[0]) & (om < PRIOR_OM[1]) & (omega_cb_of(h0 / 100.0, om) > 0)
        )
        out = np.full(theta.shape[0], -np.inf)
        if not np.any(ok):
            return out
        m = predict_manual_vec(d, h0[ok], wb[ok], om[ok], rd_fn, neff, radiation)
        c2 = chi2_vec(d, v, m)
        if bbn is not None:
            c2 = c2 + ((wb[ok] - bbn[0]) / bbn[1]) ** 2
        # NaN only arises from the CAMB table's support (omega_cdm in [0.005, 1], h in [0.2, 1])
        out[ok] = np.where(np.isfinite(c2), -0.5 * c2, -np.inf)
        return out

    return logpost


def make_logpost_hrd(d: BAOData, h_rad: float = 0.6851) -> Callable[[np.ndarray], np.ndarray]:
    """BAO-only (Omega_m, h r_d) log posterior; radiation evaluated at fixed h_rad."""

    def logpost(theta: np.ndarray) -> np.ndarray:
        theta = np.atleast_2d(theta)
        om, hrd = theta[:, 0], theta[:, 1]
        ok = (om > PRIOR_OM[0]) & (om < PRIOR_OM[1]) & (hrd > PRIOR_HRD[0]) & (hrd < PRIOR_HRD[1])
        out = np.full(theta.shape[0], -np.inf)
        if not np.any(ok):
            return out
        n = int(ok.sum())
        dm, dh = distances_manual_vec(d.z, np.full(n, h_rad), om[ok])
        m = obs_from_distances(dm, dh, d.z, d.kinds, hrd[ok] / h_rad)
        out[ok] = -0.5 * chi2_vec(d, d.vals, m)
        return out

    return logpost


def fit_map(logpost: Callable[[np.ndarray], np.ndarray], x0: np.ndarray) -> tuple[np.ndarray, float]:
    """MAP by Nelder-Mead restarts; returns (theta, -2 ln L_max)."""
    f = lambda x: float(-2.0 * logpost(np.asarray(x))[0]) if np.isfinite(logpost(np.asarray(x))[0]) else 1e30
    best = minimize(f, x0, method="Nelder-Mead", options={"xatol": 1e-9, "fatol": 1e-10, "maxiter": 20000, "maxfev": 40000})
    for _ in range(3):
        nxt = minimize(f, best.x, method="Nelder-Mead", options={"xatol": 1e-10, "fatol": 1e-11, "maxiter": 20000, "maxfev": 40000})
        if nxt.fun >= best.fun - 1e-9:
            best = nxt if nxt.fun < best.fun else best
            break
        best = nxt
    return np.asarray(best.x), float(best.fun)


def laplace_cov(logpost: Callable[[np.ndarray], np.ndarray], x: np.ndarray, steps: np.ndarray) -> np.ndarray:
    """Fisher/Laplace covariance: inverse of the Hessian of -ln P at x (central differences)."""
    n = len(x)
    f = lambda y: float(-logpost(np.asarray(y))[0])
    hess = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            ei = np.zeros(n)
            ej = np.zeros(n)
            ei[i] = steps[i]
            ej[j] = steps[j]
            val = (f(x + ei + ej) - f(x + ei - ej) - f(x - ei + ej) + f(x - ei - ej)) / (4.0 * steps[i] * steps[j])
            hess[i, j] = hess[j, i] = val
    return np.linalg.inv(hess)


@dataclass
class ChainResult:
    mean: np.ndarray
    std: np.ndarray
    cov: np.ndarray
    tau: np.ndarray
    n_steps: int
    burn: int
    ess: float
    converged_50tau: bool
    samples: np.ndarray


def run_mcmc(
    logpost: Callable[[np.ndarray], np.ndarray], x0: np.ndarray, scale: np.ndarray, seed: int,
    nwalkers: int = 32, chunk: int = 2000, max_steps: int = 60000, min_ess: float = 2000.0,
    min_steps: int = 0,
) -> ChainResult:
    """emcee until N_steps > 50 tau (all params) and ESS >= min_ess, or max_steps cap."""
    rng = np.random.default_rng(seed)
    ndim = len(x0)
    p0 = x0[None, :] + scale[None, :] * rng.standard_normal((nwalkers, ndim))
    lp = logpost(p0)
    while not np.all(np.isfinite(lp)):
        bad = ~np.isfinite(lp)
        p0[bad] = x0[None, :] + scale[None, :] * rng.standard_normal((int(bad.sum()), ndim))
        lp = logpost(p0)
    sampler = emcee.EnsembleSampler(nwalkers, ndim, logpost, vectorize=True)
    sampler._random = np.random.mtrand.RandomState(seed)  # emcee 3.1.6 has no seed kwarg
    state = sampler.run_mcmc(p0, chunk, progress=False)
    converged = False
    tau = np.full(ndim, np.inf)
    while True:
        n = sampler.iteration
        tau = sampler.get_autocorr_time(tol=0)
        burn = int(np.ceil(5 * np.max(tau)))
        ess = nwalkers * (n - burn) / np.max(tau)
        if n > 50 * np.max(tau) and ess >= min_ess and n >= min_steps:
            converged = True
            break
        if n >= max_steps:
            break
        state = sampler.run_mcmc(state, chunk, progress=False)
    burn = int(np.ceil(5 * np.max(tau)))
    flat = sampler.get_chain(discard=burn, flat=True)
    ess = nwalkers * (sampler.iteration - burn) / float(np.max(tau))
    return ChainResult(flat.mean(axis=0), flat.std(axis=0, ddof=1), np.cov(flat.T), tau, sampler.iteration,
                       burn, float(ess), converged, flat)


def chain_summary(c: ChainResult, names: list[str]) -> dict[str, object]:
    return {
        "mean": {n: float(m) for n, m in zip(names, c.mean)},
        "std": {n: float(s) for n, s in zip(names, c.std)},
        "corr": np.corrcoef(c.samples.T).tolist() if c.samples.shape[1] > 1 else [[1.0]],
        "tau": {n: float(t) for n, t in zip(names, c.tau)},
        "n_steps": c.n_steps,
        "burn": c.burn,
        "ess": c.ess,
        "converged_50tau_and_ess": c.converged_50tau,
        "n_walkers": 32,
    }


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=float))

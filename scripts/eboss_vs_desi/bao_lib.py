"""Shared library for the eboss_vs_desi cross-survey BAO consistency test.

Everything here follows results/eboss_vs_desi/preregistration.json:
  * flat LCDM, E(z) = sqrt(Om (1+z)^3 + 1 - Om), parameters (Om, h*r_d),
  * flat priors Om in [0.05, 0.95], hrd in [60, 150] Mpc,
  * SDSS/eBOSS DR16 likelihood = MGS chi2 table + DR12 Gaussian + DR16 LRG
    Gaussian + ELG DV table + QSO Gaussian + Lya auto grid + Lya x QSO grid
    (baseline), or the Gaussian-summary variant,
  * DESI DR2 = 13-point Gaussian, block-diagonal covariance.
The two surveys are NEVER combined: a guard (substring + allow-list + sha256)
refuses any non-preregistered file in the SDSS likelihood.

Prediction codes:
  A. astropy FlatLambdaCDM(H0=100, Tcmb0=0)                      (independent)
  B. hand-coded scipy.integrate.quad                            (independent)
  B'. hand-coded vectorised Gauss-Legendre (speed path for MCMC; validated
      against A and B to < 1e-4 relative before use).
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from astropy.cosmology import FlatLambdaCDM
from scipy import stats
from scipy.integrate import quad
from scipy.interpolate import CubicSpline, RectBivariateSpline
from scipy.optimize import minimize

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "results" / "eboss_vs_desi"
PREREG = RESULTS / "preregistration.json"
DATA_DIR = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
C_KM_S = 299792.458
SEED = 20260927
OM_PRIOR = (0.05, 0.95)
HRD_PRIOR = (60.0, 150.0)
MGS_RS_RESCALE = 4.29720761315
MGS_BOUNDS = (0.8005, 1.1985)
INJECTED = np.array([0.2975, 101.54])

SDSS_FILES = {
    "mgs": "sdss_MGS_prob.txt",
    "dr12_mean": "sdss_DR12_LRG_BAO_DMDH.dat",
    "dr12_cov": "sdss_DR12_LRG_BAO_DMDH_covtot.txt",
    "lrg_mean": "sdss_DR16_LRG_BAO_DMDH.dat",
    "lrg_cov": "sdss_DR16_LRG_BAO_DMDH_covtot.txt",
    "elg": "sdss_DR16_ELG_BAO_DVtable.txt",
    "qso_mean": "sdss_DR16_QSO_BAO_DMDH.txt",
    "qso_cov": "sdss_DR16_QSO_BAO_DMDH_covtot.txt",
    "lya_auto": "sdss_DR16_LYAUTO_BAO_DMDHgrid.txt",
    "lya_cross": "sdss_DR16_LYxQSO_BAO_DMDHgrid.txt",
}
DESI_FILES = {
    "mean": "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_mean.txt",
    "cov": "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_cov.txt",
}


class CombinationError(RuntimeError):
    """Raised when a DESI-derived file is offered to the SDSS likelihood."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prereg() -> dict:
    return json.loads(PREREG.read_text())


def verify_hashes() -> dict[str, str]:
    """Assert every input file matches the preregistered sha256; return them."""
    expected = load_prereg()["datasets"]["sha256"]
    out: dict[str, str] = {}
    for name in list(SDSS_FILES.values()) + list(DESI_FILES.values()):
        got = sha256(DATA_DIR / name)
        if got != expected[name]:
            raise RuntimeError(f"sha256 mismatch for {name}: {got} != {expected[name]}")
        out[name] = got
    return out


def guard_not_desi(filename: str) -> None:
    """Combination guard: the SDSS likelihood may read only the preregistered SDSS files.

    Three checks, each of which raises CombinationError:
      1. filename substring 'desi' (cheap, catches the named DESI/DESI+eBOSS files);
      2. allow-list: the basename must be one of SDSS_FILES (a DESI-derived file
         under any other name is refused);
      3. content: the file's sha256 must equal the preregistered hash for that
         basename (a DESI file renamed to an SDSS filename is refused).
    (Fix round 2026-09-27: checks 2-3 added after the referee noted that the
    substring check alone would not refuse a DESI file under another name.)
    """
    path = DATA_DIR / filename
    base = path.name
    if "desi" in base.lower() or "desi_bao_dr2" in str(filename).lower():
        raise CombinationError(f"refusing to load DESI-derived file into SDSS likelihood: {filename}")
    if base not in set(SDSS_FILES.values()):
        raise CombinationError(f"refusing non-allow-listed file in SDSS likelihood: {filename}")
    expected = load_prereg()["datasets"]["sha256"][base]
    got = sha256(path)
    if got != expected:
        raise CombinationError(f"refusing {filename}: sha256 {got} != preregistered {expected}")


# ------------------------------------------------------------ predictions --
def e_of_z(z: np.ndarray | float, om: float) -> np.ndarray | float:
    return np.sqrt(om * (1.0 + z) ** 3 + (1.0 - om))


_GL_X, _GL_W = np.polynomial.legendre.leggauss(64)


def dm_h100_gl(zs: np.ndarray, om: float) -> np.ndarray:
    """D_M(z) [Mpc] at H0=100 via 64-point Gauss-Legendre on [0, z] (speed path)."""
    zs = np.asarray(zs, dtype=float)
    half = 0.5 * zs[:, None]
    zp = half * (_GL_X[None, :] + 1.0)
    integ = np.sum(_GL_W[None, :] / e_of_z(zp, om), axis=1) * half[:, 0]
    return (C_KM_S / 100.0) * integ


def dm_h100_quad(zs: np.ndarray, om: float) -> np.ndarray:
    return np.array([(C_KM_S / 100.0) * quad(lambda x: 1.0 / e_of_z(x, om), 0.0, float(z),
                                             epsabs=0, epsrel=1e-12)[0] for z in zs])


def dm_h100_astropy(zs: np.ndarray, om: float) -> np.ndarray:
    cosmo = FlatLambdaCDM(H0=100.0, Om0=om, Tcmb0=0.0)
    return np.asarray(cosmo.comoving_distance(np.asarray(zs)).value)


def hz_h100_astropy(zs: np.ndarray, om: float) -> np.ndarray:
    cosmo = FlatLambdaCDM(H0=100.0, Om0=om, Tcmb0=0.0)
    return np.asarray(cosmo.H(np.asarray(zs)).value)


def observables(zs: np.ndarray, kinds: list[str], om: float, hrd: float,
                code: str = "gl") -> np.ndarray:
    """Vector of BAO ratios DM/rd, DH/rd, DV/rd for the given kinds."""
    zs = np.asarray(zs, dtype=float)
    if code == "gl":
        dm = dm_h100_gl(zs, om)
        hz = 100.0 * e_of_z(zs, om)
    elif code == "quad":
        dm = dm_h100_quad(zs, om)
        hz = 100.0 * e_of_z(zs, om)
    elif code == "astropy":
        dm = dm_h100_astropy(zs, om)
        hz = hz_h100_astropy(zs, om)
    else:
        raise ValueError(code)
    dm_rd = dm / hrd
    dh_rd = C_KM_S / (hz * hrd)
    dv_rd = (zs * dm_rd ** 2 * dh_rd) ** (1.0 / 3.0)
    out = np.empty(len(zs))
    for i, k in enumerate(kinds):
        if k == "DM_over_rs":
            out[i] = dm_rd[i]
        elif k == "DH_over_rs":
            out[i] = dh_rd[i]
        elif k == "DV_over_rs":
            out[i] = dv_rd[i]
        else:
            raise ValueError(f"unknown kind {k}")
    return out


# ------------------------------------------------------------ data blocks --
@dataclass
class GaussBlock:
    name: str
    zs: np.ndarray
    kinds: list[str]
    vals: np.ndarray
    cov: np.ndarray
    icov: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        assert self.cov.shape == (len(self.vals), len(self.vals)), (self.name, self.cov.shape)
        assert np.allclose(self.cov, self.cov.T, rtol=1e-6, atol=1e-10), self.name
        assert np.all(np.linalg.eigvalsh(self.cov) > 0), self.name
        self.icov = np.linalg.inv(self.cov)

    def m2lnl(self, om: float, hrd: float) -> float:
        r = self.vals - observables(self.zs, self.kinds, om, hrd)
        return float(r @ self.icov @ r)


def read_mean_file(path: Path) -> tuple[np.ndarray, list[str], np.ndarray]:
    zs: list[float] = []
    vals: list[float] = []
    kinds: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        z, v, k = line.split()[:3]
        zs.append(float(z))
        vals.append(float(v))
        kinds.append(k)
    return np.array(zs), kinds, np.array(vals)


def load_gauss(name: str, mean_file: str, cov_file: str, sdss: bool) -> GaussBlock:
    if sdss:
        guard_not_desi(mean_file)
        guard_not_desi(cov_file)
    zs, kinds, vals = read_mean_file(DATA_DIR / mean_file)
    cov = np.loadtxt(DATA_DIR / cov_file)
    return GaussBlock(name, zs, kinds, vals, np.atleast_2d(cov))


@dataclass
class MGSTable:
    """SDSS DR7 MGS: chi2 table on alpha = (DV/rd)/rs_rescale, alpha in [0.8005, 1.1985]."""
    rescale: float = MGS_RS_RESCALE
    z: float = 0.15

    def __post_init__(self) -> None:
        guard_not_desi(SDSS_FILES["mgs"])
        self.chi2_tab = np.loadtxt(DATA_DIR / SDSS_FILES["mgs"])
        assert self.chi2_tab.shape == (399,)
        self.alpha = np.linspace(MGS_BOUNDS[0], MGS_BOUNDS[1], len(self.chi2_tab))
        self.spline = CubicSpline(self.alpha, self.chi2_tab)

    def m2lnl_of_dv(self, dv_rd: float) -> float:
        a = dv_rd / self.rescale
        if not (MGS_BOUNDS[0] <= a <= MGS_BOUNDS[1]):
            return np.inf
        return float(self.spline(a))

    def m2lnl(self, om: float, hrd: float) -> float:
        dv = observables(np.array([self.z]), ["DV_over_rs"], om, hrd)[0]
        return self.m2lnl_of_dv(dv)


@dataclass
class ELGTable:
    """eBOSS DR16 ELG: (DV/rd, likelihood) table at z=0.845; ln(L/Lmax) via cubic spline."""
    z: float = 0.845

    def __post_init__(self) -> None:
        guard_not_desi(SDSS_FILES["elg"])
        tab = np.loadtxt(DATA_DIR / SDSS_FILES["elg"])
        assert tab.shape == (399, 2)
        assert np.all(np.diff(tab[:, 0]) > 0) and np.all(tab[:, 1] > 0)
        self.x = tab[:, 0]
        self.m2 = -2.0 * np.log(tab[:, 1] / tab[:, 1].max())
        self.spline = CubicSpline(self.x, self.m2)
        self.bounds = (float(self.x[0]), float(self.x[-1]))

    def m2lnl_of_dv(self, dv_rd: float) -> float:
        if not (self.bounds[0] <= dv_rd <= self.bounds[1]):
            return np.inf
        return float(self.spline(dv_rd))

    def m2lnl(self, om: float, hrd: float) -> float:
        dv = observables(np.array([self.z]), ["DV_over_rs"], om, hrd)[0]
        return self.m2lnl_of_dv(dv)


@dataclass
class LyaGrid:
    """eBOSS DR16 Lya 2D (DM/rd, DH/rd, likelihood ratio) grid at z=2.334."""
    key: str
    z: float = 2.334

    def __post_init__(self) -> None:
        fname = SDSS_FILES[self.key]
        guard_not_desi(fname)
        tab = np.loadtxt(DATA_DIR / fname)
        self.dm = np.unique(tab[:, 0])
        self.dh = np.unique(tab[:, 1])
        assert len(self.dm) * len(self.dh) == tab.shape[0] == 2500
        # DM is the outer loop, DH the inner loop
        assert np.allclose(tab[:50, 0], self.dm[0]) and np.allclose(tab[:50, 1], self.dh)
        assert tab[:, 2].min() > 0
        self.lik = tab[:, 2].reshape(len(self.dm), len(self.dh))
        self.m2 = -2.0 * np.log(self.lik / self.lik.max())
        self.spline = RectBivariateSpline(self.dm, self.dh, self.m2, kx=3, ky=3)

    def m2lnl_of(self, dm_rd: float, dh_rd: float) -> float:
        if not (self.dm[0] <= dm_rd <= self.dm[-1] and self.dh[0] <= dh_rd <= self.dh[-1]):
            return np.inf
        return float(self.spline(dm_rd, dh_rd)[0, 0])

    def m2lnl(self, om: float, hrd: float) -> float:
        dm, dh = observables(np.array([self.z, self.z]), ["DM_over_rs", "DH_over_rs"], om, hrd)
        return self.m2lnl_of(dm, dh)


# ------------------------------------------------------------ likelihoods --
class Likelihood(ABC):
    name: str = "base"
    n_data: int = 0

    @abstractmethod
    def m2lnl(self, om: float, hrd: float) -> float:
        """-2 ln L at (Om, hrd); every concrete likelihood overrides this."""
        raise TypeError(f"{type(self).__name__} must override m2lnl")

    def m2lnpost(self, theta: np.ndarray) -> float:
        om, hrd = float(theta[0]), float(theta[1])
        if not (OM_PRIOR[0] < om < OM_PRIOR[1] and HRD_PRIOR[0] < hrd < HRD_PRIOR[1]):
            return np.inf
        return self.m2lnl(om, hrd)

    def lnpost(self, theta: np.ndarray) -> float:
        v = self.m2lnpost(theta)
        return -0.5 * v if np.isfinite(v) else -np.inf


class GaussianLikelihood(Likelihood):
    def __init__(self, name: str, blocks: list[GaussBlock]) -> None:
        self.name = name
        self.blocks = blocks
        self.zs = np.concatenate([b.zs for b in blocks])
        self.kinds = [k for b in blocks for k in b.kinds]
        self.vals = np.concatenate([b.vals for b in blocks])
        n = len(self.vals)
        self.cov = np.zeros((n, n))
        i = 0
        for b in blocks:
            m = len(b.vals)
            self.cov[i:i + m, i:i + m] = b.cov
            i += m
        self.icov = np.linalg.inv(self.cov)
        self.n_data = n

    def m2lnl(self, om: float, hrd: float) -> float:
        r = self.vals - observables(self.zs, self.kinds, om, hrd)
        return float(r @ self.icov @ r)

    def with_data(self, name: str, vals: np.ndarray, cov: np.ndarray | None = None) -> "GaussianLikelihood":
        new = GaussianLikelihood.__new__(GaussianLikelihood)
        new.name = name
        new.blocks = self.blocks
        new.zs = self.zs
        new.kinds = list(self.kinds)
        new.vals = np.asarray(vals, dtype=float)
        new.cov = self.cov if cov is None else cov
        new.icov = np.linalg.inv(new.cov)
        new.n_data = self.n_data
        return new


class SDSSGridLikelihood(Likelihood):
    """Baseline SDSS/eBOSS DR16 BAO likelihood (grid tables as distributed)."""

    def __init__(self) -> None:
        self.name = "SDSS_eBOSS_DR16_baseline"
        self.mgs = MGSTable()
        self.gauss = GaussianLikelihood("sdss_gauss_pieces", [
            load_gauss("DR12", SDSS_FILES["dr12_mean"], SDSS_FILES["dr12_cov"], True),
            load_gauss("DR16_LRG", SDSS_FILES["lrg_mean"], SDSS_FILES["lrg_cov"], True),
            load_gauss("DR16_QSO", SDSS_FILES["qso_mean"], SDSS_FILES["qso_cov"], True),
        ])
        self.elg = ELGTable()
        self.lya_auto = LyaGrid("lya_auto")
        self.lya_cross = LyaGrid("lya_cross")
        # effective data count: MGS 1 + DR12 4 + LRG 2 + ELG 1 + QSO 2 + Lya 2x2
        self.n_data = 1 + 4 + 2 + 1 + 2 + 2 + 2

    def components(self, om: float, hrd: float) -> dict[str, float]:
        return {
            "MGS": self.mgs.m2lnl(om, hrd),
            "gauss(DR12+LRG+QSO)": self.gauss.m2lnl(om, hrd),
            "ELG": self.elg.m2lnl(om, hrd),
            "Lya_auto": self.lya_auto.m2lnl(om, hrd),
            "Lya_cross": self.lya_cross.m2lnl(om, hrd),
        }

    def m2lnl(self, om: float, hrd: float) -> float:
        return float(sum(self.components(om, hrd).values()))


def sdss_gaussian_summary_blocks() -> list[GaussBlock]:
    """Gaussian-summary variant (prereg): MGS, ELG, joint Lya replaced by published Gaussians."""
    blocks = [
        GaussBlock("MGS_gauss", np.array([0.15]), ["DV_over_rs"], np.array([4.47]), np.array([[0.17 ** 2]])),
        load_gauss("DR12", SDSS_FILES["dr12_mean"], SDSS_FILES["dr12_cov"], True),
        load_gauss("DR16_LRG", SDSS_FILES["lrg_mean"], SDSS_FILES["lrg_cov"], True),
        GaussBlock("ELG_gauss", np.array([0.845]), ["DV_over_rs"], np.array([18.33]), np.array([[0.595 ** 2]])),
        load_gauss("DR16_QSO", SDSS_FILES["qso_mean"], SDSS_FILES["qso_cov"], True),
    ]
    s_dh, s_dm, rho = 0.195, 1.15, -0.45
    cov = np.array([[s_dh ** 2, rho * s_dh * s_dm], [rho * s_dh * s_dm, s_dm ** 2]])
    blocks.append(GaussBlock("Lya_joint_gauss", np.array([2.334, 2.334]), ["DH_over_rs", "DM_over_rs"],
                             np.array([8.99, 37.5]), cov))
    return blocks


def sdss_gaussian_likelihood() -> GaussianLikelihood:
    return GaussianLikelihood("SDSS_eBOSS_DR16_gaussian_summary", sdss_gaussian_summary_blocks())


def desi_likelihood() -> GaussianLikelihood:
    return GaussianLikelihood("DESI_DR2", [load_gauss("DESI_DR2", DESI_FILES["mean"], DESI_FILES["cov"], False)])


# ------------------------------------------------------------ fitting --
def fit_map(like: Likelihood, x0: np.ndarray = np.array([0.3, 100.0])) -> tuple[np.ndarray, float]:
    f: Callable[[np.ndarray], float] = lambda t: min(like.m2lnpost(t), 1e12)
    best = None
    for start in (x0, np.array([0.28, 102.0]), np.array([0.33, 98.0])):
        o = minimize(f, start, method="Nelder-Mead",
                     options={"xatol": 1e-7, "fatol": 1e-9, "maxiter": 20000})
        if best is None or o.fun < best.fun:
            best = o
    return np.asarray(best.x), float(best.fun)


def laplace_cov(like: Likelihood, x: np.ndarray) -> np.ndarray:
    """Covariance from the finite-difference Hessian of -2lnL at x: C = 2 H^{-1}."""
    h = np.array([2e-4, 2e-2])
    f = like.m2lnpost
    H = np.zeros((2, 2))
    f0 = f(x)
    for i in range(2):
        e = np.zeros(2); e[i] = h[i]
        H[i, i] = (f(x + e) - 2 * f0 + f(x - e)) / h[i] ** 2
    e0 = np.array([h[0], 0.0]); e1 = np.array([0.0, h[1]])
    H[0, 1] = H[1, 0] = (f(x + e0 + e1) - f(x + e0 - e1) - f(x - e0 + e1) + f(x - e0 - e1)) / (4 * h[0] * h[1])
    return 2.0 * np.linalg.inv(H)


def grid_posterior(like: Likelihood, center: np.ndarray, sig: np.ndarray, nsig: float = 7.0,
                   n: int = 301) -> dict:
    """Normalised posterior on a regular grid centred at `center` spanning +-nsig*sig."""
    oms = np.linspace(max(center[0] - nsig * sig[0], OM_PRIOR[0] + 1e-9),
                      min(center[0] + nsig * sig[0], OM_PRIOR[1] - 1e-9), n)
    hrds = np.linspace(max(center[1] - nsig * sig[1], HRD_PRIOR[0] + 1e-9),
                       min(center[1] + nsig * sig[1], HRD_PRIOR[1] - 1e-9), n)
    m2 = np.array([[like.m2lnpost(np.array([o, r])) for r in hrds] for o in oms])
    i, j = np.unravel_index(np.argmin(m2), m2.shape)
    p = np.exp(-0.5 * (m2 - m2.min()))
    p /= p.sum()
    O, R = np.meshgrid(oms, hrds, indexing="ij")
    mo, mr = float((p * O).sum()), float((p * R).sum())
    vo = float((p * (O - mo) ** 2).sum()); vr = float((p * (R - mr) ** 2).sum())
    cor = float((p * (O - mo) * (R - mr)).sum())
    edge_mass = float(p[0, :].sum() + p[-1, :].sum() + p[:, 0].sum() + p[:, -1].sum())
    return {"oms": oms, "hrds": hrds, "m2": m2, "p": p,
            "grid_min": np.array([oms[i], hrds[j]]), "grid_min_m2": float(m2.min()),
            "mean": np.array([mo, mr]), "cov": np.array([[vo, cor], [cor, vr]]),
            "edge_mass": edge_mass}


def run_emcee(like: Likelihood, x0: np.ndarray, sig: np.ndarray, nsteps: int = 6000,
              burn: int = 1000, nwalkers: int = 32, seed: int = SEED) -> dict:
    import emcee
    rng = np.random.default_rng(seed)
    p0 = x0 + 0.3 * sig * rng.standard_normal((nwalkers, 2))
    sampler = emcee.EnsembleSampler(nwalkers, 2, like.lnpost)
    sampler._random = np.random.mtrand.RandomState(seed)
    sampler.run_mcmc(p0, nsteps, progress=False)
    tau = sampler.get_autocorr_time(tol=0)
    chain = sampler.get_chain(discard=burn, flat=True)
    return {"chain": chain, "tau": tau, "nsteps": nsteps, "burn": burn, "nwalkers": nwalkers,
            "converged": bool(np.all(50 * tau < nsteps)),
            "acceptance": float(np.mean(sampler.acceptance_fraction)),
            "mean": chain.mean(axis=0), "cov": np.cov(chain.T)}


# ------------------------------------------------------------ tension --
def tension(p1: np.ndarray, c1: np.ndarray, p2: np.ndarray, c2: np.ndarray) -> dict:
    """DESI eq.(18)-type statistic chi2 = dp^T (C1+C2)^-1 dp, 2 dof -> PTE -> two-sided N_sigma."""
    dp = np.asarray(p1) - np.asarray(p2)
    C = np.asarray(c1) + np.asarray(c2)
    chi2 = float(dp @ np.linalg.solve(C, dp))
    pte = float(stats.chi2.sf(chi2, df=len(dp)))
    nsig = float(stats.norm.isf(pte / 2.0))
    one_d = [float(abs(dp[k]) / np.sqrt(C[k, k])) for k in range(len(dp))]
    return {"chi2": chi2, "dof": len(dp), "PTE": pte, "N_sigma": nsig,
            "one_d_sigma": {"Om": one_d[0], "hrd": one_d[1]}}

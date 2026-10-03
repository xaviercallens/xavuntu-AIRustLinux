#!/usr/bin/env python3
"""Preregistered emcee posterior runs for desi_dr2_bao.

Runs: DR2 LCDM, DR2 wCDM, DR1 LCDM, DR1 wCDM (instrument check), and the
radiation sensitivity variant for DR2 LCDM / wCDM. Flat priors (DESI):
Om U[0.01,0.99], h_rd U[10,1000], w U[-3,1]. 32 walkers, seed 20260927,
tau-based convergence rule from the preregistration.

Writes results/desi_dr2_bao/chains/<run>.npz and results/desi_dr2_bao/mcmc_summary.json.
    /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python -B scripts/desi_dr2_bao/mcmc_fit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

import emcee
import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dr2_model as m  # noqa: E402

SEED = 20260927
N_WALKERS = 32
BLOCK = 20000
MAX_STEPS = 200000


def make_log_prob(ds: m.Dataset, model: str, orad: float) -> Callable[[np.ndarray], np.ndarray]:
    def log_prob(theta: np.ndarray) -> np.ndarray:
        theta = np.atleast_2d(theta)
        om = theta[:, 0]
        if model == "lcdm":
            w = np.full_like(om, -1.0)
            hrd = theta[:, 1]
        else:
            w, hrd = theta[:, 1], theta[:, 2]
        ok = ((om > m.PRIOR_OM[0]) & (om < m.PRIOR_OM[1]) & (hrd > m.PRIOR_HRD[0]) & (hrd < m.PRIOR_HRD[1])
              & (w >= m.PRIOR_W[0]) & (w <= m.PRIOR_W[1]))
        lp = np.full(om.shape, -np.inf)
        if np.any(ok):
            pred = m.predict_gl(ds, om[ok], hrd[ok], w[ok], orad)
            pred = np.atleast_2d(pred)
            lp[ok] = -0.5 * m.chi2_vals(ds, pred)
        return lp
    return log_prob


def initial_ball(model: str, rng: np.random.Generator) -> np.ndarray:
    if model == "lcdm":
        c, s = np.array([0.30, 101.0]), np.array([0.01, 1.0])
    else:
        c, s = np.array([0.30, -1.0, 101.0]), np.array([0.01, 0.05, 1.0])
    return c + s * rng.standard_normal((N_WALKERS, len(c)))


def build_sampler(ds: m.Dataset, model: str, orad: float) -> tuple[emcee.EnsembleSampler, np.ndarray]:
    rng = np.random.default_rng(SEED)
    p0 = initial_ball(model, rng)
    ndim = p0.shape[1]
    sampler = emcee.EnsembleSampler(N_WALKERS, ndim, make_log_prob(ds, model, orad), vectorize=True)
    sampler.random_state = np.random.RandomState(SEED).get_state()
    return sampler, p0


def reproducibility_check(ds: m.Dataset) -> dict[str, object]:
    chains = []
    for _ in range(2):
        s, p0 = build_sampler(ds, "wcdm", 0.0)
        s.run_mcmc(p0, 300, progress=False)
        chains.append(s.get_chain())
    return {"steps": 300, "identical": bool(np.array_equal(chains[0], chains[1]))}


def run(ds: m.Dataset, model: str, orad: float, name: str) -> dict[str, object]:
    sampler, p0 = build_sampler(ds, model, orad)
    sampler.run_mcmc(p0, BLOCK, progress=False)
    status = "UNCONVERGED"
    while True:
        n = sampler.iteration
        tau = sampler.get_autocorr_time(tol=0)
        tmax = float(np.max(tau))
        burn = int(np.ceil(5 * tmax))
        thin = max(1, int(np.max(tau) / 2))
        ess = N_WALKERS * (n - burn) / tmax
        if n >= 50 * tmax and ess >= 10000:
            status = "CONVERGED"
            break
        if n >= MAX_STEPS:
            break
        sampler.run_mcmc(None, BLOCK, progress=False)
    flat = sampler.get_chain(discard=burn, thin=thin, flat=True)
    names = ["Om", "h_rd"] if model == "lcdm" else ["Om", "w", "h_rd"]
    mean, std = flat.mean(axis=0), flat.std(axis=0, ddof=1)
    pct = np.percentile(flat, [2.5, 16, 50, 84, 97.5], axis=0)
    corr = np.corrcoef(flat.T)
    ch_dir = m.RESULTS / "chains"
    ch_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(ch_dir / f"{name}.npz", samples=flat, names=np.array(names), tau=tau)
    lp_max_idx = np.argmax(sampler.get_log_prob(flat=True))
    return {
        "run": name, "dataset": ds.label, "model": model, "Omega_r": orad, "status": status,
        "n_steps": int(n), "tau": {k: float(t) for k, t in zip(names, tau)}, "burn": burn, "thin": thin,
        "n_steps_over_50tau": float(n / (50 * tmax)), "ess": float(ess), "n_samples_kept": int(flat.shape[0]),
        "acceptance_mean": float(np.mean(sampler.acceptance_fraction)),
        "mean": {k: float(v) for k, v in zip(names, mean)},
        "std": {k: float(v) for k, v in zip(names, std)},
        "percentiles_2.5_16_50_84_97.5": {k: [float(x) for x in pct[:, i]] for i, k in enumerate(names)},
        "corr": {f"{names[i]}__{names[j]}": float(corr[i, j]) for i in range(len(names))
                 for j in range(i + 1, len(names))},
        "max_logprob_sample_chi2": float(-2 * sampler.get_log_prob(flat=True)[lp_max_idx]),
        "chain_file": str((ch_dir / f"{name}.npz").relative_to(m.REPO)),
    }


def main() -> int:
    prov = m.check_provenance()
    assert prov["preregistration_sha256_matches"] and prov["all_data_sha256_match"], prov
    dr1, dr2 = m.load_dr1(), m.load_dr2()
    orad = m.omega_rad_from_astropy()
    out: dict[str, object] = {"generated_at": m.utc_now(), "provenance": prov, "emcee_version": emcee.__version__,
                              "seed": SEED, "n_walkers": N_WALKERS, "integrator": f"Gauss-Legendre order {m.GL_ORDER}",
                              "reproducibility": reproducibility_check(dr2), "runs": {}}
    print("reproducibility:", out["reproducibility"])
    plan = [(dr2, "lcdm", 0.0, "DR2_LCDM"), (dr2, "wcdm", 0.0, "DR2_wCDM"),
            (dr1, "lcdm", 0.0, "DR1_LCDM"), (dr1, "wcdm", 0.0, "DR1_wCDM"),
            (dr2, "lcdm", orad, "DR2_LCDM_radiation"), (dr2, "wcdm", orad, "DR2_wCDM_radiation")]
    for ds, model, o, name in plan:
        r = run(ds, model, o, name)
        out["runs"][name] = r  # type: ignore[index]
        print(name, r["status"], "n", r["n_steps"], "tau", r["tau"], "ess", round(r["ess"]),
              "mean", r["mean"], "std", r["std"], "corr", r["corr"])
    path = m.RESULTS / "mcmc_summary.json"
    path.write_text(json.dumps(out, indent=1))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

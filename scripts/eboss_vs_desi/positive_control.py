"""Positive control (preregistered): injected-parameter recovery on synthetic Gaussian data.

Injected (Om, hrd) = (0.2975, 101.54). For the SDSS Gaussian-summary variant and
for DESI DR2, the data vector is the model prediction plus noise drawn from the
real covariance (numpy default_rng seed 20260927). N = 200 realizations, each
fit by MAP + Laplace (finite-difference Hessian) errors; emcee on 20 of them.
Pass thresholds are the preregistered ones. Writes
results/eboss_vs_desi/positive_control.json.
"""

from __future__ import annotations

import json
import sys

import numpy as np
from scipy import stats

import bao_lib as L

N_REAL = 200
N_EMCEE = 20


def recover(like: L.GaussianLikelihood, synthetic_vals: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    lk = like.with_data(like.name + "_synthetic", synthetic_vals)
    x, f = L.fit_map(lk, x0=L.INJECTED.copy())
    return x, L.laplace_cov(lk, x), f


def main() -> int:
    L.verify_hashes()
    rng = np.random.default_rng(L.SEED)
    likes = {"SDSS_gaussian_summary": L.sdss_gaussian_likelihood(), "DESI_DR2": L.desi_likelihood()}
    res: dict = {"injected": L.INJECTED.tolist(), "seed": L.SEED, "n_realizations": N_REAL}
    per: dict[str, dict] = {}
    for name, like in likes.items():
        truth = L.observables(like.zs, like.kinds, *L.INJECTED)
        # noiseless recovery
        x0, _, f0 = recover(like, truth)
        noiseless_rel = np.abs(x0 / L.INJECTED - 1)
        chol = np.linalg.cholesky(like.cov)
        fits, sigs, covs, chi2s = [], [], [], []
        for _ in range(N_REAL):
            synthetic_vals = truth + chol @ rng.standard_normal(len(truth))
            x, c, f = recover(like, synthetic_vals)
            fits.append(x); covs.append(c); sigs.append(np.sqrt(np.diag(c))); chi2s.append(f)
        fits = np.array(fits); sigs = np.array(sigs); covs = np.array(covs)
        inside = np.abs(fits - L.INJECTED) < sigs
        cover = inside.mean(axis=0)
        bias = np.abs((fits - L.INJECTED).mean(axis=0)) / np.median(sigs, axis=0)
        dof = like.n_data - 2
        per[name] = {"fits": fits, "covs": covs}
        res[name] = {
            "noiseless_fit": x0.tolist(), "noiseless_rel_err": noiseless_rel.tolist(),
            "noiseless_chi2": f0, "noiseless_pass": bool(np.all(noiseless_rel < 1e-3)),
            "coverage_1sigma": {"Om": float(cover[0]), "hrd": float(cover[1])},
            "coverage_pass": bool(np.all((cover >= 0.60) & (cover <= 0.76))),
            "bias_over_median_sigma": {"Om": float(bias[0]), "hrd": float(bias[1])},
            "bias_pass": bool(np.all(bias < 0.2)),
            "median_sigma": {"Om": float(np.median(sigs[:, 0])), "hrd": float(np.median(sigs[:, 1]))},
            "mean_chi2_min": float(np.mean(chi2s)), "expected_chi2_min": dof,
            "chi2_min_KS_vs_chi2dof_p": float(stats.kstest(chi2s, "chi2", args=(dof,)).pvalue),
        }
        print(name, json.dumps(res[name], indent=1)); sys.stdout.flush()

    # tension calibration: SDSS-like vs DESI-like realizations of the same truth
    ts = [L.tension(per["SDSS_gaussian_summary"]["fits"][i], per["SDSS_gaussian_summary"]["covs"][i],
                    per["DESI_DR2"]["fits"][i], per["DESI_DR2"]["covs"][i]) for i in range(N_REAL)]
    nsig = np.array([t["N_sigma"] for t in ts]); pte = np.array([t["PTE"] for t in ts])
    ks_p = float(stats.kstest(pte, "uniform").pvalue)
    res["tension_calibration"] = {"median_N_sigma": float(np.median(nsig)), "KS_PTE_uniform_p": ks_p,
                                  "frac_N_sigma_gt_2": float(np.mean(nsig > 2)),
                                  "pass": bool(np.median(nsig) < 1.0 and ks_p > 0.01)}
    print("tension calibration", res["tension_calibration"]); sys.stdout.flush()

    # emcee on a subset: re-draw N_EMCEE realizations with a separate stream
    rng2 = np.random.default_rng(L.SEED + 1)
    em: dict = {}
    for name, like in likes.items():
        truth = L.observables(like.zs, like.kinds, *L.INJECTED)
        chol = np.linalg.cholesky(like.cov)
        inside, conv, dmean = [], [], []
        for k in range(N_EMCEE):
            lk = like.with_data(name + "_synthetic", truth + chol @ rng2.standard_normal(len(truth)))
            x, _ = L.fit_map(lk, x0=L.INJECTED.copy())
            c = L.laplace_cov(lk, x)
            r = L.run_emcee(lk, x, np.sqrt(np.diag(c)), nsteps=3000, burn=500, seed=L.SEED + k)
            s = np.sqrt(np.diag(r["cov"]))
            inside.append(np.abs(r["mean"] - L.INJECTED) < s)
            conv.append(r["converged"])
            dmean.append((r["mean"] - x) / s)
        inside = np.array(inside); dmean = np.array(dmean)
        em[name] = {"n": N_EMCEE, "coverage_1sigma": inside.mean(axis=0).tolist(),
                    "all_converged": bool(all(conv)),
                    "mean_minus_MAP_over_sigma_median": np.median(dmean, axis=0).tolist()}
        print("emcee", name, em[name]); sys.stdout.flush()
    res["emcee_subset"] = em
    res["positive_control_passed"] = bool(
        all(res[n]["noiseless_pass"] and res[n]["coverage_pass"] and res[n]["bias_pass"] for n in likes)
        and res["tension_calibration"]["pass"])
    (L.RESULTS / "positive_control.json").write_text(json.dumps(res, indent=1))
    print("POSITIVE CONTROL PASSED:", res["positive_control_passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

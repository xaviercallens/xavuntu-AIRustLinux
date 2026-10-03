#!/usr/bin/env python3
"""Second, independent posterior method for desi_dr2_bao: brute-force grid marginalization.

Same likelihood (dr2_model.predict_gl + real covariance) and the same flat priors
as mcmc_fit.py, but no sampler: the posterior is evaluated on a regular grid,
normalized, and the moments (mean, std, correlation) are sums over the grid.
Grid ranges are +-N Fisher sigma around the real-data chi^2 minimum (Fisher at
the minimum, not at any published value); the probability mass in the outermost
grid cells is reported so a truncated box is visible.

Also reports: chi^2 minimum (Nelder-Mead) and Fisher covariance at the minimum.

Writes results/desi_dr2_bao/grid_summary.json.
    /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python -B scripts/desi_dr2_bao/grid_posterior.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dr2_model as m  # noqa: E402

CHUNK = 20000


def loglike_points(ds: m.Dataset, om: np.ndarray, hrd: np.ndarray, w: np.ndarray, orad: float) -> np.ndarray:
    out = np.empty(om.shape[0])
    for s in range(0, om.shape[0], CHUNK):
        e = slice(s, s + CHUNK)
        pred = np.atleast_2d(m.predict_gl(ds, om[e], hrd[e], w[e], orad))
        out[e] = -0.5 * m.chi2_vals(ds, pred)
    return out


def moments(axes: list[np.ndarray], logp: np.ndarray, names: list[str]) -> dict[str, object]:
    p = np.exp(logp - logp.max())
    p /= p.sum()
    mesh = np.meshgrid(*axes, indexing="ij")
    mean = [float(np.sum(p * g)) for g in mesh]
    cov = np.empty((len(axes), len(axes)))
    for i in range(len(axes)):
        for j in range(len(axes)):
            cov[i, j] = float(np.sum(p * (mesh[i] - mean[i]) * (mesh[j] - mean[j])))
    std = np.sqrt(np.diag(cov))
    edge = {}
    for k, name in enumerate(names):
        marg = p.sum(axis=tuple(a for a in range(len(axes)) if a != k))
        edge[name] = {"mass_first_cell": float(marg[0]), "mass_last_cell": float(marg[-1])}
    corr = {f"{names[i]}__{names[j]}": float(cov[i, j] / (std[i] * std[j]))
            for i in range(len(names)) for j in range(i + 1, len(names))}
    return {"mean": dict(zip(names, mean)), "std": dict(zip(names, [float(s) for s in std])), "corr": corr,
            "edge_marginal_mass": edge,
            "axes": {n: [float(a[0]), float(a[-1]), int(a.size)] for n, a in zip(names, axes)}}


def grid_run(ds: m.Dataset, model: str, n: int, nsig: float, orad: float = 0.0) -> dict[str, object]:
    bf = m.fit_chi2_min(ds, model, orad=orad)
    x = np.array(bf["x"])
    fcov = m.fisher_cov(ds, model, x, orad=orad)
    fsig = np.sqrt(np.diag(fcov))
    names = ["Om", "h_rd"] if model == "lcdm" else ["Om", "w", "h_rd"]
    axes = []
    for k, name in enumerate(names):
        lo, hi = x[k] - nsig * fsig[k], x[k] + nsig * fsig[k]
        if name == "Om":
            lo, hi = max(lo, m.PRIOR_OM[0] + 1e-9), min(hi, m.PRIOR_OM[1] - 1e-9)
        elif name == "w":
            lo, hi = max(lo, m.PRIOR_W[0]), min(hi, m.PRIOR_W[1])
        axes.append(np.linspace(lo, hi, n))
    mesh = [g.ravel() for g in np.meshgrid(*axes, indexing="ij")]
    if model == "lcdm":
        om, hrd, w = mesh[0], mesh[1], np.full(mesh[0].shape, -1.0)
    else:
        om, w, hrd = mesh
    logp = loglike_points(ds, om, hrd, w, orad).reshape([n] * len(names))
    res = moments(axes, logp, names)
    res["grid_chi2_min"] = float(-2 * logp.max())
    res["chi2_min_nelder_mead"] = bf
    res["fisher_at_min"] = {"sigma": dict(zip(names, [float(s) for s in fsig])),
                            "corr": {f"{names[i]}__{names[j]}": float(fcov[i, j] / (fsig[i] * fsig[j]))
                                     for i in range(len(names)) for j in range(i + 1, len(names))}}
    res["n_per_axis"], res["half_width_fisher_sigma"] = n, nsig
    return res


def main() -> int:
    prov = m.check_provenance()
    assert prov["preregistration_sha256_matches"] and prov["all_data_sha256_match"], prov
    dr1, dr2 = m.load_dr1(), m.load_dr2()
    out: dict[str, object] = {"generated_at": m.utc_now(), "provenance": prov,
                              "method": "flat-prior posterior on a regular grid (independent of emcee)", "runs": {}}
    plan = [("DR2_LCDM", dr2, "lcdm", 601, 10.0), ("DR1_LCDM", dr1, "lcdm", 601, 10.0),
            ("DR2_wCDM", dr2, "wcdm", 141, 10.0), ("DR1_wCDM", dr1, "wcdm", 141, 10.0)]
    for name, ds, model, n, nsig in plan:
        r = grid_run(ds, model, n, nsig)
        out["runs"][name] = r  # type: ignore[index]
        print(name, "mean", r["mean"], "std", r["std"], "corr", r["corr"], "edge", r["edge_marginal_mass"],
              "chi2min", r["chi2_min_nelder_mead"]["chi2"], "fisher", r["fisher_at_min"], flush=True)
    path = m.RESULTS / "grid_summary.json"
    path.write_text(json.dumps(out, indent=1))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

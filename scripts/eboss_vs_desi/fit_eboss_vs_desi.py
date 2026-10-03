"""Real fit: flat LCDM (Om, hrd) to SDSS/eBOSS DR16 BAO and, SEPARATELY, to DESI DR2 BAO.

Never combined. Per dataset:
  method 1: emcee (32 walkers, 6000 steps, burn 1000, 50*tau < chain length)
  method 2: normalised 2D grid posterior (301x301, +-7 Laplace sigma around MAP)
  plus MAP (Nelder-Mead) + Laplace (finite-difference Hessian) errors.
Tension: DESI eq.(18) chi2 = dp^T (C_S + C_D)^-1 dp, 2 dof -> PTE -> N_sigma,
using posterior mean/cov (DESI convention); cross-checks with grid moments,
MAP+Laplace, and a posterior parameter-shift (KDE) statistic.
Pulls vs preregistered targets, within_tolerance by the preregistered rule.
Writes results/eboss_vs_desi/fit.json and results/eboss_vs_desi/eboss_vs_desi_contours.pdf.
Requires instrument_check.json, positive_control.json, negative_controls.json to exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

UTC = timezone.utc

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

import bao_lib as L  # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


def analyse(like: L.Likelihood) -> dict:
    x, f = L.fit_map(like)
    c_lap = L.laplace_cov(like, x)
    s_lap = np.sqrt(np.diag(c_lap))
    g = L.grid_posterior(like, x, s_lap, nsig=7.0, n=301)
    nsteps = 6000
    em = L.run_emcee(like, x, s_lap, nsteps=nsteps, burn=1000)
    while not em["converged"] and nsteps < 48000:
        nsteps *= 2
        em = L.run_emcee(like, x, s_lap, nsteps=nsteps, burn=1000)
    s_em = np.sqrt(np.diag(em["cov"])); s_g = np.sqrt(np.diag(g["cov"]))
    grid_vs_map = np.abs(g["grid_min"] - x) / s_lap
    out = {
        "name": like.name,
        "MAP": {"Om": float(x[0]), "hrd": float(x[1]), "m2lnL_min": f, "n_data": like.n_data,
                "dof": like.n_data - 2},
        "laplace": {"sigma_Om": float(s_lap[0]), "sigma_hrd": float(s_lap[1]),
                    "corr": float(c_lap[0, 1] / (s_lap[0] * s_lap[1]))},
        "emcee": {"mean_Om": float(em["mean"][0]), "std_Om": float(s_em[0]),
                  "mean_hrd": float(em["mean"][1]), "std_hrd": float(s_em[1]),
                  "corr": float(em["cov"][0, 1] / (s_em[0] * s_em[1])),
                  "tau": em["tau"].tolist(), "nsteps": em["nsteps"], "burn": em["burn"],
                  "nwalkers": em["nwalkers"], "converged_50tau": em["converged"],
                  "acceptance": em["acceptance"],
                  "q16_50_84_Om": np.percentile(em["chain"][:, 0], [16, 50, 84]).tolist(),
                  "q16_50_84_hrd": np.percentile(em["chain"][:, 1], [16, 50, 84]).tolist()},
        "grid": {"mean_Om": float(g["mean"][0]), "std_Om": float(s_g[0]),
                 "mean_hrd": float(g["mean"][1]), "std_hrd": float(s_g[1]),
                 "corr": float(g["cov"][0, 1] / (s_g[0] * s_g[1])),
                 "grid_min_Om": float(g["grid_min"][0]), "grid_min_hrd": float(g["grid_min"][1]),
                 "grid_min_minus_MAP_in_laplace_sigma": grid_vs_map.tolist(),
                 "grid_vs_MAP_within_0.1sigma": bool(np.all(grid_vs_map < 0.1)),
                 "edge_probability_mass": g["edge_mass"], "n": 301},
        "emcee_vs_grid_mean_diff_in_sigma": (np.abs(em["mean"] - g["mean"]) / s_g).tolist(),
    }
    if isinstance(like, L.SDSSGridLikelihood):
        out["MAP"]["components_m2lnL"] = like.components(float(x[0]), float(x[1]))
    return {"summary": out, "chain": em["chain"], "grid": g, "mean": em["mean"], "cov": em["cov"],
            "gmean": g["mean"], "gcov": g["cov"], "map": x, "lcov": c_lap}


def parameter_shift(ch1: np.ndarray, ch2: np.ndarray, n: int = 20000, seed: int = L.SEED) -> dict:
    """Posterior parameter-shift: PTE = P(density(dp) < density(0)) under the KDE of dp samples."""
    rng = np.random.default_rng(seed)
    a = ch1[rng.integers(0, len(ch1), n)]; b = ch2[rng.integers(0, len(ch2), n)]
    d = a - b
    # whiten for a well-conditioned KDE
    mu = d.mean(axis=0); C = np.cov(d.T); W = np.linalg.cholesky(np.linalg.inv(C))
    dw = (d - mu) @ W; zero_w = (-mu) @ W
    kde = stats.gaussian_kde(dw.T)
    dens = kde(dw.T); d0 = kde(zero_w[:, None])[0]
    pte = float(np.mean(dens < d0))
    return {"n_samples": n, "PTE": pte, "N_sigma": float(stats.norm.isf(pte / 2)) if pte > 0 else float("inf"),
            "mean_shift": mu.tolist()}


def main() -> int:
    L.verify_hashes()
    ic = json.loads((L.RESULTS / "instrument_check.json").read_text())
    pc = json.loads((L.RESULTS / "positive_control.json").read_text())
    nc = json.loads((L.RESULTS / "negative_controls.json").read_text())
    if not (all(ic["summary"].values()) and pc["positive_control_passed"] and nc["all_negative_controls_rejected"]):
        print("BLOCKED: a control did not pass; refusing to report real-fit numbers")
        return 2
    prereg = L.load_prereg()
    sdss = L.SDSSGridLikelihood(); sg = L.sdss_gaussian_likelihood(); desi = L.desi_likelihood()
    A: dict[str, dict] = {}
    for like in (sdss, sg, desi):
        A[like.name] = analyse(like)
        print(json.dumps(A[like.name]["summary"], indent=1)); sys.stdout.flush()
    S, G, D = A[sdss.name], A[sg.name], A[desi.name]

    tens = {
        "primary_emcee_moments": L.tension(S["mean"], S["cov"], D["mean"], D["cov"]),
        "grid_moments": L.tension(S["gmean"], S["gcov"], D["gmean"], D["gcov"]),
        "MAP_laplace": L.tension(S["map"], S["lcov"], D["map"], D["lcov"]),
        "gaussian_summary_variant_emcee": L.tension(G["mean"], G["cov"], D["mean"], D["cov"]),
        "posterior_parameter_shift_KDE": parameter_shift(S["chain"], D["chain"]),
        "assumption": "surveys treated as independent; positive cross-survey correlation (e.g. ~0.57 LRG2 vs eBOSS LRG) "
                      "would increase the statistic, so N_sigma is a lower bound w.r.t. overlap",
    }
    tens["pass_N_sigma_lt_2"] = bool(tens["primary_emcee_moments"]["N_sigma"] < 2.0)

    sg_shift = (G["mean"] - S["mean"]) / np.sqrt(np.diag(S["cov"]))
    fitvals = {"SDSS_Om": (S["mean"][0], np.sqrt(S["cov"][0, 0])),
               "SDSS_hrd_Mpc": (S["mean"][1], np.sqrt(S["cov"][1, 1])),
               "DESI_DR2_Om": (D["mean"][0], np.sqrt(D["cov"][0, 0])),
               "DESI_DR2_hrd_Mpc": (D["mean"][1], np.sqrt(D["cov"][1, 1]))}
    tol = prereg["tolerance_sigma"]
    pulls = []
    for t in prereg["targets"]:
        v, s = fitvals[t["name"]]
        pull = (v - t["value"]) / t["sigma"]
        pulls.append({"name": t["name"], "target": t["value"], "target_sigma": t["sigma"],
                      "value": float(v), "sigma": float(s), "pull_sigma": float(pull),
                      "within_0.5sigma": bool(abs(pull) < tol), "status": t["status"],
                      "counts_toward_within_tolerance": t["status"] == "verified primary"})
    within = all(p["within_0.5sigma"] for p in pulls if p["counts_toward_within_tolerance"])

    # chains: small -> results/, > 5 MB -> disk 2 with pointer + sha256
    chains: dict[str, dict] = {}
    for key, R in (("sdss_baseline", S), ("sdss_gaussian_summary", G), ("desi_dr2", D)):
        path = L.RESULTS / f"chain_{key}.npz"
        np.savez_compressed(path, chain=R["chain"])
        if path.stat().st_size > 5 * 1024 * 1024:
            big = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/cosmo3/eboss_vs_desi")
            big.mkdir(parents=True, exist_ok=True)
            dest = big / path.name
            path.replace(dest)
            path = dest
        chains[key] = {"path": str(path), "sha256": L.sha256(path), "bytes": path.stat().st_size,
                       "shape": list(R["chain"].shape)}
    camb_path = L.RESULTS / "camb_crosscheck.json"
    camb_x = json.loads(camb_path.read_text()) if camb_path.exists() else None
    camb_summary = ({"all_pass": camb_x["all_pass"], "sha256_of_json": L.sha256(camb_path),
                     "max_rel_diff_by_point": {k: {q: v[q] for q in ("max_rel_DM", "max_rel_H", "max_rel_DV")}
                                               for k, v in camb_x["points"].items()},
                     "planck2018_rdrag_Mpc": camb_x["planck2018_reference"]["rdrag_Mpc"]}
                    if camb_x else "BLOCKED: camb_crosscheck.json missing (run camb_crosscheck.py with venv-cosmo)")

    fit = {
        "generated_at": datetime.now(UTC).isoformat(),
        "camb_background_crosscheck": camb_summary,
        "chains": chains,
        "preregistration_sha256": L.sha256(L.PREREG),
        "input_sha256_verified": True,
        "controls": {"instrument_check": ic["summary"], "positive_control_passed": pc["positive_control_passed"],
                     "negative_controls_all_rejected": nc["all_negative_controls_rejected"]},
        "never_combined": "SDSS and DESI fitted separately; combination guard active",
        "reported_convention": "posterior mean +- std from emcee (prereg); grid and MAP+Laplace cross-checks",
        "fits": {k: v["summary"] for k, v in A.items()},
        "baseline_vs_gaussian_summary_shift_in_baseline_sigma": {"Om": float(sg_shift[0]), "hrd": float(sg_shift[1])},
        "tension": tens,
        "pulls": pulls,
        "within_tolerance": bool(within),
        "within_tolerance_rule": "|pull| < 0.5 on the three 'verified primary' targets; SDSS_hrd reported but "
                                 "secondary-sourced (flagged, not counted)",
        "note_output_name": "prereg planned fit_results.json; task asked for fit.json - this file is that output",
    }
    (L.RESULTS / "fit.json").write_text(json.dumps(fit, indent=1))
    print(json.dumps({k: fit[k] for k in ("tension", "pulls", "within_tolerance",
                                          "baseline_vs_gaussian_summary_shift_in_baseline_sigma")}, indent=1))

    # ---------------- figure
    fig, ax = plt.subplots(figsize=(6.0, 4.8))
    for R, col, lab in ((S, ORANGE, "SDSS/eBOSS DR16 BAO"), (D, BLUE, "DESI DR2 BAO")):
        g = R["grid"]
        p = g["p"]; ps = np.sort(p.ravel())[::-1]; cs = np.cumsum(ps)
        lv = [ps[np.searchsorted(cs, q)] for q in (0.954, 0.683)]
        ax.contourf(g["oms"], g["hrds"], p.T, levels=[lv[0], lv[1], p.max()], colors=[col, col], alpha=0.25)
        ax.contour(g["oms"], g["hrds"], p.T, levels=lv, colors=[col], linewidths=1.5)
        ax.plot([], [], color=col, lw=2, label=lab)
    for t, col in (("SDSS", ORANGE), ("DESI_DR2", BLUE)):
        om = [x for x in prereg["targets"] if x["name"] == f"{t}_Om"][0]
        hr = [x for x in prereg["targets"] if x["name"] == f"{t}_hrd_Mpc"][0]
        ax.errorbar(om["value"], hr["value"], xerr=om["sigma"], yerr=hr["sigma"], fmt="s", ms=6,
                    color=col, mec="white", capsize=0, lw=1)
    ax.plot([], [], "s", color="#52514e", label="published (prereg targets)")
    ax.set_xlabel(r"$\Omega_m$"); ax.set_ylabel(r"$h\,r_d$ [Mpc]")
    t0 = tens["primary_emcee_moments"]
    ax.set_title(f"Flat ΛCDM, BAO only: SDSS vs DESI DR2 — {t0['N_sigma']:.2f}σ (fitted separately)", fontsize=10)
    ax.grid(color="#e4e3df", lw=0.6); ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(L.RESULTS / "eboss_vs_desi_contours.pdf")
    fig.savefig(L.RESULTS / "eboss_vs_desi_contours.png", dpi=130)
    print("wrote", L.RESULTS / "fit.json", "and figure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

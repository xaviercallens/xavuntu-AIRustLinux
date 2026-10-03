#!/usr/bin/env python3
"""Positive and negative controls for desi_dr2_bao, exactly as preregistered.

Writes results/desi_dr2_bao/controls.json. Run BEFORE mcmc_fit.py.
    /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python -B scripts/desi_dr2_bao/controls.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import chi2 as chi2_dist

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dr2_model as m  # noqa: E402


def pte(c2: float, dof: int) -> dict[str, float]:
    return {"chi2": float(c2), "dof": dof, "pte": float(chi2_dist.sf(c2, dof)),
            "log10_pte": float(chi2_dist.logsf(c2, dof) / np.log(10.0))}


def z_changing_perm(z: np.ndarray, seed: int) -> tuple[list[int], int]:
    """Rejection-sample a permutation with z[perm[i]] != z[i] for every i."""
    rng = np.random.default_rng(seed)
    tries = 0
    while True:
        tries += 1
        perm = rng.permutation(len(z))
        if np.all(z[perm] != z):
            return [int(p) for p in perm], tries


def gl_vs_quad_validation(ds: m.Dataset) -> dict[str, float]:
    worst = 0.0
    for om in (0.01, 0.2975, 0.99):
        for w in (-3.0, -1.0, -0.916, 1.0):
            a = m.predict_gl(ds, om, 101.0, w)
            b = m.predict_quad(ds, om, 101.0, w)
            worst = max(worst, float(np.max(np.abs(a / b - 1.0))))
    orad = m.omega_rad_from_astropy()
    a = m.predict_gl(ds, 0.3, 101.0, -0.9, orad)
    b = m.predict_quad(ds, 0.3, 101.0, -0.9, orad)
    worst_r = float(np.max(np.abs(a / b - 1.0)))
    return {"max_rel_diff_prior_corners": worst, "max_rel_diff_with_radiation": worst_r,
            "gl_order": m.GL_ORDER, "pass_1e-9": bool(max(worst, worst_r) < 1e-9)}


def main() -> int:
    out: dict[str, object] = {"generated_at": m.utc_now(), "provenance": m.check_provenance()}
    dr1, dr2 = m.load_dr1(), m.load_dr2()
    out["gl_integrator_validation"] = gl_vs_quad_validation(dr2)

    pcs: dict[str, dict[str, object]] = {}
    # PC0 regression on DR1 (quad path = parent Method B generalized; GL path too)
    for name, pred in (("quad", m.predict_quad), ("gl", m.predict_gl)):
        f = m.fit_chi2_min(dr1, "lcdm", pred)
        om, hrd, c2 = f["params"]["Om"], f["params"]["h_rd"], f["chi2"]
        pcs[f"PC0_regression_{name}"] = {
            "Om": om, "h_rd": hrd, "chi2": c2,
            "pass": bool(abs(om - 0.29389) < 1e-4 and abs(hrd - 101.9367) < 1e-3 and abs(c2 - 12.7405) < 1e-3)}

    # PC1 noiseless LCDM
    synth = dr2.with_values(m.predict_gl(dr2, 0.30, 101.0))
    f = m.fit_chi2_min(synth, "lcdm")
    d_om, d_h = f["params"]["Om"] - 0.30, f["params"]["h_rd"] - 101.0
    pcs["PC1_noiseless_LCDM"] = {"fit": f, "dOm": d_om, "dh_rd": d_h,
                                 "pass": bool(abs(d_om) < 1e-4 and abs(d_h) < 1e-2 and f["chi2"] < 1e-4)}

    # PC2 noiseless wCDM
    synth = dr2.with_values(m.predict_gl(dr2, 0.30, 101.0, -0.90))
    f = m.fit_chi2_min(synth, "wcdm")
    d_om, d_w, d_h = f["params"]["Om"] - 0.30, f["params"]["w"] + 0.90, f["params"]["h_rd"] - 101.0
    pcs["PC2_noiseless_wCDM"] = {"fit": f, "dOm": d_om, "dw": d_w, "dh_rd": d_h,
                                 "pass": bool(abs(d_om) < 1e-3 and abs(d_w) < 1e-3 and abs(d_h) < 0.02
                                              and f["chi2"] < 1e-4)}

    # PC3 500 noisy LCDM draws, pulls in Fisher sigma at truth
    truth = np.array([0.2975, 101.54])
    fcov = m.fisher_cov(dr2, "lcdm", truth)
    fsig = np.sqrt(np.diag(fcov))
    mean_vec = m.predict_gl(dr2, *truth)
    rng = np.random.default_rng(20260928)
    draws = rng.multivariate_normal(mean_vec, dr2.cov, size=500)
    fits, c2s = [], []
    for d in draws:
        f = m.fit_chi2_min(dr2.with_values(d), "lcdm", x0=(0.2975, 101.54), max_restarts=2)
        fits.append(f["x"])
        c2s.append(f["chi2"])
    fits_a = np.array(fits)
    pulls = (fits_a - truth) / fsig
    mp, sp = pulls.mean(axis=0), pulls.std(axis=0, ddof=1)
    mc2 = float(np.mean(c2s))
    pcs["PC3_noisy_LCDM_draws"] = {
        "n": 500, "fisher_sigma_at_truth": {"Om": float(fsig[0]), "h_rd": float(fsig[1])},
        "fisher_corr_at_truth": float(fcov[0, 1] / (fsig[0] * fsig[1])),
        "mean_pull": {"Om": float(mp[0]), "h_rd": float(mp[1])},
        "std_pull": {"Om": float(sp[0]), "h_rd": float(sp[1])},
        "mean_chi2_min": mc2,
        "pass": bool(np.all(np.abs(mp) < 0.15) and np.all((sp >= 0.88) & (sp <= 1.12)) and 10.3 <= mc2 <= 11.7)}

    # PC4 astropy vs quad at the real best fits
    bf_l = m.fit_chi2_min(dr2, "lcdm")
    bf_w = m.fit_chi2_min(dr2, "wcdm")
    a_l = m.predict_astropy(dr2, bf_l["params"]["Om"], bf_l["params"]["h_rd"])
    q_l = m.predict_quad(dr2, bf_l["params"]["Om"], bf_l["params"]["h_rd"])
    a_w = m.predict_astropy(dr2, bf_w["params"]["Om"], bf_w["params"]["h_rd"], bf_w["params"]["w"])
    q_w = m.predict_quad(dr2, bf_w["params"]["Om"], bf_w["params"]["h_rd"], bf_w["params"]["w"])
    rl, rw = float(np.max(np.abs(a_l / q_l - 1))), float(np.max(np.abs(a_w / q_w - 1)))
    pcs["PC4_astropy_vs_quad"] = {"max_rel_diff_lcdm": rl, "max_rel_diff_wcdm": rw,
                                  "pass": bool(max(rl, rw) < 1e-5)}
    out["positive_controls"] = pcs

    ncs: dict[str, dict[str, object]] = {}
    # NC1 redshift permutation
    perm, tries = z_changing_perm(dr2.z, 101)
    ds = dr2.with_z_kinds(dr2.z[perm], dr2.kinds)
    f = m.fit_chi2_min(ds, "lcdm")
    p = pte(f["chi2"], 11)
    ncs["NC1_redshift_permutation"] = {"perm": perm, "rejection_tries": tries, "fit": f, **p,
                                       "failed_as_required": bool(p["pte"] < 1e-3)}

    # NC2 DM <-> DH label swap
    swap = {"DM_over_rs": "DH_over_rs", "DH_over_rs": "DM_over_rs", "DV_over_rs": "DV_over_rs"}
    ds = dr2.with_z_kinds(dr2.z, [swap[k] for k in dr2.kinds])
    f = m.fit_chi2_min(ds, "lcdm")
    p = pte(f["chi2"], 11)
    ncs["NC2_DM_DH_label_swap"] = {"fit": f, **p, "failed_as_required": bool(p["pte"] < 1e-3)}

    # NC3 Einstein-de Sitter: Om = 1 fixed, h_rd free. Model is linear in s = 1/h_rd -> exact minimum.
    unit = m.predict_quad(dr2, 1.0, 1.0)  # observables for h_rd = 1 Mpc
    s_hat = float(unit @ dr2.cov_inv @ dr2.vals / (unit @ dr2.cov_inv @ unit))
    c2_exact = float(m.chi2_vals(dr2, unit * s_hat))
    nm = minimize_scalar(lambda h: float(m.chi2_vals(dr2, unit / h)), bounds=(10.0, 1000.0), method="bounded",
                         options={"xatol": 1e-8})
    dc_quad = np.array([m.predict_quad(dr2.with_z_kinds(np.array([z]), ["DM_over_rs"]), 1.0, 1.0)[0]
                        for z in dr2.z])
    dc_exact = (m.C_KM_S / 100.0) * 2.0 * (1.0 - 1.0 / np.sqrt(1.0 + dr2.z))
    p = pte(c2_exact, 12)
    ncs["NC3_wrong_model_EdS"] = {"h_rd_exact": 1.0 / s_hat, "h_rd_bounded_minimizer": float(nm.x),
                                  "chi2_bounded_minimizer": float(nm.fun),
                                  "EdS_DC_quad_vs_analytic_max_rel": float(np.max(np.abs(dc_quad / dc_exact - 1))),
                                  **p, "failed_as_required": bool(p["pte"] < 1e-6)}

    # NC4 LCDM fitted to noiseless w = -0.7 data
    ds = dr2.with_values(m.predict_gl(dr2, 0.30, 101.54, -0.70))
    fl = m.fit_chi2_min(ds, "lcdm")
    fw = m.fit_chi2_min(ds, "wcdm")
    ncs["NC4_LCDM_on_w-0.7_synthetic"] = {"lcdm_fit": fl, "wcdm_fit": fw,
                                          "failed_as_required": bool(fl["chi2"] > 9 and fw["chi2"] < 1e-4)}

    # NC5 scrambled covariance
    rows = []
    for seed in range(200, 220):
        perm, tries = z_changing_perm(dr2.z, seed)
        pa = np.array(perm)
        cprime = dr2.cov[np.ix_(pa, pa)]
        f = m.fit_chi2_min(dr2.with_cov(cprime), "lcdm")
        rows.append({"seed": seed, "perm": perm, "rejection_tries": tries, "chi2": f["chi2"],
                     "pte": float(chi2_dist.sf(f["chi2"], 11)),
                     "log10_pte": float(chi2_dist.logsf(f["chi2"], 11) / np.log(10.0))})
    med = float(np.median([r["pte"] for r in rows]))
    ncs["NC5_scrambled_covariance"] = {"runs": rows, "median_pte": med,
                                       "median_log10_pte": float(np.median([r["log10_pte"] for r in rows])),
                                       "failed_as_required": bool(med < 1e-3)}
    out["negative_controls"] = ncs

    all_pc = all(bool(v["pass"]) for v in pcs.values())
    all_nc = all(bool(v["failed_as_required"]) for v in ncs.values())
    out["summary"] = {"all_positive_controls_pass": all_pc, "all_negative_controls_fail_as_required": all_nc,
                      "gl_validation_pass": out["gl_integrator_validation"]["pass_1e-9"],
                      "pipeline_validated": bool(all_pc and all_nc and out["gl_integrator_validation"]["pass_1e-9"])}
    path = m.RESULTS / "controls.json"
    path.write_text(json.dumps(out, indent=1))
    brief = {k: v.get("pass") for k, v in pcs.items()} | {k: v.get("failed_as_required") for k, v in ncs.items()}
    print(json.dumps(brief, indent=1))
    print("PC3:", json.dumps(pcs["PC3_noisy_LCDM_draws"]))
    for k, v in ncs.items():
        print(k, {kk: v[kk] for kk in ("chi2", "pte", "log10_pte", "median_pte", "median_log10_pte") if kk in v})
    print("NC4 lcdm chi2", ncs["NC4_LCDM_on_w-0.7_synthetic"]["lcdm_fit"]["chi2"],
          "wcdm chi2", ncs["NC4_LCDM_on_w-0.7_synthetic"]["wcdm_fit"]["chi2"])
    print("PC0/1/2/4:", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "fit"} for k, v in pcs.items()
                                     if k != "PC3_noisy_LCDM_draws"}, default=str))
    print("GL:", out["gl_integrator_validation"])
    print("summary:", out["summary"])
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

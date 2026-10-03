"""Real-data fits for bao_bbn_h0 under preregistration + amendment 1.

  PRIMARY   (amendment 1): r_d = exact CAMB 2.0.4 r_drag(omega_b, omega_cdm, h) table
            (scripts/bao_bbn_h0/rd_camb_table.py; validated vs direct CAMB and vs CLASS 3.3.4).
  SECONDARY (preregistered): r_d = Aubourg+2015 eq. 16 fitting formula.

Per analysis: headline T1 (DR2 BAO+BBN), second check T2 (DR1 BAO+BBN), negative control N3
(no BBN prior). Shared: gates G1/G2 (P3; BAO-only (Omega_m, h r_d), no r_d model involved).
Sensitivity S1-S3 as preregistered (secondary-formula based) plus S3 on the primary.
The success rule (preregistration.tolerance.verdicts) is applied to the PRIMARY.

Two estimation methods for every headline number:
  A. emcee posterior mean/std (the preregistered statistic).
  B. MAP + Laplace/Fisher covariance, and a 1-D profile likelihood in H0 (delta chi2 = 1).

Writes results/bao_bbn_h0/fit.json; chains (float32 .npy) go to disk 2 with sha256 pointers
in results/bao_bbn_h0/chains_pointer.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.optimize import brentq
from scipy.stats import chi2 as chi2_dist

import common as cm

NAMES = ["H0", "omega_b", "Omega_m"]
X0 = np.array([68.5, 0.02218, 0.30])
SCALE = np.array([0.1, 0.0001, 0.002])
STEPS = np.array([0.02, 2e-6, 2e-5])
CHAINS = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/cosmo3/bao_bbn_h0/chains")
RDFN = {"primary": "camb", "secondary": "aub16"}
LOCKED = cm.RESULTS / "fit_attempt1_fittingformula_UNREAD_AT_AMENDMENT.json"
LOCKED_SHA = "b7fe5608e4ae6d0b1cb0f7844e55a6025089336cc9bcb3086e9ead6e85531910"
POINTERS: dict[str, dict[str, object]] = {}


def save_chain(name: str, samples: np.ndarray, cols: list[str]) -> None:
    p = CHAINS / f"{name}.npy"
    np.save(p, samples.astype(np.float32))
    POINTERS[name] = {"path": str(p), "sha256": cm.sha256(p), "bytes": p.stat().st_size,
                      "shape": list(samples.shape), "columns": cols}


def rd_of(rd_fn: str, h0: np.ndarray, wb: np.ndarray, om: np.ndarray) -> np.ndarray:
    h = h0 / 100.0
    if rd_fn == "camb":
        return cm.rd_camb(h, om, wb)
    return cm.rd_aubourg16(cm.omega_cb_of(h, om), wb)


def gate(d: cm.BAOData, om_t: tuple[float, float], hrd_t: tuple[float, float], seed: int) -> dict[str, object]:
    lp = cm.make_logpost_hrd(d)
    xmap, c2 = cm.fit_map(lp, np.array([0.30, 101.5]))
    lap = cm.laplace_cov(lp, xmap, np.array([2e-5, 2e-3]))
    ch = cm.run_mcmc(lp, xmap, np.array([0.002, 0.2]), seed=seed)
    save_chain(f"gate_{d.name}", ch.samples, ["Omega_m", "hrd"])
    om, hrd = ch.mean
    so, sh = ch.std
    conds = {
        "Om_within_0.25sig": bool(abs(om - om_t[0]) <= 0.25 * om_t[1]),
        "hrd_within_0.25sig": bool(abs(hrd - hrd_t[0]) <= 0.25 * hrd_t[1]),
        "sigma_Om_within_15pct": bool(abs(so / om_t[1] - 1) <= 0.15),
        "sigma_hrd_within_15pct": bool(abs(sh / hrd_t[1] - 1) <= 0.15),
    }
    dof = len(d.vals) - 2
    return {
        "data": d.name, "radiation_h_fixed": 0.6851, "map": {"Omega_m": float(xmap[0]), "hrd": float(xmap[1])},
        "laplace_sigma": {"Omega_m": float(np.sqrt(lap[0, 0])), "hrd": float(np.sqrt(lap[1, 1]))},
        "chi2_map": c2, "dof": dof, "pte": float(chi2_dist.sf(c2, dof)),
        "chain": cm.chain_summary(ch, ["Omega_m", "hrd"]),
        "target": {"Omega_m": om_t, "hrd": hrd_t},
        "pull_Om": float((om - om_t[0]) / om_t[1]), "pull_hrd": float((hrd - hrd_t[0]) / hrd_t[1]),
        "conditions": conds, "passed": bool(all(conds.values())),
    }


def profile_h0(lp_full: Callable[[np.ndarray], np.ndarray], xmap: np.ndarray, c2min: float) -> dict[str, object]:
    grid = np.arange(xmap[0] - 2.5, xmap[0] + 2.5001, 0.1)
    prof = []
    start = xmap[1:].copy()
    for h in grid:
        lp2 = lambda t, h=h: lp_full(np.column_stack([np.full(np.atleast_2d(t).shape[0], h), np.atleast_2d(t)]))
        _, c2 = cm.fit_map(lp2, start)
        prof.append(c2)
    prof_a = np.array(prof) - c2min
    i0 = int(np.argmin(prof_a))
    f = lambda h: float(np.interp(h, grid, prof_a)) - 1.0
    lo = brentq(f, grid[0], grid[i0]) if prof_a[0] > 1 else float("nan")
    hi = brentq(f, grid[i0], grid[-1]) if prof_a[-1] > 1 else float("nan")
    return {"grid": grid.tolist(), "delta_chi2": prof_a.tolist(), "H0_min_grid": float(grid[i0]),
            "H0_lo_1sig": lo, "H0_hi_1sig": hi, "sigma_sym": 0.5 * (hi - lo)}


def bbn_fit(d: cm.BAOData, seed: int, tag: str, rd_fn: str) -> dict[str, object]:
    lp = cm.make_logpost(d, rd_fn=rd_fn)
    xmap, c2 = cm.fit_map(lp, X0)
    lap = cm.laplace_cov(lp, xmap, STEPS)
    ch = cm.run_mcmc(lp, xmap, SCALE, seed=seed)
    save_chain(tag, ch.samples, NAMES)
    dof = len(d.vals) + 1 - 3
    out: dict[str, object] = {
        "data": d.name, "rd_fn": rd_fn, "map": dict(zip(NAMES, xmap.tolist())), "chi2_map": c2, "dof": dof,
        "pte": float(chi2_dist.sf(c2, dof)),
        "laplace": {"sigma": dict(zip(NAMES, np.sqrt(np.diag(lap)).tolist())), "cov": lap.tolist()},
        "chain": cm.chain_summary(ch, NAMES),
    }
    s = ch.samples
    rd = rd_of(rd_fn, s[:, 0], s[:, 1], s[:, 2])
    hr = s[:, 0] / 100.0 * rd
    out["derived"] = {"hrd_mean": float(hr.mean()), "hrd_std": float(hr.std(ddof=1)),
                      "rd_mean": float(rd.mean()), "rd_std": float(rd.std(ddof=1))}
    out["profile_H0"] = profile_h0(lp, xmap, c2)
    if rd_fn == "aub16":  # astropy predictor re-evaluation of the MAP chi2 (predict_astropy uses eq. 16)
        am = cm.predict_astropy(d, *xmap)
        out["chi2_map_astropy"] = float((d.vals - am) @ d.cov_inv @ (d.vals - am)
                                        + ((xmap[1] - cm.BBN_MEAN) / cm.BBN_SIGMA) ** 2)
    return out


def verdict(r: dict[str, object], h_t: float, h_s: float, om_t: float, om_s: float, strict: float, soft: float,
            gate_ok: bool, controls_ok: bool) -> dict[str, object]:
    h = r["chain"]["mean"]["H0"]
    sh = r["chain"]["std"]["H0"]
    om = r["chain"]["mean"]["Omega_m"]
    dh = abs(h - h_t)
    c = {"H0_strict": bool(dh <= strict), "H0_soft": bool(dh <= soft),
         "Om_within_0.25sig": bool(abs(om - om_t) <= 0.25 * om_s),
         "sigma_H0_within_15pct": bool(abs(sh / h_s - 1) <= 0.15),
         "gate_G1": gate_ok, "controls": controls_ok}
    others = c["Om_within_0.25sig"] and c["sigma_H0_within_15pct"] and c["gate_G1"] and c["controls"]
    v = "PASS" if (c["H0_strict"] and others) else ("PARTIAL" if (c["H0_soft"] and others) else "FAIL")
    return {"H0": h, "sigma_H0": sh, "Omega_m": om, "sigma_Om": r["chain"]["std"]["Omega_m"], "abs_dH0": dh,
            "pull_H0": (h - h_t) / h_s, "pull_Om": (om - om_t) / om_s, "sigma_ratio": sh / h_s,
            "conditions": c, "verdict": v}


def main() -> int:
    t0 = time.time()
    CHAINS.mkdir(parents=True, exist_ok=True)
    pre = json.loads(cm.PREREG.read_text())
    tol = pre["tolerance"]
    strict, soft = tol["strict_H0_km_s_Mpc"], tol["soft_H0_km_s_Mpc"]
    dr2, dr1 = cm.load_dr2(), cm.load_dr1()
    val = json.loads((cm.RESULTS / "rd_camb_validation.json").read_text())
    anchor_rep = json.loads((cm.RESULTS / "anchor_reproduction.json").read_text())
    anchor_camb = next(float(r["rdrag"]) for r in anchor_rep["rows"]
                       if str(r["code"]).startswith("CAMB") and r.get("nnu") == 3.044)
    anchor_class = next(float(r["rs_drag"]) for r in anchor_rep["rows"]
                        if str(r["code"]).startswith("CLASS") and r.get("N_ur") == 2.0328)
    res: dict[str, object] = {
        "problem": "bao_bbn_h0",
        "preregistration_sha256": cm.sha256(cm.PREREG),
        "amendment_1_sha256": cm.sha256(cm.RESULTS / "preregistration_amendment_1.json"),
        "rd_camb_table_sha256": cm.sha256(cm.RD_TABLE),
        "data_sha256": {str(p): cm.sha256(p) for p in (cm.DR2_MEAN, cm.DR2_COV, cm.DR1_MEAN, cm.DR1_COV)},
        "script": "scripts/bao_bbn_h0/fit_real.py",
        "analyses": {"primary": "exact CAMB 2.0.4 r_drag table (amendment 1)",
                     "secondary": "Aubourg+2015 eq. 16 fitting formula (preregistered)"},
        "rd_camb_validation_summary": {
            "anchor_planck2018_rdrag_Neff3.046": val["anchor_planck2018_rdrag_nnu3.046"],
            "interp_vs_direct_camb": val["interpolation_vs_direct_camb"],
            "class_minus_camb_max_abs_frac": max(abs(x["frac_class_minus_camb"]) for x in val["class_and_aubourg_vs_camb"]),
            "aub16_minus_camb_fracs": [x["frac_aub16_minus_camb"] for x in val["class_and_aubourg_vs_camb"]],
            "camb_background_vs_manual_max_frac": max(max(x["max_frac_DM"], x["max_frac_DH"])
                                                      for x in val["camb_background_vs_manual_distances"]),
            "n_grid_h_substituted": val["n_grid_h_substituted"]},
        "deviations": [
            "MCMC and MAP use the manual Gauss-Legendre predictor, not astropy (P4 agreement < 1e-4); "
            "for the secondary the MAP chi2 is re-evaluated with astropy; for the primary the analytic "
            "distances were checked against CAMB's own background (rd_camb_validation.json).",
            "P2 mocks also draw the BBN centre per mock (prior-as-data); written before P2 first ran.",
            "G1/G2 radiation term evaluated at fixed h=0.6851 (hr_d parametrisation carries no h); effect <1e-4.",
            "Preregistration report_rules mention N1-N4 but only N1-N3 are defined; S1 (N_eff=4.044) is a "
            "sensitivity demo, not a control. No N4 was invented.",
            "Secondary r_d = Aubourg eq. 16 at N_eff=3.044 uncorrected (eq. 17 slope gives +0.0065%, logged not applied).",
            "Primary: CAMB table support omega_cdm in [0.005,1], h in [0.2,0.99]; outside it the posterior is zero. "
            "This truncates the preregistered flat H0 prior U[20,100] to H0 <= 99 (irrelevant for the BBN fits; "
            "reported for N3).",
            "Primary omega_cdm = Omega_m h^2 - omega_b - omega_nu with CAMB's omega_nu = 0.000644899 (mnu=0.06 eV).",
            "Primary support requires omega_cdm >= 0.005, i.e. omega_b <= Omega_m h^2 - 0.0056; the secondary "
            "(eq. 16) only requires omega_cb > 0. This matters only for N3 (no BBN prior), where the posterior "
            "differs in shape between analyses; both N3 ratios are reported.",
            f"CAMB table: {val['n_grid_h_substituted']} of 8967 nodes (all at the h=0.99 node, Omega_m < 0.05) "
            "failed in CAMB's recombination solver and were filled with CAMB at h-0.01/-0.02/-0.05 "
            "(listed in rd_camb_validation.json); none lie near the posterior.",
            "N3 chains run with a 40000-step floor (first run: primary N3 stopped at 4000 steps, tau~57, "
            "which likely underestimated tau for this broad posterior).",
            "Lean plan: the preregistered 'h*r_d(h) strictly increasing in h for 1-2a>0' was not formalised. It was "
            "replaced by D_H/r_d = c/(100 (h r_d) E) (DH_over_rd_eq_hrd, DH_over_rd_degenerate) and the exact h r_d "
            "reparametrisation of the BAO-only gate (gate_reparam_exact), plus strict antitonicity of eq. 16 in "
            "omega_b, omega_cb and Omega_m. Recorded after referee review.",
        ],
        "camb_instrument_anchor": {
            "inputs": "H0=67.32, ombh2=0.022383, omch2=0.12011, mnu=0.06 (1 massive), nnu=3.046, tau=0.0543, "
                      "As=2.1e-9, ns=0.96605 (Planck 2018 Table 1 best fit, as used in the preregistration)",
            "camb_rdrag_this_run": val["anchor_planck2018_rdrag_nnu3.046"],
            "preregistration_cited_rdrag": 147.049,
            "orchestrator_positive_control_rdrag": 147.1027,
            "orchestrator_positive_control_rsdrag_class": 147.0971,
            "orchestrator_anchor_reproduction": anchor_rep,
            "published_posterior_mean_rdrag": "147.09 +- 0.26 Mpc (arXiv:1807.06209 Table 1 'Plik [1]' column and "
                                              "Table 2 TT,TE,EE+lowE+lensing column; quoted in arXiv:2404.03002 above eq. 4.3)",
            "note": "This run reproduces the preregistration's cited 147.049 (Table 1 best fit, N_eff=3.046). "
                    "The amendment's CAMB 147.1027 / CLASS 147.0971 anchors are reproduced "
                    "(anchor_reproduction.json) at the Planck 2018 Table 2 TT,TE,EE+lowE+lensing means "
                    "H0=67.36, ombh2=0.02237, omch2=0.1200, one 0.06 eV neutrino: CAMB nnu=3.044 gives "
                    f"{anchor_camb:.4f}; CLASS N_ur=2.0328 gives {anchor_class:.4f} (CLASS reports N_eff=3.046 "
                    "for that N_ur). The published 147.09 +- 0.26 is the Planck 2018 posterior mean. An earlier "
                    "version of this note wrongly said the anchor could not be reproduced and the published value "
                    "was not in the fetched sources; corrected after referee review.",
        },
    }
    # P3 gates (r_d-free, shared by both analyses)
    res["G1"] = gate(dr2, (0.2975, 0.0086), (101.54, 0.73), seed=301)
    res["G2"] = gate(dr1, (0.295, 0.015), (101.8, 1.3), seed=302)
    for g in ("G1", "G2"):
        print(g, json.dumps({k: res[g][k] for k in ("pull_Om", "pull_hrd", "conditions", "passed", "chi2_map", "pte")}),
              res[g]["chain"]["mean"], res[g]["chain"]["std"], "laplace", res[g]["laplace_sigma"], flush=True)
    cm.write_json(cm.RESULTS / "fit.json", res)

    for analysis, rd_fn in RDFN.items():
        a: dict[str, object] = {"rd_fn": rd_fn}
        for key, d, seed in (("T1_DR2", dr2, 401), ("T2_DR1", dr1, 402)):
            r = bbn_fit(d, seed, f"{key}_{analysis}", rd_fn)
            a[key] = r
            print(analysis, key, "mean", r["chain"]["mean"], "std", r["chain"]["std"], "tau", r["chain"]["tau"],
                  "ess", r["chain"]["ess"], "conv", r["chain"]["converged_50tau_and_ess"],
                  "MAP", r["map"], "chi2", r["chi2_map"], "dof", r["dof"], "pte", r["pte"],
                  "laplace", r["laplace"]["sigma"],
                  "profile", {k: r["profile_H0"][k] for k in ("H0_min_grid", "H0_lo_1sig", "H0_hi_1sig", "sigma_sym")},
                  "derived", r["derived"], flush=True)
        lpn = cm.make_logpost(dr2, bbn=None, rd_fn=rd_fn)
        # min_steps floor: a 4000-step chain underestimated tau for this broad posterior (first run)
        chn = cm.run_mcmc(lpn, np.array(list(a["T1_DR2"]["map"].values())), SCALE, seed=403, max_steps=100000,
                          min_steps=40000)
        save_chain(f"N3_noBBN_{analysis}", chn.samples, NAMES)
        ratio = float(chn.std[0] / a["T1_DR2"]["chain"]["std"]["H0"])
        a["N3"] = {"id": "N3", "chain": cm.chain_summary(chn, NAMES), "sigma_H0_ratio_vs_baseline": ratio,
                   "control_behaves": bool(ratio > 5.0),
                   "note": "posterior fills the flat priors; the 50-tau rule may not be met (capped at 1e5 steps), reported as is"}
        print(analysis, "N3", chn.mean, chn.std, "tau", chn.tau, "n_steps", chn.n_steps, "conv", chn.converged_50tau,
              "ratio", ratio, flush=True)
        ctl: dict[str, bool] = {}
        for cid in ("P1", "P2", "N1", "N2"):
            c = json.loads((cm.RESULTS / "controls" / f"{cid}_{analysis}.json").read_text())
            ctl[cid] = bool(c.get("passed", c.get("control_behaves")))
        ctl["P4"] = bool(json.loads((cm.RESULTS / "controls" / "P4.json").read_text())["passed"])
        ctl["P3_G1"] = res["G1"]["passed"]
        ctl["N3"] = a["N3"]["control_behaves"]
        a["controls_summary"] = ctl
        pos_ok = all(ctl[k] for k in ("P1", "P2", "P3_G1", "P4"))
        neg_ok = all(ctl[k] for k in ("N1", "N2", "N3"))
        a["positive_controls_passed"] = pos_ok
        a["negative_controls_behaved"] = neg_ok
        a["verdict_T1"] = verdict(a["T1_DR2"], 68.51, 0.58, 0.2977, 0.0086, strict, soft, res["G1"]["passed"], pos_ok and neg_ok)
        a["verdict_T2"] = verdict(a["T2_DR1"], 68.53, 0.80, 0.295, 0.015, strict, soft, res["G1"]["passed"], pos_ok and neg_ok)
        print(analysis, "controls", ctl, flush=True)
        print(analysis, "verdict_T1", json.dumps(a["verdict_T1"]), flush=True)
        print(analysis, "verdict_T2", json.dumps(a["verdict_T2"]), flush=True)
        res[analysis] = a
        cm.write_json(cm.RESULTS / "fit.json", res)

    # sensitivity (reported only)
    sens: dict[str, object] = {}
    for sid, kw in (("S1_Neff4.044_secondary", {"rd_fn": "aub16_neff", "neff": 4.044}),
                    ("S2_desi_eq2", {"rd_fn": "desi_eq2"}),
                    ("S3_no_radiation_secondary", {"rd_fn": "aub16", "radiation": False}),
                    ("S3_no_radiation_primary", {"rd_fn": "camb", "radiation": False})):
        base = "primary" if kw["rd_fn"] == "camb" else "secondary"
        lp = cm.make_logpost(dr2, **kw)
        ch = cm.run_mcmc(lp, X0, SCALE, seed=500 + len(sens))
        sens[sid] = {"kwargs": kw, "chain": cm.chain_summary(ch, NAMES),
                     "dH0_vs_T1": float(ch.mean[0] - res[base]["T1_DR2"]["chain"]["mean"]["H0"]), "vs": base}
        print(sid, sens[sid]["chain"]["mean"], sens[sid]["chain"]["std"], "dH0", sens[sid]["dH0_vs_T1"], flush=True)
    res["sensitivity"] = sens

    # comparison of the re-run secondary with the hash-locked pre-amendment output
    lk_sha = cm.sha256(LOCKED)
    lk = json.loads(LOCKED.read_text())
    comp: dict[str, object] = {"path": str(LOCKED), "sha256_now": lk_sha, "sha256_expected": LOCKED_SHA,
                               "sha256_matches": lk_sha == LOCKED_SHA}
    for key in ("T1_DR2", "T2_DR1"):
        old, new = lk[key]["chain"], res["secondary"][key]["chain"]
        comp[key] = {n: {"locked_mean": old["mean"][n], "rerun_mean": new["mean"][n],
                         "diff": new["mean"][n] - old["mean"][n], "locked_std": old["std"][n], "rerun_std": new["std"][n]}
                     for n in ("H0", "Omega_m")}
        comp[key]["locked_map_H0"] = lk[key]["map"]["H0"]
        comp[key]["rerun_map_H0"] = res["secondary"][key]["map"]["H0"]
    for g in ("G1", "G2"):
        comp[g] = {n: {"locked_mean": lk[g]["chain"]["mean"][n], "rerun_mean": res[g]["chain"]["mean"][n]}
                   for n in ("Omega_m", "hrd")}
    res["secondary_vs_locked_preamendment"] = comp
    print("locked comparison", json.dumps(comp), flush=True)

    # pulls vs every preregistered target, both analyses
    targets = [("T1_H0", "T1_DR2", "H0", 68.51, 0.58), ("T1b_Omega_m", "T1_DR2", "Omega_m", 0.2977, 0.0086),
               ("T2_H0", "T2_DR1", "H0", 68.53, 0.80), ("T2b_Omega_m", "T2_DR1", "Omega_m", 0.295, 0.015)]
    # per-target preregistered rule: H0 absolute strict/soft in km/s/Mpc, Omega_m and gates 0.25 sigma
    pulls = []
    for analysis in RDFN:
        for tid, key, par, v, s in targets:
            m = res[analysis][key]["chain"]["mean"][par]
            row = {"analysis": analysis, "target": tid, "value": m, "sigma_fit": res[analysis][key]["chain"]["std"][par],
                   "target_value": v, "target_sigma": s, "pull_sigma": (m - v) / s, "pull_divides_by": "target sigma"}
            if par == "H0":
                row["rule"] = f"|dH0| <= {strict} strict / {soft} soft km/s/Mpc"
                row["within_strict"] = bool(abs(m - v) <= strict)
                row["within_soft"] = bool(abs(m - v) <= soft)
            else:
                row["rule"] = "|dOm| <= 0.25 target sigma"
                row["within_strict"] = bool(abs(m - v) <= 0.25 * s)
            pulls.append(row)
    for tid, g, par, v, s in (("G1_hrd", "G1", "hrd", 101.54, 0.73), ("G1_Omega_m", "G1", "Omega_m", 0.2975, 0.0086),
                              ("G2_hrd", "G2", "hrd", 101.8, 1.3), ("G2_Omega_m", "G2", "Omega_m", 0.295, 0.015)):
        m = res[g]["chain"]["mean"][par]
        pulls.append({"analysis": "shared", "target": tid, "value": m, "sigma_fit": res[g]["chain"]["std"][par],
                      "target_value": v, "target_sigma": s, "pull_sigma": (m - v) / s, "pull_divides_by": "target sigma",
                      "rule": "|d| <= 0.25 target sigma (gate)", "within_strict": bool(abs(m - v) / s <= 0.25)})
    res["measured_formula_systematic"] = {
        "aub16_minus_camb_frac_at_5_points": [x["frac_aub16_minus_camb"] for x in val["class_and_aubourg_vs_camb"]],
        "primary_minus_secondary_H0_T1": res["primary"]["T1_DR2"]["chain"]["mean"]["H0"]
        - res["secondary"]["T1_DR2"]["chain"]["mean"]["H0"],
        "primary_minus_secondary_H0_T2": res["primary"]["T2_DR1"]["chain"]["mean"]["H0"]
        - res["secondary"]["T2_DR1"]["chain"]["mean"]["H0"],
        "preregistered_proxy_sigma_sys_H0_strict": pre["systematic_budget"]["sigma_sys_H0_strict"],
        "note": "secondary re-run identical to the locked pre-amendment file is expected (fixed seeds, same code "
                "path); it confirms reproducibility, not independent correctness.",
    }
    res["pulls"] = pulls
    # T2 strict/soft boundary vs Monte-Carlo resolution (referee minor issue; verdict unchanged)
    t2res: dict[str, object] = {}
    for analysis in RDFN:
        ch = res[analysis]["T2_DR1"]["chain"]
        dh = abs(ch["mean"]["H0"] - 68.53)
        mc = ch["std"]["H0"] / np.sqrt(ch["ess"])
        t2res[analysis] = {"abs_dH0": dh, "margin_over_strict": dh - strict, "our_mc_error_H0": float(mc),
                           "published_rounding_half_unit": 0.005,
                           "margin_over_combined_resolution": float((dh - strict) / np.hypot(mc, 0.005))}
    t2res["note"] = ("The preregistered rule gives PARTIAL, and PARTIAL is reported. The margin by which |dH0| exceeds "
                     "the strict limit is comparable to our posterior-mean MC error plus the rounding of the published "
                     "68.53; DESI's own MC error is not published, so the strict/soft boundary is not statistically "
                     "resolved.")
    res["T2_boundary_resolution"] = t2res
    print("T2 boundary", json.dumps(t2res), flush=True)
    res["headline"] = {"verdict_primary_T1": res["primary"]["verdict_T1"]["verdict"],
                       "verdict_secondary_T1": res["secondary"]["verdict_T1"]["verdict"],
                       "within_tolerance": res["primary"]["verdict_T1"]["verdict"] == "PASS",
                       "rule": "preregistration.tolerance.verdicts applied to the primary (amendment 1)"}
    res["runtime_s"] = time.time() - t0
    cm.write_json(cm.RESULTS / "fit.json", res)
    cm.write_json(cm.RESULTS / "chains_pointer.json", {"note": "MCMC chains stored on disk 2 (float32 .npy, flat, post burn-in)",
                                                      "chains": POINTERS})
    print("headline", json.dumps(res["headline"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Assemble results/desi_dr2_bao/fit.json from the regenerated stage outputs.

Inputs (all regenerated this stage): controls.json, mcmc_summary.json, grid_summary.json,
camb_crosscheck.json. Applies the preregistered pass rules verbatim
(results/desi_dr2_bao/preregistration.json, "pass_criteria", "failure_definition").
    /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python -B scripts/desi_dr2_bao/assemble_fit.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dr2_model as m  # noqa: E402


def read(name: str) -> dict[str, Any]:
    return json.loads((m.RESULTS / name).read_text())


def main() -> int:
    prereg_sha = m.sha256(m.PREREG)
    assert prereg_sha == m.PREREG_SHA256_EXPECTED, prereg_sha
    prereg = json.loads(m.PREREG.read_text())
    tol = float(prereg["tolerance_sigma"])
    ctl, mc, gr, cb = read("controls.json"), read("mcmc_summary.json"), read("grid_summary.json"), \
        read("camb_crosscheck.json")
    runs, gruns = mc["runs"], gr["runs"]

    where = {"DR2_LCDM_Om": ("DR2_LCDM", "Om"), "DR2_LCDM_hrd_Mpc": ("DR2_LCDM", "h_rd"),
             "DR2_wCDM_Om": ("DR2_wCDM", "Om"), "DR2_wCDM_w": ("DR2_wCDM", "w")}
    results, criteria = [], {}
    for t in prereg["targets"]:
        run, par = where[t["name"]]
        val, std = runs[run]["mean"][par], runs[run]["std"][par]
        gval, gstd = gruns[run]["mean"][par], gruns[run]["std"][par]
        pull = (val - t["value"]) / t["sigma"]
        width = std / t["sigma"]
        results.append({"name": t["name"], "value": val, "sigma": std, "target": t["value"],
                        "target_sigma": t["sigma"], "pull_sigma": pull, "within_0.5sigma": abs(pull) <= tol,
                        "width_ratio": width, "width_ok": 0.8 <= width <= 1.2,
                        "grid_value": gval, "grid_sigma": gstd, "grid_pull_sigma": (gval - t["value"]) / t["sigma"],
                        "emcee_minus_grid_in_emcee_sigma": (val - gval) / std, "source": t["source"]})
        criteria[f"{t['name']}_pull"] = abs(pull) <= tol
        criteria[f"{t['name']}_width"] = 0.8 <= width <= 1.2

    r = runs["DR2_LCDM"]["corr"]["Om__h_rd"]
    criteria["DR2_LCDM_corr"] = abs(r - (-0.92)) <= 0.05
    c2 = gr["runs"]["DR2_LCDM"]["chi2_min_nelder_mead"]["chi2"]
    criteria["DR2_LCDM_bestfit_chi2"] = abs(c2 - 10.2) <= 0.5
    criteria["all_mcmc_converged"] = all(v["status"] == "CONVERGED" for v in runs.values())
    criteria["positive_controls"] = bool(ctl["summary"]["all_positive_controls_pass"])
    criteria["negative_controls_fail_as_required"] = bool(ctl["summary"]["all_negative_controls_fail_as_required"])
    criteria["data_and_prereg_sha256"] = bool(mc["provenance"]["all_data_sha256_match"]
                                              and mc["provenance"]["preregistration_sha256_matches"])
    method_agree = max(abs(x["emcee_minus_grid_in_emcee_sigma"]) for x in results)

    # DR1 wCDM instrument check (secondary; not part of the overall rule)
    d1w = runs["DR1_wCDM"]
    def asym(val: float, tgt: float, sp: float, sm: float) -> float:
        return (val - tgt) / (sp if val > tgt else sm)
    dr1_instr = {
        "DR1_LCDM_Om": {"ours": runs["DR1_LCDM"]["mean"]["Om"], "target": 0.295, "sigma": 0.015,
                        "pull": (runs["DR1_LCDM"]["mean"]["Om"] - 0.295) / 0.015},
        "DR1_LCDM_hrd": {"ours": runs["DR1_LCDM"]["mean"]["h_rd"], "target": 101.8, "sigma": 1.3,
                         "pull": (runs["DR1_LCDM"]["mean"]["h_rd"] - 101.8) / 1.3},
        "DR1_wCDM_Om": {"ours": d1w["mean"]["Om"], "target": 0.293, "sigma": 0.015,
                        "pull": (d1w["mean"]["Om"] - 0.293) / 0.015},
        "DR1_wCDM_w": {"ours": d1w["mean"]["w"], "target": -0.99, "pull": asym(d1w["mean"]["w"], -0.99, 0.15, 0.13)},
        "DR1_wCDM_hrd": {"ours": d1w["mean"]["h_rd"], "target": 101.7,
                         "pull": asym(d1w["mean"]["h_rd"], 101.7, 2.9, 3.5)},
    }

    # DR1 -> DR2 shift
    om1, s1 = runs["DR1_LCDM"]["mean"]["Om"], runs["DR1_LCDM"]["std"]["Om"]
    om2, s2 = runs["DR2_LCDM"]["mean"]["Om"], runs["DR2_LCDM"]["std"]["Om"]
    d = om2 - om1
    s_nest_pre, s_nest_own = 0.01229, math.sqrt(s1**2 - s2**2)
    shift = {"Om_DR1": om1, "sd_DR1": s1, "Om_DR2": om2, "sd_DR2": s2, "Delta_Om": d,
             "published_derived_Delta_Om": 0.0025,
             "sigma_nested_prereg": s_nest_pre, "sigma_nested_own": s_nest_own,
             "sigma_independent_own": math.sqrt(s1**2 + s2**2),
             "Delta_over_sigma_nested_prereg": d / s_nest_pre, "Delta_over_sigma_nested_own": d / s_nest_own,
             "Delta_over_sigma_independent_own": d / math.sqrt(s1**2 + s2**2),
             "pred1_|D-0.0025|<=0.5*sigma_nested": {"prereg_sigma": abs(d - 0.0025) <= 0.5 * s_nest_pre,
                                                     "own_sigma": abs(d - 0.0025) <= 0.5 * s_nest_own},
             "pred2_consistent_|D|/sigma_nested<2": {"prereg_sigma": abs(d) / s_nest_pre < 2,
                                                     "own_sigma": abs(d) / s_nest_own < 2},
             "pred3_DR1_Om_within_0.5sigma_of_0.295": abs(om1 - 0.295) / 0.015 <= 0.5,
             "Delta_hrd": runs["DR2_LCDM"]["mean"]["h_rd"] - runs["DR1_LCDM"]["mean"]["h_rd"]}

    pub = {"lcdm": {"Om": 0.0086, "h_rd": 0.73}, "wcdm": {"Om": 0.0089, "w": 0.078}}
    rad = {}
    for base, key in (("DR2_LCDM", "lcdm"), ("DR2_wCDM", "wcdm")):
        rr = runs[f"{base}_radiation"]
        rad[base] = {"Omega_r": rr["Omega_r"],
                     **{f"shift_{p}_in_published_sigma": (rr["mean"][p] - runs[base]["mean"][p]) / s
                        for p, s in pub[key].items()}}
        rad[base]["significant_gt_0.3sigma"] = any(abs(v) > 0.3 for k, v in rad[base].items()
                                                   if k.startswith("shift_"))

    within = all(criteria.values())
    out = {
        "generated_at": m.utc_now(), "slug": "desi_dr2_bao",
        "preregistration_sha256": prereg_sha, "provenance": mc["provenance"],
        "estimator": "emcee posterior mean/std under DESI flat priors (primary); grid-marginalized posterior (second method); chi2 minimum + Fisher at minimum (third)",
        "emcee_version": mc["emcee_version"], "emcee_version_matches_prereg_3.1.6": mc["emcee_version"] == "3.1.6",
        "results": results,
        "DR2_wCDM_hrd_report_only": {"mean": runs["DR2_wCDM"]["mean"]["h_rd"], "std": runs["DR2_wCDM"]["std"]["h_rd"]},
        "DR2_LCDM_corr_Om_hrd": {"emcee": r, "grid": gruns["DR2_LCDM"]["corr"]["Om__h_rd"],
                                 "fisher_at_min": gruns["DR2_LCDM"]["fisher_at_min"]["corr"]["Om__h_rd"],
                                 "target": -0.92, "tol": 0.05},
        "DR2_LCDM_bestfit": gruns["DR2_LCDM"]["chi2_min_nelder_mead"], "DR2_wCDM_bestfit":
            gruns["DR2_wCDM"]["chi2_min_nelder_mead"],
        "fisher_at_min": {k: gruns[k]["fisher_at_min"] for k in gruns},
        "emcee_vs_grid_max_abs_diff_in_emcee_sigma": method_agree,
        "mcmc_diagnostics": {k: {kk: v[kk] for kk in ("status", "n_steps", "tau", "ess", "n_steps_over_50tau",
                                                      "acceptance_mean")} for k, v in runs.items()},
        "DR1_instrument_checks": dr1_instr,
        "DR1_to_DR2_shift": shift,
        "radiation_sensitivity": rad,
        "camb_crosscheck": {"massless_nu_max_rel_diff": {k: v["max_abs_rel_diff"]
                                                         for k, v in cb["a_massless_nu_exactness"].items()},
                            "primary_model_vs_camb_mnu0.06_shift_in_published_sigma":
                                {k: v["shift_in_published_sigma"]
                                 for k, v in cb["b_primary_model_systematic_vs_camb_mnu0.06"].items()},
                            "planck2018_rdrag_Mpc": cb["c_planck2018_rdrag_Mpc"]},
        "controls_summary": ctl["summary"],
        "criteria": criteria,
        "within_tolerance": within,
        "tolerance_rule": "preregistered overall rule: every target |pull|<=0.5, width ratio in [0.8,1.2], |r+0.92|<=0.05, |chi2_min-10.2|<=0.5, all controls as specified, MCMC converged, sha256 match",
        "figure": "results/desi_dr2_bao/desi_dr2_bao_posteriors.pdf",
    }
    path = m.RESULTS / "fit.json"
    path.write_text(json.dumps(out, indent=1))
    for x in results:
        print(f"{x['name']}: ours {x['value']:.5f} +- {x['sigma']:.5f} | grid {x['grid_value']:.5f} +- "
              f"{x['grid_sigma']:.5f} | target {x['target']} +- {x['target_sigma']} | pull {x['pull_sigma']:+.3f} "
              f"| width {x['width_ratio']:.3f}")
    print("corr", r, "chi2_min", c2, "emcee-vs-grid max", method_agree)
    print("criteria", criteria)
    print("DR1 instrument", json.dumps(dr1_instr))
    print("shift", json.dumps(shift))
    print("radiation", json.dumps(rad))
    print("within_tolerance", within)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

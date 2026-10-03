"""One-shot pre-fit revision of results/bao_bbn_h0/preregistration.json (no fit output exists).

Applies the corrected eq. 2 neutrino convention, the new conservative bound, and relabelled
controls. Kept in the repo so the revision is auditable.
"""
from __future__ import annotations

import json
from pathlib import Path

P = Path("/home/callensxavier_gmail_com/AutoevolveAI/.claude/worktrees/cosmo3-run/results/bao_bbn_h0/preregistration.json")


def main() -> int:
    d = json.loads(P.read_text())
    d["timestamp_utc"] = "2026-09-27T15:53:42Z"
    d["revision_note"] = (
        "Revised before any fit (15:50 -> 15:53 UTC): eq. 2 neutrino convention corrected (eq. 2 pivot 0.1432 "
        "is Omega_m h^2 incl. nu, verified at Planck 2018 Table 1 best fit: -0.016% vs CAMB); conservative box "
        "bound 0.32% -> 0.233%; soft tolerance 0.45 -> 0.33; controls relabelled."
    )
    d["model"]["background"] = (
        "astropy FlatLambdaCDM(H0, Om0=Omega_m-Onu0, Tcmb0=2.7255, Neff=3.044, m_nu=[0.06,0,0]) primary; "
        "independent manual integrator coded without astropy: photons (T=2.7255 K) + the massless-nu share of "
        "N_eff as radiation, the 0.06 eV nu treated as pure matter (inside Omega_m) at z<=2.33; must agree with "
        "astropy to <1e-4 fractional on all observables (if the matter approximation misses this, it is reported, "
        "not tuned away)"
    )
    for t in d["targets"]:
        if t["id"] == "G2":
            t["note"] = (
                "arXiv:2404.03002 gives r_d h = 101.8 +- 1.3 in Sec. 8 (p. 46) but 101.9 +- 1.3 in Sec. 6 (p. 36); "
                "101.8 used (conclusions; same value as the prior bao_flcdm comparison); difference 0.08 sigma."
            )
    s = d["systematic_budget"]
    s["rd_formula_strict_justification"] = (
        "Eq. 16 vs a sourced CAMB model (Planck 2018 Table 1 Plik best fit, r_drag=147.049): -0.020% (matches the "
        "stated 0.021%). Eq. 2 fed its pivot convention (nu-inclusive Omega_m h^2) at the same anchor: -0.016%. "
        "Eq. 2 vs eq. 16 at DESI's DR2 DESI+BBN centre: -0.053%. Anchor B hr_d offset (eq. 16) -0.077% (0.11 sigma "
        "of hr_d; loose, a function of means). Rounded up to 0.10% to cover the part of the BBN omega_b prior outside "
        "eq. 16's validity window (BBN +-2 sigma [0.02108,0.02328] exceeds the Planck-2018-proxy 3 sigma window "
        "[0.02191,0.02281]); this value is a PROXY, not a quoted accuracy."
    )
    s["rd_formula_conservative_frac"] = 0.00233
    s["rd_formula_conservative_justification"] = (
        "max |eq.2(omega_cb+omega_nu) - eq.16(omega_cb)|/eq.16 over omega_b in BBN +-3 sigma and omega_cb in "
        "[0.130,0.155] = 0.233%; box corners lie outside eq. 16's validity window and eq. 2's accuracy is not stated "
        "in any fetched source, so this is a deliberately conservative bound."
    )
    s["sigma_sys_H0_conservative"] = 0.324
    t = d["tolerance"]
    t["soft_H0_km_s_Mpc"] = 0.33
    t["soft_definition"] = "sqrt(0.324^2 + 0.05^2) = 0.328 -> 0.33"
    t["soft_in_units_of_sigma_pub_T1"] = 0.57
    t["strict_in_units_of_sigma_pub_T2"] = 0.19
    t["verdicts"]["PARTIAL"] = (
        "0.15 < |H0 - 68.51| <= 0.33 (consistent only within the conservative formula systematic), other "
        "conditions as PASS"
    )
    t["verdicts"]["FAIL"] = (
        "|H0 - 68.51| > 0.33, or sigma(H0) outside +-15%, or Omega_m condition fails, or gate G1 fails, or any "
        "control misbehaves"
    )
    t["second_check_T2"] = (
        "same strict/soft H0 thresholds (0.15/0.33 km/s/Mpc) against 68.53; sigma(H0) within +-15% of 0.80; "
        "|Omega_m - 0.295| <= 0.25*0.015. Reported separately; headline verdict is T1."
    )
    behaves = {
        "N1": "scrambled data: best-fit chi2 PTE < 1e-3 (while the real data must give PTE > 0.01)",
        "N2": "EdS model on real data: best-fit chi2 PTE < 1e-3",
        "N3": "without BBN prior: posterior sigma(H0) > 5x baseline sigma(H0) (H0 not identified without calibration)",
    }
    neg = []
    for c in d["negative_controls"]:
        if c["id"] not in behaves:
            continue
        c.pop("must_fail_if", None)
        c["control_behaves_if"] = behaves[c["id"]]
        neg.append(c)
    d["negative_controls"] = neg
    d["sensitivity_demonstrations"] = [
        {"id": "S1", "description": "r_d from Aubourg eq. 17 at N_eff=4.044 (wrong early-universe physics). "
         "Deterministic multi-km/s/Mpc shift expected; shows sensitivity to r_d physics but cannot catch a pipeline "
         "bug, so it is NOT counted as a negative control.", "reported_only": True},
        {"id": "S2", "description": "r_d from DESI eq. 2 (nu-inclusive pivot) instead of eq. 16", "reported_only": True},
        {"id": "S3", "description": "radiation removed from H(z)", "reported_only": True},
    ]
    d["p_success_prior"] = {
        "PASS_strict_full_conjunction": 0.55,
        "PASS_or_PARTIAL": 0.8,
        "reasoning": (
            "PASS = H0 within 0.15 AND Omega_m within 0.25 sigma AND sigma(H0) within 15% AND G1 passes AND all "
            "controls behave. Same data/prior as DESI; the only new ingredient is the r_d formula (-0.020% vs CAMB at "
            "the Planck anchor; unmeasured over the low-omega_b part of the BBN prior and vs DESI's newer CAMB, which "
            "is not installed here). Residual risks: posterior-mean projection effects, sampler convergence, and the "
            "tight 0.25 sigma G1 gate."
        ),
    }
    P.write_text(json.dumps(d, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

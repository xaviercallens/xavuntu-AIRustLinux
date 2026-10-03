#!/usr/bin/env python3
"""Write the DESI DR2 BAO preregistration (no fitting happens here).

Computes sha256 of every data file the fit stage will read, stamps a UTC
timestamp, and freezes the targets / tolerances / controls BEFORE any fit of
this problem is run. Targets were read from the fetched papers via the
alphaXiv MCP tools (answer_pdf_queries) on 2026-09-27; see
docs/literature/DESI_DR2_BAO_LITERATURE_REVIEW_2026.md for the quotes.

Run:
    /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python \
        scripts/desi_dr2_bao/write_preregistration.py
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "results" / "desi_dr2_bao" / "preregistration.json"

DATA_FILES: dict[str, Path] = {
    "dr2_mean": DATA_DIR / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_mean.txt",
    "dr2_cov": DATA_DIR / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_cov.txt",
    "dr1_mean": DATA_DIR / "desi_2024_gaussian_bao_ALL_GCcomb_mean.txt",
    "dr1_cov": DATA_DIR / "desi_2024_gaussian_bao_ALL_GCcomb_cov.txt",
    "data_readme": DATA_DIR / "README.md",
}

# Published values (posterior mean, 68% interval), all read from fetched paper text.
DR2_LCDM_OM = (0.2975, 0.0086)
DR2_LCDM_RDH = (101.54, 0.73)
DR2_WCDM_OM = (0.2969, 0.0089)
DR2_WCDM_W = (-0.916, 0.078)
DR1_LCDM_OM = (0.295, 0.015)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    d_om = DR2_LCDM_OM[0] - DR1_LCDM_OM[0]
    sig_nested = math.sqrt(DR1_LCDM_OM[1] ** 2 - DR2_LCDM_OM[1] ** 2)
    sig_indep = math.sqrt(DR1_LCDM_OM[1] ** 2 + DR2_LCDM_OM[1] ** 2)
    return {
        "problem": "desi_dr2_bao",
        "stage": "preregistration (no fit output of this problem has been produced or viewed)",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "revision_history": [
            "r1 2026-09-27T15:49:06Z: first write.",
            "r2 (this file): regenerated BEFORE any fit of this problem, after review: NC1/NC5 "
            "permutations now required to change redshift for every index (index-derangement could "
            "only swap same-z DM/DH pairs); PC1/PC2 chi2 threshold 1e-6 -> 1e-4 with restart rule; PC3 "
            "pulls use Fisher sigma at truth instead of real-data sigma; radiation inputs taken from "
            "astropy instead of a recalled constant; parent-import shim documented.",
        ],
        "literature_review": "docs/literature/DESI_DR2_BAO_LITERATURE_REVIEW_2026.md",
        "data_files": {
            k: {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}
            for k, p in DATA_FILES.items()
        },
        "data_sanity_checks_done_before_prereg": {
            "note": "Not fits. Read-only comparison of the likelihood files to arXiv:2503.14738v3 Table IV.",
            "dr2_n_points": 13,
            "dr2_cov_positive_definite": True,
            "means_match_table_IV_v3_to_rounding": True,
            "diag_sigma_vs_table_IV": "within ~1.5% (e.g. BGS DV 0.0761 file vs 0.075 table)",
            "DM_DH_correlation_file_vs_table_IV_v3": {
                "LRG1": [-0.452, -0.459], "LRG2": [-0.395, -0.404],
                "LRG3+ELG1": [-0.347, -0.416], "ELG2": [-0.398, -0.434],
                "QSO": [-0.494, -0.500], "Lya": [-0.431, -0.431],
            },
            "caveat": "File correlations differ from Table IV (v1 and v3) for LRG3+ELG1 and ELG2. "
                      "Table IV quotes marginal posterior moments; the file is the Gaussian "
                      "likelihood product. Recorded as a known data caveat; not a blocker.",
        },
        "model": {
            "primary": "flat, matter + dark energy only (no radiation, no massive-neutrino "
                       "correction): E(z)^2 = Om(1+z)^3 + (1-Om)(1+z)^(3(1+w)); w=-1 for LCDM. "
                       "D_M = (c/100) int_0^z dz'/E, D_H = c/(100 E); observables divided by (h r_d).",
            "parser": "reuse scripts/bao_flcdm/fit_desi_bao.py load logic (z, value, kind) unchanged; "
                      "only the file paths and E(z) are generalized.",
            "parent_import": "fit_desi_bao.py does 'from datetime import UTC' at top level, which fails "
                             "on the venv-pta Python 3.10. Import via shim: "
                             "'import datetime; datetime.UTC = datetime.timezone.utc' before "
                             "sys.path-inserting scripts/bao_flcdm and importing; reassign module globals "
                             "MEAN_FILE/COV_FILE for DR2; never call the parent main() (it writes into "
                             "results/bao_flcdm). Import+parse of the DR2 files verified (13 points, 13x13 "
                             "cov) before this preregistration; no fit run.",
            "sensitivity_variant": "add radiation with Omega_r = (Ogamma0 + Onu0) taken from "
                                   "astropy FlatLambdaCDM(H0=68, Om0=0.3, Tcmb0=Planck18.Tcmb0, "
                                   "Neff=3.044, m_nu=0) (i.e. h fixed at 0.68); report the shift in "
                                   "each parameter in units of its published sigma. Not a pass/fail "
                                   "criterion; a shift > 0.3 sigma is reported as a significant "
                                   "modelling systematic.",
        },
        "estimators": {
            "primary": "emcee posterior mean and standard deviation under the DESI flat priors",
            "priors": {"Om": [0.01, 0.99], "h_rd_Mpc": [10.0, 1000.0], "w": [-3.0, 1.0]},
            "prior_source": "arXiv:2404.03002 Table 2 (background-only rows); arXiv:2503.14738 Sec. V "
                            "says priors 'match those given in Table 2 of [38]'; [38] identified as "
                            "2404.03002 from context (bibliography entry not read).",
            "sampler": {
                "package": "emcee 3.1.6", "n_walkers": 32, "seed": 20260927,
                "init": "Gaussian ball around (0.30, 101.0[, -1.0]) with widths (0.01, 1.0[, 0.05])",
                "n_steps_min": 20000,
                "convergence": "integrated autocorrelation time tau (emcee.get_autocorr_time) for every "
                               "parameter; require n_steps >= 50*max(tau); burn-in = 5*max(tau); "
                               "thin = max(1, int(tau/2)); effective samples >= 10000. If not met, "
                               "extend in 20000-step blocks up to 200000; if still unmet, report "
                               "UNCONVERGED, not a result.",
            },
            "secondary": "chi^2 minimum (Nelder-Mead, as in fit_desi_bao.py), used only for the "
                         "published best-fit chi^2 target and the controls.",
            "cross_check": "at the best fit, astropy FlatLambdaCDM / FlatwCDM (H0=100) predictions must "
                           "agree with the manual quad predictions to |rel diff| < 1e-5 per observable.",
        },
        "targets": [
            {"name": "DR2_LCDM_Om", "value": DR2_LCDM_OM[0], "sigma": DR2_LCDM_OM[1],
             "estimator": "posterior mean",
             "source": "arXiv:2503.14738v3 eq.(17) p.19 and Table V (DESI, LCDM); identical in v1 eq.(17)"},
            {"name": "DR2_LCDM_hrd_Mpc", "value": DR2_LCDM_RDH[0], "sigma": DR2_LCDM_RDH[1],
             "estimator": "posterior mean",
             "source": "arXiv:2503.14738v3 eq.(17) p.19; identical in v1"},
            {"name": "DR2_wCDM_Om", "value": DR2_WCDM_OM[0], "sigma": DR2_WCDM_OM[1],
             "estimator": "posterior mean", "source": "arXiv:2503.14738v3 Table V, wCDM row 'DESI'"},
            {"name": "DR2_wCDM_w", "value": DR2_WCDM_W[0], "sigma": DR2_WCDM_W[1],
             "estimator": "posterior mean", "source": "arXiv:2503.14738v3 Table V, wCDM row 'DESI'"},
        ],
        "secondary_targets": [
            {"name": "DR2_LCDM_Om_hrd_correlation", "value": -0.92,
             "source": "arXiv:2503.14738v3 text after eq.(17)", "tolerance_abs": 0.05},
            {"name": "DR2_LCDM_bestfit_chi2", "value": 10.2, "dof": 11,
             "source": "arXiv:2503.14738v3 Sec. III.C.1 p.15 ('best-fit chi2/dof = 10.2/(13-2)'); same in v1",
             "estimator": "chi^2 minimum", "tolerance_abs": 0.5},
            {"name": "DR1_wCDM_Om", "value": 0.293, "sigma": 0.015,
             "source": "arXiv:2404.03002 eq.(5.1), Table 3", "use": "instrument check of wCDM code on DR1"},
            {"name": "DR1_wCDM_w", "value": -0.99, "sigma_plus": 0.15, "sigma_minus": 0.13,
             "source": "arXiv:2404.03002 eq.(5.1)", "use": "instrument check of wCDM code on DR1"},
            {"name": "DR1_wCDM_hrd_Mpc", "value": 101.7, "sigma_plus": 2.9, "sigma_minus": 3.5,
             "source": "arXiv:2404.03002 Sec. 6 p.36", "use": "instrument check of wCDM code on DR1"},
        ],
        "report_only_no_target": {
            "DR2_wCDM_hrd_Mpc": "No DR2 BAO-only wCDM h*r_d value found in 2503.14738 (Table V omits it) "
                                "or 2503.14743. Reported, not scored. DR1's 101.7 is NOT reused as a target.",
        },
        "tolerance_sigma": 0.5,
        "tolerance_justification": (
            "Same public data vector and covariance as DESI's Cobaya likelihood, same flat priors, "
            "same estimator (posterior mean). Remaining differences: (i) our E(z) omits radiation and "
            "the 0.06 eV neutrino treatment of CAMB (quantified by the sensitivity variant), (ii) Monte "
            "Carlo error with >=1e4 effective samples (~0.01 sigma). The DR1 re-fit with the parent code "
            "landed 0.07/0.11 sigma from DESI's values. DR2 sigmas are ~40% smaller, so fixed absolute "
            "modelling offsets grow in sigma units; 0.5 sigma leaves room for that while still being "
            "tight enough to catch a wrong model, wrong file or wrong prior."
        ),
        "pass_criteria": {
            "each_target": "|ours - published| <= 0.5 * published sigma",
            "width": "0.8 <= sigma_ours / sigma_published <= 1.2 for each target",
            "correlation": "|r_ours - (-0.92)| <= 0.05",
            "bestfit_chi2": "|chi2_min - 10.2| <= 0.5",
            "overall": "PASS only if every target, width, correlation and chi2 criterion passes AND all "
                       "positive and negative controls behave as specified. Any failure is reported as "
                       "FAIL for that item; nothing is re-tuned after seeing results.",
        },
        "dr1_to_dr2_shift": {
            "estimator": "same emcee pipeline, same priors, run on DR1 and DR2 files; "
                         "Delta_Om = Om_DR2 - Om_DR1 (posterior means)",
            "published_derived_shift": {
                "value": round(d_om, 5),
                "note": "DERIVED from two published numbers (2503.14738 eq.17 minus 2404.03002 eq.4.1); "
                        "DESI does not quote this difference.",
                "sigma_nested": round(sig_nested, 5),
                "sigma_independent": round(sig_indep, 5),
                "shift_in_nested_sigma": round(d_om / sig_nested, 3),
            },
            "significance": "primary: Delta_Om / sqrt(sigma_DR1^2 - sigma_DR2^2) (DR1 is a subset of DR2; "
                            "ideal-nesting approximation); bound: Delta_Om / sqrt(sigma_DR1^2 + sigma_DR2^2)",
            "predictions": [
                "|Delta_Om_ours - 0.0025| <= 0.5 * sigma_nested",
                "|Delta_Om_ours| / sigma_nested < 2 (DR1 and DR2 consistent)",
                "DR1 posterior mean Om within 0.5 sigma of 0.295 +- 0.015 (instrument check)",
            ],
            "also_reported": "per-observable DR1 vs DR2 residuals at the DR2 best fit; the DR1 z list "
                             "differs (DR1 has BGS DV, QSO DV only), so no point-by-point matching is scored.",
        },
        "positive_controls": [
            {"id": "PC0_regression",
             "test": "DR1 files through the extended code, chi^2-minimum, LCDM",
             "pass": "Om within 1e-4 of 0.29389, h_rd within 1e-3 Mpc of 101.9367, chi2 within 1e-3 of "
                     "12.7405 (results/bao_flcdm/desi_dr1_flcdm_fit.json)"},
            {"id": "PC1_noiseless_LCDM_mock",
             "test": "DR2 z/kinds, data = model(Om=0.30, h_rd=101.0), real DR2 covariance",
             "pass": "|dOm| < 1e-4, |dh_rd| < 1e-2 Mpc, chi2_min < 1e-4"},
            {"id": "PC2_noiseless_wCDM_mock",
             "test": "data = model(Om=0.30, w=-0.90, h_rd=101.0)",
             "pass": "|dOm| < 1e-3, |dw| < 1e-3, |dh_rd| < 0.02 Mpc, chi2_min < 1e-4 "
                     "(Nelder-Mead restarted from its own optimum until chi2 stops decreasing, max 5 restarts)"},
            {"id": "PC3_noisy_LCDM_mocks",
             "test": "500 draws from N(model(0.2975, 101.54), C_DR2), numpy default_rng(seed=20260928); "
                     "chi^2-minimum each; pull = (fit - truth)/sigma_Fisher, sigma_Fisher from "
                     "(J^T C^-1 J)^-1 with J the finite-difference model Jacobian at the truth point "
                     "(independent of the real-data fit)",
             "pass": "|mean pull| < 0.15 and 0.88 <= std pull <= 1.12 for Om and h_rd; "
                     "10.3 <= mean chi2_min <= 11.7"},
            {"id": "PC4_two_method_agreement",
             "test": "astropy vs manual quad predictions at best fit, LCDM and wCDM",
             "pass": "max relative difference < 1e-5"},
        ],
        "negative_controls": [
            {"id": "NC1_redshift_permutation",
             "test": "permute the 13 z values among data points with numpy default_rng(seed=101), "
                     "rejection-sampling until z_new[i] != z_old[i] for EVERY i (so same-z DM/DH pair "
                     "swaps cannot count); kinds and values unchanged; record the permutation; LCDM "
                     "chi^2-minimum",
             "must_fail": "PTE(chi2_min, 11 dof) < 1e-3"},
            {"id": "NC2_DM_DH_label_swap",
             "test": "swap every DM_over_rs <-> DH_over_rs label; LCDM chi^2-minimum",
             "must_fail": "PTE(chi2_min, 11 dof) < 1e-3"},
            {"id": "NC3_wrong_model_EdS",
             "test": "Einstein-de Sitter (Om fixed 1, no dark energy), h_rd free, real DR2 data",
             "must_fail": "PTE(chi2_min, 12 dof) < 1e-6"},
            {"id": "NC4_LCDM_on_w-0.7_mock",
             "test": "noiseless mock model(Om=0.30, w=-0.70, h_rd=101.54) fit with LCDM",
             "must_fail": "chi2_min(LCDM) > 9 (wCDM fit to same mock must give chi2_min < 1e-4)"},
            {"id": "NC5_scrambled_covariance",
             "test": "C' = P C P^T for 20 permutations P (default_rng seeds 200..219), each "
                     "rejection-sampled so that every index maps to an index at a different redshift; "
                     "data vector unpermuted; record the permutations; LCDM chi^2-minimum",
             "must_fail": "median PTE over the 20 < 1e-3"},
        ],
        "failure_definition": [
            "Any target outside 0.5 sigma, or width ratio outside [0.8, 1.2].",
            "Any positive control failing, or any negative control passing (not failing): the "
            "pipeline is then not validated and no target comparison is reported as a success.",
            "MCMC unconverged by the rule above.",
            "Data file sha256 differing from this preregistration at fit time.",
        ],
        "lean_plan": "formal/ANSE/DESI_DR2_wCDM.lean (pinned imports as in BAO_FlatLCDM.lean): "
                     "E(z)^2 > 0 for 0<Om<1, z>-1 (any real w); w=-1 reduces to LCDM E^2; "
                     "comoving distance integrand positive hence D_C monotone. Verified only via "
                     "anse/formal/lean_runner.py with in-file #print axioms.",
        "gpu": "not used",
    }


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists; a preregistration is written once, not overwritten.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=1) + "\n")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build the Elenchus claim ledger for the desi_dr2_bao exercise.

Writes results/desi_dr2_bao/ledger/{ledger.json, evidence/<sha256>.json}. Every
evidence blob is written as exact bytes and named by the sha256 of those bytes
(the verifier, Elenchus tools/ledger.py, re-hashes the raw file). Every number
in a blob is read from a regenerated JSON artifact of this run (fit.json,
controls.json, mcmc_summary.json, grid_summary.json, camb_crosscheck.json,
lean_gate.json, lean_gate_negative_control.json) or from page text fetched
with alphaXiv answer_pdf_queries on 2026-09-27; nothing is typed from memory.

Tier caps (Elenchus R-12): lean_axioms -> A, exact_harness -> B,
citation -> L, argument -> C. A claim comparing our numbers with a published
number rests on a citation and is therefore filed at L.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "desi_dr2_bao"
LEDGER_DIR = RES / "ledger"
EVID = LEDGER_DIR / "evidence"
LEAN_FILE = ROOT / "formal" / "ANSE" / "DESI_DR2_wCDM.lean"
LIT = ROOT / "docs" / "literature" / "DESI_DR2_BAO_LITERATURE_REVIEW_2026.md"
REFEREE = RES / "referee_report.json"
AUDITED_LEAN_SHA256 = "3b451bd5a93d682cd05c99fad4681808cb5c18877aa6389dda545dbace5e5adc"
AUDIT_DATE = "2026-09-27"
FETCH = "alphaXiv MCP answer_pdf_queries, page text fetched 2026-09-27 (ledger stage); excerpt whitespace-normalised from the returned PDF page text"


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def load(name: str) -> dict[str, Any]:
    return json.loads((RES / name).read_text())


def put_blob(obj: dict[str, Any]) -> str:
    raw = (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    h = hashlib.sha256(raw).hexdigest()
    (EVID / f"{h}.json").write_bytes(raw)
    return "sha256:" + h


def src(*names: str) -> dict[str, str]:
    return {f"results/desi_dr2_bao/{n}": sha_file(RES / n) for n in names}


def claim(cid: str, tier: str, kind: str, statement: str, deps: list[str],
          evidence: dict[str, Any], audit: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"schema_version": 1, "id": cid, "statement": statement, "tier": tier, "kind": kind,
            "depends_on": deps, "evidence": put_blob(evidence), "audit": audit}


def referee_audit(theorem: str, lean_sha: str) -> dict[str, Any] | None:
    """Audit object from the workflow referee's lean_statement_audit, or None.

    Set only when (a) the referee judged the statement faithful and (b) the Lean
    file is byte-identical to the file the referee audited. The auditor is an
    automated model referee, not a person, and the object says so.
    """
    if lean_sha != AUDITED_LEAN_SHA256:
        return None
    rep = json.loads(REFEREE.read_text())
    hit = [a for a in rep["lean_statement_audit"] if a["theorem"] == theorem]
    if len(hit) != 1 or hit[0]["faithful"] is not True:
        return None
    return {"by": "workflow referee (automated model referee, cosmo3 desi_dr2_bao referee pass); NOT a person",
            "auditor_kind": "model",
            "date": AUDIT_DATE,
            "kind": "statement_adequacy",
            "faithful": True,
            "comment_verbatim": hit[0]["comment"],
            "audited_file": rel(LEAN_FILE),
            "audited_file_sha256": AUDITED_LEAN_SHA256,
            "report": rel(REFEREE),
            "report_sha256": sha_file(REFEREE),
            "caveat": "Elenchus LEDGER_UNAUDITED_TIER_A asks for a person's certification; this audit is a model's. A human statement audit is still outstanding."}


def main() -> int:
    if EVID.exists():
        shutil.rmtree(EVID)
    EVID.mkdir(parents=True)

    fit = load("fit.json")
    ctl = load("controls.json")
    mc = load("mcmc_summary.json")
    gr = load("grid_summary.json")
    cb = load("camb_crosscheck.json")
    gate = load("lean_gate.json")
    neg = load("lean_gate_negative_control.json")
    log_lines = (RES / "lean_gate.log").read_text().strip().splitlines()
    lean_sha = sha_file(LEAN_FILE)
    assert lean_sha == gate["lean_file_sha256"], "Lean file changed since the gate ran"
    assert gate["gate_pass"] and gate["rc"] == 0 and gate["elenchus"]["rc"] == 0
    assert lean_sha == AUDITED_LEAN_SHA256, "Lean file differs from the file the referee audited; audits would not apply"
    res = {x["name"]: x for x in fit["results"]}
    claims: list[dict[str, Any]] = []

    # ---------------- Tier A: kernel-verified Lean theorems ----------------
    glosses = {
        "E2_pos": "for 0 < Om < 1, z >= 0 and every real w, Om(1+z)^3 + (1-Om)(1+z)^(3(1+w)) > 0 (real power)",
        "E_pos": "for 0 < Om < 1, z >= 0 and every real w, E(z) = sqrt(E2) > 0",
        "E_w_neg_one": "for every Om, z: the wCDM E at w = -1 equals ANSE.BAOFlatLCDM.E Om z (the DR1 flat-LCDM E)",
        "E_strictMonoOn_of_neg_one_le": "for 0 < Om < 1 and w >= -1, E is strictly increasing on [0, inf)",
        "invE_continuousOn": "for 0 < Om < 1 and every real w, t -> 1/E(t) is continuous on [0, inf)",
        "Dc_strictMonoOn": "for 0 < Om < 1 and every real w, D_C(z) = integral_0^z dt/E(t) is strictly increasing on [0, inf)",
    }
    a_ids = []
    for i, (thm, gloss) in enumerate(glosses.items(), start=1):
        full = f"ANSE.DESIDR2wCDM.{thm}"
        line = [ln for ln in log_lines if ln.startswith(f"'{full}'")]
        assert len(line) == 1 and gate["theorems"][full]["footprint_ok"] and gate["theorems"][full]["sorry_free"]
        cid = f"DR2-A-{i:04d}"
        a_ids.append(cid)
        claims.append(claim(cid, "A", "lean_axioms",
            f"{full} ({gloss}) is kernel-verified with axioms exactly [propext, Classical.choice, Quot.sound]; no sorryAx, no smuggled axiom.",
            [], {
                "theorem": full,
                "file": rel(LEAN_FILE),
                "source_sha256": lean_sha,
                "lean_toolchain": gate["toolchain"],
                "command": gate["command"],
                "build_root": gate["build_root"],
                "build_root_note": "shared checkout's formal/ Lake project (partial Mathlib build); the ANSE.BAO_FlatLCDM olean imported by this file comes from that build; lake env lean writes nothing git-tracked",
                "compile_rc": gate["rc"],
                "kernel_axiom_footprint": line[0],
                "gate": "scripts/desi_dr2_bao/lean_gate.py (compile + in-file #print axioms + sorryAx rejection + whitelist {propext, Classical.choice, Quot.sound}); NOT anse/formal/lean_runner.py, which requires a lake build of the module",
                "gate_output": src("lean_gate.json", "lean_gate.log"),
                "gate_timestamp_utc": gate["timestamp_utc"],
                "elenchus_check": {"rc": gate["elenchus"]["rc"], "output": gate["elenchus"]["output"]},
                "elenchus_negative_control": {"file": "results/desi_dr2_bao/lean_gate_negative_control.json",
                                              "sha256": sha_file(RES / "lean_gate_negative_control.json"),
                                              "verdict": neg["verdict"]},
                "statement_audit": "see the claim's audit object (automated model referee, results/desi_dr2_bao/referee_report.json); no person has audited it",
                "preregistration_deviation": ("lean_plan preregistered E(z)^2 > 0 for z > -1; E2_pos/E_pos are proved for z >= 0 (strictly narrower; covers every data redshift and the prior box). Left unchanged in the fix round so the audit binds to the audited file."
                                              if thm in ("E2_pos", "E_pos") else None),
            }, referee_audit(full, lean_sha)))

    # ---------------- Tier B: exact harness (our own computations) ----------------
    d2l, d2w = mc["runs"]["DR2_LCDM"], mc["runs"]["DR2_wCDM"]
    g2l, g2w = gr["runs"]["DR2_LCDM"], gr["runs"]["DR2_wCDM"]
    bf_l, bf_w = fit["DR2_LCDM_bestfit"], fit["DR2_wCDM_bestfit"]
    fisher = fit["fisher_at_min"]
    rr = load("fixround_rerun_check.json")
    assert rr["all_identical"], "fix-round regeneration did not reproduce the chains"
    common_note = ("mcmc_fit.py received an annotation-only edit (return type on make_log_prob) at 16:16Z, after the first chains "
                   "were written (16:08-16:12Z). Fix round: all 6 chains and both grids were regenerated from the current "
                   f"mcmc_fit.py (sha256 {rr['scripts_sha256']['mcmc_fit.py']}) and grid_posterior.py; every chain is np.array_equal "
                   "to its predecessor and both summaries are identical apart from timestamps (results/desi_dr2_bao/fixround_rerun_check.json)")
    claims.append(claim("DR2-B-0001", "B", "exact_harness",
        f"Flat-LCDM BAO-only fit of the real DESI DR2 Gaussian BAO file (13 points, 13x13 cov, sha256 = preregistered): emcee posterior "
        f"Om = {d2l['mean']['Om']:.5f} +- {d2l['std']['Om']:.5f}, h*rd = {d2l['mean']['h_rd']:.3f} +- {d2l['std']['h_rd']:.3f} Mpc, "
        f"corr = {d2l['corr']['Om__h_rd']:.4f} (CONVERGED, 20000 steps, ESS {d2l['ess']:.0f}); independent grid posterior "
        f"Om = {g2l['mean']['Om']:.5f} +- {g2l['std']['Om']:.5f}, h*rd = {g2l['mean']['h_rd']:.3f} +- {g2l['std']['h_rd']:.3f}; "
        f"chi2_min = {bf_l['chi2']:.3f} on {bf_l['dof']} dof.",
        [], {
            "sources": src("fit.json", "mcmc_summary.json", "grid_summary.json", "fixround_rerun_check.json"),
            "data_sha256_match_preregistration": fit["provenance"]["all_data_sha256_match"],
            "preregistration_sha256": fit["preregistration_sha256"],
            "emcee": {"version": mc["emcee_version"], "seed": mc["seed"], "n_walkers": mc["n_walkers"],
                      "mean": d2l["mean"], "std": d2l["std"], "corr": d2l["corr"], "status": d2l["status"],
                      "tau": d2l["tau"], "ess": d2l["ess"], "n_steps": d2l["n_steps"],
                      "reproducibility": mc["reproducibility"]},
            "grid": {"mean": g2l["mean"], "std": g2l["std"], "corr": g2l["corr"], "n_per_axis": g2l["n_per_axis"],
                     "edge_marginal_mass": g2l["edge_marginal_mass"]},
            "chi2_min": bf_l, "fisher_at_min": fisher["DR2_LCDM"],
            "note": common_note,
        }))
    claims.append(claim("DR2-B-0002", "B", "exact_harness",
        f"Flat-wCDM BAO-only fit of the same DR2 file: emcee posterior Om = {d2w['mean']['Om']:.5f} +- {d2w['std']['Om']:.5f}, "
        f"w = {d2w['mean']['w']:.4f} +- {d2w['std']['w']:.4f}, h*rd = {d2w['mean']['h_rd']:.2f} +- {d2w['std']['h_rd']:.2f} Mpc "
        f"(h*rd report-only; CONVERGED); grid posterior Om = {g2w['mean']['Om']:.5f} +- {g2w['std']['Om']:.5f}, "
        f"w = {g2w['mean']['w']:.4f} +- {g2w['std']['w']:.4f}; chi2_min = {bf_w['chi2']:.3f} on {bf_w['dof']} dof.",
        [], {
            "sources": src("fit.json", "mcmc_summary.json", "grid_summary.json"),
            "emcee": {"mean": d2w["mean"], "std": d2w["std"], "corr": d2w["corr"], "status": d2w["status"],
                      "tau": d2w["tau"], "ess": d2w["ess"], "n_steps": d2w["n_steps"]},
            "grid": {"mean": g2w["mean"], "std": g2w["std"], "corr": g2w["corr"], "n_per_axis": g2w["n_per_axis"]},
            "chi2_min": bf_w, "fisher_at_min": fisher["DR2_wCDM"],
            "emcee_vs_grid_max_abs_diff_in_emcee_sigma": fit["emcee_vs_grid_max_abs_diff_in_emcee_sigma"],
            "note": common_note,
        }))
    pc = ctl["positive_controls"]
    claims.append(claim("DR2-B-0003", "B", "exact_harness",
        "All preregistered positive controls pass: PC0 DR1 regression reproduces Om 0.29389 / h*rd 101.9367 / chi2 12.7405; "
        f"PC1 noiseless LCDM mock |dOm| = {abs(pc['PC1_noiseless_LCDM']['dOm']):.1e}; PC2 noiseless wCDM mock |dw| = {abs(pc['PC2_noiseless_wCDM']['dw']):.1e}; "
        f"PC3 500 noisy mocks pull mean Om {pc['PC3_noisy_LCDM_draws']['mean_pull']['Om']:.3f}, std {pc['PC3_noisy_LCDM_draws']['std_pull']['Om']:.3f}, "
        f"mean chi2_min {pc['PC3_noisy_LCDM_draws']['mean_chi2_min']:.2f}; PC4 astropy vs quad max rel diff {pc['PC4_astropy_vs_quad']['max_rel_diff_lcdm']:.1e}.",
        [], {"source": src("controls.json"), "positive_controls": pc,
             "gl_integrator_validation": ctl["gl_integrator_validation"], "summary": ctl["summary"]}))
    nc = ctl["negative_controls"]
    claims.append(claim("DR2-B-0004", "B", "exact_harness",
        "All preregistered negative controls fail as required: NC1 redshift permutation (every z changed) chi2 "
        f"{nc['NC1_redshift_permutation']['chi2']:.0f}; NC2 DM/DH swap chi2 {nc['NC2_DM_DH_label_swap']['chi2']:.0f}; "
        f"NC3 Einstein-de Sitter chi2 {nc['NC3_wrong_model_EdS']['chi2']:.1f} (PTE {nc['NC3_wrong_model_EdS']['pte']:.1e}); "
        f"NC4 LCDM on a w=-0.7 mock chi2 {nc['NC4_LCDM_on_w-0.7_synthetic']['lcdm_fit']['chi2']:.2f} > 9; "
        f"NC5 20 scrambled covariances median PTE {nc['NC5_scrambled_covariance']['median_pte']:.1e} < 1e-3 "
        f"(aggregate only: {sum(r['pte'] > 1e-3 for r in nc['NC5_scrambled_covariance']['runs'])} of {len(nc['NC5_scrambled_covariance']['runs'])} single scrambled fits have PTE > 1e-3).",
        [], {"source": src("controls.json"),
             "negative_controls": {k: {kk: vv for kk, vv in v.items() if kk != "runs"} for k, v in nc.items()},
             "NC5_per_run_chi2": [x["chi2"] for x in nc["NC5_scrambled_covariance"]["runs"]],
             "NC5_per_run_seed_pte": [[x["seed"], x["pte"]] for x in nc["NC5_scrambled_covariance"]["runs"]]}))
    a_ = cb["a_massless_nu_exactness"]
    b_ = cb["b_primary_model_systematic_vs_camb_mnu0.06"]
    claims.append(claim("DR2-B-0005", "B", "exact_harness",
        f"CAMB {cb['camb_version']} background cross-check: with massless neutrinos CAMB D_M and H agree with our quad path to "
        f"{max(a_['w=-1.0']['max_abs_rel_diff'], a_['w=-0.9']['max_abs_rel_diff']):.1e} relative (w=-1 and w=-0.9); fitting the primary "
        f"model (no radiation, no nu mass) to a noiseless CAMB 0.06 eV data vector shifts Om by {b_['lcdm']['shift_in_published_sigma']['Om']:+.3f} sigma, "
        f"h*rd by {b_['lcdm']['shift_in_published_sigma']['h_rd']:+.3f} sigma (LCDM) and w by {b_['wcdm']['shift_in_published_sigma']['w']:+.3f} sigma; "
        f"Planck-2018 rdrag = {cb['c_planck2018_rdrag_Mpc']:.4f} Mpc.",
        [], {"source": src("camb_crosscheck.json"), "a": a_,
             "b_shifts": {m: b_[m]["shift_in_published_sigma"] for m in ("lcdm", "wcdm")},
             "planck2018_rdrag_Mpc": cb["c_planck2018_rdrag_Mpc"]}))
    rad = fit["radiation_sensitivity"]
    claims.append(claim("DR2-B-0006", "B", "exact_harness",
        f"Radiation sensitivity variant (Omega_r = {rad['DR2_LCDM']['Omega_r']:.3e} from astropy): shifts Om by "
        f"{rad['DR2_LCDM']['shift_Om_in_published_sigma']:+.3f} sigma, h*rd by {rad['DR2_LCDM']['shift_h_rd_in_published_sigma']:+.3f} sigma (LCDM) "
        f"and w by {rad['DR2_wCDM']['shift_w_in_published_sigma']:+.4f} sigma (wCDM); none exceeds the preregistered 0.3 sigma flag.",
        [], {"sources": src("fit.json", "mcmc_summary.json"), "radiation_sensitivity": rad,
             "runs": {k: {"mean": mc["runs"][k]["mean"], "std": mc["runs"][k]["std"], "status": mc["runs"][k]["status"]}
                      for k in ("DR2_LCDM_radiation", "DR2_wCDM_radiation")}}))
    d1l, d1w = mc["runs"]["DR1_LCDM"], mc["runs"]["DR1_wCDM"]
    claims.append(claim("DR2-B-0007", "B", "exact_harness",
        f"Same emcee pipeline on the DESI DR1 file (12 points): LCDM Om = {d1l['mean']['Om']:.5f} +- {d1l['std']['Om']:.5f}, "
        f"h*rd = {d1l['mean']['h_rd']:.3f} +- {d1l['std']['h_rd']:.3f} Mpc; wCDM Om = {d1w['mean']['Om']:.5f}, w = {d1w['mean']['w']:.4f}, "
        f"h*rd = {d1w['mean']['h_rd']:.2f} Mpc (both CONVERGED).",
        [], {"sources": src("mcmc_summary.json", "fit.json"),
             "DR1_LCDM": {k: d1l[k] for k in ("mean", "std", "corr", "status", "ess", "tau")},
             "DR1_wCDM": {k: d1w[k] for k in ("mean", "std", "corr", "status", "ess", "tau")}}))
    sh = fit["DR1_to_DR2_shift"]
    claims.append(claim("DR2-B-0008", "B", "exact_harness",
        f"DR1->DR2 shift from our own two posteriors: Delta Om = {sh['Delta_Om']:+.5f}, Delta h*rd = {sh['Delta_hrd']:+.3f} Mpc; "
        f"Delta Om / sigma_nested(own = {sh['sigma_nested_own']:.5f}) = {sh['Delta_over_sigma_nested_own']:.3f}, "
        f"/ sigma_independent(own) = {sh['Delta_over_sigma_independent_own']:.3f}. sigma_nested is an ideal-nesting approximation.",
        ["DR2-B-0001", "DR2-B-0007"], {"source": src("fit.json"), "DR1_to_DR2_shift": sh}))

    # ---------------- Tier L: literature (fetched page text) ----------------
    lit_ptr = {"literature_review": rel(LIT), "literature_review_sha256": sha_file(LIT)}
    claims.append(claim("DR2-L-0001", "L", "citation",
        "arXiv:2503.14738v3 eq.(17): DESI DR2 BAO-only flat LCDM Om = 0.2975 +- 0.0086, h*rd = (101.54 +- 0.73) Mpc, correlation coefficient r = -0.92 (posterior mean and std).",
        [], {"source": "DESI Collaboration, DESI DR2 Results II, arXiv:2503.14738v3 (9 Oct 2025), p.19", "fetched_via": FETCH,
             "excerpt": "We find Ωm = 0.2975 ± 0.0086, hrd = (101.54 ± 0.73) Mpc, DESI DR2, (17) with a correlation coefficient of r = −0.92.",
             "estimator_excerpt": "For 1D marginalized posterior results we quote the mean and standard deviation when the distributions are symmetric",
             **lit_ptr}))
    claims.append(claim("DR2-L-0002", "L", "citation",
        "arXiv:2503.14738v3 Table V, wCDM row 'DESI' (DR2 BAO alone): Om = 0.2969 +- 0.0089, w = -0.916 +- 0.078 (marginalized posterior means); no h*rd given. Read from v3 only.",
        [], {"source": "arXiv:2503.14738v3 Table V, p.20", "fetched_via": FETCH,
             "excerpt": "wCDM ... DESI 0.2969 ± 0.0089 — — −0.916 ± 0.078 —",
             "caption_excerpt": "Results quoted for all parameters are the marginalized posterior means and 68% credible intervals",
             **lit_ptr}))
    claims.append(claim("DR2-L-0003", "L", "citation",
        "arXiv:2503.14738v3 Sec. III.C.1 (p.15): the joint LCDM fit to all DR2 tracers returns best-fit chi2/dof = 10.2/(13 - 2).",
        [], {"source": "arXiv:2503.14738v3 p.15", "fetched_via": FETCH,
             "excerpt": "The joint fit to all tracers returns a best-fit χ2/dof = 10.2/(13 − 2).", **lit_ptr}))
    claims.append(claim("DR2-L-0004", "L", "citation",
        "arXiv:2404.03002v3: DESI DR1 BAO alone gives flat LCDM Om = 0.295 +- 0.015, rd*h = (101.8 +- 1.3) Mpc (eq. 4.1), flat wCDM Om = 0.293 +- 0.015, w = -0.99 +0.15/-0.13 (eq. 5.1), and wCDM rd*h = (101.7 +2.9/-3.5) Mpc (Sec. 6, p.36).",
        [], {"source": "DESI Collaboration, DESI 2024 VI, arXiv:2404.03002v3, pp.21 and 27", "fetched_via": FETCH,
             "excerpt_4_1": "Ωm = 0.295 ± 0.015, rdh = (101.8 ± 1.3) Mpc, DESI BAO, (4.1)",
             "excerpt_5_1": "Ωm = 0.293 ± 0.015, w = −0.99 +0.15 −0.13, DESI BAO, (5.1)",
             "excerpt_sec6_p36": "r d h = (101.7 +2.9 −3.5) Mpc (wCDM)",
             "dr1_wcdm_hrd_note": "the DR1 wCDM rd*h = 101.7 (+2.9/-3.5) Mpc instrument-check value (2404.03002v3 Sec. 6, printed p.36 = PDF page 39) was re-fetched with alphaXiv answer_pdf_queries in the fix round (2026-09-27) and matches the literature review",
             **lit_ptr}))
    claims.append(claim("DR2-L-0005", "L", "citation",
        "Priors: arXiv:2404.03002v3 Table 2 gives flat priors Om ~ U[0.01, 0.99], rd*h ~ U[10, 1000] Mpc, w ~ U[-3, 1]; arXiv:2503.14738v3 Sec. V states its priors 'match those given in Table 2 of [38]'. That [38] = 2404.03002 is inferred from context (bibliography entry not read).",
        [], {"source": "arXiv:2404.03002v3 Table 2 p.16; arXiv:2503.14738v3 Sec. V p.19", "fetched_via": FETCH,
             "excerpt_table2": "background-only Ωm — U[0.01, 0.99]; no rd calibration rdh (Mpc) — U[10, 1000]; extended w0 or w −1 U[−3, 1]",
             "excerpt_2503": "Prior ranges on all sampled parameters match those given in Table 2 of [38].",
             "inference_caveat": "[38] identified as 2404.03002 because 2503.14738 p.15 says 'In [38] we reported a ~3σ difference between the DESI DR1 value of DM/rd measured in the LRG2 redshift bin'",
             **lit_ptr}))

    # ---------------- Tier L: comparisons (rest on citations) ----------------
    pulls = {n: {k: res[n][k] for k in ("value", "sigma", "target", "target_sigma", "pull_sigma", "width_ratio",
                                         "within_0.5sigma", "width_ok")} for n in res}
    claims.append(claim("DR2-L-0006", "L", "citation",
        "The four preregistered DR2 targets are reproduced within 0.5 published sigma with width ratios in [0.8, 1.2]: pulls "
        + ", ".join(f"{n} {res[n]['pull_sigma']:+.3f}" for n in res)
        + "; width ratios " + ", ".join(f"{res[n]['width_ratio']:.3f}" for n in res) + ".",
        ["DR2-B-0001", "DR2-B-0002", "DR2-L-0001", "DR2-L-0002", "DR2-L-0005"],
        {"source": src("fit.json"), "results": pulls, "tolerance_rule": fit["tolerance_rule"]}))
    corr = fit["DR2_LCDM_corr_Om_hrd"]
    claims.append(claim("DR2-L-0007", "L", "citation",
        f"Secondary DR2 criteria pass: chi2_min = {bf_l['chi2']:.3f} vs published 10.2 (|diff| <= 0.5); emcee corr(Om, h*rd) = {corr['emcee']:.4f} vs published -0.92 (|diff| <= 0.05).",
        ["DR2-B-0001", "DR2-L-0001", "DR2-L-0003"],
        {"source": src("fit.json"), "chi2_min": bf_l["chi2"], "corr": corr,
         "criteria": {k: fit["criteria"][k] for k in ("DR2_LCDM_corr", "DR2_LCDM_bestfit_chi2")}}))
    dr1c = fit["DR1_instrument_checks"]
    claims.append(claim("DR2-L-0008", "L", "citation",
        "DR1 instrument checks: our DR1 posterior means sit within 0.07 published sigma of DESI DR1: "
        + ", ".join(f"{k} pull {v['pull']:+.4f}" for k, v in dr1c.items()) + ".",
        ["DR2-B-0007", "DR2-L-0004"], {"source": src("fit.json"), "DR1_instrument_checks": dr1c}))
    claims.append(claim("DR2-L-0009", "L", "citation",
        f"Our Delta Om = {sh['Delta_Om']:+.5f} vs the published-derived +0.0025 (2503.14738 eq.17 minus 2404.03002 eq.4.1; DESI does not quote this difference): "
        f"Delta/sigma_nested(prereg 0.01229) = {sh['Delta_over_sigma_nested_prereg']:.3f}; all three preregistered shift predictions pass under both sigma choices.",
        ["DR2-B-0008", "DR2-L-0001", "DR2-L-0004"],
        {"source": src("fit.json"), "DR1_to_DR2_shift": sh,
         "published_derived": "0.2975 (2503.14738v3 eq.17) - 0.295 (2404.03002v3 eq.4.1) = +0.0025; sigma_nested = sqrt(0.015^2 - 0.0086^2) = 0.01229 (preregistered)"}))
    claims.append(claim("DR2-L-0010", "L", "citation",
        "Preregistered overall verdict within_tolerance = true: all 14 criteria (4 pulls, 4 widths, correlation, chi2, MCMC convergence, positive controls, negative controls, sha256) are true.",
        ["DR2-L-0006", "DR2-L-0007", "DR2-B-0003", "DR2-B-0004"],
        {"source": src("fit.json", "preregistration.json"), "criteria": fit["criteria"],
         "within_tolerance": fit["within_tolerance"]}))

    # ---------------- Tier C: faithfulness argument ----------------
    claims.append(claim("DR2-C-0001", "C", "argument",
        "The Lean definitions E2/E/Dc in formal/ANSE/DESI_DR2_wCDM.lean are the expressions evaluated by scripts/desi_dr2_bao/dr2_model.py with orad = 0: "
        "e_of_z = sqrt(om*zp1**3 + (1-om)*zp1**(3*(1+w))) and D_C = integral_0^z dt/E(t); hypotheses 0 < Om < 1 strictly contain the prior box [0.01, 0.99]. "
        "Reviewed by reading, not machine-checked; the automated workflow referee reached the same reading (referee_report.json); no person has reviewed it.",
        a_ids, {"lean_file": rel(LEAN_FILE), "lean_sha256": lean_sha,
                "model_file": "scripts/desi_dr2_bao/dr2_model.py",
                "model_sha256": sha_file(ROOT / "scripts" / "desi_dr2_bao" / "dr2_model.py"),
                "python_e_of_z": "return np.sqrt(om * zp1**3 + orad * zp1**4 + ode * zp1 ** (3.0 * (1.0 + w)))  with ode = 1 - om - orad",
                "lean_E2": "Om * (1 + z) ^ 3 + (1 - Om) * (1 + z) ^ (3 * (1 + w))",
                "scope_limit": "orad > 0 (sensitivity variant) is not formalised; w < -1 monotonicity of E is not claimed"}))

    ledger = {"schema_version": 1, "claims": claims}
    (LEDGER_DIR / "ledger.json").write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(claims)} claims, {len(list(EVID.iterdir()))} blobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

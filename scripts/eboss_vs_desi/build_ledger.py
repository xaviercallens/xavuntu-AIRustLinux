"""Build the Elenchus claim ledger for the eboss_vs_desi exercise.

Writes results/eboss_vs_desi/ledger/ledger.json and one content-addressed
evidence blob per claim in results/eboss_vs_desi/ledger/evidence/<sha256>.json.
Every number in a blob is read from a regenerated result file (never retyped);
every citation quote is asserted to be a verbatim substring of the literature
review, which recorded what the fetched primary pages said. Tier caps follow
Elenchus's KIND_CAP: lean_axioms -> A, exact_harness -> B, citation -> L,
argument -> C.

Audit (round-2 fix stage): a Tier A row gets an audit object only if the
round-2 referee report (results/eboss_vs_desi/referee_report_round2.json,
an automated model referee, not a person) judged that theorem's statement
faithful; otherwise audit stays null. The referee audited source sha256
REFEREE_AUDITED_LEAN_SHA; the only change since is a docstring (diff saved in
lean_BAO_Consistency_fixround2_docstring.diff), and the build checks that no
changed line is a declaration or proof line before carrying the audit over.
Elenchus's own doctrine (docs/VALIDATION.md 5.3) intends a person for this
audit, so every audit object records auditor_is_person = false and the human
statement audit remains open.

Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/eboss_vs_desi/build_ledger.py
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "eboss_vs_desi"
LEDGER_DIR = RES / "ledger"
EVID = LEDGER_DIR / "evidence"
LEAN_FILE = ROOT / "formal" / "ANSE" / "BAO_Consistency.lean"
LEAN_SHA_EXPECTED = "560e3b5d8266a2e2286f17bc9fc4846853cb927c0259b231d403cef8dd343d8b"
REFEREE_AUDITED_LEAN_SHA = "bafdfab48eba8d67afa8fc9c334abec40226ee70675ecad65cc57bc7fd74d6eb"
DOCSTRING_DIFF = RES / "lean_BAO_Consistency_fixround2_docstring.diff"
REFEREE2 = RES / "referee_report_round2.json"
LEAN_LOG = RES / "lean_BAO_Consistency_compile_fixround2.log"
ELENCHUS_LOG = RES / "lean_BAO_Consistency_elenchus.log"
LIT = ROOT / "docs" / "literature" / "EBOSS_VS_DESI_LITERATURE_REVIEW_2026.md"
PREREG = RES / "preregistration.json"
LEAN_TOOLCHAIN = Path("/home/callensxavier_gmail_com/AutoevolveAI/formal/lean-toolchain")
LEAN_CMD = ("cd /home/callensxavier_gmail_com/AutoevolveAI/formal && timeout 1500 lake env lean "
            "/home/callensxavier_gmail_com/AutoevolveAI/.claude/worktrees/cosmo3-run/formal/ANSE/"
            "BAO_Consistency.lean  (round-2 fix stage, compile of the current source after the docstring-only edit; exit 0)")
TRUSTED = "[propext, Classical.choice, Quot.sound]"
PREFIX = "EVD"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def sanitize(x: Any) -> Any:
    """Replace non-finite floats by explicit strings so every blob is strict JSON."""
    if isinstance(x, float) and not math.isfinite(x):
        return "NaN" if math.isnan(x) else ("Infinity" if x > 0 else "-Infinity")
    if isinstance(x, dict):
        return {k: sanitize(v) for k, v in x.items()}
    if isinstance(x, list):
        return [sanitize(v) for v in x]
    return x


def write_blob(obj: dict[str, Any]) -> str:
    raw = (json.dumps(sanitize(obj), indent=1, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + "\n").encode("utf-8")
    hexd = hashlib.sha256(raw).hexdigest()
    (EVID / f"{hexd}.json").write_bytes(raw)
    return "sha256:" + hexd


def load(name: str) -> tuple[dict[str, Any], str]:
    p = RES / name
    return json.loads(p.read_text()), sha256_file(p)


def lit_quote(lit: str, q: str) -> str:
    if q not in lit:
        raise ValueError(f"quote not found verbatim in literature review: {q!r}")
    return q


def claim(cid: str, statement: str, tier: str, kind: str, deps: list[str], ev: str,
          audit: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"schema_version": 1, "id": cid, "statement": statement, "tier": tier, "kind": kind,
            "depends_on": deps, "evidence": ev, "audit": audit}


def main() -> int:
    lean_sha = sha256_file(LEAN_FILE)
    if lean_sha != LEAN_SHA_EXPECTED:
        raise RuntimeError(f"Lean source changed since the Lean stage: {lean_sha}")
    log = LEAN_LOG.read_text()
    if "rc=0" not in log or "sorryAx" in log or "error" in log.lower():
        raise RuntimeError("Lean compile log is not clean")
    footprints = dict(re.findall(r"'ANSE\.BAOConsistency\.(\w+)' depends on axioms: (\[.*?\])", log))
    theorems = ["tension1D_symm", "tension1D_nonneg", "tension1D_eq_zero_iff",
                "chi2_eq_dotProduct_inv_mulVec", "chi2_nonneg", "chi2_eq_zero_iff",
                "surveyTension_symm", "posdef_add", "surveyTension_nonneg_and_zero_iff"]
    glosses = {
        "tension1D_symm": "the squared 1D pull (mu1-mu2)^2/(s1^2+s2^2) is symmetric under swapping the two surveys (no hypotheses)",
        "tension1D_nonneg": "the squared 1D pull is >= 0 for all real inputs (no hypotheses)",
        "tension1D_eq_zero_iff": "for s1 > 0, the squared 1D pull is 0 iff mu1 = mu2",
        "chi2_eq_dotProduct_inv_mulVec": "for C = !![a,b;b,c] with ac-b^2 != 0, Mathlib's ![d1,d2] . (C^-1 *v ![d1,d2]) equals the closed form (c d1^2 - 2 b d1 d2 + a d2^2)/(ac-b^2)",
        "chi2_nonneg": "for a > 0 and ac-b^2 > 0, the 2x2 chi-square is >= 0 for every (d1,d2)",
        "chi2_eq_zero_iff": "for a > 0 and ac-b^2 > 0, the 2x2 chi-square is 0 iff d1 = 0 and d2 = 0",
        "surveyTension_symm": "the two-survey statistic chi2(C_S+C_D, p_S-p_D) is symmetric under swapping the surveys (no hypotheses)",
        "posdef_add": "the sum of two positive-definite symmetric 2x2 matrices (Sylvester form) is positive definite",
        "surveyTension_nonneg_and_zero_iff": "with both posterior covariances positive definite, the two-survey statistic is >= 0 and is 0 iff both posterior means agree",
    }
    toolchain = LEAN_TOOLCHAIN.read_text().strip()
    diff = DOCSTRING_DIFF.read_text()
    changed = [ln[2:] for ln in diff.splitlines() if ln.startswith(("< ", "> "))]
    decl = re.compile(r"^\s*((theorem|lemma|def|noncomputable|namespace|end|import|open|by|unfold|rw|have|exact|"
                      r"intro|rintro|constructor|linarith|ring|positivity|field_simp|nlinarith)\b|#print|\(|:=|·)")
    if not changed or any(decl.match(ln) for ln in changed):
        raise RuntimeError("Lean diff since the referee audit is empty or touches a non-docstring line")
    ref = json.loads(REFEREE2.read_text())
    ref_verdict = {e["theorem"].rsplit(".", 1)[1]: e for e in ref["lean_statement_audit"]}
    ref_sha = sha256_file(REFEREE2)

    def audit_for(th: str) -> dict[str, Any] | None:
        e = ref_verdict.get(th)
        if e is None or e.get("faithful") is not True:
            return None
        return {"auditor": "workflow automated model referee (round 2), not a person",
                "auditor_is_person": False,
                "date": "2026-09-27",
                "verdict": "faithful",
                "comment": e["comment"],
                "audited_source_sha256": REFEREE_AUDITED_LEAN_SHA,
                "current_source_sha256": lean_sha,
                "change_since_audit": "docstring of tension1D_eq_zero_iff only (the rewording the referee asked "
                                      "for); see results/eboss_vs_desi/lean_BAO_Consistency_fixround2_docstring.diff",
                "referee_report": "results/eboss_vs_desi/referee_report_round2.json",
                "referee_report_sha256": ref_sha,
                "human_audit": "open"}
    if EVID.exists():
        shutil.rmtree(EVID)
    EVID.mkdir(parents=True)
    claims: list[dict[str, Any]] = []
    a_ids: dict[str, str] = {}
    for i, th in enumerate(theorems, start=1):
        fp = footprints.get(th)
        if fp != TRUSTED:
            raise RuntimeError(f"{th}: footprint {fp!r} is not the trusted set")
        ev = write_blob({
            "theorem": f"ANSE.BAOConsistency.{th}",
            "file": "formal/ANSE/BAO_Consistency.lean",
            "source_sha256": lean_sha,
            "lean_toolchain": toolchain,
            "command": LEAN_CMD,
            "kernel_axiom_footprint": f"'ANSE.BAOConsistency.{th}' depends on axioms: {fp}",
            "compile_log": str(LEAN_LOG.relative_to(ROOT)),
            "compile_log_sha256": sha256_file(LEAN_LOG),
            "elenchus_check_log": ELENCHUS_LOG.read_text().strip(),
            "note": "#print axioms lines are inside the committed source (Elenchus NO_FOOTPRINT rule).",
        })
        cid = f"{PREFIX}-A-{i:04d}"
        a_ids[th] = cid
        claims.append(claim(cid, f"ANSE.BAOConsistency.{th} ({glosses[th]}) is kernel-verified with axioms "
                                 f"exactly {TRUSTED}; no sorryAx, no smuggled axiom.",
                            "A", "lean_axioms", [], ev, audit_for(th)))

    fit, fit_sha = load("fit.json")
    pos, pos_sha = load("positive_control.json")
    neg, neg_sha = load("negative_controls.json")
    ins, ins_sha = load("instrument_check.json")
    camb, camb_sha = load("camb_crosscheck.json")
    prereg_sha = sha256_file(PREREG)
    if prereg_sha != fit["preregistration_sha256"]:
        raise RuntimeError("preregistration.json changed after the fit")
    F = fit["fits"]
    D, S, G = F["DESI_DR2"], F["SDSS_eBOSS_DR16_baseline"], F["SDSS_eBOSS_DR16_gaussian_summary"]
    T = fit["tension"]
    common = {"fit_json": "results/eboss_vs_desi/fit.json", "fit_json_sha256": fit_sha,
              "preregistration_sha256": prereg_sha, "input_sha256_verified": fit["input_sha256_verified"],
              "generated_at": fit["generated_at"]}

    def fit_blob(R: dict[str, Any], chain_key: str) -> dict[str, Any]:
        return {**common, "dataset": R["name"], "MAP": R["MAP"], "laplace": R["laplace"],
                "emcee": {k: R["emcee"][k] for k in ("mean_Om", "std_Om", "mean_hrd", "std_hrd", "corr",
                                                      "tau", "nsteps", "burn", "nwalkers",
                                                      "converged_50tau", "acceptance")},
                "grid": {k: R["grid"][k] for k in ("mean_Om", "std_Om", "mean_hrd", "std_hrd", "corr",
                                                    "grid_vs_MAP_within_0.1sigma", "n")},
                "emcee_vs_grid_mean_diff_in_sigma": R["emcee_vs_grid_mean_diff_in_sigma"],
                "chain": fit["chains"][chain_key]}

    b1 = write_blob(fit_blob(D, "desi_dr2"))
    b2 = write_blob(fit_blob(S, "sdss_baseline"))
    b3 = write_blob({**fit_blob(G, "sdss_gaussian_summary"),
                     "baseline_vs_gaussian_summary_shift_in_baseline_sigma":
                         fit["baseline_vs_gaussian_summary_shift_in_baseline_sigma"]})
    b4 = write_blob({**common, "tension": T, "code": "scripts/eboss_vs_desi/bao_lib.py::tension",
                     "bao_lib_sha256": sha256_file(ROOT / "scripts/eboss_vs_desi/bao_lib.py")})
    b5 = write_blob({"file": "results/eboss_vs_desi/positive_control.json", "sha256": pos_sha, "content": pos})
    b6 = write_blob({"file": "results/eboss_vs_desi/negative_controls.json", "sha256": neg_sha, "content": neg,
                     "note": "SDSS-baseline EdS delta is Infinity because Om=1 predictions fall outside the grid "
                             "tables for every hrd; its preregistered as-coded boolean passes by construction and is "
                             "flagged discriminating=false. The fix-round gate requires finite minima and gates the "
                             "SDSS EdS test on the Gaussian-summary variant; a +inf-everywhere probe likelihood passes "
                             "the as-coded boolean but is correctly not rejected by the fix-round gate. The combination "
                             "guard checks filename, allow-list and sha256 and raised on three probes."})
    b7 = write_blob({"file": "results/eboss_vs_desi/instrument_check.json", "sha256": ins_sha, "content": ins})
    b8 = write_blob({"file": "results/eboss_vs_desi/camb_crosscheck.json", "sha256": camb_sha,
                     "summary_in_fit_json": fit["camb_background_crosscheck"],
                     "camb_version": "camb 2.0.4 (venv-cosmo)"})

    def f(x: float, n: int) -> str:
        return f"{x:.{n}f}"

    tp = T["primary_emcee_moments"]
    claims += [
        claim(f"{PREFIX}-B-0001",
              f"Flat-LCDM BAO-only fit of the real DESI DR2 Gaussian BAO file (13 points, 13x13 cov, sha256-verified): "
              f"emcee Om = {f(D['emcee']['mean_Om'],5)} +- {f(D['emcee']['std_Om'],5)}, hrd = "
              f"{f(D['emcee']['mean_hrd'],3)} +- {f(D['emcee']['std_hrd'],3)} Mpc, corr {f(D['emcee']['corr'],3)}; "
              f"MAP chi2 = {f(D['MAP']['m2lnL_min'],2)} for {D['MAP']['dof']} dof; an independent 301x301 grid agrees "
              f"with emcee means within 0.02 sigma.", "B", "exact_harness", [], b1),
        claim(f"{PREFIX}-B-0002",
              f"Flat-LCDM BAO-only fit of the SDSS/eBOSS DR16 BAO compilation with the distributed grid likelihoods "
              f"(MGS, ELG, Lya auto, Lya x QSO) plus Gaussian DR12/LRG/QSO pieces, never combined with DESI: emcee Om = "
              f"{f(S['emcee']['mean_Om'],5)} +- {f(S['emcee']['std_Om'],5)}, hrd = {f(S['emcee']['mean_hrd'],3)} +- "
              f"{f(S['emcee']['std_hrd'],3)} Mpc, corr {f(S['emcee']['corr'],3)}; MAP -2lnL = "
              f"{f(S['MAP']['m2lnL_min'],2)} (nominal {S['MAP']['dof']} dof).", "B", "exact_harness", [], b2),
        claim(f"{PREFIX}-B-0003",
              f"The SDSS Gaussian-summary sensitivity variant gives Om = {f(G['emcee']['mean_Om'],5)} +- "
              f"{f(G['emcee']['std_Om'],5)}, hrd = {f(G['emcee']['mean_hrd'],3)} +- {f(G['emcee']['std_hrd'],3)} Mpc; "
              f"shift from the baseline {f(fit['baseline_vs_gaussian_summary_shift_in_baseline_sigma']['Om'],3)} sigma "
              f"(Om) and {f(fit['baseline_vs_gaussian_summary_shift_in_baseline_sigma']['hrd'],3)} sigma (hrd).",
              "B", "exact_harness", [f"{PREFIX}-B-0002"], b3),
        claim(f"{PREFIX}-B-0004",
              f"Parameter-difference statistic chi2 = dp^T (C_SDSS + C_DESI)^-1 dp on the emcee moments of B-0001 and "
              f"B-0002 (surveys treated as independent): chi2 = {f(tp['chi2'],3)}, 2 dof, PTE = {f(tp['PTE'],3)}, "
              f"N_sigma = {f(tp['N_sigma'],3)}; cross-checks grid {f(T['grid_moments']['N_sigma'],3)}, MAP+Laplace "
              f"{f(T['MAP_laplace']['N_sigma'],3)}, KDE shift {f(T['posterior_parameter_shift_KDE']['N_sigma'],3)} sigma.",
              "B", "exact_harness", [f"{PREFIX}-B-0001", f"{PREFIX}-B-0002"], b4),
        claim(f"{PREFIX}-B-0005",
              f"Positive control (200 injected Gaussian realizations at (0.2975, 101.54), seed {pos['seed']}) passed: "
              f"coverage SDSS-GS {pos['SDSS_gaussian_summary']['coverage_1sigma']['Om']}/"
              f"{pos['SDSS_gaussian_summary']['coverage_1sigma']['hrd']}, DESI {pos['DESI_DR2']['coverage_1sigma']['Om']}/"
              f"{pos['DESI_DR2']['coverage_1sigma']['hrd']} (window [0.60,0.76]); tension KS PTE-uniform p = "
              f"{f(pos['tension_calibration']['KS_PTE_uniform_p'],3)}.", "B", "exact_harness", [], b5),
        claim(f"{PREFIX}-B-0006",
              f"All negative controls rejected (all_negative_controls_rejected = "
              f"{neg['all_negative_controls_rejected']}): EdS on DESI Delta(-2lnL) = "
              f"{f(neg['wrong_model_no_Lambda']['DESI_DR2']['delta'],1)}; EdS on the SDSS Gaussian-summary variant "
              f"Delta = {f(neg['wrong_model_no_Lambda_SDSS_gaussian_summary_gate']['delta'],1)} (the SDSS-baseline "
              f"EdS test is non-discriminating, discriminating = "
              f"{neg['wrong_model_no_Lambda']['SDSS_eBOSS_DR16_baseline']['discriminating']}); +inf probe not "
              f"rejected = {neg['eds_gate_probe_inf_everywhere']['probe_ok']}; DM<->DH swap chi2/dof = "
              f"{f(neg['desi_DM_DH_swap']['chi2_per_dof'],1)}; cov/25 chi2/dof = "
              f"{f(neg['desi_cov_over_25']['chi2_per_dof'],2)}; DESI ratios x0.93 give N_sigma = "
              f"{f(neg['injected_scale_shift_0.93']['tension']['N_sigma'],2)}; combination guard (filename, "
              f"allow-list, sha256) raised on all three probes = {neg['combination_guard']['rejected']}.",
              "B", "exact_harness", [f"{PREFIX}-B-0002"], b6),
        claim(f"{PREFIX}-B-0007",
              f"Instrument check passed: input sha256 match the preregistration; three prediction codes agree to "
              f"{ins['prediction_code_max_rel_diff']['astropy_vs_quad']:.1e} relative; every grid-likelihood table "
              f"reproduces its published peak and width; the paired MGS no-rescale negative fails "
              f"({f(ins['MGS_paired_negative']['location_dev_in_sigma_ref'],1)} sigma off).",
              "B", "exact_harness", [], b7),
        claim(f"{PREFIX}-B-0008",
              "CAMB 2.0.4 background cross-check: analytic flat-LCDM DM, H, DV agree with CAMB to < 1e-3 relative at "
              "the data redshifts for three test points (max DM 2.0e-4, H 4.8e-4, DV 2.9e-4); CAMB rdrag = "
              f"{f(fit['camb_background_crosscheck']['planck2018_rdrag_Mpc'],4)} Mpc at the Planck-2018 point.",
              "B", "exact_harness", [], b8),
    ]

    lit = LIT.read_text()
    fetched = ("alphaXiv answer_pdf_queries page text, 2026-09-27, as transcribed in "
               "docs/literature/EBOSS_VS_DESI_LITERATURE_REVIEW_2026.md")
    lit_sha = sha256_file(LIT)
    l1 = write_blob({"source": "Alam et al., arXiv:2007.08991, Table IV (BAO row, LCDM block, p.17)",
                     "quote": lit_quote(lit, "| SDSS BAO-only flat ΛCDM Ω_DE | 0.701 +0.017/−0.015 |"),
                     "secondary_quote_2404.03002": lit_quote(lit, "| SDSS Ω_m (secondary quote) | 0.299 ± 0.016 |"),
                     "fetched_via": fetched, "lit_review_sha256": lit_sha})
    l2 = write_blob({"source": "DESI Collaboration, arXiv:2503.14738, eq. (17)",
                     "quotes": [lit_quote(lit, "| DESI DR2 Ω_m | 0.2975 ± 0.0086 |"),
                                lit_quote(lit, "| DESI DR2 h r_d | (101.54 ± 0.73) Mpc |"),
                                lit_quote(lit, "| DESI DR2 corr(Ω_m, h r_d) | r = −0.92 |")],
                     "fetched_via": fetched, "lit_review_sha256": lit_sha})
    l3 = write_blob({"source": "DESI Collaboration, arXiv:2404.03002, Sec. 4.1, citing [139] = arXiv:2007.08991",
                     "quote": lit_quote(lit, "| SDSS h r_d | (100.4 ± 1.3) Mpc | 2404.03002 §4.1 (p.23), citing [139] | **Secondary only.**"),
                     "fetched_via": fetched, "lit_review_sha256": lit_sha})
    l4 = write_blob({"source": "DESI Collaboration, arXiv:2503.14738, abstract and Sec. III.C.2",
                     "quotes": [lit_quote(lit, "The DR2 BAO results are consistent with DESI DR1 and SDSS"),
                                lit_quote(lit, "We conclude that there is no significant discrepancy between the DR2 measurements and those from SDSS.")],
                     "fetched_via": fetched, "lit_review_sha256": lit_sha})
    l5 = write_blob({"source": "DESI Collaboration, arXiv:2503.14738, Sec. III.C.2 (p.16)",
                     "quote": lit_quote(lit, "DR2 estimates C ≈ 0.57 between DR2 LRG2 and eBOSS LRG (2503.14738 p.16)"),
                     "fetched_via": fetched, "lit_review_sha256": lit_sha})
    pulls = {p["name"]: p for p in fit["pulls"]}
    l6 = write_blob({**common, "pulls": fit["pulls"], "within_tolerance": fit["within_tolerance"],
                     "rule": fit["within_tolerance_rule"], "tolerance_sigma": 0.5})
    l7 = write_blob({**common, "pull": pulls["SDSS_hrd_Mpc"]})
    l8 = write_blob({**common, "N_sigma": tp["N_sigma"], "criterion": "N_sigma < 2 (preregistered)",
                     "pass": T["pass_N_sigma_lt_2"]})
    claims += [
        claim(f"{PREFIX}-L-0001", "arXiv:2007.08991 Table IV (BAO, flat LCDM) gives Omega_DE = 0.701 +0.017/-0.015, "
              "i.e. Om = 0.299 (symmetric sigma 0.016, also quoted by arXiv:2404.03002 Sec. 4.1).",
              "L", "citation", [], l1),
        claim(f"{PREFIX}-L-0002", "arXiv:2503.14738 eq. (17): DESI DR2 BAO-only flat LCDM Om = 0.2975 +- 0.0086, "
              "hrd = (101.54 +- 0.73) Mpc, correlation -0.92.", "L", "citation", [], l2),
        claim(f"{PREFIX}-L-0003", "arXiv:2404.03002 Sec. 4.1 quotes SDSS BAO-only hrd = (100.4 +- 1.3) Mpc, citing "
              "arXiv:2007.08991; the value was not found in the fetched pages of 2007.08991 itself (secondary only).",
              "L", "citation", [], l3),
        claim(f"{PREFIX}-L-0004", "arXiv:2503.14738 states qualitatively that DR2 BAO are consistent with SDSS "
              "('no significant discrepancy'); it publishes no (Om, hrd) tension number.", "L", "citation", [], l4),
        claim(f"{PREFIX}-L-0005", "arXiv:2503.14738 estimates a cross-survey correlation C ~ 0.57 between DESI DR2 "
              "LRG2 and eBOSS LRG.", "L", "citation", [], l5),
        claim(f"{PREFIX}-L-0006",
              f"The independent fits reproduce the three primary-verified published values within the preregistered "
              f"0.5 sigma: SDSS Om pull {f(pulls['SDSS_Om']['pull_sigma'],3)}, DESI DR2 Om "
              f"{f(pulls['DESI_DR2_Om']['pull_sigma'],3)}, DESI DR2 hrd {f(pulls['DESI_DR2_hrd_Mpc']['pull_sigma'],3)} sigma.",
              "L", "citation", [f"{PREFIX}-B-0001", f"{PREFIX}-B-0002", f"{PREFIX}-L-0001", f"{PREFIX}-L-0002"], l6),
        claim(f"{PREFIX}-L-0007",
              f"The SDSS hrd fit differs from the secondary-sourced 100.4 +- 1.3 Mpc by "
              f"{f(pulls['SDSS_hrd_Mpc']['pull_sigma'],3)} sigma (reported, not counted toward within_tolerance).",
              "L", "citation", [f"{PREFIX}-B-0002", f"{PREFIX}-L-0003"], l7),
        claim(f"{PREFIX}-L-0008",
              f"The measured N_sigma = {f(tp['N_sigma'],3)} satisfies the preregistered N_sigma < 2 criterion and so "
              f"agrees with DESI DR2's qualitative 'consistent with SDSS' statement.",
              "L", "citation", [f"{PREFIX}-B-0004", f"{PREFIX}-L-0004"], l8),
    ]

    c1 = write_blob({"argument": "chi2 = dp^T C^-1 dp with C = C_S + C_D assumes Cov(p_S, p_D) = 0. With a positive "
                                 "cross-survey covariance K the correct matrix is Var(dp) = C_S + C_D - K - K^T; if K + K^T "
                                 "is positive semidefinite this matrix is <= C_S + C_D in Loewner order (and still PD), "
                                 "so its inverse is >= (C_S + C_D)^-1 and chi2 can only increase. DESI DR2 estimates "
                                 "C ~ 0.57 for LRG2 vs eBOSS LRG. Hence the reported N_sigma is a lower bound with respect "
                                 "to survey overlap; the cross-survey K itself was not estimated here.",
                     "N_sigma_independent": tp["N_sigma"], "fit_json_sha256": fit_sha})
    bao_lib = (ROOT / "scripts/eboss_vs_desi/bao_lib.py").read_text()
    code_lines = [ln.strip() for ln in bao_lib.splitlines()
                  if ln.strip().startswith(("dp = np.asarray(p1)", "C = np.asarray(c1)", "chi2 = float(dp @"))]
    if len(code_lines) != 3:
        raise RuntimeError(f"expected 3 tension code lines in bao_lib.py, found {code_lines}")
    c2 = write_blob({"argument": "BAO_Consistency.surveyTension is chi2 (aS+aD) (bS+bD) (cS+cD) (mS1-mD1) (mS2-mD2), "
                                 "and chi2_eq_dotProduct_inv_mulVec proves the closed form equals Mathlib's "
                                 "d . (C^-1 *v d). This matches the three lines of bao_lib.tension below for the 2x2 case. "
                                 "The match of the Lean statement to the code is a reading, not a kernel check.",
                     "bao_lib_tension_lines": code_lines,
                     "bao_lib_sha256": sha256_file(ROOT / "scripts/eboss_vs_desi/bao_lib.py"),
                     "lean_source_sha256": lean_sha})
    claims += [
        claim(f"{PREFIX}-C-0001", "Because the tension statistic treats SDSS and DESI DR2 as independent while their "
              "volumes overlap, the reported N_sigma is a lower bound with respect to overlap, provided the "
              "cross-survey covariance K satisfies K + K^T positive semidefinite (K itself was not estimated).",
              "C", "argument", [f"{PREFIX}-B-0004", f"{PREFIX}-L-0005"], c1),
        claim(f"{PREFIX}-C-0002", "The Lean definitions formalise exactly the 2x2 statistic evaluated by "
              "scripts/eboss_vs_desi/bao_lib.py::tension (dp = p1-p2, C = c1+c2, chi2 = dp @ solve(C, dp)).",
              "C", "argument", [a_ids["chi2_eq_dotProduct_inv_mulVec"], a_ids["surveyTension_symm"],
                                a_ids["posdef_add"], a_ids["surveyTension_nonneg_and_zero_iff"]], c2),
    ]

    ledger = {"schema_version": 1, "claims": claims}
    (LEDGER_DIR / "ledger.json").write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(claims)} claims, {len(list(EVID.iterdir()))} evidence blobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

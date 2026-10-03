"""Write results/eboss_vs_desi/episodes.jsonl: one row per verdict-bearing step
that actually ran in this problem, with evidence on disk.

Every verdict is read from a regenerated result file; a step whose evidence
file is missing is skipped (never invented). Rows include failures:
the non-discriminating preregistered SDSS EdS gate, the as-coded EdS gate
passing a +inf probe likelihood, the reverted round-1 ledger-audit fix, the
interrupted-run pytest failures, the antigravity_guard failure, and
unresolved referee issues from both rounds.
Fields: step, input_summary, command, verdict ('pass'|'fail'), energy
(0.0 pass / 1.0 fail), evidence_path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "eboss_vs_desi"
PY = "/mnt/disks/disk-socrateai-local-1/venv-pta/bin/python"
PYC = "/mnt/disks/disk-socrateai-local-1/venv-cosmo/bin/python"
SD = "cd scripts/eboss_vs_desi && "
LEAN = ("cd /home/callensxavier_gmail_com/AutoevolveAI/formal && timeout 1500 lake env lean "
        "/home/callensxavier_gmail_com/AutoevolveAI/.claude/worktrees/cosmo3-run/formal/ANSE/BAO_Consistency.lean")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def load(name: str) -> dict[str, Any]:
    return json.loads((RES / name).read_text())


def main() -> int:
    rows: list[dict[str, Any]] = []

    def add(step: str, inp: str, cmd: str, ok: bool, ev: Path) -> None:
        if not ev.exists():
            return
        rows.append({"step": step, "input_summary": inp, "command": cmd,
                     "verdict": "pass" if ok else "fail", "energy": 0.0 if ok else 1.0,
                     "evidence_path": rel(ev)})

    ic_p = RES / "instrument_check.json"
    ic = load("instrument_check.json")
    s = ic["summary"]
    add("instrument_check.input_sha256", "all SDSS + DESI DR2 input files vs preregistered sha256",
        SD + PY + " instrument_check.py", bool(ic["sha256_verified"]), ic_p)
    add("instrument_check.prediction_codes", "astropy vs quad vs Gauss-Legendre distances, tol 1e-4",
        SD + PY + " instrument_check.py", bool(s["prediction_codes_pass"]), ic_p)
    add("instrument_check.grid_tables", "MGS/ELG/Lya auto/Lya x QSO peak, width, rho vs published",
        SD + PY + " instrument_check.py",
        bool(s["all_locations_pass"] and s["all_widths_pass"] and s["lya_rho_pass"]), ic_p)
    add("instrument_check.mgs_paired_negative", "MGS table without the 4.2972 rs rescale must fail location",
        SD + PY + " instrument_check.py", bool(s["mgs_paired_negative_failed_as_required"]), ic_p)

    pc_p = RES / "positive_control.json"
    pc = load("positive_control.json")
    add("positive_control.injection", f"{pc['n_realizations']} injected realizations at {pc['injected']}, "
        f"SDSS Gaussian-summary + DESI DR2, seed {pc['seed']}; coverage [0.60,0.76], |bias|<0.2 sigma",
        SD + PY + " positive_control.py", bool(pc["positive_control_passed"]), pc_p)

    nc_p = RES / "negative_controls.json"
    nc = load("negative_controls.json")
    cmd = SD + PY + " negative_controls.py"
    w = nc["wrong_model_no_Lambda"]
    add("negative_control.eds_desi", f"EdS on DESI DR2, Delta(-2lnL)={w['DESI_DR2']['delta']:.1f} > 25",
        cmd, bool(w["DESI_DR2"]["rejected"]), nc_p)
    sb = w["SDSS_eBOSS_DR16_baseline"]
    add("negative_control.eds_sdss_baseline_preregistered_gate",
        "EdS on SDSS baseline grid likelihood: delta=Infinity because predictions leave every table; "
        "as-coded boolean passes by construction, verdict = discriminating",
        cmd, bool(sb["discriminating"]), nc_p)
    gs = nc["wrong_model_no_Lambda_SDSS_gaussian_summary_gate"]
    add("negative_control.eds_sdss_gaussian_summary_gate", f"EdS on SDSS Gaussian-summary, Delta={gs['delta']:.1f} > 25",
        cmd, bool(gs["rejected"]), nc_p)
    pr = nc["eds_gate_probe_inf_everywhere"]
    add("negative_control.eds_as_coded_gate_vs_inf_probe",
        "original EdS boolean (delta>25) applied to a likelihood that is +inf everywhere; must NOT reject",
        cmd, not bool(pr["rejected_as_coded"]), nc_p)
    add("negative_control.eds_fixround_gate_vs_inf_probe",
        "fix-round EdS gate (finite minima required) on the +inf-everywhere probe; must NOT reject",
        cmd, bool(pr["probe_ok"]), nc_p)
    add("negative_control.desi_dm_dh_swap", f"DM<->DH swap, chi2/dof={nc['desi_DM_DH_swap']['chi2_per_dof']:.1f} > 3",
        cmd, bool(nc["desi_DM_DH_swap"]["rejected"]), nc_p)
    add("negative_control.desi_cov_over_25", f"cov/25, chi2/dof={nc['desi_cov_over_25']['chi2_per_dof']:.2f} > 3",
        cmd, bool(nc["desi_cov_over_25"]["rejected"]), nc_p)
    sh = nc["injected_scale_shift_0.93"]
    add("negative_control.desi_scale_shift_0.93", f"DESI ratios x0.93 vs SDSS, N_sigma={sh['tension']['N_sigma']:.2f} > 3",
        cmd, bool(sh["rejected"]), nc_p)
    g = nc["combination_guard"]
    add("negative_control.guard_named_desi_file", "excluded DESI+eBOSS Lya file offered to SDSS likelihood",
        cmd, bool(g["named_desi_eboss_lya"]["raised"]), nc_p)
    msg = g["desi_renamed_nondesi_name"].get("message", "")
    add("negative_control.substring_only_guard_vs_renamed_desi_file",
        "original filename-substring guard on a DESI file renamed without 'desi' (it is caught only by the "
        "new allow-list step, so the substring check alone would have accepted it)",
        cmd, "DESI-derived" in msg, nc_p)
    add("negative_control.guard_allowlist_renamed", "DESI DR2 mean file renamed to renamed_bao_mean.txt",
        cmd, bool(g["desi_renamed_nondesi_name"]["raised"]), nc_p)
    add("negative_control.guard_sha256_renamed_as_sdss", "DESI DR2 mean file renamed to sdss_DR16_QSO_BAO_DMDH.txt",
        cmd, bool(g["desi_renamed_as_sdss_qso"]["raised"]), nc_p)
    add("negative_control.guard_accepts_real_sdss", "all 10 preregistered SDSS files pass the guard",
        cmd, bool(g["real_sdss_files_accepted"]), nc_p)

    cb_p = RES / "camb_crosscheck.json"
    fit_p = RES / "fit.json"
    fit = load("fit.json")
    cb = fit["camb_background_crosscheck"]
    add("crosscheck.camb_background", f"analytic DM/H/DV vs CAMB 2.0.4 at 3 points, tol 1e-3; rdrag={cb['planck2018_rdrag_Mpc']:.4f}",
        SD + PYC + " camb_crosscheck.py", bool(cb["all_pass"]), cb_p)
    fcmd = SD + PY + " fit_eboss_vs_desi.py"
    for key, lab in (("SDSS_eBOSS_DR16_baseline", "sdss_baseline"), ("SDSS_eBOSS_DR16_gaussian_summary", "sdss_gs"),
                     ("DESI_DR2", "desi_dr2")):
        R = fit["fits"][key]
        e = R["emcee"]
        add(f"fit.{lab}.emcee", f"emcee Om={e['mean_Om']:.5f}+-{e['std_Om']:.5f}, hrd={e['mean_hrd']:.3f}+-{e['std_hrd']:.3f}; "
            "gate 50*tau < nsteps", fcmd, bool(e["converged_50tau"]), fit_p)
        add(f"fit.{lab}.grid", "normalised grid posterior; grid minimum within 0.1 sigma of MAP",
            fcmd, bool(R["grid"]["grid_vs_MAP_within_0.1sigma"]), fit_p)
        add(f"fit.{lab}.emcee_vs_grid", f"emcee vs grid mean diff (sigma) {R['emcee_vs_grid_mean_diff_in_sigma']}; gate < 0.1",
            fcmd, max(R["emcee_vs_grid_mean_diff_in_sigma"]) < 0.1, fit_p)
    for p in fit["pulls"]:
        add(f"fit.pull.{p['name']}", f"value {p.get('value')} vs target {p.get('target')}: pull {p['pull_sigma']:+.3f} sigma, tol 0.5",
            fcmd, abs(p["pull_sigma"]) < 0.5, fit_p)
    add("fit.within_tolerance", fit["within_tolerance_rule"], fcmd, bool(fit["within_tolerance"]), fit_p)
    t = fit["tension"]["primary_emcee_moments"]
    add("fit.tension_criterion", f"chi2={t['chi2']:.3f}, PTE={t['PTE']:.3f}, N_sigma={t['N_sigma']:.3f}; prereg N_sigma<2",
        fcmd, bool(fit["tension"]["pass_N_sigma_lt_2"]), fit_p)

    stale = Path("/mnt/disks/disk-socrateai-local-1/AutoevolveAI/cosmo3/eboss_vs_desi/"
                 "stale_prior_mirror_not_regenerated/results/lean_BAO_Consistency_compile_recheck.log")
    for p, lab, src in (
            (RES / "lean_BAO_Consistency_compile_leanstage_run1.log", "lean.compile_lean_stage_run1",
             "Lean stage compile #1 of the file as found from the interrupted run (source sha not recorded; "
             "log copied from /tmp/bao_consistency_lean_run1.log)"),
            (stale, "lean.compile_interrupted_run_recheck",
             "interrupted run's recheck compile (copy kept on disk 2 only; source sha not recorded)"),
            (RES / "lean_BAO_Consistency_compile.log", "lean.compile_lean_stage_final",
             "Lean stage final compile, source sha256 bafdfab48eba8d67..."),
            (RES / "lean_BAO_Consistency_compile_fixround2.log", "lean.compile_fixround2",
             "round-2 fix stage compile after docstring-only edit, source sha256 560e3b5d8266a2e2...")):
        if p.exists():
            log = p.read_text()
            fps = re.findall(r"depends on axioms: (\[.*?\])", log)
            ok = ("rc=0" in log and "sorryAx" not in log and len(fps) == 9
                  and all(f == "[propext, Classical.choice, Quot.sound]" for f in fps))
            add(lab, f"BAO_Consistency.lean, 9 theorems, axiom whitelist; {src}", LEAN, ok, p)
    el = RES / "lean_BAO_Consistency_elenchus.log"
    if el.exists():
        add("lean.elenchus_check", "Elenchus vacuity/footprint scanner on BAO_Consistency.lean",
            "cd formal && lake env python3 .../elenchus_check.py formal/ANSE/BAO_Consistency.lean",
            "no findings" in el.read_text(), el)

    gcmd = PY + " scripts/eboss_vs_desi/ledger_gate_check.py"
    # The ledger + paper stage's gate run (all Tier A audit null) was recorded in the stage report
    # (rc=1, 0 block, 9 LEDGER_UNAUDITED_TIER_A flags); its log was overwritten by this stage, and the
    # same state is reproduced on disk by the drop-audit mutation below, so no separate row is invented.
    post = RES / "ledger" / "gate_check.json"
    if post.exists():
        d = json.loads(post.read_text())
        led = json.loads((RES / "ledger" / "ledger.json").read_text())
        n_aud = sum(1 for c in led["claims"] if c["tier"] == "A" and c.get("audit") is not None)
        add("ledger.gate_fixround2",
            f"27 claims; {n_aud}/9 Tier A rows carry an automated-model-referee audit (auditor_is_person=false, "
            f"human audit open): rc={d['real']['rc']}, n_block={d['real']['n_block']}, n_flag={d['real']['n_flag']}",
            gcmd, d["real"]["rc"] == 0, post)
        for k, v in d["verdict"].items():
            if k.startswith("real_"):
                continue
            add(f"ledger.mutation.{k}", "hand-built ledger mutation must be caught", gcmd, bool(v), post)

    rg = RES / "test_rigor_guard.log"
    if rg.exists():
        add("verify.test_rigor_guard", "anti-stub AST validation", "python3 test_rigor_guard.py", "[PASS]" in rg.read_text(), rg)
    ag = RES / "antigravity_guard.log"
    if ag.exists():
        add("verify.antigravity_guard", "hallucinated-import/syntax guard (camb only in venv-cosmo)",
            "python3 antigravity_guard.py", "[FAIL]" not in ag.read_text(), ag)
    pt = RES / "pytest_tests.log"
    if pt.exists() and pt.read_text().strip():
        txt = re.sub(r"\x1b\[[0-9;]*m", "", pt.read_text())
        last = [ln for ln in txt.splitlines() if ln.strip()][-1]
        ok = ("passed" in last) and not any(x in last for x in ("failed", "error"))
        add("verify.pytest_tests_interrupted_round1", f"repo test suite, run by the interrupted round-1 fix round "
            f"(log not regenerated since; no line mentions eboss_vs_desi); last line: {last[:160]}",
            "/home/callensxavier_gmail_com/AutoevolveAI/.venv/bin/python -m pytest tests/ -q -p no:cacheprovider", ok, pt)
    pdf_log = ROOT / "papers" / "eboss_vs_desi" / "eboss_vs_desi.log"
    if pdf_log.exists():
        lg = pdf_log.read_text(errors="replace")
        ok = ("Output written" in lg and "Undefined control sequence" not in lg
              and "undefined" not in lg.lower().split("output written")[-1])
        add("paper.pdflatex", "eboss_vs_desi.tex two-pass build", "cd papers/eboss_vs_desi && pdflatex eboss_vs_desi.tex (x2)",
            ok, pdf_log)

    # Round-1 fix outcomes. Item 7c (audits copied from the round-1 model referee to force gate rc 0) was
    # reverted by the ledger + paper stage because that report predated the regenerated fit and Lean source,
    # so it is recorded as a fail, not as the 'fixed' the round-1 file claims.
    reverted = {"7c_ledger_unaudited_tier_a": "REVERTED by the ledger + paper stage (round-1 audits predated the "
                                              "regenerated fit and final Lean source)"}
    fx = RES / "fixround_outcomes.json"
    if fx.exists():
        for it in json.loads(fx.read_text())["issues"]:
            note = reverted.get(it["id"])
            add(f"referee_round1_issue.{it['id']}",
                it["issue"] + " -> " + it["outcome"] + (f" [{note}]" if note else ""), it["command"],
                bool(it["fixed"]) and note is None, ROOT / it["evidence"])
    fx2 = RES / "fixround2_outcomes.json"
    if fx2.exists():
        for it in json.loads(fx2.read_text())["issues"]:
            add(f"referee_round2_issue.{it['id']}", it["issue"] + " -> " + it["outcome"], it["command"],
                bool(it["fixed"]), ROOT / it["evidence"])

    out = RES / "episodes.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    n_fail = sum(r["verdict"] == "fail" for r in rows)
    print(f"wrote {len(rows)} episodes ({n_fail} fail) to {rel(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

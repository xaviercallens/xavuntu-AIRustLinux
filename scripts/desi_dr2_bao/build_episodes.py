"""Write results/desi_dr2_bao/episodes.jsonl: one row per verdict-bearing step that
actually ran in this problem and left evidence on disk.

Every verdict is computed from a regenerated result file; a step whose evidence
file is missing is skipped, never invented. Failures are included (pre-audit
ledger gate rc=1, antigravity_guard rc=1, pytest rc!=0, referee issues left
unfixed). Fields: step, input_summary, command, verdict ('pass'|'fail'),
energy (0.0 pass / 1.0 fail), evidence_path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "desi_dr2_bao"
PAP = ROOT / "papers" / "desi_dr2_bao"
PY = "/mnt/disks/disk-socrateai-local-1/venv-pta/bin/python -B"
PYC = "/mnt/disks/disk-socrateai-local-1/venv-cosmo/bin/python -B"
VPY = "/home/callensxavier_gmail_com/AutoevolveAI/.venv/bin/python"
S = "scripts/desi_dr2_bao/"
LEAN = ("cd /home/callensxavier_gmail_com/AutoevolveAI/formal && timeout 1500 lake env lean "
        "/home/callensxavier_gmail_com/AutoevolveAI/.claude/worktrees/cosmo3-run/formal/ANSE/DESI_DR2_wCDM.lean")


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text())


def main() -> int:
    rows: list[dict[str, Any]] = []

    def add(step: str, inp: str, cmd: str, ok: bool, ev: Path) -> None:
        if not ev.exists():
            return
        rows.append({"step": step, "input_summary": inp, "command": cmd,
                     "verdict": "pass" if ok else "fail", "energy": 0.0 if ok else 1.0,
                     "evidence_path": rel(ev)})

    # ---- controls ----
    cp = RES / "controls.json"
    ctl = load(cp)
    pc, nc = ctl["positive_controls"], ctl["negative_controls"]
    ccmd = PY + " " + S + "controls.py"
    add("positive_control.PC0_dr1_regression", "DR1 regression vs parent fit_desi_bao (quad and GL paths)", ccmd,
        bool(pc["PC0_regression_quad"]["pass"] and pc["PC0_regression_gl"]["pass"]), cp)
    add("positive_control.PC1_noiseless_LCDM", f"noiseless LCDM mock, dOm={pc['PC1_noiseless_LCDM']['dOm']:.2e}", ccmd,
        bool(pc["PC1_noiseless_LCDM"]["pass"]), cp)
    add("positive_control.PC2_noiseless_wCDM", f"noiseless wCDM mock, dw={pc['PC2_noiseless_wCDM']['dw']:.2e}", ccmd,
        bool(pc["PC2_noiseless_wCDM"]["pass"]), cp)
    p3 = pc["PC3_noisy_LCDM_draws"]
    add("positive_control.PC3_500_noisy_mocks", f"pull mean Om {p3['mean_pull']['Om']:+.3f}, std {p3['std_pull']['Om']:.3f}, "
        f"mean chi2_min {p3['mean_chi2_min']:.2f}", ccmd, bool(p3["pass"]), cp)
    add("positive_control.PC4_astropy_vs_quad", "astropy FlatLambdaCDM/FlatwCDM vs quad distances, tol 1e-5", ccmd,
        bool(pc["PC4_astropy_vs_quad"]["pass"]), cp)
    add("instrument.gauss_legendre_vs_quad", "GL integrator vs quad at prior corners, tol 1e-9", ccmd,
        bool(ctl["gl_integrator_validation"]["pass_1e-9"]), cp)
    for k, v in nc.items():
        extra = ""
        if k == "NC5_scrambled_covariance":
            extra = f" (median PTE {v['median_pte']:.1e}; {sum(r['pte'] > 1e-3 for r in v['runs'])}/{len(v['runs'])} single fits PTE>1e-3)"
        add(f"negative_control.{k}", f"must fail as preregistered{extra}", ccmd, bool(v["failed_as_required"]), cp)

    # ---- fits ----
    mp, gp, fp = RES / "mcmc_summary.json", RES / "grid_summary.json", RES / "fit.json"
    mc, gr, fit = load(mp), load(gp), load(fp)
    for n, r in mc["runs"].items():
        add(f"fit.emcee.{n}", f"emcee 20000 steps, ESS {r['ess']:.0f}, status {r['status']}", PY + " " + S + "mcmc_fit.py",
            r["status"] == "CONVERGED", mp)
    add("fit.emcee.reproducibility", f"two identical {mc['reproducibility']['steps']}-step runs", PY + " " + S + "mcmc_fit.py",
        bool(mc["reproducibility"]["identical"]), mp)
    for n, r in gr["runs"].items():
        edge = max(v for ax in r["edge_marginal_mass"].values() for v in ax.values())
        add(f"fit.grid.{n}", f"{r['n_per_axis']}-per-axis grid posterior, max edge marginal mass {edge:.1e} (<1e-3)",
            PY + " " + S + "grid_posterior.py", edge < 1e-3, gp)
    acmd = PY + " " + S + "assemble_fit.py"
    add("fit.emcee_vs_grid", f"max |emcee-grid| = {fit['emcee_vs_grid_max_abs_diff_in_emcee_sigma']:.4f} emcee sigma (<0.1)",
        acmd, fit["emcee_vs_grid_max_abs_diff_in_emcee_sigma"] < 0.1, fp)
    for k, v in fit["criteria"].items():
        add(f"fit.criterion.{k}", "preregistered pass criterion", acmd, bool(v), fp)
    for r in fit["results"]:
        add(f"fit.target.{r['name']}", f"{r['value']:.5g}+-{r['sigma']:.3g} vs {r['target']}+-{r['target_sigma']}: "
            f"pull {r['pull_sigma']:+.3f}, width {r['width_ratio']:.3f}", acmd,
            bool(r["within_0.5sigma"] and r["width_ok"]), fp)
    add("fit.within_tolerance", fit["tolerance_rule"] if isinstance(fit["tolerance_rule"], str) else "preregistered overall rule",
        acmd, bool(fit["within_tolerance"]), fp)
    rad = fit["radiation_sensitivity"]
    rs = [abs(v) for m in rad.values() for k, v in m.items() if k.startswith("shift_")]
    add("fit.radiation_sensitivity", f"Omega_r variant, max |shift| {max(rs):.3f} sigma (flag at 0.3)", acmd, max(rs) < 0.3, fp)
    sh = fit["DR1_to_DR2_shift"]
    add("fit.dr1_to_dr2_shift", f"Delta Om {sh['Delta_Om']:+.5f}, {sh['Delta_over_sigma_nested_prereg']:.3f} sigma_nested(prereg)",
        acmd, all(v for k, x in sh.items() if k.startswith("pred")
                  for v in (x.values() if isinstance(x, dict) else [x])), fp)

    # ---- CAMB ----
    cbp = RES / "camb_crosscheck.json"
    cb = load(cbp)
    a = cb["a_massless_nu_exactness"]
    mx = max(a["w=-1.0"]["max_abs_rel_diff"], a["w=-0.9"]["max_abs_rel_diff"])
    add("crosscheck.camb_massless_exactness", f"CAMB {cb['camb_version']} D_M,H vs quad, max rel diff {mx:.1e} (<1e-6)",
        PYC + " " + S + "camb_crosscheck.py", mx < 1e-6, cbp)
    add("crosscheck.camb_planck18_rdrag", f"Planck-2018 rdrag {cb['c_planck2018_rdrag_Mpc']:.4f} vs orchestrator 147.1027",
        PYC + " " + S + "camb_crosscheck.py", abs(cb["c_planck2018_rdrag_Mpc"] - 147.1027) < 1e-3, cbp)
    b = cb["b_primary_model_systematic_vs_camb_mnu0.06"]
    bs = [abs(v) for m in ("lcdm", "wcdm") for v in b[m]["shift_in_published_sigma"].values()]
    add("crosscheck.camb_mnu0.06_systematic", f"primary model on CAMB 0.06 eV vector, max |shift| {max(bs):.3f} sigma (<0.3)",
        PYC + " " + S + "camb_crosscheck.py", max(bs) < 0.3, cbp)

    # ---- fix-round rerun ----
    rr = RES / "fixround_rerun_check.json"
    if rr.exists():
        d = load(rr)
        add("fixround.rerun_bit_identical", "mcmc_fit.py + grid_posterior.py re-run from current files vs pre-fix-round outputs",
            PY + " " + S + "compare_rerun.py", bool(d["all_identical"]), rr)

    # ---- Lean ----
    lg = RES / "lean_gate.json"
    g = load(lg)
    add("lean.compile_and_axiom_gate", f"DESI_DR2_wCDM.lean sha {g['lean_file_sha256'][:12]}, 6 theorems, whitelist",
        LEAN, bool(g["gate_pass"] and g["rc"] == 0), lg)
    add("lean.elenchus_check", "Elenchus vacuity/footprint scanner", "cd formal && lake env python3 .../elenchus_check.py <file>",
        g["elenchus"]["rc"] == 0, lg)
    ln = RES / "lean_gate_negative_control.json"
    if ln.exists():
        first = str(load(ln)["genuine_first_compile_log"])
        fps = re.findall(r"depends on axioms: (\[.*?\])", first)
        add("lean.compile_first_attempt_lean_stage", "genuine file, first compile in the Lean stage (log kept in negative-control record)",
            LEAN, "rc=0" in first and "sorryAx" not in first and len(fps) == 6
            and all(f == "[propext, Classical.choice, Quot.sound]" for f in fps), ln)
        add("lean.negative_control_sorry_mutant", "copy with E_w_neg_one proof -> sorry must be flagged INHERITED_SORRY",
            "lake env python3 .../elenchus_check.py /tmp/DESI_DR2_wCDM_negctrl.lean",
            load(ln)["verdict"].startswith("instrument valid"), ln)

    # ---- ledger ----
    lcmd = PY + " " + S + "check_ledger.py"
    pre = RES / "ledger" / "gate_check_pre_audit.json"
    if pre.exists():
        d = load(pre)["real"]
        add("ledger.gate_pre_audit", f"25 claims, audit null on 6 Tier A: rc={d['rc']}, blocks={d['n_block']}, flags={d['n_flag']}",
            lcmd, d["rc"] == 0, pre)
    post = RES / "ledger" / "gate_check.json"
    if post.exists():
        d = load(post)
        add("ledger.gate_post_audit", f"Tier A audited by model referee: rc={d['real']['rc']}, blocks={d['real']['n_block']}, "
            f"flags={d['real']['n_flag']}", lcmd, d["real"]["rc"] == 0, post)
        for k, v in d["verdict"].items():
            if not k.startswith("real_"):
                add(f"ledger.control.{k}", "ledger gate control (positive or hand-built mutation)", lcmd, bool(v), post)

    ab = RES / "ledger" / "audit_binding_control.json"
    if ab.exists():
        add("ledger.audit_binding_control", "audit attached only for the audited Lean sha and faithful theorems",
            "python -B -c <build_ledger.referee_audit calls>", bool(load(ab)["result"]["pass"]), ab)

    # ---- independent referee re-runs (read from the saved referee report) ----
    refp = RES / "referee_report.json"
    if refp.exists():
        rtxt = " ".join(i["description"] for i in load(refp)["issues"])
        add("referee.independent_lean_recompile", "referee re-ran lake env lean on DESI_DR2_wCDM.lean: rc=0, six clean footprints, Elenchus no findings",
            LEAN, "rc=0" in rtxt and "no sorryAx" in rtxt, refp)
        add("referee.independent_numerics_rerun", "referee re-ran controls, CAMB and DR2_LCDM/DR2_wCDM/DR1_LCDM chains in /tmp copies",
            "referee: scripts copied to /tmp/ref_dr2_rerun", "bit-for-bit" in rtxt and "np.array_equal true" in rtxt, refp)
        add("referee.ledger_gate_rerun", "referee re-ran ledger gate read-only: rc=1, 0 blocks, 6 unaudited-Tier-A flags",
            "referee: ledger.py --evidence-dir ...", False, refp)

    # ---- repo guards / pytest / paper ----
    agl = RES / "guard_antigravity_ledger_stage.txt"
    if agl.exists():
        n_find = agl.read_text().count("Hallucinated import")
        add("verify.antigravity_guard_ledger_stage", f"repo guard, ledger stage: {n_find} hallucinated-import findings",
            VPY + " antigravity_guard.py", agl.read_text().rstrip().endswith("rc=0"), agl)
    for name, step, cmd in (("guard_test_rigor_fixround.txt", "verify.test_rigor_guard", VPY + " test_rigor_guard.py"),
                            ("guard_antigravity_fixround.txt", "verify.antigravity_guard", VPY + " antigravity_guard.py")):
        p = RES / name
        if p.exists():
            add(step, f"repo guard, fix round: {p.read_text().count('Hallucinated import')} hallucinated-import findings", cmd, p.read_text().rstrip().endswith("rc=0"), p)
    for name, step in (("pytest_ledger_stage.txt", "verify.pytest_plain_ledger_stage"),
                       ("pytest_ledger_stage_continue.txt", "verify.pytest_continue_ledger_stage"),
                       ("pytest_fixround_continue.txt", "verify.pytest_continue_fixround")):
        p = RES / name
        if p.exists():
            txt = re.sub(r"\x1b\[[0-9;]*m", "", p.read_text())
            last = [x for x in txt.splitlines() if x.strip() and not x.startswith("rc=")][-1]
            add(step, f"repo test suite ({name}); {last[:150]}", VPY + " -m pytest tests/ -q -p no:cacheprovider",
                txt.rstrip().endswith("rc=0"), p)
    plog = PAP / "desi_dr2_bao.log"
    if plog.exists():
        lg_txt = plog.read_text(errors="replace")
        ok = "Output written" in lg_txt and "Undefined control sequence" not in lg_txt and "undefined" not in lg_txt.lower()
        add("paper.pdflatex_two_pass", "desi_dr2_bao.tex", "cd papers/desi_dr2_bao && pdflatex desi_dr2_bao.tex (x2)", ok, plog)

    # ---- referee issues and fix-round outcomes (verdict = fixed in this round) ----
    tex = " ".join((PAP / "desi_dr2_bao.tex").read_text().split())
    gnum = (PAP / "gen_numbers.tex").read_text() if (PAP / "gen_numbers.tex").exists() else ""
    ref = RES / "referee_report.json"
    post_ok = post.exists() and load(post)["real"]["rc"] == 0
    rerun_ok = rr.exists() and bool(load(rr)["all_identical"])
    ag = RES / "guard_antigravity_fixround.txt"
    ag_ok = ag.exists() and "desi_dr2_bao" not in ag.read_text()
    issues = [
        ("1_lean_runner_not_used", "preregistered gate anse/formal/lean_runner.py not used (needs built olean; writes a temp file into the shared formal/)",
         False, "recorded as a process deviation (LL.md text returned); lean_runner not run", lg),
        ("2_z_domain_narrower", "E2_pos/E_pos proved for z>=0, preregistered z>-1",
         False, "disclosed as a preregistration deviation in paper, ledger blobs; Lean file unchanged to keep the audit binding", PAP / "desi_dr2_bao.tex"),
        ("3_ledger_unaudited_tier_A", "6 LEDGER_UNAUDITED_TIER_A flags",
         post_ok, "audit objects from the model referee recorded (auditor_kind=model); human audit still outstanding", post),
        ("4_byline_unverifiable", "byline named a model version and human supervision",
         "Opus" not in tex and "human-supervised" not in tex and "human supervision" not in tex, "byline and acknowledgment reworded", PAP / "desi_dr2_bao.tex"),
        ("5_nc5_per_realisation", "NC5 passes only in aggregate; 6/20 single fits PTE>1e-3",
         "NCfiveAbove" in tex and "NCfiveAbove" in gnum, "count and seeds generated into paper text, controls table and ledger B-0004", PAP / "gen_numbers.tex"),
        ("6_antigravity_guard", "antigravity_guard flags dr2_model.py sys.path import of fit_desi_bao",
         ag_ok, "not changed: the sys.path import is the preregistered model.parent_import mechanism", ag),
        ("7_rerun_coverage", "referee could not complete regeneration of DR1_wCDM, radiation chains and wCDM grids",
         rerun_ok, "all 6 chains and both grids regenerated from current scripts and compared", rr),
        ("8_dr1_wcdm_hrd_not_refetched", "DR1 wCDM rd*h=101.7(+2.9/-3.5) not re-fetched",
         "re-fetched in the fix round" in tex, "re-fetched 2404.03002v3 p.36 via alphaXiv; excerpt added to ledger L-0004", PAP / "desi_dr2_bao.tex"),
    ]
    for iid, issue, ok, outcome, ev in issues:
        add(f"referee_issue.{iid}", f"{issue} -> {outcome}", f"referee: {rel(ref)}", bool(ok), ev)

    out = RES / "episodes.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"wrote {len(rows)} episodes ({sum(r['verdict'] == 'fail' for r in rows)} fail) to {rel(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

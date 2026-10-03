"""Write results/bao_bbn_h0/episodes.jsonl: one row per verdict-bearing step with evidence on disk.

Every verdict is read from a result file at run time (never typed); a row whose evidence file
is missing makes the script fail rather than emit an unsupported row.
Run: python3 scripts/bao_bbn_h0/write_episodes.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "bao_bbn_h0"
PY = "/mnt/disks/disk-socrateai-local-1/venv-pta/bin/python"
PYC = "/mnt/disks/disk-socrateai-local-1/venv-cosmo/bin/python"
LEAN = ("cd /home/callensxavier_gmail_com/AutoevolveAI/formal && timeout 1500 lake env lean "
        "<worktree>/formal/ANSE/BAO_BBN_H0.lean")


def rel(p: Path) -> str:
    if not p.exists():
        raise FileNotFoundError(p)
    return str(p.relative_to(ROOT))


def row(step: str, inp: str, cmd: str, ok: bool, ev: Path) -> dict[str, Any]:
    return {"step": step, "input_summary": inp, "command": cmd, "verdict": "pass" if ok else "fail",
            "energy": 0.0 if ok else 1.0, "evidence_path": rel(ev)}


def main() -> int:
    rows: list[dict[str, Any]] = []
    fit = json.loads((RES / "fit.json").read_text())
    val = json.loads((RES / "rd_camb_validation.json").read_text())
    anc = json.loads((RES / "anchor_reproduction.json").read_text())

    # CAMB instrument
    src = (ROOT / "scripts" / "bao_bbn_h0" / "rd_camb_table.py").read_text()
    if "for 26 low-Omega_m nodes (first build, logged)" in src:
        rows.append(row("camb_rd_table_build_h1.0", "CAMB 2.0.4 r_drag grid with top h node 1.0",
                        f"{PYC} scripts/bao_bbn_h0/rd_camb_table.py", False,
                        ROOT / "scripts" / "bao_bbn_h0" / "rd_camb_table.py"))
    rows.append(row("camb_rd_table_build_final", f"49x61x3 grid, h<=0.99, {val['n_grid_h_substituted']} nodes refilled "
                    f"at lower h, n_grid_fail={val['n_grid_fail']}", f"{PYC} scripts/bao_bbn_h0/rd_camb_table.py",
                    val["n_grid_fail"] == 0, RES / "rd_camb_validation.json"))
    iv = {r["region"]: r for r in val["interpolation_vs_direct_camb"]}
    rows.append(row("camb_table_interpolation_vs_direct", f"core max {iv['core']['max_abs_frac']:.1e}, wide max "
                    f"{iv['wide']['max_abs_frac']:.1e} (accept < 1e-4)", f"{PYC} scripts/bao_bbn_h0/rd_camb_table.py",
                    max(iv["core"]["max_abs_frac"], iv["wide"]["max_abs_frac"]) < 1e-4, RES / "rd_camb_validation.json"))
    cls = max(abs(r["frac_class_minus_camb"]) for r in val["class_and_aubourg_vs_camb"])
    rows.append(row("class_vs_camb_rd_crosscheck", f"5 points, max |frac| {cls:.1e} (accept < 1e-4)",
                    f"{PYC} scripts/bao_bbn_h0/rd_camb_table.py", cls < 1e-4, RES / "rd_camb_validation.json"))
    r18 = val["anchor_planck2018_rdrag_nnu3.046"]
    rows.append(row("camb_anchor_planck2018_table1_bestfit", f"CAMB {r18:.4f} vs published 147.049 (accept |d| < 0.01)",
                    f"{PYC} scripts/bao_bbn_h0/rd_camb_table.py", abs(r18 - 147.049) < 0.01, RES / "rd_camb_validation.json"))
    a_camb = next(r for r in anc["rows"] if str(r["code"]).startswith("CAMB") and r.get("nnu") == 3.044)
    a_cls = next(r for r in anc["rows"] if str(r["code"]).startswith("CLASS") and r.get("N_ur") == 2.0328)
    rows.append(row("amendment_anchor_reproduction", f"Planck 2018 Table 2 lensing means: CAMB {a_camb['rdrag']:.4f} vs "
                    f"147.1027, CLASS {a_cls['rs_drag']:.4f} vs 147.0971 (accept |d| < 1e-3)",
                    f"{PYC} scripts/bao_bbn_h0/anchor_reproduce.py",
                    abs(a_camb["diff"]) < 1e-3 and abs(a_cls["diff"]) < 1e-3, RES / "anchor_reproduction.json"))

    # controls
    for name in ("P1", "P2", "N1", "N2"):
        for a in ("primary", "secondary"):
            p = RES / "controls" / f"{name}_{a}.json"
            d = json.loads(p.read_text())
            ok = bool(d.get("passed", d.get("control_behaves")))
            kind = "positive" if name.startswith("P") else "negative"
            rows.append(row(f"{kind}_control_{name}_{a}", f"{name} ({a} r_d); rule {d.get('pass_if', 'behaves as expected')}",
                            f"cd scripts/bao_bbn_h0 && {PY} controls.py {name.lower() if name.startswith('P') else 'n1n2'} {a}",
                            ok, p))
    p4 = json.loads((RES / "controls" / "P4.json").read_text())
    rows.append(row("positive_control_P4_predictor", f"manual vs astropy distances max frac {p4['max_frac_diff']:.1e}",
                    f"cd scripts/bao_bbn_h0 && {PY} controls.py p4 primary", bool(p4["passed"]), RES / "controls" / "P4.json"))
    for g in ("G1", "G2"):
        rows.append(row(f"positive_control_gate_{g}", f"BAO-only (Omega_m, h r_d) pulls {fit[g]['pull_Om']:.3f}, "
                        f"{fit[g]['pull_hrd']:.3f} (rule <= 0.25 sigma)", f"cd scripts/bao_bbn_h0 && {PY} fit_real.py",
                        bool(fit[g]["passed"]), RES / "fit.json"))
    for a in ("primary", "secondary"):
        n3 = fit[a]["N3"]
        rows.append(row(f"negative_control_N3_{a}", f"no BBN prior, sigma(H0) ratio {n3['sigma_H0_ratio_vs_baseline']:.2f} (rule > 5)",
                        f"cd scripts/bao_bbn_h0 && {PY} fit_real.py", bool(n3["control_behaves"]), RES / "fit.json"))
    if any("primary N3 stopped at 4000 steps" in d for d in fit["deviations"]):
        rows.append(row("negative_control_N3_primary_first_run_4000_steps",
                        "first N3 run stopped at 4000 steps with tau~57: tau likely underestimated, rerun with a 40000-step floor",
                        f"cd scripts/bao_bbn_h0 && {PY} fit_real.py", False, RES / "fit.json"))

    # fits: each estimation method, each analysis, each target
    for a in ("primary", "secondary"):
        for key, tgt in (("T1_DR2", 68.51), ("T2_DR1", 68.53)):
            r = fit[a][key]
            v = fit[a]["verdict_T1" if key == "T1_DR2" else "verdict_T2"]
            cmd = f"cd scripts/bao_bbn_h0 && {PY} fit_real.py"
            rows.append(row(f"fit_{a}_{key}_emcee_verdict", f"H0 {r['chain']['mean']['H0']:.3f} +- {r['chain']['std']['H0']:.3f} "
                            f"vs {tgt}; preregistered verdict {v['verdict']}", cmd, v["verdict"] == "PASS", RES / "fit.json"))
            rows.append(row(f"fit_{a}_{key}_map_laplace", f"MAP H0 {r['map']['H0']:.3f}, Laplace sigma "
                            f"{r['laplace']['sigma']['H0']:.3f}, |dH0| {abs(r['map']['H0'] - tgt):.3f} (strict 0.15)",
                            cmd, abs(r["map"]["H0"] - tgt) <= 0.15, RES / "fit.json"))
            pr = r["profile_H0"]
            mid = 0.5 * (pr["H0_lo_1sig"] + pr["H0_hi_1sig"])
            rows.append(row(f"fit_{a}_{key}_profile_likelihood", f"profile 1-sigma [{pr['H0_lo_1sig']:.3f}, "
                            f"{pr['H0_hi_1sig']:.3f}], midpoint |d| {abs(mid - tgt):.3f} (strict 0.15)",
                            cmd, abs(mid - tgt) <= 0.15, RES / "fit.json"))
    lk = fit["secondary_vs_locked_preamendment"]
    rows.append(row("secondary_vs_locked_preamendment", f"sha256 matches {lk['sha256_matches']}; T1 H0 diff "
                    f"{lk['T1_DR2']['H0']['diff']}", f"cd scripts/bao_bbn_h0 && {PY} fit_real.py",
                    bool(lk["sha256_matches"]) and lk["T1_DR2"]["H0"]["diff"] == 0.0, RES / "fit.json"))

    # Lean: every compile log on disk, each judged against its own expected theorem count
    for i, name, nthm in ((1, "lean_compile_1.txt", 8), (2, "lean_compile_2.txt", 8),
                          ("2b_rerun", "lean_compile_rerun_2026-09-27.txt", 8),
                          (3, "lean_compile_3_ledger_recheck.txt", 8),
                          (4, "lean_compile_4_fixround_attempt1.txt", 10), (5, "lean_compile_5_fixround.txt", 10)):
        p = RES / name
        t = p.read_text()
        fps = re.findall(r"depends on axioms: (\[.*?\])", t)
        clean_ax = len(fps) == nthm and all(f == "[propext, Classical.choice, Quot.sound]" for f in fps)
        rc0 = bool(re.search(r"^rc=0$", t, flags=re.M))
        warn = "warning" in t.lower()
        nerr = len(re.findall(r": error", t))
        rows.append(row(f"lean_compile_{i}", f"BAO_BBN_H0.lean ({nthm} theorems): rc0={rc0}, trusted footprints={clean_ax}, "
                        f"warning={warn}, errors={nerr}", LEAN, rc0 and clean_ax and not warn and nerr == 0, p))
    for name, target in (("lean_negative_control_sorry.txt", "DH_over_rd_degenerate"),
                         ("lean_negative_control_sorry_fixround.txt", "hrd_strictMonoOn_h")):
        p = RES / name
        t = p.read_text()
        caught = bool(re.search(r"^rc=0$", t, flags=re.M)) and bool(
            re.search(rf"'ANSE\.BAOBBNH0\.{target}' depends on axioms: \[[^\]]*sorryAx", t))
        rows.append(row(f"negative_control_lean_sorry_{target}", f"copy with {target} proved by sorry: rc 0 but sorryAx "
                        "must appear (the axiom rule, not rc, must reject it)", LEAN.replace("<worktree>/formal/ANSE", "/tmp"),
                        caught, p))
    el = RES / "elenchus_check.txt"
    rows.append(row("elenchus_check_lean", "elenchus_check.py on BAO_BBN_H0.lean (fix-round revision)",
                    "cd /home/callensxavier_gmail_com/AutoevolveAI/formal && lake env python3 .../elenchus_check.py <file>",
                    "no findings" in el.read_text(), el))

    # ledger
    lc = RES / "ledger" / "ledger_check.txt"
    lct = lc.read_text()
    nflag = lct.count("flag  LEDGER_UNAUDITED_TIER_A")
    rows.append(row("ledger_gate_fixround", f"Elenchus ledger.py on 43 claims: {nflag} unaudited Tier A flags (the two "
                    "fix-round identifiability theorems), block findings "
                    f"{lct.count(' block ')}", "python3 scripts/bao_bbn_h0/run_ledger_check.py ledger_check.txt",
                    "\nrc=0" in lct, lc))
    gc = json.loads((RES / "ledger" / "gate_check.json").read_text())
    for m in ("tier_inversion_caught", "blob_tamper_caught", "kind_overclaim_caught"):
        rows.append(row(f"ledger_mutation_{m}", "hand-built ledger mutation must be caught",
                        f"{PY} scripts/bao_bbn_h0/ledger_gate_check.py", bool(gc["verdict"][m]),
                        RES / "ledger" / "gate_check.json"))

    # paper build
    bl = json.loads((ROOT / "papers" / "bao_bbn_h0" / "build_log.json").read_text())
    rcs = [p["rc"] for p in bl["passes"]]
    nund, novf = len(bl["warnings"]["undefined"]), len(bl["warnings"]["overfull"])
    rows.append(row("paper_build", f"pdflatex x2 rc {rcs}, undefined {nund}, overfull {novf}, pages {bl['pages']}",
                    f"{PY} scripts/bao_bbn_h0/build_paper.py",
                    all(x == 0 for x in rcs) and nund == 0 and novf == 0,
                    ROOT / "papers" / "bao_bbn_h0" / "build_log.json"))

    # guards
    g1 = RES / "guard_test_rigor_fixround.txt"
    rows.append(row("guard_test_rigor", "test_rigor_guard.py (repo-wide)", "python3 test_rigor_guard.py",
                    "[PASS]" in g1.read_text(), g1))
    g2 = RES / "guard_antigravity_fixround.txt"
    rows.append(row("guard_antigravity", "antigravity_guard.py (repo-wide; 74 flags, 0 in scripts/bao_bbn_h0/)",
                    "python3 antigravity_guard.py", "[FAIL]" not in g2.read_text(), g2))
    pt = RES / "pytest_full_fixround.txt"
    if pt.exists():
        t = re.sub(r"\x1b\[[0-9;]*m", "", pt.read_text())
        last = [ln for ln in t.splitlines() if ln.strip()][-1] if t.strip() else "empty output"
        rows.append(row("pytest_tests", f"pytest tests/ with worktree .venv: {last[:200]}",
                        ".venv/bin/python -m pytest tests/ -q -p no:cacheprovider",
                        bool(re.search(r"\bpassed\b", last)) and not re.search(r"\b(failed|error|errors)\b", last), pt))

    # fix-round diagnostics and post-hoc control
    dg = json.loads((RES / "fixround_diagnostics.json").read_text())
    mono = dg["hrd_monotonicity"]
    boxes = [k for k in mono if k != "below_threshold_aub16"]
    rows.append(row("numeric_hrd_monotonicity", "h r_d(h) strictly increasing at fixed (Omega_m, omega_b), eq.16 + CAMB, "
                    "T1 +-5 sigma and wide boxes", f"{PY} scripts/bao_bbn_h0/fixround_diagnostics.py",
                    all(mono[k]["n_strictly_increasing"] == mono[k]["n_curves"] for k in boxes),
                    RES / "fixround_diagnostics.json"))
    bt = mono["below_threshold_aub16"]
    rows.append(row("numeric_hrd_hypothesis_needed", "below omega_m(1-2a) < omega_nu, eq.16 h r_d must decrease (Lean "
                    "hypothesis non-vacuous)", f"{PY} scripts/bao_bbn_h0/fixround_diagnostics.py",
                    bool(bt["strictly_decreasing_below"]) and bool(bt["strictly_increasing_above"]),
                    RES / "fixround_diagnostics.json"))
    n4p = RES / "controls" / "N4.json"
    n4 = json.loads(n4p.read_text())
    rows.append(row("negative_control_N4_posthoc", f"omega_nu not subtracted in CAMB r_d: dH0 {n4['dH0_wrong_minus_correct']:.3f} "
                    f"(must exceed strict 0.15), dchi2 {n4['delta_chi2_wrong_minus_correct']:.1e}",
                    f"cd scripts/bao_bbn_h0 && {PY} control_n4.py run", bool(n4["control_behaves"]), n4p))
    rb = dg["tolerance_rebudget"]
    rows.append(row("tolerance_rebudget_primary_T2", f"T2 |dH0| {rb['T2_abs_dH0']:.3f} vs re-derived strict "
                    f"{rb['rebudget_strict_km_s_Mpc']:.3f} (information only)",
                    f"{PY} scripts/bao_bbn_h0/fixround_diagnostics.py", bool(rb["T2_within_rebudget"]),
                    RES / "fixround_diagnostics.json"))

    # referee issues (fix round) and their outcomes, each judged from an artifact
    tex_p = ROOT / "papers" / "bao_bbn_h0" / "bao_bbn_h0.tex"
    tex = tex_p.read_text()
    lean_src = (ROOT / "formal" / "ANSE" / "BAO_BBN_H0.lean").read_text()
    led = json.loads((RES / "ledger" / "ledger.json").read_text())
    st = {c["id"]: c["statement"] for c in led["claims"]}
    lv = json.loads((RES / "lean_verification.json").read_text())
    common_src = (ROOT / "scripts" / "bao_bbn_h0" / "common.py").read_text()
    ref = [
        ("referee_fix1_fixed_E_glosses", "add 'at fixed E' to DH_over_rd glosses (Lean, ledger A-0006/7)",
         "At fixed `E`" in lean_src and "at fixed E" in st["BBNH0-A-0006"] and "at fixed E" in st["BBNH0-A-0007"],
         RES / "ledger" / "ledger.json"),
        ("referee_fix2_identifiability_theorem", "prove the preregistered h*r_d(h) strictly increasing statement",
         bool(lv["accepted"]) and "hrd_strictMonoOn_h" in lv["theorems"], RES / "lean_verification.json"),
        ("referee_fix3_tolerance_generous", "say the strict limit is generous for the CAMB primary, with re-derived budget",
         "generous for the" in tex and "\\RebStrict" in tex, tex_p),
        ("referee_fix4_control_power", "state control discriminating power; add informative post-hoc control N4",
         "What the controls do and do not show" in tex and n4p.exists(), tex_p),
        ("referee_fix5_h_dependence_docs", "fix '~1e-7' docstring; use HDep in the paper",
         "~1e-7" not in common_src and tex.count("\\HDep") >= 1, ROOT / "scripts" / "bao_bbn_h0" / "common.py"),
        ("referee_fix6_T2_propagation", "add h r_d propagation for the T2 offset",
         "\\PropEight" in tex and "\\PropNine" in tex, tex_p),
        ("referee_fix7_unverifiable_labels", "label model attribution and 'not read' assertion as unverifiable",
         tex.count("unverifiable") >= 2, tex_p),
    ]
    for step, inp, ok, ev in ref:
        rows.append(row(step, inp, "fix round (see evidence)", ok, ev))
    rows.append(row("referee_fix8_repo_guards", "referee issue 8 outcome: NOT fixed (same observation as the "
                    "guard_antigravity row above; 74 flags outside this problem, outside the write scope)",
                    "python3 antigravity_guard.py",
                    "[FAIL]" not in g2.read_text(), g2))

    out = RES / "episodes.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    npass = sum(r["verdict"] == "pass" for r in rows)
    print(f"wrote {len(rows)} episodes ({npass} pass, {len(rows) - npass} fail) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

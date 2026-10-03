"""Generate the LaTeX inputs of papers/bao_bbn_h0/bao_bbn_h0.tex from regenerated result files.

Every number from this run that appears in the paper is a macro written here
from results/bao_bbn_h0/*.json (fit.json, controls/, rd_camb_validation.json,
ledger/gate_check.json) or from preregistration.json (published targets); the
tex file types none of them. Also writes the DESI data tables (read from the
sha256-locked data files), the verbatim Lean theorem statements (extracted from
formal/ANSE/BAO_BBN_H0.lean, Unicode mapped to LaTeX math) and the verbatim
axiom log.

Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/bao_bbn_h0/make_paper_inputs.py
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "bao_bbn_h0"
OUT = ROOT / "papers" / "bao_bbn_h0"
LEAN = ROOT / "formal" / "ANSE" / "BAO_BBN_H0.lean"
LEAN_LOG = RES / "lean_compile_5_fixround.txt"
DATA = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
DR2 = ("desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_mean.txt", "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_cov.txt")
DR1 = ("desi_2024_gaussian_bao_ALL_GCcomb_mean.txt", "desi_2024_gaussian_bao_ALL_GCcomb_cov.txt")
GLYPHS = [("ℝ", "$\\mathbb{R}$"), ("≠", "$\\neq$"), ("≤", "$\\le$"), ("→", "$\\to$"), ("↦", "$\\mapsto$"),
          ("ω", "$\\omega$"), ("Ω", "$\\Omega$"), ("ₘ", "$_m$"), ("²", "$^2$"), ("∞", "$\\infty$"), ("∧", "$\\wedge$")]


def fmt(x: float, n: int) -> str:
    return f"{x:.{n}f}"


def sci(x: float, n: int = 1) -> str:
    if x == 0:
        return "0"
    e = int(math.floor(math.log10(abs(x))))
    m = x / 10 ** e
    return f"\\ensuremath{{{m:.{n}f}\\times10^{{{e}}}}}"


def sgn(x: float, n: int) -> str:
    return f"{x:+.{n}f}"


def load(rel: str) -> dict[str, Any]:
    return json.loads((RES / rel).read_text())


def run_macros(m: dict[str, str], pre: str, r: dict[str, Any], v: dict[str, Any]) -> None:
    c = r["chain"]
    m[pre + "H"] = fmt(c["mean"]["H0"], 2)
    m[pre + "HErr"] = fmt(c["std"]["H0"], 2)
    m[pre + "Hthree"] = fmt(c["mean"]["H0"], 3)
    m[pre + "HErrthree"] = fmt(c["std"]["H0"], 3)
    m[pre + "Om"] = fmt(c["mean"]["Omega_m"], 4)
    m[pre + "OmErr"] = fmt(c["std"]["Omega_m"], 4)
    m[pre + "Wb"] = fmt(c["mean"]["omega_b"], 5)
    m[pre + "WbErr"] = fmt(c["std"]["omega_b"], 5)
    m[pre + "MapH"] = fmt(r["map"]["H0"], 2)
    m[pre + "LapH"] = fmt(r["laplace"]["sigma"]["H0"], 2)
    m[pre + "ProfLo"] = fmt(r["profile_H0"]["H0_lo_1sig"], 2)
    m[pre + "ProfHi"] = fmt(r["profile_H0"]["H0_hi_1sig"], 2)
    m[pre + "ProfSig"] = fmt(r["profile_H0"]["sigma_sym"], 2)
    m[pre + "Chi"] = fmt(r["chi2_map"], 2)
    m[pre + "Dof"] = str(r["dof"])
    m[pre + "Pte"] = fmt(r["pte"], 2)
    m[pre + "Ess"] = fmt(c["ess"], 0)
    m[pre + "Steps"] = str(c["n_steps"])
    m[pre + "Tau"] = fmt(max(c["tau"].values()), 0)
    m[pre + "Rd"] = fmt(r["derived"]["rd_mean"], 1)
    m[pre + "RdErr"] = fmt(r["derived"]["rd_std"], 1)
    m[pre + "Hrd"] = fmt(r["derived"]["hrd_mean"], 2)
    m[pre + "HrdErr"] = fmt(r["derived"]["hrd_std"], 2)
    m[pre + "Corr"] = fmt(c["corr"][0][1], 2)
    m[pre + "DH"] = fmt(v["abs_dH0"], 3)
    m[pre + "PullH"] = fmt(v["pull_H0"], 2)
    m[pre + "PullOm"] = fmt(v["pull_Om"], 4)
    m[pre + "SigRatio"] = fmt(v["sigma_ratio"], 3)
    m[pre + "Verdict"] = v["verdict"]


def gate_macros(m: dict[str, str], pre: str, g: dict[str, Any]) -> None:
    c = g["chain"]
    m[pre + "Om"] = fmt(c["mean"]["Omega_m"], 4)
    m[pre + "OmErr"] = fmt(c["std"]["Omega_m"], 4)
    m[pre + "Hrd"] = fmt(c["mean"]["hrd"], 2)
    m[pre + "HrdErr"] = fmt(c["std"]["hrd"], 2)
    m[pre + "Corr"] = fmt(c["corr"][0][1], 2)
    m[pre + "Chi"] = fmt(g["chi2_map"], 2)
    m[pre + "Dof"] = str(g["dof"])
    m[pre + "Pte"] = fmt(g["pte"], 2)
    m[pre + "PullOm"] = fmt(g["pull_Om"], 3)
    m[pre + "PullHrd"] = fmt(g["pull_hrd"], 3)
    m[pre + "Passed"] = "passed" if g["passed"] else "FAILED"


def macros() -> dict[str, str]:
    fit = load("fit.json")
    prereg = load("preregistration.json")
    val = load("rd_camb_validation.json")
    gate = load("ledger/gate_check.json")
    lean_v = load("lean_verification.json")
    ctrl = {k: load(f"controls/{k}.json") for k in
            ("P1_primary", "P1_secondary", "P2_primary", "P2_secondary", "N1_primary", "N1_secondary",
             "N2_primary", "N2_secondary", "P4")}
    m: dict[str, str] = {}
    P, S = fit["primary"], fit["secondary"]
    run_macros(m, "PTOne", P["T1_DR2"], P["verdict_T1"])
    run_macros(m, "PTTwo", P["T2_DR1"], P["verdict_T2"])
    run_macros(m, "STOne", S["T1_DR2"], S["verdict_T1"])
    run_macros(m, "STTwo", S["T2_DR1"], S["verdict_T2"])
    gate_macros(m, "GOne", fit["G1"])
    gate_macros(m, "GTwo", fit["G2"])
    m["GRadH"] = str(fit["G1"]["radiation_h_fixed"])

    tg = {t["id"]: t for t in prereg["targets"]}
    m["TgTOneH"], m["TgTOneHErr"] = str(tg["T1"]["value"]), str(tg["T1"]["sigma"])
    m["TgTOneOm"], m["TgTOneOmErr"] = str(tg["T1b"]["value"]), str(tg["T1b"]["sigma"])
    m["TgTTwoH"], m["TgTTwoHErr"] = str(tg["T2"]["value"]), fmt(tg["T2"]["sigma"], 2)
    m["TgTTwoOm"], m["TgTTwoOmErr"] = str(tg["T2b"]["value"]), str(tg["T2b"]["sigma"])
    m["TgGOneOm"], m["TgGOneOmErr"] = str(tg["G1"]["Omega_m"][0]), str(tg["G1"]["Omega_m"][1])
    m["TgGOneHrd"], m["TgGOneHrdErr"] = str(tg["G1"]["hrd_Mpc"][0]), str(tg["G1"]["hrd_Mpc"][1])
    m["TgGOneCorr"] = str(tg["G1"]["corr"])
    m["TgGTwoOm"], m["TgGTwoOmErr"] = str(tg["G2"]["Omega_m"][0]), str(tg["G2"]["Omega_m"][1])
    m["TgGTwoHrd"], m["TgGTwoHrdErr"] = str(tg["G2"]["hrd_Mpc"][0]), str(tg["G2"]["hrd_Mpc"][1])
    bbn = prereg["model"]["bbn_prior"]
    m["BbnMean"], m["BbnSig"] = str(bbn["omega_b_mean"]), str(bbn["omega_b_sigma"])
    tol = prereg["tolerance"]
    m["TolStrict"], m["TolSoft"] = str(tol["strict_H0_km_s_Mpc"]), str(tol["soft_H0_km_s_Mpc"])
    m["TolStrictSig"] = str(tol["strict_in_units_of_sigma_pub_T1"])
    m["SysStrict"] = str(prereg["systematic_budget"]["sigma_sys_H0_strict"])
    m["PreregTime"] = prereg["timestamp_utc"].replace("T", " ").replace("Z", "")
    amend = load("preregistration_amendment_1.json")
    m["AmendTime"] = amend["timestamp_utc"].replace("T", " ").replace("Z", "")

    p1p, p1s, p2p, p2s = ctrl["P1_primary"], ctrl["P1_secondary"], ctrl["P2_primary"], ctrl["P2_secondary"]
    m["POneHp"], m["POneOmp"] = sgn(p1p["dH0"], 4), sgn(p1p["dOm"], 4)
    m["POneHs"], m["POneOms"] = sgn(p1s["dH0"], 4), sgn(p1s["dOm"], 4)
    m["PTwoN"] = str(p2p["n_mocks"])
    m["PTwoMeanP"], m["PTwoStdP"] = fmt(p2p["pull_H0_mean"], 3), fmt(p2p["pull_H0_std"], 3)
    m["PTwoMeanS"], m["PTwoStdS"] = fmt(p2s["pull_H0_mean"], 3), fmt(p2s["pull_H0_std"], 3)
    m["PTwoOmMeanP"], m["PTwoOmStdP"] = fmt(p2p["pull_Om_mean"], 3), fmt(p2p["pull_Om_std"], 3)
    m["PTwoChiP"] = fmt(p2p["chi2_mean"], 2)
    m["PFour"] = sci(ctrl["P4"]["max_frac_diff"])
    n1p, n1s, n2p, n2s = ctrl["N1_primary"], ctrl["N1_secondary"], ctrl["N2_primary"], ctrl["N2_secondary"]
    m["NOneChiP"], m["NOneChiS"] = sci(n1p["chi2"], 2), sci(n1s["chi2"], 2)
    m["NOnePte"] = str(n1p["pte"])
    m["NOneRealPte"] = fmt(n1p["real_pte"], 3)
    m["NTwoChiP"], m["NTwoChiS"] = fmt(n2p["chi2"], 1), fmt(n2s["chi2"], 1)
    m["NTwoDof"], m["NTwoPte"] = str(n2p["dof"]), sci(n2p["pte"])
    for a, key in (("P", P), ("S", S)):
        n3 = key["N3"]
        tmax = max(n3["chain"]["tau"].values())
        m[f"NThreeRatio{a}"] = fmt(n3["sigma_H0_ratio_vs_baseline"], 2)
        m[f"NThreeSig{a}"] = fmt(n3["chain"]["std"]["H0"], 1)
        m[f"NThreeSteps{a}"] = str(n3["chain"]["n_steps"])
        m[f"NThreeTau{a}"] = fmt(tmax, 0)
        m[f"NThreeStepsTau{a}"] = fmt(n3["chain"]["n_steps"] / tmax, 0)

    anc = fit["camb_instrument_anchor"]
    m["CambAnchor"] = fmt(anc["camb_rdrag_this_run"], 4)
    m["CambOrch"] = str(anc["orchestrator_positive_control_rdrag"])
    m["ClassOrch"] = str(anc["orchestrator_positive_control_rsdrag_class"])
    arows = anc["orchestrator_anchor_reproduction"]["rows"]
    a_camb = next(r for r in arows if str(r["code"]).startswith("CAMB") and r.get("nnu") == 3.044)
    a_cls = next(r for r in arows if str(r["code"]).startswith("CLASS") and r.get("N_ur") == 2.0328)
    a_cls44 = next(r for r in arows if str(r["code"]).startswith("CLASS") and r.get("N_ur") == 2.0308)
    m["AnchorCambTwo"] = fmt(a_camb["rdrag"], 4)
    m["AnchorClassTwo"] = fmt(a_cls["rs_drag"], 4)
    m["AnchorClassNeff"] = fmt(a_cls["class_Neff"], 3)
    m["AnchorClassMatched"] = fmt(a_cls44["rs_drag"], 4)
    m["AnchorClassMatchedNeff"] = fmt(a_cls44["class_Neff"], 3)
    m["AnchorMatchedFrac"] = sci(a_cls44["rs_drag"] / a_camb["rdrag"] - 1.0)
    t2b = fit["T2_boundary_resolution"]
    m["TTwoMarginP"] = fmt(t2b["primary"]["margin_over_strict"], 3)
    m["TTwoMcP"] = fmt(t2b["primary"]["our_mc_error_H0"], 3)
    m["TTwoResRatioP"] = fmt(t2b["primary"]["margin_over_combined_resolution"], 1)
    m["TTwoMarginS"] = fmt(t2b["secondary"]["margin_over_strict"], 3)
    m["TTwoMcS"] = fmt(t2b["secondary"]["our_mc_error_H0"], 3)
    m["TTwoResRatioS"] = fmt(t2b["secondary"]["margin_over_combined_resolution"], 1)
    iv = {r["region"]: r for r in val["interpolation_vs_direct_camb"]}
    m["InterpCoreMax"], m["InterpCoreRms"] = sci(iv["core"]["max_abs_frac"]), sci(iv["core"]["rms_frac"])
    m["InterpWideMax"] = sci(iv["wide"]["max_abs_frac"])
    m["InterpCoreN"], m["InterpWideN"] = str(iv["core"]["n"]), str(iv["wide"]["n"])
    rows = val["class_and_aubourg_vs_camb"]
    m["ClassMax"] = sci(max(abs(r["frac_class_minus_camb"]) for r in rows))
    aub = [r["frac_aub16_minus_camb"] for r in rows]
    m["AubMin"], m["AubMax"] = fmt(100 * min(aub), 3), sgn(100 * max(aub), 3)
    m["AubMaxAbs"] = fmt(100 * max(abs(x) for x in aub), 3)
    # uncorrected N_eff offset of eq. 16 (fitted at N_eff = 3.046) at N_eff = 3.044, using the
    # N_eff slope of Aubourg eq. 17 as in build_ledger.py (claim BBNH0-L-0013)
    m["NeffOffsetPct"] = fmt(100 * (3.046 - 3.044) / 30.60, 4)
    m["BgMax"] = sci(max(max(r["max_frac_DM"], r["max_frac_DH"]) for r in val["camb_background_vs_manual_distances"]))
    m["NSubst"] = str(val["n_grid_h_substituted"])
    m["NGrid"] = str(val["grid"]["ln_omega_b"][2] * val["grid"]["ln_omega_cdm"][2] * len(val["grid"]["h_nodes"]))
    m["HDep"] = sci(val["max_frac_h_dependence_over_nodes"])
    # fix-round diagnostics (scripts/bao_bbn_h0/fixround_diagnostics.py) and post-hoc control N4
    dg = load("fixround_diagnostics.json")
    hd = dg["h_dependence"]
    m["HDepCore"] = sci(hd["max_frac_core"])
    m["HDepArgH"] = fmt(hd["argmax"]["h_node"], 1)
    mono = dg["hrd_monotonicity"]
    m["MonoN"] = str(mono["T1_pm5sigma_camb"]["n_curves"])
    m["MonoAllOk"] = "all" if all(v["n_strictly_increasing"] == v["n_curves"] for k, v in mono.items()
                                  if k != "below_threshold_aub16") else "NOT all"
    m["MonoThr"] = fmt(mono["below_threshold_aub16"]["omega_m_threshold"], 4)
    m["MonoBelowDec"] = "strictly decreasing" if mono["below_threshold_aub16"]["strictly_decreasing_below"] else "NOT decreasing"
    sl = dg["slope_and_T2_propagation"]
    m["SlopeP"] = fmt(sl["primary_T1_DR2_dlnhrd_dlnh"], 3)
    t2p = [r for r in sl["T2_propagation"] if r["analysis"] == "primary"]
    m["PropEight"] = fmt(t2p[0]["implied_H0_excess_km_s_Mpc"], 2)
    m["PropNine"] = fmt(t2p[1]["implied_H0_excess_km_s_Mpc"], 2)
    m["PropSlopeTwo"] = fmt(t2p[0]["slope"], 3)
    rb = dg["tolerance_rebudget"]
    m["RebMc"] = fmt(rb["sigma_mc_from_preregistration"], 2)
    m["RebInterp"] = fmt(rb["interp_term_km_s_Mpc"], 3)
    m["RebStrict"] = fmt(rb["rebudget_strict_km_s_Mpc"], 3)
    m["RebTOne"] = "passes" if rb["T1_within_rebudget"] else "fails"
    m["RebTTwo"] = "passes" if rb["T2_within_rebudget"] else "fails"
    n4 = load("controls/N4.json")
    m["NFourShift"] = sgn(n4["dH0_wrong_minus_correct"], 3)
    m["NFourDchi"] = sci(abs(n4["delta_chi2_wrong_minus_correct"]))
    m["NFourCaught"] = "exceeds" if n4["control_behaves"] else "does NOT exceed"
    lv = load("lean_verification.json")
    m["LeanNThm"] = str(len(lv["theorems"]))
    m["CambVer"] = val["camb_version"]

    mfs = fit["measured_formula_systematic"]
    m["DPrimSecOne"] = sgn(mfs["primary_minus_secondary_H0_T1"], 3)
    m["DPrimSecTwo"] = sgn(mfs["primary_minus_secondary_H0_T2"], 3)
    sens = fit["sensitivity"]
    m["SensEqTwo"] = sgn(sens["S2_desi_eq2"]["dH0_vs_T1"], 3)
    m["SensNoRadS"] = sgn(sens["S3_no_radiation_secondary"]["dH0_vs_T1"], 3)
    m["SensNoRadP"] = sgn(sens["S3_no_radiation_primary"]["dH0_vs_T1"], 3)
    m["SensNeff"] = sgn(sens["S1_Neff4.044_secondary"]["dH0_vs_T1"], 2)

    lk = fit["secondary_vs_locked_preamendment"]
    m["LockedSha"] = lk["sha256_now"][:16]
    m["LockedHOne"] = fmt(lk["T1_DR2"]["H0"]["locked_mean"], 3)
    m["LockedHOneErr"] = fmt(lk["T1_DR2"]["H0"]["locked_std"], 3)
    m["LockedHTwo"] = fmt(lk["T2_DR1"]["H0"]["locked_mean"], 3)
    m["LockedHTwoErr"] = fmt(lk["T2_DR1"]["H0"]["locked_std"], 3)
    m["LockedOmOne"] = fmt(lk["T1_DR2"]["Omega_m"]["locked_mean"], 4)
    m["LockedDiffOne"] = str(lk["T1_DR2"]["H0"]["diff"])
    m["LockedDiffTwo"] = str(lk["T2_DR1"]["H0"]["diff"])

    m["PreregShaShort"] = fit["preregistration_sha256"][:16]
    m["FitShaShort"] = hashlib.sha256((RES / "fit.json").read_bytes()).hexdigest()[:16]
    m["LeanShaShort"] = lean_v["file_sha256_after_final_compile"][:16]
    m["LedgerClaims"] = str(gate["real"]["n_claims"])
    m["LedgerBlock"] = str(gate["real"]["n_block"])
    m["LedgerFlag"] = str(gate["real"]["n_flag"])
    m["LedgerRc"] = str(gate["real"]["rc"])
    m["Runtime"] = fmt(fit["runtime_s"], 0)
    # repository checks re-run in the fix round (raw logs under results/bao_bbn_h0/)
    rig = (RES / "guard_test_rigor_fixround.txt").read_text()
    mt = re.search(r"All tests in (\d+) file\(s\) passed anti-stub AST validation", rig)
    m["RigorFiles"] = mt.group(1) if mt else "FAILED"
    ag = (RES / "guard_antigravity_fixround.txt").read_text()
    ag_lines = [ln for ln in ag.splitlines() if "Hallucinated import" in ln]
    m["AgStatus"] = "FAIL" if "[FAIL]" in ag else "PASS"
    m["AgFlags"] = str(len(ag_lines))
    m["AgOwnFlags"] = str(sum("scripts/bao_bbn_h0/" in ln for ln in ag_lines))
    m["AgOwnCamb"] = str(sum("scripts/bao_bbn_h0/" in ln and "'camb'" in ln for ln in ag_lines))
    py = re.sub(r"\x1b\[[0-9;]*m", "", (RES / "pytest_full_fixround.txt").read_text())
    last = [ln for ln in py.splitlines() if ln.strip()][-1]
    coll = re.search(r"Interrupted: (\d+) errors? during collection", py)
    if coll:
        mods = sorted(set(re.findall(r"ModuleNotFoundError: No module named '([\w.]+)'", py)))
        m["PyResult"] = (f"collection was interrupted by {coll.group(1)} errors, all "
                         f"\\texttt{{ModuleNotFoundError}} for "
                         + ", ".join(f"\\texttt{{{x}}}" for x in mods)
                         + " (the worktree venv lacks the optional extras), so no test ran")
    else:
        m["PyResult"] = last.strip("= ").replace("%", "\\%")
    return m


def data_table(mean_f: str, cov_f: str) -> str:
    qname = {"DM_over_rs": r"$D_M/r_d$", "DH_over_rs": r"$D_H/r_d$", "DV_over_rs": r"$D_V/r_d$"}
    rows = []
    for ln in (DATA / mean_f).read_text().splitlines():
        if ln.strip() and not ln.lstrip().startswith("#"):
            z, v, q = ln.split()
            rows.append((float(z), q, float(v)))
    sig = np.sqrt(np.diag(np.atleast_2d(np.loadtxt(DATA / cov_f))))
    if len(sig) != len(rows):
        raise ValueError(f"{mean_f}: {len(rows)} rows vs cov dim {len(sig)}")
    body = "\n".join(f"{z:.3f} & {qname[q]} & {v:.3f} & {s:.3f} \\\\" for (z, q, v), s in zip(rows, sig))
    return ("\\begin{tabular}{cccc}\n\\toprule\n$z_\\mathrm{eff}$ & Quantity & Value & $\\sigma$ \\\\\n"
            "\\midrule\n" + body + "\n\\bottomrule\n\\end{tabular}\n")


def lean_statements() -> str:
    src = LEAN.read_text()
    blocks = re.findall(r"^(theorem .*?:= by)", src, flags=re.S | re.M)
    out = []
    for b in blocks:
        b = b[: -len(":= by")].rstrip() + " := ..."
        for u, t in GLYPHS:
            b = b.replace(u, t)
        bad = sorted({c for c in b if ord(c) > 127})
        if bad:
            raise ValueError(f"unmapped non-ASCII characters in Lean statement: {bad}")
        out.append(b)
    if len(out) != 10:
        raise ValueError(f"expected 10 theorems, found {len(out)}")
    return "\\begin{lstlisting}[mathescape]\n" + "\n\n".join(out) + "\n\\end{lstlisting}\n"


def lean_defs() -> str:
    src = LEAN.read_text()
    blocks = re.findall(r"^(noncomputable def .*?)(?=\n\n|\n/--)", src, flags=re.S | re.M)
    out = []
    for b in blocks:
        for u, t in GLYPHS:
            b = b.replace(u, t)
        bad = sorted({c for c in b if ord(c) > 127})
        if bad:
            raise ValueError(f"unmapped non-ASCII characters in Lean definition: {bad}")
        out.append(b.rstrip())
    if len(out) != 5:
        raise ValueError(f"expected 5 definitions, found {len(out)}")
    return "\\begin{lstlisting}[mathescape]\n" + "\n\n".join(out) + "\n\\end{lstlisting}\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    m = macros()
    for k, v in m.items():
        if re.fullmatch(r"[+-]\d+(\.\d+)?", v):
            m[k] = f"\\ensuremath{{{v}}}"
    for k in m:
        if not re.fullmatch(r"[A-Za-z]+", k):
            raise ValueError(f"bad macro name {k}")
    (OUT / "gen_numbers.tex").write_text(
        "% generated by scripts/bao_bbn_h0/make_paper_inputs.py -- do not edit\n"
        + "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(m.items())))
    (OUT / "gen_dr2_table.tex").write_text(data_table(*DR2))
    (OUT / "gen_dr1_table.tex").write_text(data_table(*DR1))
    (OUT / "gen_lean.tex").write_text(lean_statements())
    (OUT / "gen_lean_defs.tex").write_text(lean_defs())
    log = LEAN_LOG.read_text()
    if any(ord(c) > 127 for c in log):
        raise ValueError("non-ASCII in Lean log")
    body = "\n".join(ln for ln in log.splitlines() if not ln.startswith("# command"))
    (OUT / "gen_axioms.tex").write_text("\\begin{verbatim}\n" + body.replace("' depends", "'\n    depends")
                                        + "\n\\end{verbatim}\n")
    print(f"wrote {len(m)} macros and 5 table/listing files to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

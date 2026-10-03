"""Generate the LaTeX inputs of papers/eboss_vs_desi/eboss_vs_desi.tex from result files.

No number in the paper's results, controls or data tables is typed by hand: this
script reads results/eboss_vs_desi/*.json, the Lean source and its compile log,
and the sha256-verified data files, and writes
  papers/eboss_vs_desi/gen_numbers.tex      (\newcommand macros)
  papers/eboss_vs_desi/gen_desi_table.tex   (DESI DR2 data rows, sigma = sqrt(diag cov))
  papers/eboss_vs_desi/gen_sdss_table.tex   (SDSS Gaussian pieces, sigma = sqrt(diag cov))
  papers/eboss_vs_desi/gen_lean.tex         (theorem statements extracted from the .lean file)
  papers/eboss_vs_desi/gen_axioms.tex       (the #print axioms output, verbatim)
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
RES = ROOT / "results" / "eboss_vs_desi"
OUT = ROOT / "papers" / "eboss_vs_desi"
DATA = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
LEAN = ROOT / "formal" / "ANSE" / "BAO_Consistency.lean"
LEAN_LOG = RES / "lean_BAO_Consistency_compile_fixround2.log"
ELG_TABLE = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao/sdss_DR16_ELG_BAO_DVtable.txt")

GLYPHS = [("⬝ᵥ", r"$\cdot_v$"), ("*ᵥ", r"$*_v$"), ("⁻¹", r"$^{-1}$"), ("ℝ", r"$\mathbb{R}$"),
          ("μ", r"$\mu$"), ("σ", r"$\sigma$"), ("≠", r"$\neq$"), ("≤", r"$\le$"),
          ("↔", r"$\leftrightarrow$"), ("∧", r"$\wedge$"), ("→", r"$\to$")]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def fmt(x: float, n: int) -> str:
    if not math.isfinite(x):
        raise ValueError("non-finite value must be handled explicitly")
    return f"{x:.{n}f}"


def sci(x: float) -> str:
    m, e = f"{x:.1e}".split("e")
    return rf"{m}\times10^{{{int(e)}}}"


def macros(fit: dict[str, Any], pos: dict[str, Any], neg: dict[str, Any], ins: dict[str, Any],
           camb: dict[str, Any], gate: dict[str, Any]) -> dict[str, str]:
    F = fit["fits"]
    D, S, G = F["DESI_DR2"], F["SDSS_eBOSS_DR16_baseline"], F["SDSS_eBOSS_DR16_gaussian_summary"]
    T = fit["tension"]
    P = {p["name"]: p for p in fit["pulls"]}
    m: dict[str, str] = {}
    for tag, R in (("Desi", D), ("Sdss", S), ("Sgs", G)):
        e, g, mp, la = R["emcee"], R["grid"], R["MAP"], R["laplace"]
        m[f"{tag}Om"] = fmt(e["mean_Om"], 4)
        m[f"{tag}OmErr"] = fmt(e["std_Om"], 4)
        m[f"{tag}Hrd"] = fmt(e["mean_hrd"], 2)
        m[f"{tag}HrdErr"] = fmt(e["std_hrd"], 2)
        m[f"{tag}Corr"] = fmt(e["corr"], 3)
        m[f"{tag}GridOm"] = fmt(g["mean_Om"], 4)
        m[f"{tag}GridOmErr"] = fmt(g["std_Om"], 4)
        m[f"{tag}GridHrd"] = fmt(g["mean_hrd"], 2)
        m[f"{tag}GridHrdErr"] = fmt(g["std_hrd"], 2)
        m[f"{tag}MapOm"] = fmt(mp["Om"], 4)
        m[f"{tag}MapHrd"] = fmt(mp["hrd"], 2)
        m[f"{tag}MapChi"] = fmt(mp["m2lnL_min"], 2)
        m[f"{tag}Dof"] = str(mp["dof"])
        m[f"{tag}Ndata"] = str(mp["n_data"])
        m[f"{tag}LapOmErr"] = fmt(la["sigma_Om"], 4)
        m[f"{tag}LapHrdErr"] = fmt(la["sigma_hrd"], 2)
        m[f"{tag}TauMax"] = fmt(max(e["tau"]), 1)
        m[f"{tag}Acc"] = fmt(e["acceptance"], 2)
        m[f"{tag}EmGridDiff"] = fmt(max(R["emcee_vs_grid_mean_diff_in_sigma"]), 3)
    e0 = D["emcee"]
    m["Nwalk"], m["Nstep"], m["Nburn"] = str(e0["nwalkers"]), str(e0["nsteps"]), str(e0["burn"])
    m["GridN"] = str(D["grid"]["n"])
    sh = fit["baseline_vs_gaussian_summary_shift_in_baseline_sigma"]
    m["ShiftOm"], m["ShiftHrd"] = fmt(sh["Om"], 3), fmt(sh["hrd"], 3)
    for tag, k in (("T", "primary_emcee_moments"), ("TGrid", "grid_moments"), ("TMap", "MAP_laplace"),
                   ("TGs", "gaussian_summary_variant_emcee")):
        m[f"{tag}Chi"] = fmt(T[k]["chi2"], 3)
        m[f"{tag}Pte"] = fmt(T[k]["PTE"], 3)
        m[f"{tag}Nsig"] = fmt(T[k]["N_sigma"], 3)
        m[f"{tag}OneOm"] = fmt(T[k]["one_d_sigma"]["Om"], 3)
        m[f"{tag}OneHrd"] = fmt(T[k]["one_d_sigma"]["hrd"], 3)
    m["TKdePte"] = fmt(T["posterior_parameter_shift_KDE"]["PTE"], 3)
    m["TKdeNsig"] = fmt(T["posterior_parameter_shift_KDE"]["N_sigma"], 3)
    m["TKdeN"] = str(T["posterior_parameter_shift_KDE"]["n_samples"])
    for tag, k in (("PullSdssOm", "SDSS_Om"), ("PullSdssHrd", "SDSS_hrd_Mpc"),
                   ("PullDesiOm", "DESI_DR2_Om"), ("PullDesiHrd", "DESI_DR2_hrd_Mpc")):
        m[tag] = f"{P[k]['pull_sigma']:+.3f}"
    m["WithinTol"] = "true" if fit["within_tolerance"] else "false"
    # positive control
    m["PcN"], m["PcSeed"] = str(pos["n_realizations"]), str(pos["seed"])
    for tag, k in (("PcS", "SDSS_gaussian_summary"), ("PcD", "DESI_DR2")):
        m[f"{tag}CovOm"] = fmt(pos[k]["coverage_1sigma"]["Om"], 3)
        m[f"{tag}CovHrd"] = fmt(pos[k]["coverage_1sigma"]["hrd"], 3)
        m[f"{tag}BiasOm"] = fmt(pos[k]["bias_over_median_sigma"]["Om"], 3)
        m[f"{tag}BiasHrd"] = fmt(pos[k]["bias_over_median_sigma"]["hrd"], 3)
        m[f"{tag}EmCov"] = "/".join(fmt(x, 2) for x in pos["emcee_subset"][k]["coverage_1sigma"])
    m["PcTMed"] = fmt(pos["tension_calibration"]["median_N_sigma"], 3)
    m["PcTKs"] = fmt(pos["tension_calibration"]["KS_PTE_uniform_p"], 3)
    m["PcTGtTwo"] = fmt(pos["tension_calibration"]["frac_N_sigma_gt_2"], 3)
    m["PcPass"] = "passed" if pos["positive_control_passed"] else "FAILED"
    m["PcSKsChi"] = fmt(pos["SDSS_gaussian_summary"]["chi2_min_KS_vs_chi2dof_p"], 3)
    m["PcDKsChi"] = fmt(pos["DESI_DR2"]["chi2_min_KS_vs_chi2dof_p"], 3)
    m["IcElgLowL"] = fmt(ins["ELG"]["L_over_Lmax_at_lower_edge"], 2)
    m["IcElgLowX"] = fmt(float(np.loadtxt(ELG_TABLE)[0, 0]), 2)
    m["FitElgMtwo"] = fmt(fit["fits"]["SDSS_eBOSS_DR16_baseline"]["MAP"]["components_m2lnL"]["ELG"], 2)
    # negative controls
    sd = neg["wrong_model_no_Lambda"]["SDSS_eBOSS_DR16_baseline"]["delta"]
    m["NcEdsSdss"] = r"$\infty$" if sd in ("Infinity", math.inf) else fmt(float(sd), 1)
    m["NcEdsDesi"] = fmt(neg["wrong_model_no_Lambda"]["DESI_DR2"]["delta"], 1)
    m["NcEdsSgs"] = fmt(neg["wrong_model_no_Lambda_SDSS_gaussian_summary_gate"]["delta"], 1)
    pr = neg["eds_gate_probe_inf_everywhere"]
    m["NcProbeAsCoded"] = ("as-coded boolean: rejected" if pr["rejected_as_coded"]
                           else "as-coded boolean: not rejected")
    m["NcProbeOk"] = "probe check passed" if pr["probe_ok"] else "probe check FAILED"
    m["NcGuard"] = "passed" if neg["combination_guard"]["rejected"] else "FAILED"
    m["NcSwap"] = fmt(neg["desi_DM_DH_swap"]["chi2_per_dof"], 1)
    m["NcCov"] = fmt(neg["desi_cov_over_25"]["chi2_per_dof"], 2)
    m["NcShift"] = fmt(neg["injected_scale_shift_0.93"]["tension"]["N_sigma"], 2)
    m["NcPermChi"] = fmt(neg["sdss_cov_permutation_report_only"]["m2lnL_min"], 2)
    m["NcPermRef"] = fmt(neg["sdss_cov_permutation_report_only"]["unpermuted_m2lnL_min"], 2)
    m["NcAll"] = "all rejected" if neg["all_negative_controls_rejected"] else "NOT all rejected"
    # instrument check
    m["IcPred"] = "$" + sci(ins["prediction_code_max_rel_diff"]["astropy_vs_quad"]) + "$"
    for tag, k in (("Mgs", "MGS"), ("Elg", "ELG")):
        m[f"Ic{tag}Peak"] = fmt(ins[k]["peak"], 3)
        m[f"Ic{tag}Ref"] = fmt(ins[k]["reference"], 3)
        m[f"Ic{tag}Dev"] = fmt(ins[k]["location_dev_in_sigma_ref"], 4)
        m[f"Ic{tag}W"] = fmt(ins[k]["width_ratio"], 3)
    m["IcMgsNegPeak"] = fmt(ins["MGS_paired_negative"]["peak"], 3)
    m["IcMgsNegDev"] = fmt(ins["MGS_paired_negative"]["location_dev_in_sigma_ref"], 1)
    for tag, k in (("La", "Lya_auto"), ("Lx", "Lya_cross")):
        r = ins[k]
        m[f"Ic{tag}DM"], m[f"Ic{tag}DH"] = fmt(r["peak_DM"], 2), fmt(r["peak_DH"], 3)
        m[f"Ic{tag}Rho"] = fmt(r["rho"], 3)
        m[f"Ic{tag}RefDM"], m[f"Ic{tag}RefDH"] = fmt(r["reference"]["DM"], 2), fmt(r["reference"]["DH"], 3)
        m[f"Ic{tag}RefRho"] = fmt(r["reference"]["rho"], 2)
        m[f"Ic{tag}WDM"], m[f"Ic{tag}WDH"] = fmt(r["DM_width_ratio"], 2), fmt(r["DH_width_ratio"], 2)
    # CAMB
    cb = fit["camb_background_crosscheck"]
    mx = {q: max(v[f"max_rel_{q}"] for v in cb["max_rel_diff_by_point"].values()) for q in ("DM", "H", "DV")}
    m["CambDM"], m["CambH"], m["CambDV"] = ("$" + sci(mx["DM"]) + "$", "$" + sci(mx["H"]) + "$",
                                            "$" + sci(mx["DV"]) + "$")
    m["CambRd"] = fmt(cb["planck2018_rdrag_Mpc"], 4)
    m["CambPass"] = "passed" if cb["all_pass"] else "FAILED"
    # provenance
    m["PreregSha"] = fit["preregistration_sha256"][:16]
    m["FitShaShort"] = sha(RES / "fit.json")[:16]
    m["LeanSha"] = sha(LEAN)[:16]
    m["FitGenerated"] = fit["generated_at"][:19].replace("T", " ")
    m["LedgerClaims"] = str(gate["real"]["n_claims"])
    m["LedgerBlock"] = str(gate["real"]["n_block"])
    m["LedgerFlag"] = str(gate["real"]["n_flag"])
    m["LedgerRc"] = str(gate["real"]["rc"])
    return m


def read_mean(fname: str) -> list[tuple[float, str, float]]:
    rows = []
    for ln in (DATA / fname).read_text().splitlines():
        if ln.strip() and not ln.lstrip().startswith("#"):
            z, v, q = ln.split()
            rows.append((float(z), q, float(v)))
    return rows


def data_table(pieces: list[tuple[str, str, str]]) -> str:
    qname = {"DM_over_rs": r"$D_M/r_d$", "DH_over_rs": r"$D_H/r_d$", "DV_over_rs": r"$D_V/r_d$"}
    lines = []
    for label, mean_f, cov_f in pieces:
        rows = read_mean(mean_f)
        sig = np.sqrt(np.diag(np.atleast_2d(np.loadtxt(DATA / cov_f))))
        if len(sig) != len(rows):
            raise ValueError(f"{mean_f}: {len(rows)} rows vs cov dim {len(sig)}")
        for (z, q, v), s in zip(rows, sig):
            lines.append(f"{label} & {z:.3f} & {qname[q]} & {v:.3f} & {s:.3f} \\\\")
    return "\n".join(lines) + "\n"


def lean_statements() -> str:
    src = LEAN.read_text()
    blocks = re.findall(r"^(theorem .*?:=)", src, flags=re.S | re.M)
    out = []
    for b in blocks:
        b = b.rstrip(":=").rstrip() + " := ..."
        for u, t in GLYPHS:
            b = b.replace(u, t)
        bad = sorted({c for c in b if ord(c) > 127})
        if bad:
            raise ValueError(f"unmapped non-ASCII characters in Lean statement: {bad}")
        out.append(b)
    if len(out) != 9:
        raise ValueError(f"expected 9 theorems, found {len(out)}")
    return ("\\begin{lstlisting}[mathescape]\n" + "\n\n".join(out) + "\n\\end{lstlisting}\n")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fit = json.loads((RES / "fit.json").read_text())
    pos = json.loads((RES / "positive_control.json").read_text())
    neg = json.loads((RES / "negative_controls.json").read_text())
    ins = json.loads((RES / "instrument_check.json").read_text())
    camb = json.loads((RES / "camb_crosscheck.json").read_text())
    gate = json.loads((RES / "ledger" / "gate_check.json").read_text())
    m = macros(fit, pos, neg, ins, camb, gate)
    for k in m:
        if not re.fullmatch(r"[A-Za-z]+", k):
            raise ValueError(f"bad macro name {k}")
    (OUT / "gen_numbers.tex").write_text(
        "% generated by scripts/eboss_vs_desi/make_paper_inputs.py -- do not edit\n"
        + "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(m.items())))
    (OUT / "gen_desi_table.tex").write_text(data_table(
        [("DESI DR2", "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_mean.txt",
          "desi_bao_dr2/desi_gaussian_bao_ALL_GCcomb_cov.txt")]))
    (OUT / "gen_sdss_table.tex").write_text(data_table([
        ("BOSS DR12", "sdss_DR12_LRG_BAO_DMDH.dat", "sdss_DR12_LRG_BAO_DMDH_covtot.txt"),
        ("eBOSS LRG", "sdss_DR16_LRG_BAO_DMDH.dat", "sdss_DR16_LRG_BAO_DMDH_covtot.txt"),
        ("eBOSS QSO", "sdss_DR16_QSO_BAO_DMDH.txt", "sdss_DR16_QSO_BAO_DMDH_covtot.txt")]))
    (OUT / "gen_lean.tex").write_text(lean_statements())
    log = LEAN_LOG.read_text()
    if any(ord(c) > 127 for c in log):
        raise ValueError("non-ASCII in Lean log")
    (OUT / "gen_axioms.tex").write_text("\\begin{verbatim}\n" + log.replace("' depends", "'\n    depends")
                                        + "\\end{verbatim}\n")
    print(f"wrote {len(m)} macros and 4 table/listing files to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

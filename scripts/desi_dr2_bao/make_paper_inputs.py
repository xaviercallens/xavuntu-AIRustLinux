"""Generate LaTeX inputs for papers/desi_dr2_bao/desi_dr2_bao.tex from the run's JSON artifacts.

Every number in the paper's tables and macros comes from results/desi_dr2_bao/*.json
(regenerated in the fit stage) or the Lean gate outputs; nothing is retyped.
Outputs: gen_numbers.tex, gen_results_table.tex, gen_controls_table.tex,
gen_lean.tex (definitions and theorem signatures extracted from the .lean file),
gen_axioms.tex (lean_gate.log verbatim).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "desi_dr2_bao"
OUT = ROOT / "papers" / "desi_dr2_bao"
LEAN = ROOT / "formal" / "ANSE" / "DESI_DR2_wCDM.lean"


def load(n: str) -> dict[str, Any]:
    return json.loads((RES / n).read_text())


def sci(x: float, d: int = 1) -> str:
    if x == 0:
        return "0"
    m, e = f"{x:.{d}e}".split("e")
    return f"{m}\\times10^{{{int(e)}}}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    fit, ctl, mc, gr, cb = (load(n) for n in ("fit.json", "controls.json", "mcmc_summary.json",
                                               "grid_summary.json", "camb_crosscheck.json"))
    gate, led = load("lean_gate.json"), json.loads((RES / "ledger" / "gate_check.json").read_text())
    res = {x["name"]: x for x in fit["results"]}
    runs, pc, nc = mc["runs"], ctl["positive_controls"], ctl["negative_controls"]
    sh, rad, camb = fit["DR1_to_DR2_shift"], fit["radiation_sensitivity"], fit["camb_crosscheck"]
    m: dict[str, str] = {}
    m["FitSha"] = hashlib.sha256((RES / "fit.json").read_bytes()).hexdigest()[:16]
    m["PreregSha"] = fit["preregistration_sha256"][:16]
    m["FitGenerated"] = fit["generated_at"][:19].replace("T", " ")
    m["EmceeVersion"] = fit["emcee_version"]
    m["LCDMchi"] = f"{fit['DR2_LCDM_bestfit']['chi2']:.3f}"
    m["WCDMchi"] = f"{fit['DR2_wCDM_bestfit']['chi2']:.3f}"
    c = fit["DR2_LCDM_corr_Om_hrd"]
    m["CorrEmcee"], m["CorrGrid"], m["CorrFisher"] = (f"{c[k]:.4f}" for k in ("emcee", "grid", "fisher_at_min"))
    m["WhrdMean"] = f"{fit['DR2_wCDM_hrd_report_only']['mean']:.2f}"
    m["WhrdStd"] = f"{fit['DR2_wCDM_hrd_report_only']['std']:.2f}"
    m["EmGridMax"] = f"{fit['emcee_vs_grid_max_abs_diff_in_emcee_sigma']:.4f}"
    taus = [max(v["tau"].values()) for v in fit["mcmc_diagnostics"].values()]
    m["TauMax"] = f"{max(taus):.1f}"
    m["EssMin"] = f"{min(v['ess'] for v in fit['mcmc_diagnostics'].values()):.0f}"
    m["NstepsOverTauMin"] = f"{min(v['n_steps_over_50tau'] for v in fit['mcmc_diagnostics'].values()):.1f}"
    m["GridNtwo"] = str(gr["runs"]["DR2_LCDM"]["n_per_axis"])
    m["GridNthree"] = str(gr["runs"]["DR2_wCDM"]["n_per_axis"])
    edge = max(v for run in gr["runs"].values() for ax in run["edge_marginal_mass"].values() for v in ax.values())
    m["GridEdgeMax"] = f"${sci(edge)}$"
    # DR1
    d1 = fit["DR1_instrument_checks"]
    m["DOneOm"], m["DOneOmPull"] = f"{d1['DR1_LCDM_Om']['ours']:.5f}", f"{d1['DR1_LCDM_Om']['pull']:+.4f}"
    m["DOneHrd"], m["DOneHrdPull"] = f"{d1['DR1_LCDM_hrd']['ours']:.3f}", f"{d1['DR1_LCDM_hrd']['pull']:+.3f}"
    m["DOneOmSd"] = f"{sh['sd_DR1']:.5f}"
    m["DOneWOm"], m["DOneWw"], m["DOneWhrd"] = (f"{d1['DR1_wCDM_Om']['ours']:.5f}", f"{d1['DR1_wCDM_w']['ours']:.4f}",
                                                 f"{d1['DR1_wCDM_hrd']['ours']:.2f}")
    m["DOneWOmPull"], m["DOneWwPull"], m["DOneWhrdPull"] = (f"{d1[k]['pull']:+.4f}" for k in
                                                             ("DR1_wCDM_Om", "DR1_wCDM_w", "DR1_wCDM_hrd"))
    # shift
    m["DeltaOm"] = f"{sh['Delta_Om']:+.5f}"
    m["DeltaHrd"] = f"{sh['Delta_hrd']:+.2f}"
    m["SigNestOwn"] = f"{sh['sigma_nested_own']:.5f}"
    m["SigIndOwn"] = f"{sh['sigma_independent_own']:.5f}"
    m["ShiftNestPrereg"] = f"{sh['Delta_over_sigma_nested_prereg']:.3f}"
    m["ShiftNestOwn"] = f"{sh['Delta_over_sigma_nested_own']:.3f}"
    m["ShiftInd"] = f"{sh['Delta_over_sigma_independent_own']:.3f}"
    # radiation / CAMB
    m["Orad"] = f"${sci(rad['DR2_LCDM']['Omega_r'], 2)}$"
    m["RadOm"] = f"{rad['DR2_LCDM']['shift_Om_in_published_sigma']:+.3f}"
    m["RadHrd"] = f"{rad['DR2_LCDM']['shift_h_rd_in_published_sigma']:+.3f}"
    m["RadW"] = f"{rad['DR2_wCDM']['shift_w_in_published_sigma']:+.4f}"
    m["RadWOm"] = f"{rad['DR2_wCDM']['shift_Om_in_published_sigma']:+.3f}"
    m["CambVersion"] = cb["camb_version"]
    m["CambMassless"] = f"${sci(max(camb['massless_nu_max_rel_diff'].values()))}$"
    s = camb["primary_model_vs_camb_mnu0.06_shift_in_published_sigma"]
    m["CambOm"], m["CambHrd"] = f"{s['lcdm']['Om']:+.3f}", f"{s['lcdm']['h_rd']:+.3f}"
    m["CambWOm"], m["CambW"] = f"{s['wcdm']['Om']:+.3f}", f"{s['wcdm']['w']:+.3f}"
    m["CambRd"] = f"{camb['planck2018_rdrag_Mpc']:.4f}"
    camb_shifts = [abs(v) for mdl in s.values() for v in mdl.values()]
    rad_shifts = [abs(v) for mdl in rad.values() for k, v in mdl.items() if k.startswith("shift_")]
    m["CambMaxShift"] = f"{max(camb_shifts):.3f}"
    m["SystMaxShift"] = f"{max(camb_shifts + rad_shifts):.3f}"
    # controls
    m["GLdiff"] = f"${sci(ctl['gl_integrator_validation']['max_rel_diff_prior_corners'])}$"
    # Lean
    m["LeanSha"] = gate["lean_file_sha256"][:16]
    m["LeanToolchain"] = gate["toolchain"].replace("_", r"\_")
    m["LeanStamp"] = gate["timestamp_utc"][:19].replace("T", " ")
    real = led["real"]
    m["LedgerClaims"], m["LedgerRc"] = str(real["n_claims"]), str(real["rc"])
    m["LedgerBlock"], m["LedgerFlag"] = str(real["n_block"]), str(real["n_flag"])
    ledger_rows = json.loads((RES / "ledger" / "ledger.json").read_text())["claims"]
    tier_a = [r for r in ledger_rows if r["tier"] == "A"]
    m["LedgerTierA"] = str(len(tier_a))
    m["LedgerAudited"] = str(sum(r.get("audit") is not None for r in tier_a))
    pre = json.loads((RES / "ledger" / "gate_check_pre_audit.json").read_text())["real"]
    m["LedgerPreRc"], m["LedgerPreFlag"] = str(pre["rc"]), str(pre["n_flag"])
    # NC5 per-realisation discriminating power (referee issue)
    nc5_runs = nc["NC5_scrambled_covariance"]["runs"]
    above = sorted((r for r in nc5_runs if r["pte"] > 1e-3), key=lambda r: r["seed"])
    m["NCfiveN"] = str(len(nc5_runs))
    m["NCfiveAbove"] = str(len(above))
    m["NCfiveAboveList"] = ", ".join(f"{r['seed']}: {r['pte']:.2g}" for r in above)
    m["NCfiveMaxPte"] = f"{max(r['pte'] for r in nc5_runs):.3f}"
    m["Verdict"] = "PASS" if fit["within_tolerance"] else "FAIL"
    m["NCriteria"] = str(len(fit["criteria"]))
    m["NCriteriaTrue"] = str(sum(bool(v) for v in fit["criteria"].values()))
    (OUT / "gen_numbers.tex").write_text(
        "% generated by scripts/desi_dr2_bao/make_paper_inputs.py -- do not edit\n"
        + "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(m.items())))

    # ---- main results table ----
    lab = {"DR2_LCDM_Om": r"$\Lambda$CDM $\Omega_m$", "DR2_LCDM_hrd_Mpc": r"$\Lambda$CDM $h r_d$ [Mpc]",
           "DR2_wCDM_Om": r"$w$CDM $\Omega_m$", "DR2_wCDM_w": r"$w$CDM $w$"}
    dig = {"DR2_LCDM_Om": 5, "DR2_LCDM_hrd_Mpc": 3, "DR2_wCDM_Om": 5, "DR2_wCDM_w": 4}
    rows = []
    for n, r in res.items():
        d = dig[n]
        rows.append(f"{lab[n]} & ${r['value']:.{d}f}\\pm{r['sigma']:.{d}f}$ & ${r['grid_value']:.{d}f}\\pm{r['grid_sigma']:.{d}f}$ "
                    f"& ${r['target']}\\pm{r['target_sigma']}$ & ${r['pull_sigma']:+.3f}$ & {r['width_ratio']:.3f} \\\\")
    (OUT / "gen_results_table.tex").write_text("% generated -- do not edit\n" + "\n".join(rows) + "\n")

    # ---- controls table ----
    p3 = pc["PC3_noisy_LCDM_draws"]
    crow = [
        ("PC0 DR1 regression", "$\\Omega_m$, $hr_d$, $\\chi^2$ within $10^{-4}$, $10^{-3}$, $10^{-3}$ of parent",
         f"{pc['PC0_regression_quad']['Om']:.6f}, {pc['PC0_regression_quad']['h_rd']:.4f}, {pc['PC0_regression_quad']['chi2']:.4f}",
         pc["PC0_regression_quad"]["pass"] and pc["PC0_regression_gl"]["pass"]),
        ("PC1 noiseless $\\Lambda$CDM mock", "$|\\Delta\\Omega_m|<10^{-4}$, $\\chi^2<10^{-4}$",
         f"$\\Delta\\Omega_m={sci(pc['PC1_noiseless_LCDM']['dOm'])}$", pc["PC1_noiseless_LCDM"]["pass"]),
        ("PC2 noiseless $w$CDM mock", "$|\\Delta w|<10^{-3}$, $\\chi^2<10^{-4}$",
         f"$\\Delta w={sci(pc['PC2_noiseless_wCDM']['dw'])}$", pc["PC2_noiseless_wCDM"]["pass"]),
        ("PC3 500 noisy mocks", "$|\\bar p|<0.15$, $0.88\\le s_p\\le1.12$, $10.3\\le\\bar\\chi^2\\le11.7$",
         f"$\\bar p_{{\\Omega_m}}={p3['mean_pull']['Om']:+.3f}$, $s_p={p3['std_pull']['Om']:.3f}/{p3['std_pull']['h_rd']:.3f}$, "
         f"$\\bar\\chi^2={p3['mean_chi2_min']:.2f}$", p3["pass"]),
        ("PC4 astropy vs.\\ quad", "max rel.\\ diff $<10^{-5}$",
         f"${sci(max(pc['PC4_astropy_vs_quad']['max_rel_diff_lcdm'], pc['PC4_astropy_vs_quad']['max_rel_diff_wcdm']))}$",
         pc["PC4_astropy_vs_quad"]["pass"]),
        ("NC1 $z$ permutation (all $z$ changed)", "must give PTE $<10^{-3}$",
         f"$\\chi^2={nc['NC1_redshift_permutation']['chi2']:.0f}$", nc["NC1_redshift_permutation"]["failed_as_required"]),
        ("NC2 $D_M\\leftrightarrow D_H$ swap", "must give PTE $<10^{-3}$",
         f"$\\chi^2={nc['NC2_DM_DH_label_swap']['chi2']:.0f}$", nc["NC2_DM_DH_label_swap"]["failed_as_required"]),
        ("NC3 Einstein--de Sitter", "must give PTE $<10^{-6}$",
         f"$\\chi^2={nc['NC3_wrong_model_EdS']['chi2']:.1f}$, PTE ${sci(nc['NC3_wrong_model_EdS']['pte'])}$",
         nc["NC3_wrong_model_EdS"]["failed_as_required"]),
        ("NC4 $\\Lambda$CDM on $w=-0.7$ mock", "must give $\\chi^2_{\\Lambda\\rm CDM}>9$",
         f"$\\chi^2={nc['NC4_LCDM_on_w-0.7_synthetic']['lcdm_fit']['chi2']:.2f}$ ($w$CDM: ${sci(nc['NC4_LCDM_on_w-0.7_synthetic']['wcdm_fit']['chi2'])}$)",
         nc["NC4_LCDM_on_w-0.7_synthetic"]["failed_as_required"]),
        ("NC5 20 scrambled covariances", "must give median PTE $<10^{-3}$",
         f"median PTE ${sci(nc['NC5_scrambled_covariance']['median_pte'])}$; "
         f"{sum(r['pte'] > 1e-3 for r in nc['NC5_scrambled_covariance']['runs'])} of "
         f"{len(nc['NC5_scrambled_covariance']['runs'])} single fits have PTE $>10^{{-3}}$",
         nc["NC5_scrambled_covariance"]["failed_as_required"]),
    ]
    (OUT / "gen_controls_table.tex").write_text("% generated -- do not edit\n" + "\n".join(
        f"{a} & {b} & {c_} & {'as required' if ok else 'NOT as required'} \\\\" for a, b, c_, ok in crow) + "\n")

    # ---- DR2 data table, read from the preregistered likelihood files ----
    prereg = load("preregistration.json")["data_files"]
    mean_p, cov_p = Path(prereg["dr2_mean"]["path"]), Path(prereg["dr2_cov"]["path"])
    assert hashlib.sha256(mean_p.read_bytes()).hexdigest() == prereg["dr2_mean"]["sha256"]
    assert hashlib.sha256(cov_p.read_bytes()).hexdigest() == prereg["dr2_cov"]["sha256"]
    rows_d = [ln.split() for ln in mean_p.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    cov = [[float(x) for x in ln.split()] for ln in cov_p.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    kname = {"DV_over_rs": "D_V/r_d", "DM_over_rs": "D_M/r_d", "DH_over_rs": "D_H/r_d"}
    drows = [f"{float(z):.3f} & ${kname.get(k, k)}$ & {float(v):.4f} & {cov[i][i] ** 0.5:.4f} \\\\"
             for i, (z, v, k) in enumerate(rows_d)]
    (OUT / "gen_data_table.tex").write_text("% generated from the sha256-verified DR2 mean/cov files -- do not edit\n"
                                            + "\n".join(drows) + "\n")
    m_extra = {"NData": str(len(rows_d))}
    tag = {"DR2_LCDM_Om": ("LOm", 5), "DR2_LCDM_hrd_Mpc": ("LHrd", 3), "DR2_wCDM_Om": ("WOm", 5), "DR2_wCDM_w": ("Ww", 4)}
    for n, (t, d) in tag.items():
        m_extra[f"Res{t}"] = f"{res[n]['value']:.{d}f}"
        m_extra[f"Res{t}Sd"] = f"{res[n]['sigma']:.{d}f}"
    m_extra["MaxAbsPull"] = f"{max(abs(r['pull_sigma']) for r in res.values()):.3f}"
    m_extra["MaxWidthDevPct"] = f"{100 * max(abs(r['width_ratio'] - 1) for r in res.values()):.1f}"
    with (OUT / "gen_numbers.tex").open("a") as fh:
        fh.write("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in m_extra.items()))

    # ---- Lean definitions and theorem signatures (verbatim from the file) ----
    src = LEAN.read_text()
    blocks = []
    for mt in re.finditer(r"^(noncomputable def|theorem) ", src, flags=re.M):
        if mt.group(1) == "theorem":
            text = src[mt.start():src.index(":= by", mt.start())].rstrip() + " := ..."
        else:
            text = src[mt.start():src.index("\n\n", mt.start())].rstrip()
        blocks.append(text)
    (OUT / "gen_lean.tex").write_text("\\begin{lstlisting}\n" + "\n\n".join(blocks) + "\n\\end{lstlisting}\n")
    (OUT / "gen_axioms.tex").write_text("\\begin{lstlisting}[language={}]\n" + (RES / "lean_gate.log").read_text().strip()
                                        + "\n\\end{lstlisting}\n")
    print("wrote", sorted(p.name for p in OUT.glob("gen_*.tex")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

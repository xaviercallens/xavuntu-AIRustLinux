"""Build the Elenchus claim ledger for the bao_bbn_h0 exercise.

Writes results/bao_bbn_h0/ledger/ledger.json and one content-addressed evidence
blob per claim in results/bao_bbn_h0/ledger/evidence/<sha256>.json (same format
as results/bao_flcdm/ledger and results/eboss_vs_desi/ledger).

Every number in a blob or statement is read from a regenerated result file
(fit.json, controls/*.json, rd_camb_validation.json, the Lean re-check log);
none is retyped. Every citation quote is asserted to be a verbatim substring of
docs/literature/BAO_BBN_H0_LITERATURE_REVIEW_2026.md, which transcribed what the
fetched source pages said. The build refuses to run if any hash-locked input
drifted (Lean source, preregistration, amendment 1, the locked pre-amendment
fit, the CAMB r_d table). Tier caps follow Elenchus KIND_CAP: lean_axioms -> A,
exact_harness -> B, citation -> L, argument -> C.

Audit (fix round, per the orchestrator's instruction): Tier A rows whose theorem the
fix-round MODEL referee judged faithful (ledger/referee_statement_audit_fixround.json,
transcribed from the orchestrator-supplied report) carry an audit object whose `by`
field says it is a model referee, not a person. Elenchus ledger.py describes an audit as a
person's certification, so these rows are model-audited only; no person has audited any
statement. Theorems the referee did not see (added in the fix round) keep audit: null and
their LEDGER_UNAUDITED_TIER_A flags stay open (ledger.py exits 1; reported, not silenced).
The earlier-run review ledger/referee_statement_audit.json is NOT used.

Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/bao_bbn_h0/build_ledger.py
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
RES = ROOT / "results" / "bao_bbn_h0"
LEDGER_DIR = RES / "ledger"
EVID = LEDGER_DIR / "evidence"
LEAN_FILE = ROOT / "formal" / "ANSE" / "BAO_BBN_H0.lean"
LEAN_SHA_EXPECTED = "2b6530838efa0df9bfb475a5d8b25ee29aa121989cc83d04e07f595f5f616e38"
LEAN_LOG = RES / "lean_compile_5_fixround.txt"
REFEREE_AUDIT = LEDGER_DIR / "referee_statement_audit_fixround.json"
ELENCHUS_LOG = RES / "elenchus_check.txt"
LEAN_TOOLCHAIN = Path("/home/callensxavier_gmail_com/AutoevolveAI/formal/lean-toolchain")
LIT = ROOT / "docs" / "literature" / "BAO_BBN_H0_LITERATURE_REVIEW_2026.md"
PREREG = RES / "preregistration.json"
AMEND = RES / "preregistration_amendment_1.json"
AMEND_SHA_EXPECTED = "b0c7b80d885bf15a9becf0c3f9b3cae0419b9abaef3c9f7dd0ed840d2265a6f4"
LOCKED = RES / "fit_attempt1_fittingformula_UNREAD_AT_AMENDMENT.json"
LOCKED_SHA_EXPECTED = "b7fe5608e4ae6d0b1cb0f7844e55a6025089336cc9bcb3086e9ead6e85531910"
RD_TABLE = RES / "rd_camb_table.npz"
COMMON = ROOT / "scripts" / "bao_bbn_h0" / "common.py"
TRUSTED = "[propext, Classical.choice, Quot.sound]"
PREFIX = "BBNH0"
THEOREMS = ["rd_numerator_pos", "rdAubourg_pos", "rdAubourg_strictAntiOn_cb", "rdAubourg_strictAntiOn_b",
            "rd_strictAntiOn_Om", "DH_over_rd_eq_hrd", "DH_over_rd_degenerate", "gate_reparam_exact",
            "hrd_mono_generic", "hrd_strictMonoOn_h"]
GLOSSES = {
    "rd_numerator_pos": "the numerator 55.154 exp(-72.3 (omega_nu + 0.0006)^2) of Aubourg eq. 16 is > 0",
    "rdAubourg_pos": "for omega_cb > 0 and omega_b > 0, the eq. 16 sound horizon (real powers) is > 0",
    "rdAubourg_strictAntiOn_cb": "at fixed omega_b > 0, eq. 16 r_d is strictly decreasing in omega_cb on (0, inf)",
    "rdAubourg_strictAntiOn_b": "at fixed omega_cb > 0, eq. 16 r_d is strictly decreasing in omega_b on (0, inf)",
    "rd_strictAntiOn_Om": "for h > 0, omega_b > 0, Omega_m -> r_d(Omega_m h^2 - omega_nu, omega_b) is strictly "
                          "decreasing on {Omega_m : Omega_m h^2 - omega_nu > 0}",
    "DH_over_rd_eq_hrd": "at fixed E, (c / (100 h)) / E / r_d = c / (100 (h r_d) E) for all reals (field identity; "
                         "E is free here, while in the BBN fits E(z) depends on h via radiation, so the "
                         "'only through h r_d' reading is exact only at fixed E)",
    "DH_over_rd_degenerate": "at fixed E: h r_d = h' r_d' implies equal D_H/r_d at the same c and the same E "
                             "(in the BBN fits E carries a small h dependence via radiation)",
    "gate_reparam_exact": "for h_rad != 0, D_H/r_d evaluated at h_rad with r_d := hrd / h_rad equals c / (100 hrd E)",
    "hrd_mono_generic": "for 0 < a <= 1/3, w > 0, Omega_m > 0, 0 < h1 < h2 and w <= (1 - 2a) Omega_m h1^2: "
                        "h1 (Omega_m h2^2 - w)^a < h2 (Omega_m h1^2 - w)^a (real powers)",
    "hrd_strictMonoOn_h": "for Omega_m > 0, omega_b > 0, h -> h * r_d(Omega_m h^2 - omega_nu, omega_b) with the eq. 16 "
                          "(secondary) r_d is strictly increasing on {h > 0 : omega_nu <= (1 - 2*0.25351) Omega_m h^2} "
                          "-- the preregistered identifiability statement, with the hypothesis strengthened from "
                          "1 - 2a > 0 because omega_nu > 0 sits inside the power; the set contains the T1 posterior "
                          "but not the prior corner omega_nu < Omega_m h^2 < 0.0013, where h r_d decreases",
}


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


def load(rel: str) -> tuple[dict[str, Any], str]:
    p = RES / rel
    return json.loads(p.read_text()), sha256_file(p)


def lit_quote(lit: str, q: str) -> str:
    if q not in lit:
        raise ValueError(f"quote not found verbatim in literature review: {q!r}")
    return q


def claim(cid: str, statement: str, tier: str, kind: str, deps: list[str], ev: str) -> dict[str, Any]:
    return {"schema_version": 1, "id": cid, "statement": statement, "tier": tier, "kind": kind,
            "depends_on": deps, "evidence": ev, "audit": None}


def f(x: float, n: int) -> str:
    return f"{x:.{n}f}"


def check_locks(fit: dict[str, Any]) -> dict[str, str]:
    got = {"lean": sha256_file(LEAN_FILE), "prereg": sha256_file(PREREG), "amend": sha256_file(AMEND),
           "locked": sha256_file(LOCKED), "rd_table": sha256_file(RD_TABLE)}
    want = {"lean": LEAN_SHA_EXPECTED, "prereg": fit["preregistration_sha256"], "amend": AMEND_SHA_EXPECTED,
            "locked": LOCKED_SHA_EXPECTED, "rd_table": fit["rd_camb_table_sha256"]}
    for k in got:
        if got[k] != want[k]:
            raise RuntimeError(f"hash lock broken for {k}: {got[k]} != {want[k]}")
    if fit["amendment_1_sha256"] != got["amend"]:
        raise RuntimeError("fit.json records a different amendment sha256")
    if not fit["secondary_vs_locked_preamendment"]["sha256_matches"]:
        raise RuntimeError("fit.json says the locked file did not match")
    return got


def main() -> int:
    fit, fit_sha = load("fit.json")
    locks = check_locks(fit)

    log = LEAN_LOG.read_text()
    if "\nrc=0" not in log or "sorryAx" in log or "error" in log.lower() or "warning" in log.lower():
        raise RuntimeError("Lean re-check log is not clean")
    if f"# source_sha256: {LEAN_SHA_EXPECTED}" not in log:
        raise RuntimeError("Lean re-check log was produced from a different source")
    footprints = dict(re.findall(r"'ANSE\.BAOBBNH0\.(\w+)' depends on axioms: (\[.*?\])", log))
    src = LEAN_FILE.read_text()
    declared = re.findall(r"^theorem (\w+)", src, flags=re.M)
    if declared != THEOREMS:
        raise RuntimeError(f"Lean theorem list changed: {declared}")
    if "sorry" in src.replace("sorryAx", ""):
        raise RuntimeError("'sorry' appears in the Lean source")
    toolchain = LEAN_TOOLCHAIN.read_text().strip()
    elenchus = ELENCHUS_LOG.read_text().strip()
    if "no findings" not in elenchus or "elenchus_rc=0" not in elenchus:
        raise RuntimeError("Elenchus log is not clean")
    if f"# source_sha256: {LEAN_SHA_EXPECTED}" not in elenchus:
        raise RuntimeError("Elenchus log was produced from a different source")

    if EVID.exists():
        shutil.rmtree(EVID)
    EVID.mkdir(parents=True)
    claims: list[dict[str, Any]] = []
    a_ids: dict[str, str] = {}
    referee = {r["theorem"]: r for r in json.loads(REFEREE_AUDIT.read_text())["lean_statement_audit"]}
    lean_cmd = log.splitlines()[0].removeprefix("# command: ")
    for i, th in enumerate(THEOREMS, start=1):
        fp = footprints.get(th)
        if fp != TRUSTED:
            raise RuntimeError(f"{th}: footprint {fp!r} is not the trusted set")
        ev = write_blob({
            "theorem": f"ANSE.BAOBBNH0.{th}",
            "file": "formal/ANSE/BAO_BBN_H0.lean",
            "source_sha256": locks["lean"],
            "lean_toolchain": toolchain,
            "command": lean_cmd + "  (re-run in the fix round via scripts/bao_bbn_h0/lean_recheck.py; rc=0)",
            "kernel_axiom_footprint": f"'ANSE.BAOBBNH0.{th}' depends on axioms: {fp}",
            "compile_log": str(LEAN_LOG.relative_to(ROOT)),
            "compile_log_sha256": sha256_file(LEAN_LOG),
            "elenchus_check_log": elenchus,
            "elenchus_check_log_sha256": sha256_file(ELENCHUS_LOG),
            "note": "#print axioms lines are inside the committed source (Elenchus NO_FOOTPRINT rule).",
        })
        cid = f"{PREFIX}-A-{i:04d}"
        a_ids[th] = cid
        row = claim(cid, f"ANSE.BAOBBNH0.{th} ({GLOSSES[th]}) is kernel-verified with axioms exactly "
                         f"{TRUSTED}; no sorryAx, no smuggled axiom.", "A", "lean_axioms", [], ev)
        ra = referee.get(f"ANSE.BAOBBNH0.{th}")
        if ra is not None and ra["faithful"] is True:
            row["audit"] = {"by": "model referee (fix-round report supplied by the workflow orchestrator); NOT a person",
                            "date": "2026-09-27", "kind": "statement_adequacy",
                            "evidence": str(REFEREE_AUDIT.relative_to(ROOT)),
                            "evidence_sha256": sha256_file(REFEREE_AUDIT),
                            "reviewed_source_sha256": "c0663994721a6113ad4569c29298c516d659a97ffc93db91a2123fe113483689",
                            "comment": ra["comment"]}
        claims.append(row)

    # ------------------------------------------------------------- Tier B ----
    P, S = fit["primary"], fit["secondary"]
    common = {"fit_json": "results/bao_bbn_h0/fit.json", "fit_json_sha256": fit_sha,
              "preregistration_sha256": locks["prereg"], "amendment_1_sha256": locks["amend"],
              "rd_camb_table_sha256": locks["rd_table"], "data_sha256": fit["data_sha256"],
              "script": fit["script"], "common_py_sha256": sha256_file(COMMON)}
    ptr, ptr_sha = load("chains_pointer.json")

    def run_blob(block: dict[str, Any], analysis: str, key: str, chain_key: str) -> dict[str, Any]:
        r = block[key]
        body = {k: v for k, v in r.items() if k != "profile_H0"}
        prof = r["profile_H0"]
        body["profile_H0"] = {k: prof[k] for k in ("H0_min_grid", "H0_lo_1sig", "H0_hi_1sig", "sigma_sym")}
        return {**common, "analysis": analysis, "run": key, "result": body,
                "chain_file": ptr["chains"][chain_key], "chains_pointer_sha256": ptr_sha}

    def run_stmt(label: str, r: dict[str, Any], ndata: int) -> str:
        c = r["chain"]
        return (f"{label}: emcee posterior H0 = {f(c['mean']['H0'],3)} +- {f(c['std']['H0'],3)} km/s/Mpc, "
                f"Omega_m = {f(c['mean']['Omega_m'],5)} +- {f(c['std']['Omega_m'],5)}, omega_b = "
                f"{f(c['mean']['omega_b'],5)} +- {f(c['std']['omega_b'],5)} ({c['n_walkers']} walkers x "
                f"{c['n_steps']} steps, ESS {f(c['ess'],0)}, 50-tau rule met: {c['converged_50tau_and_ess']}); "
                f"MAP H0 = {f(r['map']['H0'],3)}, Laplace sigma {f(r['laplace']['sigma']['H0'],3)}, profile-likelihood "
                f"1-sigma [{f(r['profile_H0']['H0_lo_1sig'],3)}, {f(r['profile_H0']['H0_hi_1sig'],3)}]; "
                f"chi2_MAP = {f(r['chi2_map'],2)} for {r['dof']} dof ({ndata} BAO points + BBN prior), "
                f"PTE {f(r['pte'],3)}.")

    b1 = write_blob(run_blob(P, "primary (CAMB r_d table)", "T1_DR2", "T1_DR2_primary"))
    b2 = write_blob(run_blob(P, "primary (CAMB r_d table)", "T2_DR1", "T2_DR1_primary"))
    b3 = write_blob(run_blob(S, "secondary (Aubourg eq. 16)", "T1_DR2", "T1_DR2_secondary"))
    b4 = write_blob(run_blob(S, "secondary (Aubourg eq. 16)", "T2_DR1", "T2_DR1_secondary"))
    g1, g2 = fit["G1"], fit["G2"]
    b5 = write_blob({**common, "gate": "G1", "result": g1, "chain_file": ptr["chains"]["gate_DESI_DR2"]})
    b6 = write_blob({**common, "gate": "G2", "result": g2, "chain_file": ptr["chains"]["gate_DESI_DR1"]})
    val, val_sha = load("rd_camb_validation.json")
    b7 = write_blob({"file": "results/bao_bbn_h0/rd_camb_validation.json", "sha256": val_sha,
                     "camb_version": val["camb_version"], "grid": val["grid"],
                     "n_grid_fail": val["n_grid_fail"], "n_grid_h_substituted": val["n_grid_h_substituted"],
                     "grid_h_substitutions": val["grid_h_substitutions"],
                     "max_frac_h_dependence_over_nodes": val["max_frac_h_dependence_over_nodes"],
                     "interpolation_vs_direct_camb": val["interpolation_vs_direct_camb"],
                     "rd_camb_table_sha256": locks["rd_table"], "script": "scripts/bao_bbn_h0/rd_camb_table.py"})
    b8 = write_blob({"file": "results/bao_bbn_h0/rd_camb_validation.json", "sha256": val_sha,
                     "class_and_aubourg_vs_camb": val["class_and_aubourg_vs_camb"],
                     "class_version": "classy 3.3.4 (venv-cosmo)", "camb_version": val["camb_version"]})
    p4, p4_sha = load("controls/P4.json")
    b9 = write_blob({"camb_background_vs_manual_distances": val["camb_background_vs_manual_distances"],
                     "rd_camb_validation_sha256": val_sha, "P4": p4, "P4_sha256": p4_sha})
    ctrl: dict[str, Any] = {}
    for name in ("P1_primary", "P1_secondary", "P2_primary", "P2_secondary",
                 "N1_primary", "N1_secondary", "N2_primary", "N2_secondary"):
        d, s = load(f"controls/{name}.json")
        d = {k: v for k, v in d.items() if k != "rows"}
        ctrl[name] = {"sha256": s, "content": d}
    b10 = write_blob({"positive_controls": {k: v for k, v in ctrl.items() if k.startswith("P")},
                      "preregistered_pass_rules": {"P1": ctrl["P1_primary"]["content"]["pass_if"],
                                                   "P2": ctrl["P2_primary"]["content"]["pass_if"]}})
    n3 = {"primary": P["N3"], "secondary": S["N3"]}
    n3_ratio = {a: {"nsteps_over_max_tau": n3[a]["chain"]["n_steps"] / max(n3[a]["chain"]["tau"].values())}
                for a in n3}
    b11 = write_blob({"negative_controls": {k: v for k, v in ctrl.items() if k.startswith("N")},
                      "N3": n3, "N3_nsteps_over_max_tau_computed_here": n3_ratio,
                      "fit_json_sha256": fit_sha})
    sens = fit["sensitivity"]
    b12 = write_blob({**common, "measured_formula_systematic": fit["measured_formula_systematic"],
                      "sensitivity_dH0": {k: {"dH0_vs_T1": v["dH0_vs_T1"], "vs": v["vs"], "kwargs": v["kwargs"]}
                                          for k, v in sens.items()}})
    lk = fit["secondary_vs_locked_preamendment"]
    b13 = write_blob({**common, "locked_file": "results/bao_bbn_h0/fit_attempt1_fittingformula_UNREAD_AT_AMENDMENT.json",
                      "locked_sha256_now": locks["locked"], "comparison": lk,
                      "note": fit["measured_formula_systematic"]["note"]})
    b14 = write_blob({**common, "camb_instrument_anchor": fit["camb_instrument_anchor"]})
    anc, anc_sha = load("anchor_reproduction.json")
    b15 = write_blob({"file": "results/bao_bbn_h0/anchor_reproduction.json", "sha256": anc_sha,
                      "rows": anc["rows"], "script": anc["script"], "note": anc["note"]})
    arow = {("CAMB" if str(r["code"]).startswith("CAMB") else "CLASS") + "|" + str(r.get("nnu", r.get("N_ur"))): r
            for r in anc["rows"]}
    a_camb, a_cls, a_cls44 = arow["CAMB|3.044"], arow["CLASS|2.0328"], arow["CLASS|2.0308"]

    t1p, t2p, t1s, t2s = P["T1_DR2"], P["T2_DR1"], S["T1_DR2"], S["T2_DR1"]
    mfs = fit["measured_formula_systematic"]
    aub = mfs["aub16_minus_camb_frac_at_5_points"]
    cls = [r["frac_class_minus_camb"] for r in val["class_and_aubourg_vs_camb"]]
    iv = {r["region"]: r for r in val["interpolation_vs_direct_camb"]}
    bg = max(max(r["max_frac_DM"], r["max_frac_DH"]) for r in val["camb_background_vs_manual_distances"])
    pc = {k: v["content"] for k, v in ctrl.items()}
    diag, diag_sha = load("fixround_diagnostics.json")
    mono, hd = diag["hrd_monotonicity"], diag["h_dependence"]
    slp = diag["slope_and_T2_propagation"]
    t2r = [r for r in slp["T2_propagation"] if r["analysis"] == "primary"]
    b16 = write_blob({"file": "results/bao_bbn_h0/fixround_diagnostics.json", "sha256": diag_sha,
                      "hrd_monotonicity": mono, "h_dependence": hd,
                      "slopes": {k: v for k, v in slp.items() if k.endswith("dlnh")},
                      "script": "scripts/bao_bbn_h0/fixround_diagnostics.py", "rd_camb_table_sha256": locks["rd_table"]})
    n4, n4_sha = load("controls/N4.json")
    n4e, n4e_sha = load("controls/N4_expectation.json")
    b17 = write_blob({"N4": n4, "N4_sha256": n4_sha, "expectation": n4e, "expectation_sha256": n4e_sha,
                      "script": "scripts/bao_bbn_h0/control_n4.py", "rd_camb_table_sha256": locks["rd_table"]})
    claims += [
        claim(f"{PREFIX}-B-0001", run_stmt("PRIMARY (CAMB 2.0.4 r_d table, amendment 1), DESI DR2 BAO + BBN omega_b "
                                           "prior, flat LCDM", t1p, 13), "B", "exact_harness", [], b1),
        claim(f"{PREFIX}-B-0002", run_stmt("PRIMARY, DESI DR1 BAO + BBN", t2p, 12), "B", "exact_harness", [], b2),
        claim(f"{PREFIX}-B-0003", run_stmt("SECONDARY (preregistered Aubourg eq. 16 r_d), DESI DR2 BAO + BBN", t1s, 13),
              "B", "exact_harness", [], b3),
        claim(f"{PREFIX}-B-0004", run_stmt("SECONDARY, DESI DR1 BAO + BBN", t2s, 12), "B", "exact_harness", [], b4),
        claim(f"{PREFIX}-B-0005",
              f"BAO-only (Omega_m, h r_d) fit of DESI DR2 (r_d-free, radiation at fixed h = {g1['radiation_h_fixed']}): "
              f"Omega_m = {f(g1['chain']['mean']['Omega_m'],5)} +- {f(g1['chain']['std']['Omega_m'],5)}, h r_d = "
              f"{f(g1['chain']['mean']['hrd'],3)} +- {f(g1['chain']['std']['hrd'],3)} Mpc, corr "
              f"{f(g1['chain']['corr'][0][1],3)}; chi2_MAP = {f(g1['chi2_map'],2)} for {g1['dof']} dof.",
              "B", "exact_harness", [], b5),
        claim(f"{PREFIX}-B-0006",
              f"BAO-only (Omega_m, h r_d) fit of DESI DR1: Omega_m = {f(g2['chain']['mean']['Omega_m'],5)} +- "
              f"{f(g2['chain']['std']['Omega_m'],5)}, h r_d = {f(g2['chain']['mean']['hrd'],3)} +- "
              f"{f(g2['chain']['std']['hrd'],3)} Mpc; chi2_MAP = {f(g2['chi2_map'],2)} for {g2['dof']} dof.",
              "B", "exact_harness", [], b6),
        claim(f"{PREFIX}-B-0007",
              f"CAMB {val['camb_version']} r_drag table on a 49x61x3 (ln omega_b, ln omega_cdm, h) grid (N_eff = 3.044, one "
              f"0.06 eV neutrino): the interpolant (bicubic spline of ln r_drag in (ln omega_b, ln omega_cdm) per h node, "
              f"linear in h) matches direct CAMB calls to max {iv['core']['max_abs_frac']:.1e} "
              f"(rms {iv['core']['rms_frac']:.1e}, {iv['core']['n']} core points) and max {iv['wide']['max_abs_frac']:.1e} "
              f"({iv['wide']['n']} wide points); {val['n_grid_h_substituted']} nodes at the h = 0.99 node failed in CAMB's "
              f"recombination solver and were refilled at h = 0.98 (listed).", "B", "exact_harness", [], b7),
        claim(f"{PREFIX}-B-0008",
              f"CLASS 3.3.4 rs_drag vs CAMB r_drag at 5 points (incl. BBN +-2 sigma omega_b edges): max |frac diff| "
              f"{max(abs(x) for x in cls):.1e}. Aubourg eq. 16 minus CAMB (N_eff = 3.044) at the same points ranges "
              f"{100*min(aub):.3f}% to {100*max(aub):+.3f}%.", "B", "exact_harness", [], b8),
        claim(f"{PREFIX}-B-0009",
              f"The analytic Gauss-Legendre background used in the MCMC agrees with CAMB's own background D_M, D_H to "
              f"max {bg:.1e} fractional (3 points) and with astropy to max {p4['max_frac_diff']:.1e} "
              f"(P4, threshold {p4['threshold']:.0e}).", "B", "exact_harness", [], b9),
        claim(f"{PREFIX}-B-0010",
              f"Positive controls pass in both analyses. P1 noiseless mock (truth H0 = 68, Omega_m = 0.30): primary dH0 = "
              f"{f(pc['P1_primary']['dH0'],4)}, dOm = {f(pc['P1_primary']['dOm'],4)}; secondary dH0 = "
              f"{f(pc['P1_secondary']['dH0'],4)}, dOm = {f(pc['P1_secondary']['dOm'],4)} (rule |dH0| <= 0.1, |dOm| <= "
              f"0.002). P2, {pc['P2_primary']['n_mocks']} noisy mocks: H0 pull mean/std primary "
              f"{f(pc['P2_primary']['pull_H0_mean'],3)}/{f(pc['P2_primary']['pull_H0_std'],3)}, secondary "
              f"{f(pc['P2_secondary']['pull_H0_mean'],3)}/{f(pc['P2_secondary']['pull_H0_std'],3)} (rule |mean| <= 0.2, "
              f"std in [0.8, 1.2]).", "B", "exact_harness", [], b10),
        claim(f"{PREFIX}-B-0011",
              f"Negative controls behave in both analyses: N1 scrambled DR2 vector chi2 = {f(pc['N1_primary']['chi2'],0)} "
              f"(primary) / {f(pc['N1_secondary']['chi2'],0)} (secondary), PTE {pc['N1_primary']['pte']} vs real-data PTE "
              f"{f(pc['N1_primary']['real_pte'],3)}; N2 Einstein-de Sitter chi2 = {f(pc['N2_primary']['chi2'],1)} for "
              f"{pc['N2_primary']['dof']} dof, PTE {pc['N2_primary']['pte']:.1e}; N3 without the BBN prior sigma(H0) grows "
              f"{f(P['N3']['sigma_H0_ratio_vs_baseline'],2)}x (primary) and {f(S['N3']['sigma_H0_ratio_vs_baseline'],2)}x "
              f"(secondary), rule > 5x.", "B", "exact_harness", [], b11),
        claim(f"{PREFIX}-B-0012",
              f"Primary minus secondary posterior-mean H0: {f(mfs['primary_minus_secondary_H0_T1'],3)} (DR2) and "
              f"{f(mfs['primary_minus_secondary_H0_T2'],3)} (DR1) km/s/Mpc, below the preregistered strict r_d-formula "
              f"proxy {mfs['preregistered_proxy_sigma_sys_H0_strict']}. Sensitivity runs: DESI eq. 2 r_d "
              f"{f(sens['S2_desi_eq2']['dH0_vs_T1'],3)}, no radiation {f(sens['S3_no_radiation_secondary']['dH0_vs_T1'],3)} "
              f"(secondary) / {f(sens['S3_no_radiation_primary']['dH0_vs_T1'],3)} (primary), N_eff = 4.044 "
              f"(eq. 16 with the eq. 17 slope; demo only) {f(sens['S1_Neff4.044_secondary']['dH0_vs_T1'],2)} km/s/Mpc; "
              f"each shift is relative to the T1 posterior mean of the analysis named.",
              "B", "exact_harness", [f"{PREFIX}-B-0001", f"{PREFIX}-B-0002", f"{PREFIX}-B-0003", f"{PREFIX}-B-0004"], b12),
        claim(f"{PREFIX}-B-0013",
              f"The hash-locked pre-amendment fitting-formula output (sha256 {locks['locked'][:16]}..., unchanged) and "
              f"this stage's re-run secondary analysis agree bit for bit (T1 H0 diff {lk['T1_DR2']['H0']['diff']}, "
              f"T2 H0 diff {lk['T2_DR1']['H0']['diff']}, G1/G2 identical): reproducibility under fixed seeds, not "
              f"independent correctness.", "B", "exact_harness", [f"{PREFIX}-B-0003", f"{PREFIX}-B-0004"], b13),
        claim(f"{PREFIX}-B-0014",
              f"CAMB 2.0.4 at the Planck 2018 Table 1 best-fit inputs (N_eff = 3.046) gives r_drag = "
              f"{f(fit['camb_instrument_anchor']['camb_rdrag_this_run'],4)} Mpc (the preregistration's anchor; the "
              f"amendment's anchor is BBNH0-B-0015).", "B", "exact_harness", [], b14),
        claim(f"{PREFIX}-B-0015",
              f"At the Planck 2018 Table 2 TT,TE,EE+lowE+lensing means (H0 = 67.36, omega_b = 0.02237, omega_c = 0.1200, "
              f"one 0.06 eV neutrino) CAMB 2.0.4 with nnu = 3.044 gives r_drag = {f(a_camb['rdrag'],4)} Mpc and CLASS 3.3.4 "
              f"with N_ur = 2.0328 gives rs_drag = {f(a_cls['rs_drag'],4)} Mpc (CLASS N_eff = {f(a_cls['class_Neff'],4)}), "
              f"reproducing the amendment's 147.1027 / 147.0971; with N_ur = 2.0308 (CLASS N_eff = "
              f"{f(a_cls44['class_Neff'],4)}) CLASS gives {f(a_cls44['rs_drag'],4)} Mpc.", "B", "exact_harness", [], b15),
        claim(f"{PREFIX}-B-0016",
              f"Fix-round diagnostics (no refit): at fixed (Omega_m, omega_b), h -> h r_d(h) is strictly increasing on "
              f"all {mono['T1_pm5sigma_camb']['n_curves']} sampled curves in the T1 +-5 sigma box and in a wide box, for "
              f"both the CAMB-table and the eq. 16 r_d; for eq. 16 it is strictly decreasing below the Lean threshold "
              f"omega_m = {mono['below_threshold_aub16']['omega_m_threshold']:.5f} "
              f"({mono['below_threshold_aub16']['strictly_decreasing_below']}). d ln(h r_d)/d ln h at the T1 primary mean "
              f"= {f(slp['primary_T1_DR2_dlnhrd_dlnh'],4)}. CAMB-table h dependence at fixed physical densities: max "
              f"{hd['max_frac_all_nodes']:.1e} (h = {hd['argmax']['h_node']} node, far corner, not a refilled node), "
              f"{hd['max_frac_core']:.1e} in the core region.", "B", "exact_harness", [f"{PREFIX}-B-0007"], b16),
        claim(f"{PREFIX}-B-0017",
              f"Post-hoc negative control N4 (not preregistered, not in the verdict): omitting the omega_nu subtraction "
              f"in the primary CAMB r_d shifts the DR2 BAO+BBN MAP H0 by {f(n4['dH0_wrong_minus_correct'],3)} km/s/Mpc "
              f"(> strict 0.15: {n4['control_behaves']}) with delta chi2 = {n4['delta_chi2_wrong_minus_correct']:.1e}, "
              f"i.e. the data cannot see this error; only the external comparison can.", "B", "exact_harness", [], b17),
    ]

    # ------------------------------------------------------------- Tier L ----
    lit = LIT.read_text()
    l15 = write_blob({"diagnostics": diag["slope_and_T2_propagation"], "fixround_diagnostics_sha256": diag_sha,
                      "quote": lit_quote(lit, "(§6 on p. 36 gives 101.9 ± 1.3, an internal 0.08σ inconsistency; 101.8 is used)"),
                      "lit_review_sha256": sha256_file(LIT)})
    lit_sha = sha256_file(LIT)
    fetched = ("alphaXiv answer_pdf_queries on the source PDFs, 2026-09-27, as transcribed in "
               "docs/literature/BAO_BBN_H0_LITERATURE_REVIEW_2026.md (not re-fetched by the ledger stage)")

    def lblob(source: str, quotes: list[str]) -> str:
        return write_blob({"source": source, "quotes": [lit_quote(lit, q) for q in quotes],
                           "fetched_via": fetched, "lit_review_sha256": lit_sha})

    l1 = lblob("DESI Collaboration, arXiv:2503.14738, eq. (19) and Table V (DESI+BBN)",
               ["| **T1 (headline)** H0, DESI DR2 BAO + BBN, flat LCDM | **68.51 ± 0.58** km/s/Mpc |",
                "| T1b Omega_m, same run | 0.2977 ± 0.0086 | 2503.14738 Table V | |",
                "Internal discrepancy: DR2 §IX (Conclusions) states 68.50 ± 0.58, while eq. 19 and Table V state 68.51 ± 0.58."])
    l2 = lblob("DESI Collaboration, arXiv:2404.03002, eq. (4.4) and Table 3",
               ["| **T2 (second check)** H0, DESI DR1 BAO + BBN | **68.53 ± 0.80** km/s/Mpc |",
                "| T2b Omega_m, DR1 DESI+BBN | 0.295 ± 0.015 | 2404.03002 Table 3 | |"])
    l3 = lblob("DESI Collaboration, arXiv:2503.14738, eq. (17)",
               ["| G1 (gate) DR2 BAO-only | Omega_m = 0.2975 ± 0.0086, hr_d = 101.54 ± 0.73 Mpc, r = −0.92 | 2503.14738 eq. (17) | uncalibrated |"])
    l4 = lblob("DESI Collaboration, arXiv:2404.03002, Sec. 8 (p. 46)",
               ["| G2 (gate) DR1 BAO-only | Omega_m = 0.295 ± 0.015, r_d h = 101.8 ± 1.3 Mpc |"])
    l5 = lblob("arXiv:2503.14738 eq. 14 = arXiv:2404.03002 eq. 2.8 = Schoeneberg arXiv:2401.15054 eq. 5.1",
               ["DR2 eq. 14 (arXiv:2503.14738 §IV.A): **Omega_b h^2 = 0.02218 ± 0.00055** in LCDM."])
    l6 = lblob("Aubourg et al., arXiv:1411.1074, eq. 16",
               ["r_d ≈ 55.154 exp[−72.3 (omega_nu + 0.0006)^2] / (omega_cb^0.25351 omega_b^0.12807)  Mpc",
                "accurate to 0.021% for a standard radiation background with N_eff = 3.046, sum m_nu < 0.6 eV, and values of omega_b and omega_cb within 3σ of values derived by Planck."])
    l7 = lblob("Planck Collaboration, arXiv:1807.06209, Table 1 (Plik best fit)",
               ["- Planck 2018 Table 1 Plik best fit is a single CAMB model: omega_b = 0.022383, omega_c = 0.12011, r_drag = 147.049 Mpc."])
    l14 = lblob("Planck Collaboration, arXiv:1807.06209, Table 1 and Table 2; DESI Collaboration, arXiv:2404.03002, "
                "text before eq. (4.3)",
                ["- Planck 2018 Table 1 r_drag row: Plik best fit 147.049 | Plik [1] 147.09 ± 0.26 | CamSpec [2] "
                 "147.26 ± 0.28 | +0.6 | Combined 147.18 ± 0.29.",
                 "- Planck 2018 Table 2, TT,TE,EE+lowE+lensing column (68% limits): Omega_b h^2 = 0.02237 ± 0.00015, "
                 "Omega_c h^2 = 0.1200 ± 0.0012, H0 = 67.36 ± 0.54, r_drag = 147.09 ± 0.26 Mpc.",
                 "Directly calibrating the BAO standard ruler using the value r_d = 147.09 ± 0.26 Mpc obtained from "
                 "using all CMB and CMB lensing information [15] gives H0 = (69.29 ± 0.87)"])
    claims += [
        claim(f"{PREFIX}-L-0014", "Planck 2018 (arXiv:1807.06209) Table 1 'Plik [1]' and Table 2 TT,TE,EE+lowE+lensing give "
              "the posterior r_drag = 147.09 +- 0.26 Mpc at means H0 = 67.36, omega_b = 0.02237, omega_c = 0.1200; "
              "arXiv:2404.03002 quotes this value before its eq. (4.3).", "L", "citation", [], l14),
        claim(f"{PREFIX}-L-0001", "arXiv:2503.14738 eq. (19)/Table V: DESI DR2 BAO + BBN (no CMB theta*) gives H0 = 68.51 +- 0.58 "
              "km/s/Mpc and Omega_m = 0.2977 +- 0.0086 (Sec. IX text says 68.50).", "L", "citation", [], l1),
        claim(f"{PREFIX}-L-0002", "arXiv:2404.03002 eq. (4.4)/Table 3: DESI DR1 BAO + BBN gives H0 = 68.53 +- 0.80 km/s/Mpc and "
              "Omega_m = 0.295 +- 0.015.", "L", "citation", [], l2),
        claim(f"{PREFIX}-L-0003", "arXiv:2503.14738 eq. (17): DESI DR2 BAO-only Omega_m = 0.2975 +- 0.0086, h r_d = 101.54 +- 0.73 "
              "Mpc, r = -0.92.", "L", "citation", [], l3),
        claim(f"{PREFIX}-L-0004", "arXiv:2404.03002 Sec. 8: DESI DR1 BAO-only Omega_m = 0.295 +- 0.015, r_d h = 101.8 +- 1.3 Mpc.",
              "L", "citation", [], l4),
        claim(f"{PREFIX}-L-0005", "The BBN prior DESI uses is omega_b = 0.02218 +- 0.00055 (arXiv:2503.14738 eq. 14, from "
              "arXiv:2401.15054 eq. 5.1).", "L", "citation", [], l5),
        claim(f"{PREFIX}-L-0006", "Aubourg et al. (arXiv:1411.1074) eq. 16 gives r_d = 55.154 exp[-72.3 (omega_nu+0.0006)^2] / "
              "(omega_cb^0.25351 omega_b^0.12807) Mpc, stated accurate to 0.021% for N_eff = 3.046 within 3 sigma of Planck.",
              "L", "citation", [], l6),
        claim(f"{PREFIX}-L-0007", "Planck 2018 (arXiv:1807.06209) Table 1 best fit: omega_b = 0.022383, omega_c = 0.12011, "
              "r_drag = 147.049 Mpc.", "L", "citation", [], l7),
    ]

    vp1, vp2, vs1, vs2 = P["verdict_T1"], P["verdict_T2"], S["verdict_T1"], S["verdict_T2"]
    rule = json.loads(PREREG.read_text())["tolerance"]["verdicts"]
    v1 = write_blob({**common, "verdict_T1_primary": vp1, "preregistered_rule": rule,
                     "headline": fit["headline"], "controls_summary": P["controls_summary"]})
    v2 = write_blob({**common, "verdict_T2_primary": vp2, "preregistered_rule_T2":
                     json.loads(PREREG.read_text())["tolerance"]["second_check_T2"]})
    v3 = write_blob({**common, "verdict_T1_secondary": vs1, "verdict_T2_secondary": vs2,
                     "controls_summary": S["controls_summary"]})
    v4 = write_blob({**common, "G1": {k: g1[k] for k in ("pull_Om", "pull_hrd", "conditions", "passed", "target")},
                     "G2": {k: g2[k] for k in ("pull_Om", "pull_hrd", "conditions", "passed", "target")}})
    v5 = write_blob({**common, "camb_instrument_anchor": fit["camb_instrument_anchor"], "anchor_reproduction": anc,
                     "frac_diff": fit["camb_instrument_anchor"]["camb_rdrag_this_run"] / 147.049 - 1.0})
    v6 = write_blob({"aub16_minus_camb_frac_at_5_points_Neff3.044": aub, "stated_accuracy_frac": 0.00021,
                     "Neff_offset_frac_from_eq17": (3.046 - 3.044) / 30.60,
                     "rd_camb_validation_sha256": val_sha})
    claims += [
        claim(f"{PREFIX}-L-0008",
              f"Headline verdict under the preregistered rule applied to the PRIMARY analysis (amendment 1): T1 = "
              f"{vp1['verdict']}. |H0 - 68.51| = {f(vp1['abs_dH0'],3)} <= 0.15 km/s/Mpc; Omega_m pull "
              f"{f(vp1['pull_Om'],4)} sigma (<= 0.25); sigma(H0) ratio {f(vp1['sigma_ratio'],3)} (within +-15%); gate G1 "
              f"passed; all controls behaved.",
              "L", "citation", [f"{PREFIX}-B-0001", f"{PREFIX}-B-0005", f"{PREFIX}-B-0007", f"{PREFIX}-B-0009",
                                f"{PREFIX}-B-0010", f"{PREFIX}-B-0011",
                                f"{PREFIX}-L-0001", f"{PREFIX}-L-0003"], v1),
        claim(f"{PREFIX}-L-0009",
              f"Second check T2 (DESI DR1), primary: {vp2['verdict']}. |H0 - 68.53| = {f(vp2['abs_dH0'],3)} exceeds the "
              f"strict 0.15 and is within the soft 0.33 km/s/Mpc; Omega_m pull {f(vp2['pull_Om'],3)}, sigma ratio "
              f"{f(vp2['sigma_ratio'],3)}.", "L", "citation", [f"{PREFIX}-B-0002", f"{PREFIX}-L-0002"], v2),
        claim(f"{PREFIX}-L-0010",
              f"SECONDARY (preregistered eq. 16) verdicts: T1 {vs1['verdict']} (|dH0| = {f(vs1['abs_dH0'],3)}), T2 "
              f"{vs2['verdict']} (|dH0| = {f(vs2['abs_dH0'],3)}).",
              "L", "citation", [f"{PREFIX}-B-0003", f"{PREFIX}-B-0004", f"{PREFIX}-L-0001", f"{PREFIX}-L-0002"], v3),
        claim(f"{PREFIX}-L-0011",
              f"Gates pass: G1 pulls Omega_m {f(g1['pull_Om'],3)}, h r_d {f(g1['pull_hrd'],3)} sigma; G2 pulls "
              f"{f(g2['pull_Om'],3)}, {f(g2['pull_hrd'],3)} sigma (rule <= 0.25 sigma, sigma within +-15%).",
              "L", "citation", [f"{PREFIX}-B-0005", f"{PREFIX}-B-0006", f"{PREFIX}-L-0003", f"{PREFIX}-L-0004"], v4),
        claim(f"{PREFIX}-L-0012",
              f"The CAMB instrument reproduces the Planck 2018 Table 1 r_drag = 147.049 Mpc "
              f"({f(fit['camb_instrument_anchor']['camb_rdrag_this_run'],4)}), and reproduces the amendment's CAMB "
              f"anchor 147.1027 Mpc ({f(a_camb['rdrag'],4)}) at the Table 2 lensing means, "
              f"{f((a_camb['rdrag'] - 147.09) / 0.26, 3)} sigma from the published posterior 147.09 +- 0.26.",
              "L", "citation", [f"{PREFIX}-B-0014", f"{PREFIX}-B-0015", f"{PREFIX}-L-0007", f"{PREFIX}-L-0014"], v5),
        claim(f"{PREFIX}-L-0013",
              f"At N_eff = 3.044 the measured eq. 16 minus CAMB deviation reaches {100*max(abs(x) for x in aub):.3f}% in "
              f"magnitude, above Aubourg's stated 0.021% (stated for N_eff = 3.046); the uncorrected N_eff offset from "
              f"Aubourg eq. 17 accounts for {100*(3.046-3.044)/30.60:.4f}% of it.",
              "L", "citation", [f"{PREFIX}-B-0008", f"{PREFIX}-L-0006"], v6),
        claim(f"{PREFIX}-L-0015",
              f"Propagating the G2 h r_d ({f(t2r[0]['our_G2_hrd'],3)} Mpc) through d ln(h r_d)/d ln h = "
              f"{f(t2r[0]['slope'],4)}: if DESI's DR1 chain sat at the Sec. 8 value 101.8, our H0 would be high by "
              f"{f(t2r[0]['implied_H0_excess_km_s_Mpc'],3)} km/s/Mpc (observed T2 offset {f(t2r[0]['observed_T2_offset'],3)}); "
              f"at the Sec. 6 value 101.9, by {f(t2r[1]['implied_H0_excess_km_s_Mpc'],3)}. The T2 PARTIAL is therefore "
              f"plausibly a DESI-side h r_d rounding/MC difference; this is a heuristic, not a resolution.",
              "L", "citation", [f"{PREFIX}-B-0006", f"{PREFIX}-B-0016", f"{PREFIX}-L-0004", f"{PREFIX}-L-0009"], l15),
    ]

    # ------------------------------------------------------------- Tier C ----
    code = COMMON.read_text().splitlines()
    wanted = ("OMEGA_NU_AUBOURG = 0.0107 * MNU", "return 55.154 * np.exp(-72.3 * (OMEGA_NU_AUBOURG + 0.0006) ** 2) / (",
              "np.asarray(omega_cb) ** 0.25351 * np.asarray(omega_b) ** 0.12807",
              "return np.asarray(om) * np.asarray(h) ** 2 - OMEGA_NU_AUBOURG",
              "dh0 = C_KM_S / (100.0 * h[:, :, 0])", "dh = dh0 / _e_of_z(z[None, :], om[:, :, 0], orad[:, :, 0])",
              "return out / rd", "orad = omega_r_h2(neff, radiation) / h**2",
              "dm, dh = distances_manual_vec(d.z, np.full(n, h_rad), om[ok])",
              "m = obs_from_distances(dm, dh, d.z, d.kinds, hrd[ok] / h_rad)",
              "& (om > PRIOR_OM[0]) & (om < PRIOR_OM[1]) & (omega_cb_of(h0 / 100.0, om) > 0)")
    found = [ln.strip() for ln in code if ln.strip() in wanted]
    if sorted(set(found)) != sorted(wanted):
        raise RuntimeError(f"code lines not found in common.py: {sorted(set(wanted) - set(found))}")
    c1 = write_blob({"argument": "rdAubourg, omegaNu and omegaCb in BAO_BBN_H0.lean transcribe rd_aubourg16, OMEGA_NU_AUBOURG "
                                 "and omega_cb_of (lines below; numpy ** on positive floats = Real.rpow). DH_over_rd "
                                 "transcribes dh0 / E / rd with E a free real, and gate_reparam_exact transcribes "
                                 "make_logpost_hrd (distances at fixed h_rad, r_d := hrd / h_rad). CAVEAT: in the BBN "
                                 "fits E(z) itself depends on h through orad = omega_r_h2 / h^2, so 'D_H/r_d depends on "
                                 "(h, r_d) only through h r_d' is exact only at fixed E (the gate, or no radiation); it "
                                 "is not a statement about the full BBN likelihood. The theorems say nothing about the "
                                 "CAMB r_d of the primary analysis. This match is a reading, not a kernel check.",
                     "common_py_lines": list(wanted), "common_py_sha256": sha256_file(COMMON),
                     "lean_source_sha256": locks["lean"]})
    claims.append(claim(f"{PREFIX}-C-0001",
                        "The Lean definitions formalise the secondary r_d (Aubourg eq. 16 with omega_cb = Omega_m h^2 - "
                        "omega_nu), the coded D_H/r_d observable at fixed E, and the gate's hrd/h_rad substitution exactly "
                        "as in scripts/bao_bbn_h0/common.py; they assert nothing about the primary CAMB r_d or any fitted "
                        "number.", "C", "argument",
                        [a_ids["rdAubourg_pos"], a_ids["rd_strictAntiOn_Om"], a_ids["DH_over_rd_eq_hrd"],
                         a_ids["gate_reparam_exact"]], c1))

    ledger = {"schema_version": 1, "claims": claims}
    (LEDGER_DIR / "ledger.json").write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(claims)} claims, {len(list(EVID.iterdir()))} evidence blobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Negative controls (preregistered). Each must be REJECTED at its preset threshold.

  1. wrong_model_no_Lambda: EdS (Om=1) best fit over hrd raises -2lnL by > 25
     vs the flat-LCDM best fit, on EACH real dataset (SDSS baseline, DESI DR2).
  2. DESI DM<->DH swap within each anisotropic bin (paired by kind, not by
     position; the Lya rows are ordered DH, DM): chi2_min/dof > 3.
  3. DESI covariance / 25: chi2_min/dof > 3.
  4. report-only: random row/col permutation of the SDSS Gaussian-piece covariance.
  5. injected scale shift: every DESI ratio and sigma x 0.93; DESI-vs-SDSS
     N_sigma must exceed 3.
  6. combination guard raises on the excluded DESI+eBOSS Lya file.
Writes results/eboss_vs_desi/negative_controls.json (strict JSON: non-finite
floats are written as the strings "Infinity" / "-Infinity" / "NaN").

Fix round (2026-09-27, referee report). Every change makes a gate stricter,
never looser:
  * Control 1 on the SDSS baseline does not discriminate: EdS predictions leave
    the grid tables for every hrd, so delta = inf passes by construction. The
    preregistered as-coded boolean is still recorded, now flagged
    discriminating=false, and the SDSS EdS test is ALSO gated on the
    Gaussian-summary variant (finite delta). A probe likelihood that returns
    +inf everywhere is run through the same gate and must NOT be rejected.
  * Control 6 now also feeds (a) a DESI DR2 file copied under a non-DESI name and
    (b) the same file copied under a real SDSS filename; both must raise, and
    every real SDSS file must still be accepted.
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

import bao_lib as L


class InfEverywhere(L.Likelihood):
    """Deliberately broken likelihood: -2lnL = +inf everywhere (gate probe)."""

    name = "probe_inf_everywhere"

    def m2lnl(self, om: float, hrd: float) -> float:
        return math.inf


def eds_best(like: L.Likelihood) -> tuple[float, float]:
    """Best -2lnL for Om = 1 (Einstein-de Sitter), hrd free in [30, 250]."""
    hs = np.linspace(30.0, 250.0, 2201)
    vals = np.array([like.m2lnl(1.0, h) for h in hs])
    if not np.any(np.isfinite(vals)):
        return float("nan"), float("inf")
    k = int(np.nanargmin(np.where(np.isfinite(vals), vals, np.nan)))
    lo, hi = hs[max(k - 1, 0)], hs[min(k + 1, len(hs) - 1)]
    r = minimize_scalar(lambda h: like.m2lnl(1.0, h), bounds=(lo, hi), method="bounded")
    return float(r.x), float(min(r.fun, vals[k]))


def eds_gate(like: L.Likelihood) -> dict:
    """EdS-vs-LCDM gate.

    rejected_as_coded: the preregistered boolean delta > 25 (as first coded).
    discriminating: both minima finite and below fit_map's 1e12 cap, i.e. the
      likelihood actually evaluated both models somewhere inside its support.
    rejected: rejected_as_coded AND discriminating (the fix-round gate).
    """
    x, f = L.fit_map(like)
    h_eds, f_eds = eds_best(like)
    delta = f_eds - f
    disc = bool(math.isfinite(f) and math.isfinite(f_eds) and f < 1e12 and f_eds < 1e12)
    as_coded = bool(delta > 25)
    return {"lcdm_min_m2lnL": f, "lcdm_map": x.tolist(), "eds_hrd": h_eds, "eds_min_m2lnL": f_eds,
            "delta": delta, "rejected_as_coded": as_coded, "discriminating": disc,
            "rejected": bool(as_coded and disc)}


def strict(o: object) -> object:
    """Map non-finite floats to JSON strings so the output is strict JSON."""
    if isinstance(o, float) and not math.isfinite(o):
        return "NaN" if math.isnan(o) else ("Infinity" if o > 0 else "-Infinity")
    if isinstance(o, dict):
        return {k: strict(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [strict(v) for v in o]
    return o


def moments(like: L.Likelihood) -> tuple[np.ndarray, np.ndarray, float]:
    x, f = L.fit_map(like)
    c = L.laplace_cov(like, x)
    g = L.grid_posterior(like, x, np.sqrt(np.diag(c)), nsig=8.0, n=241)
    return g["mean"], g["cov"], f


def guard_control() -> dict:
    """Control 6: the SDSS combination guard, with renamed-file probes."""
    guard: dict = {}
    try:
        L.load_gauss("bad", "desi_2024_eboss_gaussian_bao_Lya_GCcomb_mean.txt",
                     "desi_2024_eboss_gaussian_bao_Lya_GCcomb_cov.txt", sdss=True)
        guard["named_desi_eboss_lya"] = {"raised": False}
    except L.CombinationError as exc:
        guard["named_desi_eboss_lya"] = {"raised": True, "message": str(exc)}
    src = L.DATA_DIR / L.DESI_FILES["mean"]
    with tempfile.TemporaryDirectory(prefix="eboss_guard_probe_") as td:
        for label, newname in (("desi_renamed_nondesi_name", "renamed_bao_mean.txt"),
                               ("desi_renamed_as_sdss_qso", L.SDSS_FILES["qso_mean"])):
            dst = Path(td) / newname
            shutil.copyfile(src, dst)
            try:
                L.guard_not_desi(str(dst))
                guard[label] = {"file": newname, "raised": False}
            except L.CombinationError as exc:
                guard[label] = {"file": newname, "raised": True,
                                "message": str(exc).replace(td, "<tmpdir>")}
    real_ok = True
    for fn in L.SDSS_FILES.values():
        try:
            L.guard_not_desi(fn)
        except L.CombinationError:
            real_ok = False
    guard["real_sdss_files_accepted"] = real_ok
    probes = [v["raised"] for v in guard.values() if isinstance(v, dict)]
    guard["rejected"] = bool(all(probes) and real_ok)
    return guard


def main() -> int:
    L.verify_hashes()
    desi = L.desi_likelihood()
    sdss = L.SDSSGridLikelihood()
    res: dict = {}

    # 1. EdS: preregistered gate as coded, on each real dataset
    res["wrong_model_no_Lambda"] = {like.name: eds_gate(like) for like in (sdss, desi)}
    # Discriminating SDSS EdS gate (fix round): Gaussian-summary variant, finite delta.
    gs = eds_gate(L.sdss_gaussian_likelihood())
    gs["gate"] = ("fix-round gate added on top of the preregistered one: the SDSS-baseline EdS "
                  "boolean above is non-discriminating (discriminating=false)")
    res["wrong_model_no_Lambda_SDSS_gaussian_summary_gate"] = gs
    # Gate probe: a likelihood that is +inf everywhere must NOT pass the EdS gate.
    probe = eds_gate(InfEverywhere())
    probe["must_be"] = "rejected == false (a broken likelihood must not pass the gate)"
    probe["probe_ok"] = not probe["rejected"]
    res["eds_gate_probe_inf_everywhere"] = probe

    # 2. DM<->DH swap by kind pairing
    vals = desi.vals.copy()
    swapped = vals.copy()
    pairs = []
    for z in np.unique(desi.zs):
        idx = np.where(desi.zs == z)[0]
        kinds = [desi.kinds[i] for i in idx]
        if "DM_over_rs" in kinds and "DH_over_rs" in kinds:
            i_dm = idx[kinds.index("DM_over_rs")]
            i_dh = idx[kinds.index("DH_over_rs")]
            swapped[i_dm], swapped[i_dh] = vals[i_dh], vals[i_dm]
            pairs.append([float(z), float(vals[i_dm]), float(vals[i_dh])])
    lk = desi.with_data("DESI_swapDMDH", swapped)
    x, f = L.fit_map(lk)
    dof = desi.n_data - 2
    res["desi_DM_DH_swap"] = {"swapped_pairs_z_DM_DH": pairs, "map": x.tolist(), "chi2_min": f, "dof": dof,
                              "chi2_per_dof": f / dof, "rejected": bool(f / dof > 3)}

    # 3. cov / 25
    lk = desi.with_data("DESI_cov_over_25", desi.vals, desi.cov / 25.0)
    x, f = L.fit_map(lk)
    res["desi_cov_over_25"] = {"map": x.tolist(), "chi2_min": f, "dof": dof, "chi2_per_dof": f / dof,
                               "rejected": bool(f / dof > 3)}

    # 4. report-only SDSS gaussian-piece cov permutation
    rng = np.random.default_rng(L.SEED)
    g = sdss.gauss
    perm = rng.permutation(g.n_data)
    permuted_cov = g.cov[np.ix_(perm, perm)]
    try:
        gp = g.with_data("sdss_gauss_permcov", g.vals, permuted_cov)
        orig = sdss.gauss
        sdss.gauss = gp
        x, f = L.fit_map(sdss)
        sdss.gauss = orig
        x0, f0 = L.fit_map(sdss)
        res["sdss_cov_permutation_report_only"] = {"perm": perm.tolist(), "map": x.tolist(), "m2lnL_min": f,
                                                   "unpermuted_m2lnL_min": f0, "gate": "report only"}
    except np.linalg.LinAlgError as exc:
        res["sdss_cov_permutation_report_only"] = {"perm": perm.tolist(), "error": str(exc), "gate": "report only"}

    # 5. injected scale shift x0.93 on DESI; tension vs real SDSS baseline
    s = 0.93
    lk = desi.with_data("DESI_scaled_0.93", desi.vals * s, desi.cov * s ** 2)
    m_sh, c_sh, f_sh = moments(lk)
    m_sd, c_sd, _ = moments(sdss)
    t = L.tension(m_sd, c_sd, m_sh, c_sh)
    res["injected_scale_shift_0.93"] = {"desi_shifted_mean": m_sh.tolist(), "desi_shifted_cov": c_sh.tolist(),
                                        "desi_shifted_chi2_min": f_sh,
                                        "sdss_mean": m_sd.tolist(), "sdss_cov": c_sd.tolist(),
                                        "tension": t, "rejected": bool(t["N_sigma"] > 3)}

    # 6. guard
    res["combination_guard"] = guard_control()

    # Preregistered booleans as coded (both datasets) must hold, AND the
    # discriminating versions: DESI directly, SDSS via the Gaussian-summary variant.
    # The SDSS-baseline discriminating flag is reported, not gated (it cannot be
    # true: EdS leaves every grid table), so the substitute is disclosed.
    gates = [res["wrong_model_no_Lambda"][k]["rejected_as_coded"] for k in res["wrong_model_no_Lambda"]]
    gates.append(res["wrong_model_no_Lambda"][desi.name]["rejected"])
    gates.append(res["wrong_model_no_Lambda_SDSS_gaussian_summary_gate"]["rejected"])
    gates.append(res["eds_gate_probe_inf_everywhere"]["probe_ok"])
    gates += [res[k]["rejected"] for k in ("desi_DM_DH_swap", "desi_cov_over_25",
                                          "injected_scale_shift_0.93", "combination_guard")]
    res["all_negative_controls_rejected"] = bool(all(gates))
    text = json.dumps(strict(res), indent=1, allow_nan=False)
    (L.RESULTS / "negative_controls.json").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

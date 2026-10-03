"""Instrument checks (LL.md Sec. 1) before any cosmology fit.

1. sha256 of every input file must equal the preregistered hash.
2. Prediction codes: astropy vs quad vs Gauss-Legendre agree < 1e-4 relative.
3. Grid likelihood tables reproduce their published peak and 68% width
   (prereg 'instrument_check_grid_likelihoods'), plus the paired negative:
   dropping the MGS rs rescaling must FAIL the MGS location check.
4. Combination guard refuses the excluded DESI+eBOSS Lya file.
Writes results/eboss_vs_desi/instrument_check.json.
"""

from __future__ import annotations

import json
from typing import Callable

import numpy as np
from scipy.optimize import brentq, minimize, minimize_scalar

import bao_lib as L


def interval_1d(f: Callable[[float], float], lo: float, hi: float) -> tuple[float, float, float]:
    """Minimum of f and the Delta f = 1 crossings inside [lo, hi]."""
    r = minimize_scalar(f, bounds=(lo, hi), method="bounded", options={"xatol": 1e-10})
    x0, f0 = float(r.x), float(r.fun)
    g = lambda x: f(x) - f0 - 1.0
    left = brentq(g, lo, x0) if g(lo) > 0 else float("nan")
    right = brentq(g, x0, hi) if g(hi) > 0 else float("nan")
    return x0, left, right


def check_1d(name: str, loc: float, left: float, right: float, ref: float, ref_sig: float,
             width_tol: float = 0.15) -> dict:
    width = 0.5 * (right - left)
    loc_dev = abs(loc - ref) / ref_sig
    wr = width / ref_sig
    return {"name": name, "peak": loc, "minus": loc - left, "plus": right - loc, "half_width": width,
            "reference": ref, "reference_sigma": ref_sig,
            "location_dev_in_sigma_ref": loc_dev, "width_ratio": wr,
            "location_pass": bool(loc_dev < 0.1), "width_pass": bool(abs(wr - 1) < width_tol)}


def lya_moments(g: L.LyaGrid) -> dict:
    p = g.lik / g.lik.sum()
    DM, DH = np.meshgrid(g.dm, g.dh, indexing="ij")
    mdm, mdh = float((p * DM).sum()), float((p * DH).sum())
    sdm = float(np.sqrt((p * (DM - mdm) ** 2).sum())); sdh = float(np.sqrt((p * (DH - mdh) ** 2).sum()))
    rho = float((p * (DM - mdm) * (DH - mdh)).sum() / (sdm * sdh))
    i, j = np.unravel_index(np.argmax(g.lik), g.lik.shape)
    # preregistered location = the peak; located on the bicubic spline surface
    # (grid spacing is ~0.19 sigma in DM, so the raw grid argmax is quantised)
    o = minimize(lambda t: min(g.m2lnl_of(t[0], t[1]), 1e9), [g.dm[i], g.dh[j]], method="Nelder-Mead",
                 options={"xatol": 1e-8, "fatol": 1e-10})
    return {"mean_DM": mdm, "mean_DH": mdh, "std_DM": sdm, "std_DH": sdh, "rho": rho,
            "grid_argmax_DM": float(g.dm[i]), "grid_argmax_DH": float(g.dh[j]),
            "peak_DM": float(o.x[0]), "peak_DH": float(o.x[1])}


def check_lya(name: str, mom: dict, ref: dict) -> dict:
    out = {"name": name, **mom, "reference": ref}
    out["location_definition"] = ("peak of the bicubic spline of -2lnL (prereg: 'locate the peak'); "
                                  "posterior-mean deviations also reported (info only)")
    out["DM_mean_dev_info"] = abs(mom["mean_DM"] - ref["DM"]) / ref["sDM"]
    out["DH_mean_dev_info"] = abs(mom["mean_DH"] - ref["DH"]) / ref["sDH"]
    out["DM_location_dev"] = abs(mom["peak_DM"] - ref["DM"]) / ref["sDM"]
    out["DH_location_dev"] = abs(mom["peak_DH"] - ref["DH"]) / ref["sDH"]
    out["DM_width_ratio"] = mom["std_DM"] / ref["sDM"]
    out["DH_width_ratio"] = mom["std_DH"] / ref["sDH"]
    out["rho_diff"] = mom["rho"] - ref["rho"]
    out["location_pass"] = bool(out["DM_location_dev"] < 0.1 and out["DH_location_dev"] < 0.1)
    out["width_pass"] = bool(abs(out["DM_width_ratio"] - 1) < 0.25 and abs(out["DH_width_ratio"] - 1) < 0.25)
    out["rho_pass"] = bool(abs(out["rho_diff"]) < 0.1)
    return out


def main() -> int:
    res: dict = {}
    res["sha256_verified"] = L.verify_hashes()
    print("sha256: all", len(res["sha256_verified"]), "input files match preregistration")

    # --- prediction-code agreement on every SDSS and DESI data point
    desi = L.desi_likelihood()
    sg = L.sdss_gaussian_likelihood()
    zs = np.concatenate([desi.zs, sg.zs, [0.15, 0.845, 2.334]])
    kinds = desi.kinds + sg.kinds + ["DV_over_rs", "DV_over_rs", "DM_over_rs"]
    worst = {"astropy_vs_quad": 0.0, "gl_vs_quad": 0.0, "gl_vs_astropy": 0.0}
    for om, hrd in [(0.25, 95.0), (0.2975, 101.54), (0.31, 100.4), (0.40, 110.0), (0.15, 120.0)]:
        a = L.observables(zs, kinds, om, hrd, "astropy")
        q = L.observables(zs, kinds, om, hrd, "quad")
        g = L.observables(zs, kinds, om, hrd, "gl")
        worst["astropy_vs_quad"] = max(worst["astropy_vs_quad"], float(np.max(np.abs(a / q - 1))))
        worst["gl_vs_quad"] = max(worst["gl_vs_quad"], float(np.max(np.abs(g / q - 1))))
        worst["gl_vs_astropy"] = max(worst["gl_vs_astropy"], float(np.max(np.abs(g / a - 1))))
    res["prediction_code_max_rel_diff"] = worst
    res["prediction_codes_pass"] = bool(max(worst.values()) < 1e-4)
    print("prediction codes max rel diff:", worst)

    # --- MGS
    mgs = L.MGSTable()
    f = lambda dv: mgs.m2lnl_of_dv(dv)
    lo, hi = L.MGS_BOUNDS[0] * L.MGS_RS_RESCALE, L.MGS_BOUNDS[1] * L.MGS_RS_RESCALE
    x0, l, r = interval_1d(f, lo + 1e-9, hi - 1e-9)
    mgs_c = check_1d("MGS", x0, l, r, 4.465666824, 0.1681350461)
    # also the likelihood-weighted mean/std (info only)
    xs = np.linspace(lo, hi, 20001); w = np.exp(-0.5 * np.array([f(x) for x in xs])); w /= w.sum()
    mgs_c["lik_mean"] = float((w * xs).sum()); mgs_c["lik_std"] = float(np.sqrt((w * (xs - mgs_c["lik_mean"]) ** 2).sum()))
    mgs_c["argmin_alpha"] = float(x0 / L.MGS_RS_RESCALE)
    res["MGS"] = mgs_c
    # paired negative: no rescaling (treat the alpha table as DV/rd directly)
    fneg = lambda dv: float(mgs.spline(dv)) if L.MGS_BOUNDS[0] <= dv <= L.MGS_BOUNDS[1] else np.inf
    xn, ln_, rn = interval_1d(fneg, L.MGS_BOUNDS[0] + 1e-9, L.MGS_BOUNDS[1] - 1e-9)
    neg = check_1d("MGS_no_rescale_NEGATIVE", xn, ln_, rn, 4.465666824, 0.1681350461)
    neg["must_fail_location"] = True
    neg["failed_as_required"] = not neg["location_pass"]
    res["MGS_paired_negative"] = neg

    # --- ELG
    elg = L.ELGTable()
    x0, l, r = interval_1d(elg.m2lnl_of_dv, elg.bounds[0], elg.bounds[1])
    elg_c = check_1d("ELG", x0, l, r, 18.33, 0.595)
    elg_c["published_asym"] = "+0.57/-0.62"
    elg_c["L_over_Lmax_at_lower_edge"] = float(np.exp(-0.5 * elg.m2[0]))
    elg_c["L_over_Lmax_at_upper_edge"] = float(np.exp(-0.5 * elg.m2[-1]))
    res["ELG"] = elg_c

    # --- Lya
    res["Lya_auto"] = check_lya("Lya_auto", lya_moments(L.LyaGrid("lya_auto")),
                                {"DM": 37.6, "sDM": 1.9, "DH": 8.93, "sDH": 0.275, "rho": -0.49})
    res["Lya_cross"] = check_lya("Lya_cross", lya_moments(L.LyaGrid("lya_cross")),
                                 {"DM": 37.3, "sDM": 1.65, "DH": 9.08, "sDH": 0.34, "rho": -0.43})

    # --- combination guard
    try:
        L.load_gauss("bad", "desi_2024_eboss_gaussian_bao_Lya_GCcomb_mean.txt",
                     "desi_2024_eboss_gaussian_bao_Lya_GCcomb_cov.txt", sdss=True)
        res["combination_guard_raised"] = False
    except L.CombinationError as exc:
        res["combination_guard_raised"] = True
        res["combination_guard_message"] = str(exc)

    loc_ok = all(res[k]["location_pass"] for k in ("MGS", "ELG", "Lya_auto", "Lya_cross"))
    wid_ok = all(res[k]["width_pass"] for k in ("MGS", "ELG", "Lya_auto", "Lya_cross"))
    rho_ok = res["Lya_auto"]["rho_pass"] and res["Lya_cross"]["rho_pass"]
    res["summary"] = {"all_locations_pass": loc_ok, "all_widths_pass": wid_ok, "lya_rho_pass": rho_ok,
                      "mgs_paired_negative_failed_as_required": neg["failed_as_required"],
                      "combination_guard_raised": res["combination_guard_raised"],
                      "prediction_codes_pass": res["prediction_codes_pass"]}
    out = L.RESULTS / "instrument_check.json"
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "sha256_verified"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

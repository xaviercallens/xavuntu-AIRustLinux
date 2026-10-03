"""Referee fix-round diagnostics for bao_bbn_h0 (no refit; reads the locked table and fit.json).

Sections (each writes its numbers into results/bao_bbn_h0/fixround_diagnostics.json):
  1. hrd_monotonicity: numerical companion of the Lean theorem hrd_strictMonoOn_h. At fixed
     (Omega_m, omega_b), is h -> h * r_d(h) strictly increasing on the sampled support, for the
     SECONDARY eq.-16 r_d and for the PRIMARY CAMB-table r_d? And does it FAIL (eq. 16) where the
     Lean hypothesis omega_m (1 - 2a) >= omega_nu is violated (showing the hypothesis is needed)?
  2. h_dependence: spread of the CAMB r_drag table across its h nodes at fixed physical densities,
     with and without the 22 nodes that were refilled at a lower h, core vs wide region.
  3. slope_and_T2_propagation: d ln(h r_d)/d ln h at fixed (Omega_m, omega_b) at the posterior means,
     for both r_d models, and the H0 offset implied by the DR1 h r_d quoted as 101.8 (Sec. 8) or
     101.9 (Sec. 6) versus our G2 value.
  4. tolerance_rebudget: the strict tolerance re-derived for the PRIMARY without the fitting-formula
     systematic (text-only; the preregistered verdict rule is NOT changed).

Run: /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python scripts/bao_bbn_h0/fixround_diagnostics.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm  # noqa: E402

A_CB = 0.25351


def hrd_of(model: str, h: np.ndarray, om: float, wb: float) -> np.ndarray:
    if model == "camb":
        return h * cm.rd_camb(h, np.full_like(h, om), np.full_like(h, wb))
    return h * cm.rd_aubourg16(cm.omega_cb_of(h, om), wb)


def monotonicity(fit: dict[str, Any]) -> dict[str, Any]:
    rng = np.random.default_rng(20260927)
    out: dict[str, Any] = {}
    # sampled support of the T1 posterior (+-5 sigma box) and a wide box inside the priors/table
    t1 = fit["primary"]["T1_DR2"]["chain"]
    mu, sd = t1["mean"], t1["std"]
    boxes = {"T1_pm5sigma": ((mu["Omega_m"] - 5 * sd["Omega_m"], mu["Omega_m"] + 5 * sd["Omega_m"]),
                             (mu["omega_b"] - 5 * sd["omega_b"], mu["omega_b"] + 5 * sd["omega_b"]),
                             (mu["H0"] / 100 - 0.05, mu["H0"] / 100 + 0.05)),
             "wide": ((0.1, 0.6), (0.015, 0.03), (0.5, 0.95))}
    for name, (omr, wbr, hr) in boxes.items():
        for model in ("aub16", "camb"):
            nmono, ntot, worst = 0, 0, np.inf
            for _ in range(300):
                om, wb = rng.uniform(*omr), rng.uniform(*wbr)
                h = np.linspace(*hr, 201)
                v = hrd_of(model, h, om, wb)
                ok = np.isfinite(v)
                d = np.diff(v[ok])
                ntot += 1
                nmono += int(np.all(d > 0))
                worst = min(worst, float(np.min(d)) if d.size else np.inf)
            out[f"{name}_{model}"] = {"n_curves": ntot, "n_strictly_increasing": nmono, "min_step_Mpc": worst,
                                      "box": {"Omega_m": omr, "omega_b": wbr, "h": hr}}
    # below the Lean threshold: omega_m (1-2a) < omega_nu, i.e. Om h^2 < omega_nu / (1-2a) (eq. 16 only;
    # far outside any prior, used only to show the hypothesis is not vacuous)
    thr = cm.OMEGA_NU_AUBOURG / (1 - 2 * A_CB)
    om = 0.01
    h_lo = np.sqrt(cm.OMEGA_NU_AUBOURG / om) * 1.0001
    h_thr = np.sqrt(thr / om)
    h = np.linspace(h_lo, h_thr, 401)
    v = hrd_of("aub16", h, om, 0.022)
    h2 = np.linspace(h_thr, 2 * h_thr, 401)
    v2 = hrd_of("aub16", h2, om, 0.022)
    out["below_threshold_aub16"] = {
        "Omega_m": om, "omega_m_threshold": thr, "h_range": [float(h_lo), float(h_thr)],
        "strictly_decreasing_below": bool(np.all(np.diff(v) < 0)),
        "strictly_increasing_above": bool(np.all(np.diff(v2) > 0))}
    return out


def h_dependence(val: dict[str, Any]) -> dict[str, Any]:
    z = np.load(cm.RD_TABLE)
    tab, lnwb, lnwc, hn = z["rdrag"], z["ln_omega_b"], z["ln_omega_cdm"], z["h"]
    frac = np.abs(tab / tab[1][None] - 1.0)  # vs the h=0.6 node
    sub = np.zeros(tab.shape[1:], dtype=bool)
    for s in val["grid_h_substitutions"]:
        i = int(np.argmin(np.abs(lnwb - np.log(s["omega_b"]))))
        j = int(np.argmin(np.abs(lnwc - np.log(s["omega_cdm"]))))
        sub[i, j] = True
    wb, wc = np.meshgrid(np.exp(lnwb), np.exp(lnwc), indexing="ij")
    core = (wb >= 0.019) & (wb <= 0.026) & (wc >= 0.10) & (wc <= 0.14)
    k = int(np.unravel_index(np.argmax(frac), frac.shape)[0])
    i, j = np.unravel_index(np.argmax(frac[k]), frac[k].shape)
    return {
        "reference_h_node": float(hn[1]),
        "max_frac_all_nodes": float(frac.max()),
        "argmax": {"h_node": float(hn[k]), "omega_b": float(wb[i, j]), "omega_cdm": float(wc[i, j]),
                   "refilled_node": bool(sub[i, j]) if k == 2 else False},
        "max_frac_excluding_refilled": float(max(frac[0].max(), frac[2][~sub].max())),
        "max_frac_core": float(max(frac[0][core].max(), frac[2][core].max())),
        "max_frac_h0.99_node_core": float(frac[2][core].max()),
        "max_frac_h0.2_node_core": float(frac[0][core].max()),
        "n_refilled": int(sub.sum()),
    }


def slope_and_t2(fit: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    eps = 1e-4
    for a, model in (("primary", "camb"), ("secondary", "aub16")):
        for key in ("T1_DR2", "T2_DR1"):
            m = fit[a][key]["chain"]["mean"]
            h = m["H0"] / 100
            hh = np.array([h * (1 - eps), h * (1 + eps)])
            v = hrd_of(model, hh, m["Omega_m"], m["omega_b"])
            out[f"{a}_{key}_dlnhrd_dlnh"] = float((np.log(v[1]) - np.log(v[0])) / (np.log(hh[1]) - np.log(hh[0])))
    g2 = fit["G2"]["chain"]["mean"]["hrd"]
    rows = []
    for a in ("primary", "secondary"):
        s = out[f"{a}_T2_DR1_dlnhrd_dlnh"]
        h0 = fit[a]["T2_DR1"]["chain"]["mean"]["H0"]
        for quoted, where in ((101.8, "2404.03002 Sec. 8 (Table/text used for G2 target)"),
                              (101.9, "2404.03002 Sec. 6")):
            rows.append({"analysis": a, "desi_hrd_quoted": quoted, "where": where, "our_G2_hrd": g2,
                         "slope": s, "implied_H0_excess_km_s_Mpc": float(h0 * (g2 / quoted - 1.0) / s),
                         "observed_T2_offset": float(h0 - 68.53)})
    out["T2_propagation"] = rows
    return out


def rebudget(fit: dict[str, Any], val: dict[str, Any], slope: float) -> dict[str, Any]:
    pre = json.loads(cm.PREREG.read_text())
    mc = float(_find(pre, "sigma_mc_and_numerics_allowance"))
    core = next(r for r in val["interpolation_vs_direct_camb"] if r["region"] == "core")["max_abs_frac"]
    h0 = fit["primary"]["T1_DR2"]["chain"]["mean"]["H0"]
    interp = h0 * core / slope
    budget = float(np.hypot(mc, interp))
    d1 = abs(fit["primary"]["T1_DR2"]["chain"]["mean"]["H0"] - 68.51)
    d2 = abs(fit["primary"]["T2_DR1"]["chain"]["mean"]["H0"] - 68.53)
    return {"sigma_mc_from_preregistration": mc, "interp_term_km_s_Mpc": float(interp),
            "rebudget_strict_km_s_Mpc": budget, "preregistered_strict_km_s_Mpc": pre["tolerance"]["strict_H0_km_s_Mpc"],
            "T1_abs_dH0": float(d1), "T1_within_rebudget": bool(d1 <= budget),
            "T2_abs_dH0": float(d2), "T2_within_rebudget": bool(d2 <= budget),
            "note": "text-only: the preregistered verdict rule (strict 0.15) is applied unchanged; this shows the "
                    "strict limit is generous for the primary once the formula systematic no longer applies"}


def _find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r is not None:
                return r
    return None


def main() -> int:
    fit = json.loads((cm.RESULTS / "fit.json").read_text())
    val = json.loads((cm.RESULTS / "rd_camb_validation.json").read_text())
    res: dict[str, Any] = {"hrd_monotonicity": monotonicity(fit), "h_dependence": h_dependence(val)}
    res["slope_and_T2_propagation"] = slope_and_t2(fit)
    res["tolerance_rebudget"] = rebudget(fit, val, res["slope_and_T2_propagation"]["primary_T1_DR2_dlnhrd_dlnh"])
    cm.write_json(cm.RESULTS / "fixround_diagnostics.json", res)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Amendment 1 primary sound horizon: exact CAMB r_drag table + validation.

Run with /mnt/disks/disk-socrateai-local-1/venv-cosmo/bin/python (camb 2.0.4, classy 3.3.4).

Builds r_drag(omega_b, omega_cdm, h) with CAMB for flat LCDM, N_eff = 3.044, one massive
neutrino of 0.06 eV (num_massive_neutrinos=1), T_cmb = 2.7255 K, BBN-consistent Y_He
(CAMB default). Grid: 49 x 61 x 3 nodes in (ln omega_b, ln omega_cdm, h).

Writes:
  results/bao_bbn_h0/rd_camb_table.npz        the table (small, a few 100 kB)
  results/bao_bbn_h0/rd_camb_validation.json  anchor, interpolation accuracy vs direct CAMB,
                                              CLASS cross-check, CAMB-background vs analytic
                                              distance cross-check, eq.16 vs CAMB comparison.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import camb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm  # noqa: E402

LNWB = np.linspace(np.log(0.005), np.log(0.1), 49)
LNWC = np.linspace(np.log(0.005), np.log(1.0), 61)
# top node 0.99, not 1.0: CAMB 2.0.4 raises "failed to find end of recombination" at h=1.0
# for 26 low-Omega_m nodes (first build, logged); h in (0.99, 1.0] maps to zero support.
HNODES = np.array([0.2, 0.6, 0.99])


def camb_params(ombh2: float, omch2: float, h: float) -> camb.CAMBparams:
    p = camb.CAMBparams()
    p.set_cosmology(H0=100.0 * h, ombh2=ombh2, omch2=omch2, mnu=cm.MNU, nnu=cm.NEFF,
                    num_massive_neutrinos=1, TCMB=cm.T_CMB, omk=0.0)
    return p


def camb_rd(ombh2: float, omch2: float, h: float) -> float:
    r = camb.get_background(camb_params(ombh2, omch2, h), no_thermo=False)
    return float(r.get_derived_params()["rdrag"])


def build_table() -> tuple[np.ndarray, int, list[dict[str, float]]]:
    """Fill each node with CAMB at the node's h. If CAMB's recombination solver fails there
    (seen only at h >= 0.99 and Omega_m < 0.05), retry at h - 0.01, -0.02, -0.05: r_drag at fixed
    physical densities is nearly h-independent (spread vs the h=0.6 node: <= 1.8e-5 in the core
    region, max 2.1e-4 at the h=0.2 node in a far corner; results/bao_bbn_h0/fixround_diagnostics.json),
    so the substitute is exact to that level. Every substitution is logged."""
    tab = np.full((len(HNODES), len(LNWB), len(LNWC)), np.nan)
    nfail = 0
    subs: list[dict[str, float]] = []
    for k, h in enumerate(HNODES):
        for i, lb in enumerate(LNWB):
            for j, lc in enumerate(LNWC):
                wb, wc = float(np.exp(lb)), float(np.exp(lc))
                for dh in (0.0, -0.01, -0.02, -0.05):
                    try:
                        tab[k, i, j] = camb_rd(wb, wc, float(h) + dh)
                    except Exception:  # CAMB error: try the next h, count if all fail
                        continue
                    if dh != 0.0:
                        subs.append({"h_node": float(h), "h_used": float(h) + dh, "omega_b": wb, "omega_cdm": wc})
                    break
                else:
                    nfail += 1
    return tab, nfail, subs


def class_rd(ombh2: float, omch2: float, h: float) -> tuple[float, float]:
    from classy import Class

    c = Class()
    # N_ur chosen so that N_eff = 3.044 with one massive species at CLASS's default T_ncdm
    c.set({"omega_b": ombh2, "omega_cdm": omch2, "h": h, "T_cmb": cm.T_CMB, "N_ur": 2.0308,
           "N_ncdm": 1, "m_ncdm": cm.MNU})
    c.compute(level=["thermodynamics"])
    rd = float(c.rs_drag())
    neff = float(c.Neff())
    c.struct_cleanup()
    c.empty()
    return rd, neff


def main() -> int:
    t0 = time.time()
    out: dict[str, object] = {"camb_version": camb.__version__, "grid": {
        "ln_omega_b": [float(LNWB[0]), float(LNWB[-1]), len(LNWB)],
        "ln_omega_cdm": [float(LNWC[0]), float(LNWC[-1]), len(LNWC)], "h_nodes": HNODES.tolist()}}
    omnuh2 = float(camb_params(0.0222, 0.12, 0.68).omnuh2)
    out["omega_nu_camb"] = omnuh2
    # anchor: Planck 2018 best fit (same parameters as the orchestrator's positive control)
    p18 = camb.set_params(H0=67.32, ombh2=0.022383, omch2=0.12011, mnu=0.06, nnu=3.046, num_massive_neutrinos=1,
                          tau=0.0543, As=2.1e-9, ns=0.96605)
    r18 = camb.get_background(p18, no_thermo=False).get_derived_params()["rdrag"]
    out["anchor_planck2018_rdrag_nnu3.046"] = float(r18)
    print("omega_nu_camb", omnuh2, "anchor rdrag (Neff 3.046)", r18, flush=True)

    tab, nfail, subs = build_table()
    out["n_grid_fail"] = nfail
    out["n_grid_h_substituted"] = len(subs)
    out["grid_h_substitutions"] = subs
    out["build_s"] = time.time() - t0
    np.savez(cm.RD_TABLE, ln_omega_b=LNWB, ln_omega_cdm=LNWC, h=HNODES, rdrag=tab,
             omega_nu_camb=omnuh2, camb_version=camb.__version__)
    print("table built", tab.shape, "fails", nfail, "t", out["build_s"], flush=True)
    h_spread = np.nanmax(np.abs(tab / tab[1][None] - 1.0))
    out["max_frac_h_dependence_over_nodes"] = float(h_spread)

    interp = cm.RdCambTable(cm.RD_TABLE)
    rng = np.random.default_rng(20260927)
    rows = []
    for region, n, wb_r, wc_r, h_r in (("core", 200, (0.019, 0.026), (0.10, 0.14), (0.60, 0.76)),
                                       ("wide", 100, (0.006, 0.09), (0.01, 0.8), (0.25, 0.95))):
        wb = rng.uniform(*wb_r, n)
        wc = np.exp(rng.uniform(np.log(wc_r[0]), np.log(wc_r[1]), n))
        hh = rng.uniform(*h_r, n)
        direct = np.array([camb_rd(float(a), float(b), float(c)) for a, b, c in zip(wb, wc, hh)])
        tabv = interp(wb, wc, hh)
        fr = tabv / direct - 1.0
        rows.append({"region": region, "n": n, "max_abs_frac": float(np.max(np.abs(fr))),
                     "rms_frac": float(np.sqrt(np.mean(fr**2)))})
        print("interp", rows[-1], flush=True)
    out["interpolation_vs_direct_camb"] = rows

    # CLASS cross-check and Aubourg eq.16 vs CAMB at a few points
    pts = [(0.02218, 0.1190, 0.685), (0.02108, 0.1250, 0.66), (0.02328, 0.1150, 0.71),
           (0.02218, 0.1300, 0.64), (0.022383, 0.12011, 0.6732)]
    cc = []
    for wb, wc, h in pts:
        rc = camb_rd(wb, wc, h)
        rcl, neff_cl = class_rd(wb, wc, h)
        ra = float(cm.rd_aubourg16(wb + wc + omnuh2 - cm.OMEGA_NU_AUBOURG, wb))
        cc.append({"omega_b": wb, "omega_cdm": wc, "h": h, "camb": rc, "class": rcl, "class_Neff": neff_cl,
                   "frac_class_minus_camb": rcl / rc - 1.0, "aubourg16": ra, "frac_aub16_minus_camb": ra / rc - 1.0})
        print("class/aub16", cc[-1], flush=True)
    out["class_and_aubourg_vs_camb"] = cc

    # CAMB background distances vs the analytic manual predictor (Omega_m includes the nu)
    d2 = cm.load_dr2()
    dist = []
    for h0, om in ((68.5, 0.2977), (64.0, 0.33), (73.0, 0.27)):
        h = h0 / 100.0
        wb = 0.02218
        wc = om * h * h - wb - omnuh2
        res = camb.get_background(camb_params(wb, wc, h), no_thermo=True)
        dm_c = res.comoving_radial_distance(d2.z)
        dh_c = cm.C_KM_S / res.hubble_parameter(d2.z)
        dm_m, dh_m = cm.distances_manual_vec(d2.z, np.array([h]), np.array([om]))
        dist.append({"H0": h0, "Omega_m": om, "max_frac_DM": float(np.max(np.abs(dm_m[0] / dm_c - 1))),
                     "max_frac_DH": float(np.max(np.abs(dh_m[0] / dh_c - 1)))})
        print("distances camb vs manual", dist[-1], flush=True)
    out["camb_background_vs_manual_distances"] = dist
    out["runtime_s"] = time.time() - t0
    cm.write_json(cm.RESULTS / "rd_camb_validation.json", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

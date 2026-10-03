"""CAMB background cross-check of the analytic flat-LCDM distances (run with venv-cosmo).

The fit model neglects radiation (prereg: "<0.1% at z<=2.33"). This script tests
that claim: at every data redshift used by either likelihood, it compares
  D_M(z) = comoving_radial_distance and H(z) = hubble_parameter from CAMB 2.0.4
(massless neutrinos, radiation included, Omega_m = (ombh2+omch2)/h^2 set equal to
the analytic Om) with the hand-coded quad / Gauss-Legendre / astropy codes.
Gate: max relative difference < 1e-3 for D_M, H and DV. Also records CAMB r_drag
and h*r_drag at the Planck-2018 point and at the tested points.
Writes results/eboss_vs_desi/camb_crosscheck.json.
"""

from __future__ import annotations

import json

import camb
import numpy as np

import bao_lib as L

GATE = 1e-3


def camb_background(om: float, h: float, ombh2: float = 0.02237, tcmb: float = 2.7255) -> camb.CAMBdata:
    omch2 = om * h * h - ombh2
    pars = camb.CAMBparams()
    pars.set_cosmology(H0=100.0 * h, ombh2=ombh2, omch2=omch2, mnu=0.0, num_massive_neutrinos=0,
                       omk=0.0, TCMB=tcmb)
    return camb.get_background(pars)


def compare(om: float, h: float, zs: np.ndarray) -> dict:
    bg = camb_background(om, h)
    dm_camb = np.asarray(bg.comoving_radial_distance(zs))
    hz_camb = np.asarray(bg.hubble_parameter(zs))
    dm_quad = L.dm_h100_quad(zs, om) / h
    dm_gl = L.dm_h100_gl(zs, om) / h
    dm_ast = L.dm_h100_astropy(zs, om) / h
    hz_an = 100.0 * h * L.e_of_z(zs, om)
    dv_camb = (zs * dm_camb ** 2 * L.C_KM_S / hz_camb) ** (1 / 3)
    dv_an = (zs * dm_quad ** 2 * L.C_KM_S / hz_an) ** (1 / 3)
    rel_dm = np.abs(dm_quad / dm_camb - 1)
    rel_hz = np.abs(hz_an / hz_camb - 1)
    rel_dv = np.abs(dv_an / dv_camb - 1)
    derived = bg.get_derived_params()
    return {
        "Om": om, "h": h, "camb_Omega_m_check": float(bg.get_Omega("cdm", 0) + bg.get_Omega("baryon", 0)),
        "camb_Omega_radiation_z0": float(bg.get_Omega("photon", 0) + bg.get_Omega("neutrino", 0)),
        "camb_rdrag_Mpc": float(derived["rdrag"]), "camb_h_rdrag_Mpc": float(h * derived["rdrag"]),
        "z": zs.tolist(),
        "rel_diff_DM_quad_vs_camb": rel_dm.tolist(),
        "rel_diff_H_analytic_vs_camb": rel_hz.tolist(),
        "rel_diff_DV_analytic_vs_camb": rel_dv.tolist(),
        "max_rel_DM": float(rel_dm.max()), "max_rel_H": float(rel_hz.max()), "max_rel_DV": float(rel_dv.max()),
        "max_rel_quad_vs_gl": float(np.max(np.abs(dm_quad / dm_gl - 1))),
        "max_rel_quad_vs_astropy": float(np.max(np.abs(dm_quad / dm_ast - 1))),
        "pass": bool(max(rel_dm.max(), rel_hz.max(), rel_dv.max()) < GATE),
    }


def main() -> int:
    L.verify_hashes()
    desi = L.desi_likelihood()
    sg = L.sdss_gaussian_likelihood()
    zs = np.unique(np.concatenate([desi.zs, sg.zs, [0.15, 0.845, 2.334]]))
    points = {"DESI_DR2_published": (0.2975, 0.6736), "SDSS_published": (0.299, 0.70),
              "high_Om_stress": (0.35, 0.65)}
    res: dict = {"camb_version": camb.__version__, "gate_max_rel_diff": GATE,
                 "neutrinos": "massless (mnu=0), so Omega_m = (ombh2+omch2)/h^2 exactly matches analytic Om",
                 "points": {}}
    for k, (om, h) in points.items():
        res["points"][k] = compare(om, h, zs)
        r = res["points"][k]
        print(k, "Om", om, "h", h, "max rel DM", f"{r['max_rel_DM']:.3e}", "H", f"{r['max_rel_H']:.3e}",
              "DV", f"{r['max_rel_DV']:.3e}", "rdrag", f"{r['camb_rdrag_Mpc']:.4f}", "pass", r["pass"])
    # Planck-2018 reference point (default CAMB neutrinos: one massive 0.06 eV) for r_d sanity
    pp = camb.CAMBparams()
    pp.set_cosmology(H0=67.36, ombh2=0.02237, omch2=0.1200, mnu=0.06, omk=0.0, tau=0.0544)
    bgp = camb.get_background(pp)
    rd = float(bgp.get_derived_params()["rdrag"])
    res["planck2018_reference"] = {"H0": 67.36, "ombh2": 0.02237, "omch2": 0.12, "mnu": 0.06,
                                   "rdrag_Mpc": rd, "h_rdrag_Mpc": 0.6736 * rd,
                                   "orchestrator_positive_control_rdrag": 147.1027}
    print("Planck-2018 CAMB rdrag", f"{rd:.4f}", "h*rdrag", f"{0.6736 * rd:.3f}")
    res["all_pass"] = bool(all(p["pass"] for p in res["points"].values()))
    (L.RESULTS / "camb_crosscheck.json").write_text(json.dumps(res, indent=1))
    print("CAMB CROSS-CHECK PASS:", res["all_pass"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

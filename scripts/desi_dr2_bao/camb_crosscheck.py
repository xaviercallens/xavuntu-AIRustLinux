#!/usr/bin/env python3
"""CAMB cross-check of the analytic distances used in the desi_dr2_bao fit.

(a) Exactness check. CAMB with m_nu = 0 (all neutrinos massless), LCDM and w=-0.9
    fluid. Omega_r is taken from CAMB's own photon + massless-neutrino densities.
    CAMB D_M(z) and H(z), rescaled to H0 = 100 units, are compared with
    dr2_model.predict_quad(..., orad=Omega_r) at the 13 DR2 redshifts.
(b) Modelling systematic of the PRIMARY model (no radiation, no neutrino mass).
    CAMB with one 0.06 eV massive neutrino (the DESI baseline) generates a
    noiseless DR2-shaped data vector (D/r_d with CAMB's own r_drag). The primary
    model is then fitted to it by chi^2 minimum with the real DR2 covariance; the
    parameter offsets vs the CAMB input are reported in units of the published
    DR2 sigmas. Per-observable residuals are reported in units of the DR2 errors.
(c) Planck-2018-like r_drag reproduction (orchestrator's positive control).

Needs camb: run with the venv-cosmo interpreter.
    /mnt/disks/disk-socrateai-local-1/venv-cosmo/bin/python -B scripts/desi_dr2_bao/camb_crosscheck.py
Writes results/desi_dr2_bao/camb_crosscheck.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import camb
import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dr2_model as m  # noqa: E402

NNU = 3.044


def camb_background(h0: float, ombh2: float, omch2: float, mnu: float, w: float) -> camb.CAMBdata:
    pars = camb.CAMBparams()
    if mnu > 0:
        pars.set_cosmology(H0=h0, ombh2=ombh2, omch2=omch2, mnu=mnu, num_massive_neutrinos=1, nnu=NNU, omk=0.0)
    else:
        pars.set_cosmology(H0=h0, ombh2=ombh2, omch2=omch2, mnu=0.0, num_massive_neutrinos=0, nnu=NNU, omk=0.0)
    if w != -1.0:
        pars.set_dark_energy(w=w, wa=0.0, dark_energy_model="fluid")
    return camb.get_background(pars)


def camb_observables(res: camb.CAMBdata, ds: m.Dataset, h: float, hrd: float) -> np.ndarray:
    """D_M, H in H0=100 units from CAMB, assembled with the fit code's own _assemble."""
    dm100 = np.array([res.comoving_radial_distance(float(z)) for z in ds.z]) * h
    e = np.array([res.hubble_parameter(float(z)) for z in ds.z]) / (100.0 * h)
    return m._assemble(ds.z, ds.kinds, dm100, e, hrd)


def omegas(res: camb.CAMBdata) -> dict[str, float]:
    return {k: float(res.get_Omega(k, z=0.0)) for k in ("cdm", "baryon", "photon", "neutrino", "nu", "de")}


def main() -> int:
    dr2 = m.load_dr2()
    sig = np.sqrt(np.diag(dr2.cov))
    out: dict[str, object] = {"generated_at": m.utc_now(), "camb_version": camb.__version__,
                              "preregistration_sha256": m.sha256(m.PREREG)}
    h0, ombh2, omch2 = 68.5, 0.0222, 0.1180
    h = h0 / 100.0

    # (a) exactness with massless neutrinos
    part_a = {}
    for w in (-1.0, -0.9):
        res = camb_background(h0, ombh2, omch2, 0.0, w)
        om_ = omegas(res)
        om = om_["cdm"] + om_["baryon"]
        orad = om_["photon"] + om_["neutrino"]
        hrd = float(res.get_derived_params()["rdrag"]) * h
        cam = camb_observables(res, dr2, h, hrd)
        ours = m.predict_quad(dr2, om, hrd, w, orad)
        rel = cam / ours - 1.0
        part_a[f"w={w}"] = {"Omega_m": om, "Omega_r": orad, "omegas_z0": om_, "h_rd": hrd,
                            "max_abs_rel_diff": float(np.max(np.abs(rel))),
                            "max_abs_diff_in_DR2_sigma": float(np.max(np.abs(cam - ours) / sig)),
                            "pass_rel_1e-4": bool(np.max(np.abs(rel)) < 1e-4)}
        print("(a)", w, part_a[f"w={w}"], flush=True)
    out["a_massless_nu_exactness"] = part_a

    # (b) primary-model systematic vs CAMB with 0.06 eV
    pub = {"lcdm": {"Om": 0.0086, "h_rd": 0.73}, "wcdm": {"Om": 0.0089, "w": 0.078}}
    part_b = {}
    for w, model in ((-1.0, "lcdm"), (-0.9, "wcdm")):
        res = camb_background(h0, ombh2, omch2, 0.06, w)
        om_ = omegas(res)
        om_in = om_["cdm"] + om_["baryon"] + om_["nu"]
        rdrag = float(res.get_derived_params()["rdrag"])
        cam = camb_observables(res, dr2, h, rdrag * h)
        f = m.fit_chi2_min(dr2.with_values(cam), model,
                           x0=(om_in, rdrag * h) if model == "lcdm" else (om_in, w, rdrag * h))
        truth = {"Om": om_in, "h_rd": rdrag * h} | ({"w": w} if model == "wcdm" else {})
        shift = {k: f["params"][k] - truth[k] for k in f["params"]}
        shift_pub = {k: shift[k] / pub[model][k] for k in pub[model]}
        prim = m.model_vector(dr2, model, f["x"])
        part_b[model] = {"camb_input": truth, "omegas_z0": om_, "rdrag_Mpc": rdrag, "primary_fit": f,
                         "shift": shift, "shift_in_published_sigma": shift_pub,
                         "camb_minus_primary_at_truth_in_DR2_sigma":
                             [float(v) for v in (cam - m.model_vector(
                                 dr2, model, [om_in, rdrag * h] if model == "lcdm" else [om_in, w, rdrag * h])) / sig],
                         "residual_at_primary_fit_in_DR2_sigma": [float(v) for v in (cam - prim) / sig]}
        print("(b)", model, "truth", truth, "fit", f["params"], "chi2", f["chi2"], "shift/pub_sigma", shift_pub,
              flush=True)
    out["b_primary_model_systematic_vs_camb_mnu0.06"] = part_b

    # (c) Planck 2018 best-fit r_drag
    res = camb_background(67.36, 0.02237, 0.1200, 0.06, -1.0)
    out["c_planck2018_rdrag_Mpc"] = float(res.get_derived_params()["rdrag"])
    print("(c) rdrag", out["c_planck2018_rdrag_Mpc"])
    path = m.RESULTS / "camb_crosscheck.json"
    path.write_text(json.dumps(out, indent=1))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

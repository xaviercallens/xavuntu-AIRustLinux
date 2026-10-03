"""Reproduce the amendment-1 positive-control anchor (CAMB 147.1027 / CLASS 147.0971 Mpc).

Run with /mnt/disks/disk-socrateai-local-1/venv-cosmo/bin/python (camb 2.0.4, classy 3.3.4).

Fix-round response to the referee's major issue: the amendment's anchor was produced at the
Planck 2018 Table 2 TT,TE,EE+lowE+lensing *marginalised means* (H0 = 67.36, omega_b = 0.02237,
omega_c = 0.1200; arXiv:1807.06209 Table 2, same as the Table 1 'Plik [1]' column), with
N_eff = 3.044 and one massive 0.06 eV neutrino. This script evaluates CAMB and CLASS there and,
for contrast, at the Table 1 Plik best fit with N_eff = 3.046 (the preregistration's anchor).

Writes results/bao_bbn_h0/anchor_reproduction.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import camb
import classy
from classy import Class

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as cm  # noqa: E402

TABLE2_LENSING_MEANS = {"H0": 67.36, "ombh2": 0.02237, "omch2": 0.1200}
TABLE1_BESTFIT = {"H0": 67.32, "ombh2": 0.022383, "omch2": 0.12011}


def camb_rdrag(H0: float, ombh2: float, omch2: float, nnu: float) -> float:
    p = camb.set_params(H0=H0, ombh2=ombh2, omch2=omch2, mnu=0.06, nnu=nnu, num_massive_neutrinos=1,
                        tau=0.0544, As=2.1e-9, ns=0.9649)
    return float(camb.get_background(p, no_thermo=False).get_derived_params()["rdrag"])


def class_rsdrag(H0: float, ombh2: float, omch2: float, n_ur: float) -> tuple[float, float]:
    c = Class()
    c.set({"omega_b": ombh2, "omega_cdm": omch2, "h": H0 / 100.0, "T_cmb": cm.T_CMB, "N_ur": n_ur,
           "N_ncdm": 1, "m_ncdm": 0.06})
    c.compute(level=["thermodynamics"])
    rd, neff = float(c.rs_drag()), float(c.Neff())
    c.struct_cleanup()
    c.empty()
    return rd, neff


def main() -> int:
    t2 = TABLE2_LENSING_MEANS
    t1 = TABLE1_BESTFIT
    rows: list[dict[str, object]] = []
    r = camb_rdrag(t2["H0"], t2["ombh2"], t2["omch2"], 3.044)
    rows.append({"code": "CAMB " + camb.__version__, "inputs": "Planck 2018 Table 2 TT,TE,EE+lowE+lensing means",
                 **t2, "nnu": 3.044, "rdrag": r, "amendment_value": 147.1027, "diff": r - 147.1027})
    for n_ur in (2.0328, 2.0308):
        rc, neff = class_rsdrag(t2["H0"], t2["ombh2"], t2["omch2"], n_ur)
        rows.append({"code": "CLASS " + classy.__version__, "inputs": "Planck 2018 Table 2 TT,TE,EE+lowE+lensing means",
                     **t2, "N_ur": n_ur, "class_Neff": neff, "rs_drag": rc, "amendment_value": 147.0971,
                     "diff": rc - 147.0971})
    rb = camb_rdrag(t1["H0"], t1["ombh2"], t1["omch2"], 3.046)
    rows.append({"code": "CAMB " + camb.__version__, "inputs": "Planck 2018 Table 1 Plik best fit (preregistration anchor)",
                 **t1, "nnu": 3.046, "rdrag": rb, "published": 147.049, "diff": rb - 147.049})
    out = {
        "script": "scripts/bao_bbn_h0/anchor_reproduce.py",
        "rows": rows,
        "published_rdrag_planck2018": {
            "value": "147.09 +- 0.26 Mpc",
            "source": "arXiv:1807.06209 Table 1 (r_drag row, 'Plik [1]' 68% column; best fit 147.049) and "
                      "Table 2 (TT,TE,EE+lowE+lensing column); quoted in arXiv:2404.03002 text above eq. (4.3)",
        },
        "note": "The amendment's CAMB 147.1027 and CLASS 147.0971 anchors are reproduced at the Planck 2018 "
                "Table 2 TT,TE,EE+lowE+lensing marginalised means with N_eff = 3.044 and one massive 0.06 eV "
                "neutrino (reproduction first reported by the referee, re-run here). They are point evaluations "
                "at the posterior means, so they are not expected to equal the posterior mean 147.09 exactly. "
                "The CLASS 147.0971 value needs N_ur = 2.0328, for which CLASS itself reports N_eff = 3.046, not "
                "3.044; with N_ur = 2.0308 (CLASS N_eff = 3.044, the setting used in rd_camb_table.py) CLASS gives "
                "147.1071, i.e. +3e-5 fractional from CAMB at matched N_eff.",
    }
    for row in rows:
        print(json.dumps(row), flush=True)
    (cm.RESULTS / "anchor_reproduction.json").write_text(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Real figure from the actual fit result -- data points with error bars
(from the diagonal of the real covariance) vs the best-fit model curve."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import fit_desi_bao as fb
import matplotlib.pyplot as plt
import numpy as np


def main() -> int:
    zs, vals, kinds, cov = fb.load_data()
    result = json.loads(Path("results/bao_flcdm/desi_dr1_flcdm_fit.json").read_text())
    fit = result["fit_astropy_H0trick"]
    om, rdh = fit["Om_m"], fit["rd_h_Mpc"]
    errs = np.sqrt(np.diag(cov))

    z_dense = np.linspace(0.0, 2.4, 200)
    zs_arr = np.array(zs)

    fig, ax = plt.subplots(1, 1, figsize=(7, 5))
    dm_mask = [k == "DM_over_rs" for k in kinds]
    dh_mask = [k == "DH_over_rs" for k in kinds]
    dv_mask = [k == "DV_over_rs" for k in kinds]

    ax.errorbar(zs_arr[dm_mask], np.array(vals)[dm_mask], yerr=errs[dm_mask],
                fmt="o", color="#1a6fa8", label=r"$D_M/r_d$ (data)", capsize=3)
    ax.errorbar(zs_arr[dh_mask], np.array(vals)[dh_mask], yerr=errs[dh_mask],
                fmt="s", color="#c1440e", label=r"$D_H/r_d$ (data)", capsize=3)
    ax.errorbar(zs_arr[dv_mask], np.array(vals)[dv_mask], yerr=errs[dv_mask],
                fmt="^", color="#2e7d4f", label=r"$D_V/r_d$ (data)", capsize=3)

    dm_model = [fb.comoving_distance_h100(z, om) / rdh for z in z_dense]
    dh_model = [fb.C_KM_S / (100 * fb.e_of_z(z, om) * rdh) for z in z_dense]
    ax.plot(z_dense, dm_model, "-", color="#1a6fa8", alpha=0.6, lw=1.5,
            label=rf"best fit $D_M/r_d$ ($\Omega_m$={om:.3f})")
    ax.plot(z_dense, dh_model, "-", color="#c1440e", alpha=0.6, lw=1.5,
            label=r"best fit $D_H/r_d$")

    ax.set_xlabel("redshift $z$")
    ax.set_ylabel("distance / $r_d$")
    ax.set_title(f"DESI DR1 BAO: flat-$\\Lambda$CDM fit ($\\chi^2$/dof = {fit['chi2_per_dof']:.2f})")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = Path("results/bao_flcdm/desi_dr1_flcdm_fit.pdf")
    fig.savefig(out)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

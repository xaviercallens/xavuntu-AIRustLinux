"""Pre-registration helpers for the bao_bbn_h0 problem (NO data fitting here).

1. sha256 of every data file the fit will read.
2. Pure-formula comparison of two published r_d approximations over the
   prior box, used to set the pre-declared fitting-formula systematic:
   - Aubourg et al. 2015 (arXiv:1411.1074) eq. 16 (CAMB convention,
     stated accuracy 0.021% for N_eff=3.046, sum m_nu<0.6 eV, omega_b and
     omega_cb within 3 sigma of Planck 2013/2015 values);
   - DESI DR2 (arXiv:2503.14738) eq. 2 power law (no accuracy stated there).
   No BAO data are touched by part 2.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

DATA = Path("/mnt/disks/disk-socrateai-local-1/dualscale-data-r3/desi_sdss_bao")
FILES = [
    DATA / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_mean.txt",
    DATA / "desi_bao_dr2" / "desi_gaussian_bao_ALL_GCcomb_cov.txt",
    DATA / "desi_2024_gaussian_bao_ALL_GCcomb_mean.txt",
    DATA / "desi_2024_gaussian_bao_ALL_GCcomb_cov.txt",
    DATA / "README.md",
]

OMEGA_NU_PER_EV = 0.0107  # Aubourg+2015 text below eq. 16: omega_nu = 0.0107 (sum m_nu / 1 eV)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rd_aubourg16(omega_cb: np.ndarray, omega_b: np.ndarray, mnu_ev: float) -> np.ndarray:
    """Aubourg et al. 2015 eq. 16 [Mpc]."""
    omega_nu = OMEGA_NU_PER_EV * mnu_ev
    return 55.154 * np.exp(-72.3 * (omega_nu + 0.0006) ** 2) / (
        omega_cb ** 0.25351 * omega_b ** 0.12807
    )


def rd_desi_eq2(omega_bc: np.ndarray, omega_b: np.ndarray, neff: float) -> np.ndarray:
    """DESI DR2 eq. 2 power law [Mpc]."""
    return 147.05 * (omega_b / 0.02236) ** -0.13 * (omega_bc / 0.1432) ** -0.23 * (neff / 3.04) ** -0.1


def main() -> int:
    hashes = {str(p): sha256(p) for p in FILES}
    mnu = 0.06
    neff = 3.044
    wb = np.linspace(0.02218 - 3 * 0.00055, 0.02218 + 3 * 0.00055, 61)
    wcb = np.linspace(0.130, 0.155, 101)
    WB, WCB = np.meshgrid(wb, wcb)
    omega_nu = OMEGA_NU_PER_EV * mnu
    # CONVENTION: eq. 2's pivots (0.02236, 0.1432, 147.05) are the Planck 2018 Table 2
    # TT,TE,EE+lowE column, where 0.1432 is Omega_m h^2 INCLUDING the 0.06 eV nu. Tested at the
    # Planck 2018 Table 1 best fit (Omega_m h^2 = 0.14314 listed there): feeding the nu-inclusive
    # value gives -0.016% vs CAMB, the nu-exclusive value +0.088%. So eq. 2 is fed
    # omega_m = omega_cb + omega_nu; eq. 16 is fed omega_cb (nu excluded), as Aubourg defines.
    ra = rd_aubourg16(WCB, WB, mnu)
    rp = rd_desi_eq2(WCB + omega_nu, WB, neff)
    frac = (rp - ra) / ra
    fid = {
        "desi_eq2_at_planck2018_table2_pivot_incl_nu": float(rd_desi_eq2(np.array(0.1432), np.array(0.02236), neff)),
        "aubourg16_at_planck2018_table2_pivot_omega_cb_excl_nu": float(rd_aubourg16(np.array(0.1432 - omega_nu), np.array(0.02236), mnu)),
        "planck2018_table2_rdrag_TTTEEE_lowE": 147.05,
    }
    # --- Anchor A: Planck 2018 (arXiv:1807.06209) Table 1, Plik BEST FIT (a single CAMB model):
    #     omega_b=0.022383, omega_c=0.12011, Omega_m h^2=0.14314 (incl nu), r_drag=147.049 Mpc.
    wb_bf, wc_bf, wm_bf, rd_camb_bf = 0.022383, 0.12011, 0.14314, 147.049
    ra_bf = float(rd_aubourg16(np.array(wb_bf + wc_bf), np.array(wb_bf), mnu))
    rp_bf = float(rd_desi_eq2(np.array(wm_bf), np.array(wb_bf), neff))
    # --- Anchor B: DESI DR2 published centre (arXiv:2503.14738 Table V / eq. 17, 19):
    #     DESI+BBN: Om=0.2977, H0=68.51, omega_b = BBN prior centre 0.02218 (eq. 14; posterior
    #     omega_b not quoted, prior centre used as proxy). BAO-only hr_d = 101.54 +- 0.73 Mpc.
    om_d, h_d, wb_d = 0.2977, 0.6851, 0.02218
    wcb_d = om_d * h_d ** 2 - omega_nu  # DESI Omega_m includes massive nu (DR1 Table 2 caption)
    wbc_d_eq2 = om_d * h_d ** 2  # eq.2 pivot convention: nu-inclusive (see CONVENTION above)
    ra_d = float(rd_aubourg16(np.array(wcb_d), np.array(wb_d), mnu))
    rp_d = float(rd_desi_eq2(np.array(wbc_d_eq2), np.array(wb_d), neff))
    # --- Validity window of Aubourg eq. 16: "within 3 sigma of values derived by Planck".
    #     Proxy: Planck 2018 Table 2 TT,TE,EE+lowE: omega_b=0.02236+-0.00015, Omega_m h^2=0.1432+-0.0013
    #     (Aubourg used Planck 2013 values; those uncertainties were NOT fetched -> proxy only).
    pl_wb, pl_wb_s = 0.02236, 0.00015
    pl_wcb, pl_wcb_s = 0.1432 - omega_nu, 0.0013
    bbn_lo, bbn_hi = 0.02218 - 2 * 0.00055, 0.02218 + 2 * 0.00055
    validity = {
        "planck2018_proxy_window_omega_b": [pl_wb - 3 * pl_wb_s, pl_wb + 3 * pl_wb_s],
        "planck2018_proxy_window_omega_cb": [pl_wcb - 3 * pl_wcb_s, pl_wcb + 3 * pl_wcb_s],
        "bbn_prior_2sigma_omega_b": [bbn_lo, bbn_hi],
        "bbn_2sigma_inside_window": bool(bbn_lo >= pl_wb - 3 * pl_wb_s and bbn_hi <= pl_wb + 3 * pl_wb_s),
        "desi_bbn_centre_omega_cb": wcb_d,
        "desi_bbn_centre_omega_cb_in_sigma_from_planck": (wcb_d - pl_wcb) / pl_wcb_s,
        "desi_bbn_centre_inside_window": bool(abs(wcb_d - pl_wcb) <= 3 * pl_wcb_s),
    }
    anchors = {
        "planck2018_bestfit_camb_rdrag": rd_camb_bf,
        "aubourg16_at_planck2018_bestfit": ra_bf,
        "aubourg16_frac_err_vs_camb": (ra_bf - rd_camb_bf) / rd_camb_bf,
        "desi_eq2_at_planck2018_bestfit": rp_bf,
        "desi_eq2_frac_err_vs_camb": (rp_bf - rd_camb_bf) / rd_camb_bf,
        "desi_centre_rd_aubourg16": ra_d,
        "desi_centre_hrd_aubourg16": h_d * ra_d,
        "desi_centre_rd_eq2": rp_d,
        "desi_centre_hrd_eq2": h_d * rp_d,
        "desi_dr2_bao_only_hrd": 101.54,
        "desi_dr2_bao_only_hrd_sigma": 0.73,
        "hrd_offset_aubourg16_frac": (h_d * ra_d - 101.54) / 101.54,
        "hrd_offset_eq2_frac": (h_d * rp_d - 101.54) / 101.54,
    }
    out = {
        "sha256": hashes,
        "validity_check_aubourg16": validity,
        "camb_anchors": anchors,
        "formula_comparison_box": {
            "omega_b_range": [float(wb[0]), float(wb[-1])],
            "omega_cb_range": [float(wcb[0]), float(wcb[-1])],
            "frac_diff_eq2_minus_eq16_min": float(frac.min()),
            "frac_diff_eq2_minus_eq16_max": float(frac.max()),
            "frac_diff_max_abs": float(np.abs(frac).max()),
            **fid,
        },
    }
    json.dump(out, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

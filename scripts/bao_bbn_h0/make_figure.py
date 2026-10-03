"""Figure for bao_bbn_h0: results/bao_bbn_h0/bao_bbn_h0_fit.pdf (reads fit.json + disk-2 chains)."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import common as cm  # noqa: E402

COL = {"primary": "#1f5fa8", "secondary": "#d9822b"}


def hpd_levels(h: np.ndarray, fracs: tuple[float, ...]) -> list[float]:
    s = np.sort(h.ravel())[::-1]
    c = np.cumsum(s) / s.sum()
    return sorted(float(s[np.searchsorted(c, f)]) for f in fracs)


def contour(ax: plt.Axes, x: np.ndarray, y: np.ndarray, color: str, label: str) -> None:
    h, xe, ye = np.histogram2d(x, y, bins=60)
    from scipy.ndimage import gaussian_filter

    h = gaussian_filter(h, 1.2)
    xc, yc = 0.5 * (xe[1:] + xe[:-1]), 0.5 * (ye[1:] + ye[:-1])
    lv = hpd_levels(h, (0.954, 0.683))
    ax.contour(xc, yc, h.T, levels=lv + [h.max() * 1.01], colors=[color, color], linewidths=[1.0, 1.8])
    ax.plot([], [], color=color, label=label)


def main() -> int:
    fit = json.loads((cm.RESULTS / "fit.json").read_text())
    ptr = json.loads((cm.RESULTS / "chains_pointer.json").read_text())["chains"]
    fig, axs = plt.subplots(1, 3, figsize=(14, 4.4))
    ax = axs[0]
    for an in ("primary", "secondary"):
        s = np.load(ptr[f"T1_DR2_{an}"]["path"])
        m = fit[an]["T1_DR2"]["chain"]["mean"]
        contour(ax, s[:, 2], s[:, 0], COL[an], f"{an}: H0={m['H0']:.2f}, Om={m['Omega_m']:.4f}")
    ax.errorbar([0.2977], [68.51], xerr=[0.0086], yerr=[0.58], fmt="ks", ms=4, capsize=3, label="DESI DR2 BAO+BBN (target)")
    ax.set_xlabel(r"$\Omega_m$")
    ax.set_ylabel(r"$H_0$ [km/s/Mpc]")
    ax.set_title("DR2 BAO + BBN (68/95%)")
    ax.legend(fontsize=7, loc="upper right")

    ax = axs[1]
    for an in ("primary", "secondary"):
        p = fit[an]["T1_DR2"]["profile_H0"]
        ax.plot(p["grid"], p["delta_chi2"], color=COL[an], label=f"{an} profile")
    ax.axvspan(68.51 - 0.15, 68.51 + 0.15, color="0.6", alpha=0.35, label="strict tol. +-0.15")
    ax.axvspan(68.51 - 0.33, 68.51 + 0.33, color="0.8", alpha=0.3, label="soft tol. +-0.33")
    ax.axvline(68.51, color="k", lw=0.8)
    ax.axhline(1.0, color="k", ls=":", lw=0.8)
    ax.set_ylim(0, 6)
    ax.set_xlabel(r"$H_0$ [km/s/Mpc]")
    ax.set_ylabel(r"$\Delta\chi^2_{\rm profile}$")
    ax.set_title("H0 profile likelihood (DR2+BBN)")
    ax.legend(fontsize=7)

    ax = axs[2]
    s = np.load(ptr["gate_DESI_DR2"]["path"])
    m = fit["G1"]["chain"]["mean"]
    contour(ax, s[:, 0], s[:, 1], "#3a8a3a", f"gate G1: Om={m['Omega_m']:.4f}, hrd={m['hrd']:.2f}")
    ax.errorbar([0.2975], [101.54], xerr=[0.0086], yerr=[0.73], fmt="ks", ms=4, capsize=3, label="DESI DR2 BAO-only")
    ax.set_xlabel(r"$\Omega_m$")
    ax.set_ylabel(r"$h\,r_d$ [Mpc]")
    ax.set_title("Gate G1: DR2 BAO only")
    ax.legend(fontsize=7)
    fig.tight_layout()
    out = cm.RESULTS / "bao_bbn_h0_fit.pdf"
    fig.savefig(out)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

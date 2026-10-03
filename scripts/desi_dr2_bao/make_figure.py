#!/usr/bin/env python3
"""Figure for desi_dr2_bao: posterior contours from the regenerated emcee chains.

Left: flat LCDM (Om, h r_d), DR1 vs DR2 (68% / 95%). Right: flat wCDM (Om, w), DR2 and DR1.
Published DESI posterior means (the preregistered targets) are marked with crosses.
Writes results/desi_dr2_bao/desi_dr2_bao_posteriors.pdf.
    /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python -B scripts/desi_dr2_bao/make_figure.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.ndimage import gaussian_filter  # noqa: E402

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dr2_model as m  # noqa: E402

DR2_COLOR = "#2a78d6"  # reference palette slot 1
DR1_COLOR = "#eb6834"  # reference palette slot 2
INK = "#0b0b0b"
MUTED = "#52514e"


def levels_for(h: np.ndarray, fracs: tuple[float, ...]) -> list[float]:
    flat = np.sort(h.ravel())[::-1]
    cum = np.cumsum(flat) / flat.sum()
    return sorted(float(flat[np.searchsorted(cum, f)]) for f in fracs)


def contour(ax: plt.Axes, x: np.ndarray, y: np.ndarray, color: str, ls: str, label: str) -> None:
    h, xe, ye = np.histogram2d(x, y, bins=80)
    h = gaussian_filter(h, 1.2)
    xc, yc = 0.5 * (xe[1:] + xe[:-1]), 0.5 * (ye[1:] + ye[:-1])
    lv = levels_for(h, (0.954, 0.683))
    ax.contour(xc, yc, h.T, levels=lv, colors=color, linestyles=ls, linewidths=2.0)
    ax.plot([], [], color=color, ls=ls, lw=2.0, label=label)


def load(name: str) -> tuple[np.ndarray, list[str]]:
    d = np.load(m.RESULTS / "chains" / f"{name}.npz")
    return d["samples"], [str(s) for s in d["names"]]


def main() -> int:
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2))
    ax = axes[0]
    for name, col, ls, lab in (("DR1_LCDM", DR1_COLOR, "--", "DR1 (this work)"),
                               ("DR2_LCDM", DR2_COLOR, "-", "DR2 (this work)")):
        s, _ = load(name)
        contour(ax, s[:, 0], s[:, 1], col, ls, lab)
    ax.plot(0.2975, 101.54, "x", color=INK, ms=9, mew=2, label="DESI DR2 published mean")
    ax.plot(0.295, 101.8, "+", color=MUTED, ms=10, mew=2, label="DESI DR1 published mean")
    ax.set_xlabel(r"$\Omega_m$")
    ax.set_ylabel(r"$h\,r_d$ [Mpc]")
    ax.set_title("Flat ΛCDM, BAO only (68%, 95%)", color=INK, fontsize=11)
    ax.set_xlim(0.25, 0.345)
    ax.legend(fontsize=8, frameon=False, loc="lower left")

    ax = axes[1]
    for name, col, ls, lab in (("DR1_wCDM", DR1_COLOR, "--", "DR1 (this work)"),
                               ("DR2_wCDM", DR2_COLOR, "-", "DR2 (this work)")):
        s, _ = load(name)
        contour(ax, s[:, 0], s[:, 1], col, ls, lab)
    ax.plot(0.2969, -0.916, "x", color=INK, ms=9, mew=2, label="DESI DR2 published mean")
    ax.plot(0.293, -0.99, "+", color=MUTED, ms=10, mew=2, label="DESI DR1 published mean")
    ax.axhline(-1.0, color=MUTED, lw=0.8, ls=":")
    ax.set_xlabel(r"$\Omega_m$")
    ax.set_ylabel(r"$w$")
    ax.set_title("Flat wCDM, BAO only (68%, 95%)", color=INK, fontsize=11)
    ax.set_xlim(0.25, 0.345)
    ax.set_ylim(-1.75, -0.55)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    for a in axes:
        a.grid(color="#e6e5e1", lw=0.6)
        a.set_axisbelow(True)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    fig.tight_layout()
    path = m.RESULTS / "desi_dr2_bao_posteriors.pdf"
    fig.savefig(path, metadata={"CreationDate": None})
    fig.savefig("/tmp/desi_dr2_bao_posteriors.png", dpi=110)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""N4: POST-HOC wrong-convention negative control (added in the referee fix round; NOT preregistered,
NOT part of the verdict's `controls` condition).

Purpose: the referee noted N1/N2 would fail for any pipeline. N4 asks whether the preregistered strict
tolerance (0.15 km/s/Mpc) can detect a SUBTLE, realistic bookkeeping error: the primary CAMB r_d evaluated
with omega_cdm = Omega_m h^2 - omega_b, i.e. forgetting to subtract the massive-neutrino density
(Omega_m is neutrino-inclusive in this pipeline). The same DR2 BAO+BBN likelihood is maximised (MAP) with
the correct and the wrong r_d.

Modes:
  declare  writes results/bao_bbn_h0/controls/N4_expectation.json (must exist before `run`; never rewritten)
  run      writes results/bao_bbn_h0/controls/N4.json

Run: cd scripts/bao_bbn_h0 && /mnt/disks/disk-socrateai-local-1/venv-pta/bin/python control_n4.py declare|run
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import numpy as np

import common as cm

EXP = cm.RESULTS / "controls" / "N4_expectation.json"
OUT = cm.RESULTS / "controls" / "N4.json"
X0 = np.array([68.5, 0.02218, 0.30])


def declare() -> int:
    if EXP.exists():
        print("expectation already declared; not rewritten:", EXP)
        return 0
    cm.write_json(EXP, {
        "control": "N4 wrong neutrino bookkeeping in the primary CAMB r_d (omega_nu not subtracted from omega_cdm)",
        "declared_utc": datetime.now(timezone.utc).isoformat(),
        "status": "post-hoc (referee fix round), not preregistered, not in the verdict's controls condition",
        "expectation": "omega_cdm rises by omega_nu ~ 6.4e-4 (~0.5%), r_d falls by ~0.13%, and with h r_d fixed by BAO "
                       "H0 rises by ~0.13%/0.49 ~ 0.27% ~ 0.2 km/s/Mpc (rough, before running)",
        "behaves_if": "|H0_MAP(wrong) - H0_MAP(correct)| > 0.15 km/s/Mpc (the preregistered strict tolerance), i.e. the "
                      "tolerance would catch this error; otherwise the control reports that it would NOT be caught",
    })
    print("declared", EXP)
    return 0


def run() -> int:
    if not EXP.exists():
        raise SystemExit("declare the expectation first")
    d = cm.load_dr2()
    x_ok, c2_ok = cm.fit_map(cm.make_logpost(d, rd_fn="camb"), X0)
    correct = cm.rd_camb

    def wrong(h: np.ndarray, om: np.ndarray, wb: np.ndarray) -> np.ndarray:
        correct(np.atleast_1d(h), np.atleast_1d(om), np.atleast_1d(wb))  # ensure table loaded
        tab = cm._RD_CAMB
        assert tab is not None
        wc = np.asarray(om) * np.asarray(h) ** 2 - np.asarray(wb)
        return tab(wb, wc, h)

    cm.rd_camb = wrong
    try:
        x_bad, c2_bad = cm.fit_map(cm.make_logpost(d, rd_fn="camb"), X0)
    finally:
        cm.rd_camb = correct
    shift = float(x_bad[0] - x_ok[0])
    exp = json.loads(EXP.read_text())
    res = {"expectation_file": str(EXP), "behaves_if": exp["behaves_if"],
           "map_correct": dict(zip(["H0", "omega_b", "Omega_m"], x_ok.tolist())), "chi2_correct": c2_ok,
           "map_wrong": dict(zip(["H0", "omega_b", "Omega_m"], x_bad.tolist())), "chi2_wrong": c2_bad,
           "dH0_wrong_minus_correct": shift, "strict_tolerance": 0.15,
           "control_behaves": bool(abs(shift) > 0.15),
           "delta_chi2_wrong_minus_correct": float(c2_bad - c2_ok)}
    cm.write_json(OUT, res)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(declare() if sys.argv[1:] == ["declare"] else run())

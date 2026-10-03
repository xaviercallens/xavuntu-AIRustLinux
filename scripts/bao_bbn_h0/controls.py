"""Positive and negative controls for bao_bbn_h0 (preregistered P1, P2, P4, N1, N2), run for
both analyses of amendment 1:
  primary   : rd_fn="camb"  (exact CAMB r_drag table, scripts/bao_bbn_h0/rd_camb_table.py)
  secondary : rd_fn="aub16" (preregistered Aubourg+2015 eq. 16 fitting formula)

P3 (gate G1) and N3 (no BBN prior) need the real-data machinery and run in fit_real.py.

Usage: python controls.py {p4|p1|p2|n1n2|all} {primary|secondary}
Each control writes results/bao_bbn_h0/controls/<id>_<analysis>.json when it finishes.

Pre-run clarification (logged before P2 was first run, see P2_NOTE): the prereg draws the
P2 mocks from N(model, C_DR2) only. The BBN prior acts as a measurement of omega_b;
with it held fixed at 0.02218 while only the BAO vector scatters, the H0 pull width
would be below 1 by construction. Each mock therefore also draws its own BBN centre
omega_b,obs ~ N(0.02218, 0.00055) (prior-as-data), truth stays at 0.02218.
"""
from __future__ import annotations

import sys
import time

import numpy as np
from scipy.stats import chi2 as chi2_dist

import common as cm

OUT = cm.RESULTS / "controls"
TRUTH = np.array([68.0, 0.02218, 0.300])
NAMES = ["H0", "omega_b", "Omega_m"]
SCALE = np.array([0.3, 0.0003, 0.005])
STEPS = np.array([0.02, 2e-6, 2e-5])
RDFN = {"primary": "camb", "secondary": "aub16"}
P2_NOTE = (
    "Pre-run clarification (written before P2 first ran): each mock draws the BBN centre "
    "omega_b,obs ~ N(0.02218, 0.00055) in addition to the BAO vector ~ N(model, C_DR2); "
    "truth omega_b = 0.02218. Without this the pull width is < 1 by construction."
)


def p4(analysis: str) -> dict[str, object]:
    """Predictor cross-check: astropy vs manual (GL-64 and quad) on DR2 and DR1 observables.
    r_d enters both predictors identically (eq. 16), so P4 tests the background only and is
    shared by both analyses; the CAMB-background distance check is in rd_camb_validation.json."""
    pts = [(68.0, 0.02218, 0.30), (62.0, 0.0205, 0.35), (74.0, 0.0240, 0.26)]
    rows = []
    worst = 0.0
    for d in (cm.load_dr2(), cm.load_dr1()):
        for h0, wb, om in pts:
            a = cm.predict_astropy(d, h0, wb, om)
            m = cm.predict_manual_vec(d, np.array([h0]), np.array([wb]), np.array([om]))[0]
            q = cm.predict_manual_quad(d, h0, wb, om)
            fam = float(np.max(np.abs(m / a - 1.0)))
            fqm = float(np.max(np.abs(q / m - 1.0)))
            worst = max(worst, fam)
            _, onu = cm.astropy_cosmo(h0, om)
            rows.append({"data": d.name, "H0": h0, "omega_b": wb, "Omega_m": om,
                         "max_frac_astropy_vs_manualGL": fam, "max_frac_quad_vs_GL": fqm,
                         "astropy_Onu_massive": onu, "Onu_massive_via_aubourg_0.0107": cm.OMEGA_NU_AUBOURG / (h0 / 100) ** 2})
    res = {"id": "P4", "analysis": "shared (background only)", "rows": rows, "max_frac_diff": worst,
           "threshold": 1e-4, "passed": worst < 1e-4}
    cm.write_json(OUT / "P4.json", res)
    return res


def p1(analysis: str) -> dict[str, object]:
    rd_fn = RDFN[analysis]
    d = cm.load_dr2()
    mock = cm.predict_manual_vec(d, TRUTH[:1], TRUTH[1:2], TRUTH[2:], rd_fn=rd_fn)[0]
    lp = cm.make_logpost(d, vals=mock, rd_fn=rd_fn)
    xmap, c2 = cm.fit_map(lp, TRUTH * 1.01)
    ch = cm.run_mcmc(lp, xmap, SCALE * 0.2, seed=101)
    dh0 = float(ch.mean[0] - TRUTH[0])
    dom = float(ch.mean[2] - TRUTH[2])
    res = {"id": "P1", "analysis": analysis, "rd_fn": rd_fn, "truth": dict(zip(NAMES, TRUTH.tolist())),
           "map": dict(zip(NAMES, xmap.tolist())), "chi2_map": c2, "chain": cm.chain_summary(ch, NAMES),
           "dH0": dh0, "dOm": dom, "pass_if": "|dH0|<=0.1 and |dOm|<=0.002",
           "passed": bool(abs(dh0) <= 0.1 and abs(dom) <= 0.002)}
    cm.write_json(OUT / f"P1_{analysis}.json", res)
    return res


def p2(analysis: str, n_mocks: int = 100) -> dict[str, object]:
    rd_fn = RDFN[analysis]
    d = cm.load_dr2()
    rng = np.random.default_rng(20260927)
    mean_model = cm.predict_manual_vec(d, TRUTH[:1], TRUTH[1:2], TRUTH[2:], rd_fn=rd_fn)[0]
    L = np.linalg.cholesky(d.cov)
    rows = []
    for i in range(n_mocks):
        vals = mean_model + L @ rng.standard_normal(len(mean_model))
        wb_obs = cm.BBN_MEAN + cm.BBN_SIGMA * rng.standard_normal()
        lp = cm.make_logpost(d, vals=vals, bbn=(wb_obs, cm.BBN_SIGMA), rd_fn=rd_fn)
        xmap, c2 = cm.fit_map(lp, TRUTH)
        cov = cm.laplace_cov(lp, xmap, STEPS)
        sig = np.sqrt(np.diag(cov))
        rows.append({"i": i, "map": xmap.tolist(), "sigma": sig.tolist(), "chi2": c2, "wb_obs": wb_obs,
                     "pull_H0": float((xmap[0] - TRUTH[0]) / sig[0]),
                     "pull_Om": float((xmap[2] - TRUTH[2]) / sig[2])})
    ph = np.array([r["pull_H0"] for r in rows])
    po = np.array([r["pull_Om"] for r in rows])
    c2s = np.array([r["chi2"] for r in rows])
    res = {"id": "P2", "analysis": analysis, "rd_fn": rd_fn, "note": P2_NOTE, "n_mocks": n_mocks, "seed": 20260927,
           "pull_H0_mean": float(ph.mean()), "pull_H0_std": float(ph.std(ddof=1)),
           "pull_Om_mean": float(po.mean()), "pull_Om_std": float(po.std(ddof=1)),
           "chi2_mean": float(c2s.mean()), "chi2_expected_dof": 11,
           "pass_if": "mean pull H0 in [-0.2,0.2] and std in [0.8,1.2]",
           "passed": bool(abs(ph.mean()) <= 0.2 and 0.8 <= ph.std(ddof=1) <= 1.2), "rows": rows}
    cm.write_json(OUT / f"P2_{analysis}.json", res)
    return res


def n1n2(analysis: str) -> dict[str, object]:
    rd_fn = RDFN[analysis]
    d = cm.load_dr2()
    # real data reference fit (needed for 'real data PTE > 0.01' clause of N1)
    lp_real = cm.make_logpost(d, rd_fn=rd_fn)
    x_real, c2_real = cm.fit_map(lp_real, TRUTH)
    pte_real = float(chi2_dist.sf(c2_real, 11))
    # N1: scrambled data vector
    rng = np.random.default_rng(20260927)
    perm = rng.permutation(len(d.vals))
    scr = d.vals[perm]
    lp_scr = cm.make_logpost(d, vals=scr, rd_fn=rd_fn)
    best: tuple[np.ndarray | None, float] = (None, np.inf)
    for x0 in ([68.0, 0.02218, 0.3], [50.0, 0.02218, 0.5], [85.0, 0.02218, 0.15], [30.0, 0.02218, 0.8]):
        x, c2 = cm.fit_map(lp_scr, np.array(x0))
        if c2 < best[1]:
            best = (x, c2)
    pte_scr = float(chi2_dist.sf(best[1], 11))
    n1 = {"id": "N1", "analysis": analysis, "rd_fn": rd_fn, "seed": 20260927, "permutation": perm.tolist(),
          "map": best[0].tolist(), "chi2": best[1], "dof": 11, "pte": pte_scr, "real_map": x_real.tolist(),
          "real_chi2": c2_real, "real_pte": pte_real, "control_behaves": bool(pte_scr < 1e-3 and pte_real > 0.01)}

    # N2: Einstein-de Sitter (Omega_m = 1, matter only), H0 and omega_b free, BBN prior on
    def lp_eds(theta: np.ndarray) -> np.ndarray:
        theta = np.atleast_2d(theta)
        h0, wb = theta[:, 0], theta[:, 1]
        ok = (h0 > cm.PRIOR_H0[0]) & (h0 < cm.PRIOR_H0[1]) & (wb > cm.PRIOR_WB[0]) & (wb < cm.PRIOR_WB[1])
        out = np.full(theta.shape[0], -np.inf)
        if not np.any(ok):
            return out
        m = cm.predict_manual_vec(d, h0[ok], wb[ok], np.ones(int(ok.sum())), rd_fn=rd_fn, radiation=False)
        c2 = cm.chi2_vec(d, d.vals, m) + ((wb[ok] - cm.BBN_MEAN) / cm.BBN_SIGMA) ** 2
        out[ok] = np.where(np.isfinite(c2), -0.5 * c2, -np.inf)
        return out

    best2: tuple[np.ndarray | None, float] = (None, np.inf)
    for x0 in ([68.0, 0.02218], [40.0, 0.02218], [90.0, 0.02218], [55.0, 0.03]):
        x, c2 = cm.fit_map(lp_eds, np.array(x0))
        if c2 < best2[1]:
            best2 = (x, c2)
    pte_eds = float(chi2_dist.sf(best2[1], 12))
    n2 = {"id": "N2", "analysis": analysis, "rd_fn": rd_fn,
          "map": {"H0": float(best2[0][0]), "omega_b": float(best2[0][1])}, "chi2": best2[1],
          "dof": 12, "pte": pte_eds, "control_behaves": bool(pte_eds < 1e-3)}
    cm.write_json(OUT / f"N1_{analysis}.json", n1)
    cm.write_json(OUT / f"N2_{analysis}.json", n2)
    return {"N1": n1, "N2": n2}


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    analysis = sys.argv[2] if len(sys.argv) > 2 else "primary"
    if analysis not in RDFN:
        raise SystemExit(f"analysis must be one of {list(RDFN)}")
    for name, fn in (("p4", p4), ("p1", p1), ("p2", p2), ("n1n2", n1n2)):
        if which in (name, "all"):
            t = time.time()
            r = fn(analysis)
            if name == "p1":
                slim = {k: r[k] for k in ("analysis", "truth", "map", "dH0", "dOm", "passed")} | {
                    "mean": r["chain"]["mean"], "std": r["chain"]["std"], "tau": r["chain"]["tau"],
                    "n_steps": r["chain"]["n_steps"], "ess": r["chain"]["ess"]}
            elif name == "n1n2":
                slim = {k: {kk: vv for kk, vv in v.items() if kk != "permutation"} for k, v in r.items()}
            else:
                slim = {k: v for k, v in r.items() if k != "rows"}
            print(name, analysis, f"({time.time() - t:.1f}s)", cm.json.dumps(slim, indent=1, default=float), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

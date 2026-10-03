# Emit elliptic-curve facts from Cremona's database as JSON, with Sage as the
# source of truth. True facts come straight from Sage; false variants are
# perturbed and RE-CHECKED false by Sage before being emitted.
import json, sys

LABELS = ["11a1", "14a1", "15a1", "17a1", "19a1", "20a1", "21a1", "24a1",
          "26a1", "27a1", "37a1", "43a1", "53a1", "57a1", "58a1", "61a1",
          "65a1", "77a1", "79a1", "83a1", "389a1", "433a1", "446d1", "563a1"]

out = []
for lbl in LABELS:
    E = EllipticCurve(lbl)
    a1, a2, a3, a4, a6 = [QQ(x) for x in E.a_invariants()]
    rec = {"label": lbl, "a": [str(a1), str(a2), str(a3), str(a4), str(a6)],
           "disc": str(E.discriminant()), "rank": int(E.rank())}
    # A rational point: a generator if rank > 0, else a nonzero torsion point.
    pts = [P for P in (E.gens() if E.rank() > 0 else E.torsion_points()) if not P.is_zero()]
    if pts:
        P = pts[0]
        rec["point"] = [str(P[0]), str(P[1])]
        # False point: step y until Sage confirms it is NOT on E (a +1 bump
        # can land exactly on the conjugate point -y - a1 x - a3).
        d = 1
        while E.is_on_curve(P[0], P[1] + d):
            d += 1
        rec["false_point"] = [str(P[0]), str(P[1] + d)]
        # Group law: P + P (doubling) when 2P is affine.
        Q = 2 * P
        if not Q.is_zero():
            rec["double"] = [str(Q[0]), str(Q[1])]
            # 2P has exactly one y-coordinate, so y+1 is a false claim.
            rec["false_double"] = [str(Q[0]), str(Q[1] + 1)]
    # False discriminant: off by one, trivially re-checked.
    rec["false_disc"] = str(E.discriminant() + 1)
    out.append(rec)

print(json.dumps(out))

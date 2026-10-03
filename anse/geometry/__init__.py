"""
ANSE Differential Geometry Module — Riemannian SDEs, Gauss–Bonnet, SO(3) integration.

Includes Riemannian trust-region Newton optimizer and Yoshida 4th-order symplectic
integrator derived from K3 PhD problems (v13.5.0).
"""

from anse.geometry.riemannian_sde_engine import (
    RiemannianSDEEngine,
    RiemannianSDEResult,
)
from anse.geometry.riemannian_trust_region import (
    TrustRegionResult,
    YoshidaResult,
    riemannian_trust_region_newton,
    yoshida4_integrate,
)

__all__ = [
    "RiemannianSDEEngine",
    "RiemannianSDEResult",
    "TrustRegionResult",
    "YoshidaResult",
    "riemannian_trust_region_newton",
    "yoshida4_integrate",
]

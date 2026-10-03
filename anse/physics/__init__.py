"""
ANSE Physics World Model Benchmark & Learning Module.

Includes K3 surface astrophysics modules derived from the 10 PhD-level
problems (v13.5.0): balanced metric, Eguchi-Hanson gluing, symplectic Kerr.
"""
from anse.physics.world_models import (
    PHYSICS_USE_CASES,
    PhysicsSimulationResult,
    PhysicsWorldModelBenchmark,
    run_physics_learning_loop,
)
from anse.physics.k3_balanced_metric import (
    DonaldsonResult,
    WeilPeterssonResult,
    TadpoleCancellationResult,
    PicardFuchsResult,
    compute_donaldson_balanced_metric,
    compute_weil_petersson_curvature,
    solve_g_flux_tadpole_lll,
    compute_picard_fuchs_period,
)
from anse.physics.eguchi_hanson_k3 import (
    EguchiHansonResult,
    compute_eguchi_hanson_c2_gluing,
)
from anse.physics.kerr_symplectic_projection import (
    SymplecticKerrResult,
    SymplecticProjectionKerrIntegrator,
    integrate_kerr_geodesic_symplectic,
)

__all__ = [
    # Core world models
    "PHYSICS_USE_CASES",
    "PhysicsSimulationResult",
    "PhysicsWorldModelBenchmark",
    "run_physics_learning_loop",
    # K3 balanced metric & moduli
    "DonaldsonResult",
    "WeilPeterssonResult",
    "TadpoleCancellationResult",
    "PicardFuchsResult",
    "compute_donaldson_balanced_metric",
    "compute_weil_petersson_curvature",
    "solve_g_flux_tadpole_lll",
    "compute_picard_fuchs_period",
    # K3 orbifold desingularization
    "EguchiHansonResult",
    "compute_eguchi_hanson_c2_gluing",
    # Symplectic Kerr geodesics
    "SymplecticKerrResult",
    "SymplecticProjectionKerrIntegrator",
    "integrate_kerr_geodesic_symplectic",
]

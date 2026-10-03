"""
PhD Problem Specification: K3 Surface in Theoretical Astrophysics.

Topic:
Attractor Geodesic Flow and Symplectic Energy Conservation in
K3-Compactified Extremal Astrophysical Black Holes with Donaldson Balanced Metrics.

Mathematical & Physical Invariants:
1. Cohomology & Topology:
   - Dim = 2 (complex), Dim_R = 4
   - Betti numbers: b_0=1, b_1=0, b_2=22, b_3=0, b_4=1
   - Hodge numbers: h^{2,0}=1, h^{1,1}=20, h^{0,2}=1
   - Euler characteristic: chi(K3) = 24
   - Signature: sigma = b_+ - b_- = 3 - 19 = -16
   - Unimodular even lattice: Gamma^{3,19} = 2 E8(-1) + 3 U, rank=22, det = -1
   - Picard rank bound: rho <= h^{1,1} = 20

2. Supergravity Black Hole Attractor Mechanism:
   - Magnetic & Electric charge vectors: p, q in Gamma^{3,19}
   - Intersection invariants:
       p^2 = 8,  q^2 = 12,  p . q = 2
   - Quartic invariant:
       I_4(p, q) = p^2 q^2 - (p . q)^2 = 8 * 12 - 4 = 92
   - Horizon central charge:
       |Z_hor|^2 = sqrt(I_4) = sqrt(92) = 9.591663046625438
   - Bekenstein-Hawking Horizon Area & Entropy:
       S_BH = pi * |Z_hor|^2 = pi * sqrt(92) = 30.13324045543165
       A_H  = 4 * S_BH = 4 * pi * sqrt(92) = 120.5329618217266

3. Symplectic Dynamics:
   - Attractor flow maps to conservative Hamiltonian system H(q, p_q) = (1/2) p^2 + V_BH(q)
   - Symplectic 2-form conservation: d omega = 0
   - Relative energy preservation tolerance: |Delta H / H_0| < 1.0e-5

4. Donaldson Monge-Ampere Metric:
   - Balanced metric T-operator convergence on Kummer K3 surface
   - L2 convergence tolerance: ||T(h) - h||_2 < 1.0e-4
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class K3TopologySpec:
    """Exact topological invariants of the K3 Calabi-Yau surface."""

    dim_complex: int = 2
    dim_real: int = 4
    b0: int = 1
    b1: int = 0
    b2: int = 22
    b3: int = 0
    b4: int = 1
    h20: int = 1
    h11: int = 20
    h02: int = 1
    euler_characteristic: int = 24
    signature: int = -16  # 3 - 19
    picard_rank_max: int = 20
    lattice_rank: int = 22
    lattice_signature_pos: int = 3
    lattice_signature_neg: int = 19
    lattice_determinant: int = -1


@dataclass(frozen=True)
class BlackHoleAttractorSpec:
    """Astrophysical extremal black hole charges and thermodynamic ground truth."""

    p_squared: float = 8.0
    q_squared: float = 12.0
    p_dot_q: float = 2.0

    @property
    def quartic_invariant(self) -> float:
        return self.p_squared * self.q_squared - (self.p_dot_q ** 2)

    @property
    def horizon_moduli_norm_sq(self) -> float:
        return math.sqrt(self.quartic_invariant)

    @property
    def bekenstein_hawking_entropy(self) -> float:
        return math.pi * self.horizon_moduli_norm_sq

    @property
    def horizon_area(self) -> float:
        return 4.0 * self.bekenstein_hawking_entropy


@dataclass(frozen=True)
class SymplecticSimulationSpec:
    """Numerical integration parameters for attractor geodesic flow."""

    t_start: float = 0.0
    t_end: float = 20.0
    num_steps: int = 20_000
    dt: float = 0.001
    energy_tolerance: float = 1.0e-5
    initial_q: float = 3.5
    initial_p: float = 0.0
    target_q_attractor: float = math.sqrt(92.0)  # = 9.591663...


@dataclass(frozen=True)
class DonaldsonMetricSpec:
    """Donaldson balanced metric parameters on Kummer K3 surface."""

    degree_k: int = 4
    num_sample_points: int = 1200
    max_iterations: int = 25
    convergence_tolerance: float = 1.0e-4


def build_gamma_3_19_gram_matrix() -> np.ndarray:
    """
    Construct the canonical Gram matrix for the even unimodular lattice
    Gamma^{3,19} = 2 E8(-1) + 3 U.
    Rank: 22, Signature: (3, 19), Determinant: -1.
    """
    # 1. Hyperbolic plane U: 2x2 matrix [[0, 1], [1, 0]]
    u = np.array([[0.0, 1.0], [1.0, 0.0]])

    # 2. E8 Cartan matrix (positive definite, det = +1)
    e8_pos = np.array([
        [ 2, -1,  0,  0,  0,  0,  0,  0],
        [-1,  2, -1,  0,  0,  0,  0,  0],
        [ 0, -1,  2, -1,  0,  0,  0,  0],
        [ 0,  0, -1,  2, -1,  0,  0,  0],
        [ 0,  0,  0, -1,  2, -1,  0, -1],
        [ 0,  0,  0,  0, -1,  2, -1,  0],
        [ 0,  0,  0,  0,  0, -1,  2,  0],
        [ 0,  0,  0,  0, -1,  0,  0,  2],
    ], dtype=np.float64)

    # Negative definite E8(-1): det = (-1)^8 * 1 = 1, signature (0, 8)
    e8_neg = -e8_pos

    # Block diagonal assembly: 3 U + 2 E8(-1)
    gram = np.zeros((22, 22), dtype=np.float64)
    # 3 copies of U -> dims 0..5
    for i in range(3):
        gram[2*i:2*i+2, 2*i:2*i+2] = u
    # 2 copies of E8(-1) -> dims 6..13 and 14..21
    gram[6:14, 6:14] = e8_neg
    gram[14:22, 14:22] = e8_neg

    return gram


def verify_lattice_invariants(gram: np.ndarray) -> tuple[bool, int, tuple[int, int], float]:
    """Verify rank, signature, and determinant of the lattice Gram matrix."""
    rank = int(gram.shape[0])
    eigenvalues = np.linalg.eigvalsh(gram)
    pos_count = int(np.sum(eigenvalues > 1.0e-7))
    neg_count = int(np.sum(eigenvalues < -1.0e-7))
    det = float(np.linalg.det(gram))

    is_valid = (
        rank == 22
        and pos_count == 3
        and neg_count == 19
        and abs(round(det) - (-1)) < 1.0e-3
    )
    return is_valid, rank, (pos_count, neg_count), det

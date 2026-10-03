"""
ANSE Semantic & Epistemic Hard-Gate: Anti-Trivialization AST Linter.
Detects and rejects:
1. Hypothesis Smuggling (ad-hoc theorem assumptions that trivially entail the goal: h_invol, h_comm, h_ortho).
2. Vacuous Structural Abstraction (opaque structures and boolean flags mocking complex theories).
3. Operator Absence (rejects physical/mathematical problems lacking governing differential operators).

Assigns Fail-Closed Barrier Penalty E = 10^6 (Maximum Pain) on violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class SemanticViolation:
    rule: str
    message: str
    severity: str = "FAIL_CLOSED"
    penalty_energy: float = 1_000_000.0


@dataclass
class SemanticAuditResult:
    passed: bool
    violations: List[str]
    energy_score: float



class SemanticGatekeeper:
    """Enforces non-triviality, mathematical depth, and zero epistemic cheat."""

    # Tautology-inducing hypothesis patterns in theorem parameters
    SMUGGLED_HYPOTHESES = [
        (r"\bh_invol\b", "Hypothesis Smuggling: 'h_invol' injects the conclusion involution directly as an axiom."),
        (r"\bh_comm\b", "Hypothesis Smuggling: 'h_comm' assumes operator commutativity, trivializing the bracket/commutator to zero."),
        (r"\bh_ortho\b", "Hypothesis Smuggling: 'h_ortho' assumes orthogonality, reducing Helmholtz-Leray to standard Pythagoras."),
        (r"\bhCR1\b|\bhCR2\b", "Hypothesis Smuggling: Cauchy-Riemann derivative equality injected as raw real scalar assumptions."),
        (r"∀\s*\w+,\s*star\s*\(\s*star\s*\w+\s*\)\s*=\s*\w+", "Tautological Involution: Dual involution asserted in theorem hypothesis."),
        (r"\b\w+\s*\*\s*\w+\s*=\s*\w+\s*\*\s*\w+\b", "Tautological Commutativity: Direct commute assumption in theorem signature."),
    ]

    # Vacuous structure patterns (opaque boolean flags mocking deep conjectures)
    VACUOUS_PATTERNS = [
        (r"structure\s+ComplexProjectiveManifold\b[^:]*where\s+dim\s*:\s*\w+\s+is_smooth\s*:\s*Prop\b",
         "Vacuous Structure: ComplexProjectiveManifold mocked with empty Prop flags without differential geometry."),
        (r"structure\s+CohomologyClass\b[^:]*where\s+is_hodge\s*:\s*Prop\s+is_algebraic\s*:\s*Prop\b",
         "Vacuous Structure: CohomologyClass mocked with boolean flags 'is_hodge' and 'is_algebraic'."),
        (r"structure\s+RationalEllipticCurve\b[^:]*where\s+algebraic_rank\s*:\s*ℕ\s+analytic_order_at_one\s*:\s*ℕ\b",
         "Vacuous Structure: RationalEllipticCurve mocked with unconstrained Nat numbers rather than WeierstrassCurve and L-series."),
    ]

    # LaTeX Bleed-Through patterns (TeX macros mistakenly injected into Lean code)
    LATEX_BLEED_PATTERNS = [
        (r"\\(?:theta|rightarrow|leftarrow|Sigma|mathbb|mathbf|forall|exists|times|le|ge|neq|Delta|nabla|alpha|beta|gamma|nu|mu|psi|omega|pi)\b",
         "LaTeX Bleed-Through: Raw TeX macro detected in Lean source code. Use native Unicode (e.g. ℝ, ℂ, ℕ, →, ∑, ∀, ∃) or Lean identifiers."),
    ]

    # Mathematical Tautologies (Algebraic remainder solving for arbitrary function values)
    TAUTOLOGY_PATTERNS = [
        (r"hasse_weil_L_series.*=.*c\s*\*\s*\(s\s*-\s*1\)\^r\s*\+\s*R\s*\*",
         "Algebraic Tautology: BSD vanishing order trivialized via unconstrained remainder R. Use Filter.Tendsto or Asymptotics."),
    ]

    # Required operators per topic
    OPERATOR_REQUIREMENTS = {
        "navier_stokes": {

            "required_any": [r"Deriv", r"fderiv", r"nabla", r"div", r"curl", r"Laplacian", r"ContDiff"],
            "description": "Navier-Stokes requires differential calculus operators (fderiv, div, ContDiff, etc.)."
        },
        "yang_mills": {
            "required_any": [r"LieAlgebra", r"bracket", r"⁅", r"ExteriorAlgebra", r"ContinuousLinearMap", r"unitaryGroup"],
            "description": "Yang-Mills requires Lie algebra, connection, or gauge curvature structures."
        },
        "birch_swinnerton_dyer": {
            "required_any": [r"WeierstrassCurve", r"LSeries", r"LFunction", r"Point"],
            "description": "Birch and Swinnerton-Dyer requires genuine Weierstrass curves and L-series."
        },
        "hodge": {
            "required_any": [r"Manifold", r"DeRham", r"DifferentialForm", r"Hodge", r"Homology", r"VectorBundle"],
            "description": "Hodge Conjecture requires complex manifolds, De Rham cohomology, or differential forms."
        }
    }

    def audit_lean_code(self, code: str, topic: str | None = None) -> Tuple[bool, List[SemanticViolation], float]:
        """
        Audits Lean 4 code against Semantic Smuggling.
        Returns: (passed, violations, energy_penalty)
        """
        violations: List[SemanticViolation] = []

        # 1. Check for Hypothesis Smuggling
        for pattern, msg in self.SMUGGLED_HYPOTHESES:
            if re.search(pattern, code):
                violations.append(SemanticViolation(rule="NO_HYPOTHESIS_SMUGGLING", message=msg))

        # 2. Check for Vacuous Structures
        for pattern, msg in self.VACUOUS_PATTERNS:
            if re.search(pattern, code):
                violations.append(SemanticViolation(rule="NO_VACUOUS_STRUCTURES", message=msg))

        # 3. Check for Topic-Specific Operator Completeness
        if topic and topic.lower() in self.OPERATOR_REQUIREMENTS:
            req = self.OPERATOR_REQUIREMENTS[topic.lower()]
            found = any(re.search(pat, code) for pat in req["required_any"])
            if not found:
                violations.append(SemanticViolation(
                    rule="OPERATOR_COMPLETENESS",
                    message=f"Missing essential operators for {topic}. {req['description']}"
                ))

        # 4. Check for LaTeX Bleed-Through
        for pattern, msg in self.LATEX_BLEED_PATTERNS:
            if re.search(pattern, code):
                violations.append(SemanticViolation(rule="NO_LATEX_BLEED_THROUGH", message=msg))

        # 5. Check for Mathematical Tautologies
        for pattern, msg in self.TAUTOLOGY_PATTERNS:
            if re.search(pattern, code):
                violations.append(SemanticViolation(rule="NO_MATHEMATICAL_TAUTOLOGY", message=msg))

        # Calculate Energy Penalty
        if violations:
            return False, violations, 1_000_000.0

        return True, [], 0.0

    def audit_python_code(self, code: str) -> Tuple[bool, List[SemanticViolation], float]:
        """
        Audits Python code to prevent scalar mock simplifications (e.g. 0 - 0 = 0).
        """
        violations: List[SemanticViolation] = []
        if re.search(r"0\s*-\s*0\.5\s*\*\s*0\s*\*\s*g", code):
            violations.append(SemanticViolation(
                rule="NO_SCALAR_MOCK",
                message="Trivialized Einstein vacuum equations with literal scalar zeros."
            ))
        if re.search(r"err\s*=\s*abs\(\s*0\.0\s*-\s*0\.0\s*\)", code):
            violations.append(SemanticViolation(
                rule="NO_SCALAR_MOCK",
                message="Trivialized invariant check with literal zeros."
            ))

        if violations:
            return False, violations, 1_000_000.0

        return True, [], 0.0


def audit_lean4_code(code: str, topic: str | None = None, filename: str = "") -> SemanticAuditResult:
    """Convenience function to audit Lean 4 code against hypothesis smuggling and vacuous mocks."""
    gk = SemanticGatekeeper()
    if not topic and filename:
        fn_lower = filename.lower()
        if "navierstokes" in fn_lower or "navier_stokes" in fn_lower:
            topic = "navier_stokes"
        elif "yangmills" in fn_lower or "yang_mills" in fn_lower:
            topic = "yang_mills"
        elif "bsd" in fn_lower or "elliptic" in fn_lower:
            topic = "bsd"
        elif "hodge" in fn_lower:
            topic = "hodge"
    passed, viols, energy = gk.audit_lean_code(code, topic=topic)
    return SemanticAuditResult(
        passed=passed,
        violations=[f"[{v.rule}] {v.message}" for v in viols],
        energy_score=energy,
    )


if __name__ == "__main__":
    gatekeeper = SemanticGatekeeper()

    # Test smuggled code (Must Fail Closed)
    smuggled_code = """
theorem problem_54_hodge_star_dual_involution
    (h_invol: ∀ x, star (star x) = x) (w: E):
    star (star w) - w = 0 := by rw [h_invol w, sub_self]
"""
    passed, violations, energy = gatekeeper.audit_lean_code(smuggled_code, topic="hodge")
    print("Smuggled Code Audit Passed:", passed)
    print("Energy Assigned:", energy)
    for v in violations:
        print(f"  • [{v.rule}] {v.message}")
    assert not passed, "Gatekeeper must catch hypothesis smuggling!"
    assert energy >= 1_000_000.0, "Violations must trigger Maximum Pain E = 10^6!"

    print("\n✅ SemanticGatekeeper self-test successfully passed.")

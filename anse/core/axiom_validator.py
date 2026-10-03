ALLOWED_AXIOMS = {"propext", "Quot.sound", "Classical.choice"}

def validate_lean_axioms(used_axioms: set) -> bool:
    """
    ANSE v8: Smart Axiom Filtering.
    Ensures the theorem only relies on canonical Mathlib axioms.
    """
    unauthorized = used_axioms - ALLOWED_AXIOMS
    if unauthorized:
        raise ValueError(f"ANSE Security: Unauthorized axioms detected: {unauthorized}")
    return True

-- MVK v9.3.1 CI/CD FFI type helpers and compatibility layer
-- Bypasses type mismatches for toIO' in theorems/axioms

def _root_.IO.toIO' {α : Type} (x : IO α) (_ : Unit) : IO α := x

import re

def sanitize_lean_typography(code: str) -> str:
    """
    ANSE v8: Pre-processor to fix typographical LLM hallucinations 
    before sending code to Lean 4 LSP.
    """
    # Fix mathbb chars
    code = code.replace(" C ", " ℂ ").replace(": C", ": ℂ")
    code = code.replace(" R ", " ℝ ").replace(": R", ": ℝ")
    code = code.replace(" N ", " ℕ ").replace(": N", ": ℕ")
    
    # Fix operators
    code = code.replace("/\\", "∧")
    code = code.replace("\\/", "∨")
    code = code.replace("->", "→")
    code = code.replace("=>", "⇒")
    code = code.replace("<->", "↔")
    
    # Remove raw LaTeX macros inside Lean blocks
    code = re.sub(r'\\mathfrak{[a-zA-Z]}', 's', code)
    
    return code

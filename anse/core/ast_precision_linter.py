import ast

class HighPrecisionLinter(ast.NodeVisitor):
    def __init__(self):
        self.errors = []

    def visit_Call(self, node):
        # Disallow native `complex()` if high-precision is required
        if isinstance(node.func, ast.Name):
            if node.func.id == 'complex':
                self.errors.append(f"Ligne {node.lineno}: Usage de `complex()` interdit en haute précision. Utilisez `sympy.Float`.")
            elif node.func.id == 'getattr':
                self.errors.append(f"Ligne {node.lineno}: Usage de `getattr()` interdit (risque d'obscurcissement sémantique/évasion).")
        self.generic_visit(node)

    def visit_Constant(self, node):
        # Disallow native floats if they exceed normal usage in a high precision block
        if isinstance(node.value, float):
            self.errors.append(f"Ligne {node.lineno}: Flottant IEEE 754 détecté ({node.value}). Perte de précision. Utilisez une String via `sympy.Float('...', 30)`.")
        self.generic_visit(node)

def lint_script(code_str: str) -> bool:
    try:
        tree = ast.parse(code_str)
        linter = HighPrecisionLinter()
        linter.visit(tree)
        if linter.errors:
            for error in linter.errors:
                print(f"[AST Linter Error] {error}")
            return False
        return True
    except SyntaxError as e:
        print(f"[AST Linter] Syntax Error: {e}")
        return False

if __name__ == "__main__":
    test_code = """
import sympy as sp
t1 = 14.134725141734693
s1 = complex(0.5, t1)
z1 = sp.zeta(s1).evalf(30)
    """
    print("Testing non-compliant code:")
    lint_script(test_code)
    
    test_code_compliant = """
import sympy as sp
t1_str = '14.1347251417346937156614437215'
s1 = sp.Float('0.5', 30) + sp.I * sp.Float(t1_str, 30)
z1 = sp.zeta(s1).evalf(30)
    """
    print("\nTesting compliant code:")
    success = lint_script(test_code_compliant)
    if success:
        print("[AST Linter] Validation réussie. Précision garantie.")

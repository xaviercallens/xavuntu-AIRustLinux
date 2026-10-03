"""
SWE-agent and AutoCodeRover inspired AST-localized symbol navigator and editor.
Locates target functions/classes, extracts localized line windows, and applies
surgical in-place AST replacements without full-file rewrites.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class LocalizedSymbolWindow:
    """Localized code window for a specific symbol."""
    file_path: Path
    symbol_name: str
    kind: str  # "function", "method", "class"
    start_line: int
    end_line: int
    source_snippet: str
    docstring: str = ""


class ASTLocalizedNavigator:
    """
    Navigates Python codebases at the AST level, extracting localized function
    and class scopes for fine-grained token-bounded editing.
    """

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path.cwd()

    def find_symbol(self, file_path: Path, target_symbol: str) -> Optional[LocalizedSymbolWindow]:
        """
        Locates target_symbol (e.g. 'integrate_kerr_geodesic' or 'SystolicArraySTA.analyze_critical_path')
        within file_path and returns its exact line boundaries.
        """
        if not file_path.exists():
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
            lines = content.splitlines(keepends=True)
        except Exception:
            return None

        parts = target_symbol.split(".")
        if len(parts) == 1:
            name = parts[0]
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                    start = node.lineno
                    end = getattr(node, "end_lineno", start + 20)
                    snippet = "".join(lines[start - 1 : end])
                    doc = ast.get_docstring(node) or ""
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    return LocalizedSymbolWindow(
                        file_path=file_path,
                        symbol_name=name,
                        kind=kind,
                        start_line=start,
                        end_line=end,
                        source_snippet=snippet,
                        docstring=doc,
                    )
        elif len(parts) == 2:
            class_name, method_name = parts
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == method_name:
                            start = sub.lineno
                            end = getattr(sub, "end_lineno", start + 20)
                            snippet = "".join(lines[start - 1 : end])
                            doc = ast.get_docstring(sub) or ""
                            return LocalizedSymbolWindow(
                                file_path=file_path,
                                symbol_name=target_symbol,
                                kind="method",
                                start_line=start,
                                end_line=end,
                                source_snippet=snippet,
                                docstring=doc,
                            )
        return None

    def replace_symbol(
        self,
        file_path: Path,
        target_symbol: str,
        replacement_snippet: str,
    ) -> Tuple[bool, str]:
        """
        Surgically replaces only the target symbol within file_path,
        preserving all surrounding functions, imports, and comments.
        """
        window = self.find_symbol(file_path, target_symbol)
        if not window:
            return False, f"Symbol '{target_symbol}' not found in {file_path.name}"

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)

        # Ensure replacement snippet has trailing newline
        if not replacement_snippet.endswith("\n"):
            replacement_snippet += "\n"

        # Surgical slice replacement
        new_lines = lines[: window.start_line - 1] + [replacement_snippet] + lines[window.end_line :]
        new_content = "".join(new_lines)

        # Validate syntax of updated file
        try:
            ast.parse(new_content)
        except SyntaxError as exc:
            return False, f"Syntax error produced by replacement: {exc}"

        file_path.write_text(new_content, encoding="utf-8")
        return True, f"Successfully replaced {target_symbol} at lines {window.start_line}-{window.end_line}"

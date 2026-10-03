"""
Aider-inspired compact AST repository mapper and unified diff application engine.
Extracts ranked symbol declarations (classes, functions, signatures) in < 800 tokens
to give agents whole-repository awareness without token window bloat.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import difflib
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class SymbolTag:
    """Represents a declaration tag extracted from source AST."""
    rel_path: str
    symbol_name: str
    kind: str  # "class", "function", "async_function", "variable"
    line_number: int
    signature: str
    docstring_summary: str = ""
    rank_score: float = 0.0


class RepoMapGenerator:
    """
    Scans repository Python files, extracts concise AST tags, ranks them
    against target goal keywords, and formats a compact architecture map.
    """

    DEFAULT_EXCLUDES = {
        ".git", ".venv", "venv", "__pycache__", "build", "dist",
        "vendor", ".pytest_cache", ".hypothesis", "artifacts",
    }

    def __init__(self, root_dir: Optional[Path] = None, max_map_tokens: int = 800):
        self.root_dir = root_dir or Path.cwd()
        self.max_map_tokens = max_map_tokens

    def extract_file_tags(self, file_path: Path) -> List[SymbolTag]:
        """Parses a Python file with ast and extracts top-level and class-level tags."""
        tags: List[SymbolTag] = []
        try:
            rel_path = str(file_path.relative_to(self.root_dir))
        except ValueError:
            rel_path = file_path.name

        try:
            code = file_path.read_text(encoding="utf-8")
            tree = ast.parse(code, filename=str(file_path))
        except Exception:
            return tags

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or ""
                doc_summary = doc.split("\n")[0].strip() if doc else ""
                tags.append(SymbolTag(
                    rel_path=rel_path,
                    symbol_name=node.name,
                    kind="class",
                    line_number=node.lineno,
                    signature=f"class {node.name}:",
                    docstring_summary=doc_summary,
                ))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        sub_doc = ast.get_docstring(sub) or ""
                        sub_summary = sub_doc.split("\n")[0].strip() if sub_doc else ""
                        args = [a.arg for a in sub.args.args if a.arg != "self"]
                        tags.append(SymbolTag(
                            rel_path=rel_path,
                            symbol_name=f"{node.name}.{sub.name}",
                            kind="method",
                            line_number=sub.lineno,
                            signature=f"  def {sub.name}({', '.join(args)}):",
                            docstring_summary=sub_summary,
                        ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node) or ""
                doc_summary = doc.split("\n")[0].strip() if doc else ""
                args = [a.arg for a in node.args.args]
                tags.append(SymbolTag(
                    rel_path=rel_path,
                    symbol_name=node.name,
                    kind="function",
                    line_number=node.lineno,
                    signature=f"def {node.name}({', '.join(args)}):",
                    docstring_summary=doc_summary,
                ))

        return tags

    def collect_all_tags(self, target_dirs: Optional[List[str]] = None) -> List[SymbolTag]:
        """Recursively collects tags across targeted directories (defaulting to anse/)."""
        target_dirs = target_dirs or ["anse", "antigravity-harness"]
        all_tags: List[SymbolTag] = []

        for d in target_dirs:
            dir_path = self.root_dir / d
            if not dir_path.exists():
                continue
            for root, dirs, files in os.walk(dir_path):
                dirs[:] = [sub for sub in dirs if sub not in self.DEFAULT_EXCLUDES]
                for f in files:
                    if f.endswith(".py"):
                        p = Path(root) / f
                        all_tags.extend(self.extract_file_tags(p))

        return all_tags

    def rank_tags(self, tags: List[SymbolTag], query: str) -> List[SymbolTag]:
        """Ranks symbol tags based on token overlap with query."""
        keywords = set(re.findall(r"\w+", query.lower()))
        for tag in tags:
            score = 0.0
            search_str = f"{tag.rel_path} {tag.symbol_name} {tag.docstring_summary}".lower()
            tag_words = set(re.findall(r"\w+", search_str))
            matched = keywords.intersection(tag_words)
            score += len(matched) * 3.0
            if any(k in tag.symbol_name.lower() for k in keywords):
                score += 5.0
            tag.rank_score = score

        return sorted(tags, key=lambda t: t.rank_score, reverse=True)

    def generate_repo_map(self, query: str, max_tokens: Optional[int] = None) -> str:
        """
        Builds the compact Aider-style repo map string formatted for minimal token consumption.
        """
        max_tokens = max_tokens or self.max_map_tokens
        tags = self.collect_all_tags()
        ranked = self.rank_tags(tags, query)

        # Group symbols by file
        files_map: Dict[str, List[SymbolTag]] = {}
        for t in ranked:
            if t.rank_score > 0:
                files_map.setdefault(t.rel_path, []).append(t)

        # Fallback if no direct keyword matches: take highest-level exports
        if not files_map and ranked:
            for t in ranked[:25]:
                files_map.setdefault(t.rel_path, []).append(t)

        lines: List[str] = [
            f"# COMPACT REPO MAP (Target Query: {query})",
            "# Symbols ranked by architectural relevance:",
        ]

        result_str = "\n".join(lines)
        curr_tokens = len(result_str) // 4
        truncation_marker = "  │ ... (truncated to preserve token budget)"
        marker_tokens = (len(truncation_marker) // 4) + 2

        for rel_path, file_tags in files_map.items():
            file_header = f"\n{rel_path}:"
            header_tokens = (len(file_header) // 4) + 1
            if curr_tokens + header_tokens + marker_tokens >= max_tokens:
                lines.append(truncation_marker)
                return "\n".join(lines)

            lines.append(file_header)
            curr_tokens += header_tokens

            for tag in file_tags:
                doc_note = f"  # {tag.docstring_summary}" if tag.docstring_summary else ""
                tag_line = f"  │ {tag.signature}{doc_note}"
                tag_tokens = (len(tag_line) // 4) + 1

                if curr_tokens + tag_tokens + marker_tokens >= max_tokens:
                    lines.append(truncation_marker)
                    return "\n".join(lines)

                lines.append(tag_line)
                curr_tokens += tag_tokens

        return "\n".join(lines)


def apply_unified_diff(original_content: str, patch_text: str) -> Tuple[bool, str, str]:
    """
    Applies a standard unified diff patch to original_content cleanly line-by-line.
    Returns (success, patched_content, error_message).
    """
    orig_lines = original_content.splitlines(keepends=True)
    patch_lines = patch_text.splitlines(keepends=True)

    # Clean patch if enclosed in markdown diff fences
    cleaned: List[str] = []
    in_fence = False
    for line in patch_lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        cleaned.append(line)

    try:
        # Standard difflib reconstruction or line-hunk replacement
        hunks = []
        current_hunk: List[str] = []
        for line in cleaned:
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = [line]
            elif current_hunk:
                current_hunk.append(line)
        if current_hunk:
            hunks.append(current_hunk)

        if not hunks:
            # If plain replacement text was provided
            return True, "".join(cleaned), "Applied direct replacement."

        patched = list(orig_lines)
        for hunk in hunks:
            header = hunk[0]
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
            if not m:
                continue
            orig_start = int(m.group(1)) - 1
            orig_count = int(m.group(2)) if m.group(2) else 1

            new_lines: List[str] = []
            for hline in hunk[1:]:
                if hline.startswith("+"):
                    new_lines.append(hline[1:])
                elif hline.startswith(" "):
                    new_lines.append(hline[1:])
                # lines starting with "-" are omitted

            patched[orig_start : orig_start + orig_count] = new_lines

        return True, "".join(patched), "Unified diff successfully applied."
    except Exception as exc:
        return False, original_content, f"Failed to apply unified diff: {exc}"

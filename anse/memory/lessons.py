"""
Lesson memory: verified solutions that the agent loop reads back on similar tasks.

Only trajectories verified by hidden tests are stored, so self-graded (possibly
wrong) code never enters memory. Retrieval is lexical and deterministic.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from anse.algorithms.kdtree import KDTree

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    "a an and are as at be by for from if in into is it its must not of on or that the "
    "then this to when where which with write function functions return returns returned "
    "returning given python e g i example examples should".split()
)


@dataclass
class Lesson:
    task: str
    code: str
    failure: str = ""
    """First failure feedback that had to be overcome ('' if solved first try)."""
    iterations: int = 1
    timestamp: float = field(default_factory=time.time)
    embedding: list[float] | None = None


def _tokens(text: str) -> set[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    words = re.split(r"[^A-Za-z0-9]+", text.lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def task_similarity(a: str, b: str) -> float:
    """Jaccard similarity over content words (identifiers are split on case and underscores)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class LessonMemory:
    """Append-only JSONL store of verified lessons with similarity retrieval."""

    def __init__(self, path: Path, min_similarity: float = 0.12, frozen: bool = False) -> None:
        self.path = Path(path)
        self.frozen = frozen
        self.min_similarity = min_similarity
        self._lessons: list[Lesson] = []
        self._vocab: list[str] = []
        self._idf: dict[str, float] = {}

        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._lessons.append(Lesson(**json.loads(line)))

        if len(self._lessons) >= 10:
            self._init_vocab()
            for l in self._lessons:
                if l.embedding is None:
                    l.embedding = self._embed(l.task)

    def _init_vocab(self) -> None:
        df: Counter[str] = Counter()
        base_lessons = self._lessons[:10]
        for lesson in base_lessons:
            words = _tokens(lesson.task)
            for w in set(words):
                df[w] += 1
        top_words = [w for w, c in df.most_common(128)]
        self._vocab = top_words
        self._idf = {w: math.log(10.0 / c) for w, c in df.items() if w in top_words}

    def _embed(self, task: str) -> list[float]:
        words = _tokens(task)
        tf: Counter[str] = Counter(words)
        total = max(1, len(words))
        return [(tf.get(w, 0) / total) * self._idf.get(w, 0.0) for w in self._vocab]

    def __len__(self) -> int:
        return len(self._lessons)

    def prune_context(self, max_tokens: int = 2000) -> None:
        """Drops oldest lessons when the serialized lesson block exceeds max_tokens * 4 bytes."""
        max_bytes = max_tokens * 4
        while len(self._lessons) > 10:
            block_size = sum(len(l.task) + len(l.code) + len(l.failure) for l in self._lessons)
            if block_size > max_bytes:
                self._lessons.pop(10)
            else:
                break

    def add(self, lesson: Lesson) -> bool:
        """Store *lesson* unless the memory is frozen or the identical task is already stored."""
        if self.frozen or any(existing.task == lesson.task for existing in self._lessons):
            return False
            
        self._lessons.append(lesson)
        
        if len(self._lessons) == 10:
            self._init_vocab()
            for l in self._lessons:
                l.embedding = self._embed(l.task)
        elif len(self._lessons) > 10:
            lesson.embedding = self._embed(lesson.task)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(lesson)
        data.pop('embedding', None)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")
            
        self.prune_context()
        return True

    def retrieve(self, task: str, k: int = 2) -> list[tuple[float, Lesson]]:
        """Return up to *k* (similarity, lesson) pairs above the threshold, best first."""
        if len(self._lessons) < 10:
            scored = [(task_similarity(task, lesson.task), lesson) for lesson in self._lessons]
            scored = [pair for pair in scored if pair[0] >= self.min_similarity]
            scored.sort(key=lambda pair: pair[0], reverse=True)
            return scored[:k]

        target_emb = self._embed(task)
        points = [(l.embedding, l) for l in self._lessons if l.embedding is not None]
        if not points:
            return []
            
        tree = KDTree(points)
        nearest = tree.query_knn(target_emb, k=k)
        
        results = []
        for neighbor in nearest:
            sim = task_similarity(task, neighbor.payload.task)
            if sim >= self.min_similarity:
                results.append((sim, neighbor.payload))
        results.sort(key=lambda pair: pair[0], reverse=True)
        return results


def format_lessons(lessons: list[tuple[float, Lesson]], max_code_chars: int = 1200) -> str:
    """Render retrieved lessons as a prompt block ('' when there are none)."""
    if not lessons:
        return ""
    parts = ["LESSONS FROM SIMILAR TASKS YOU SOLVED BEFORE (verified by tests):"]
    for i, (_, lesson) in enumerate(lessons, 1):
        parts.append(f"--- Lesson {i} ---\nTask: {lesson.task.strip()}")
        if lesson.failure:
            parts.append(f"Mistake made first: {lesson.failure.strip()[:400]}")
        parts.append(f"Verified solution:\n```python\n{lesson.code[:max_code_chars]}\n```")
    parts.append("--- End of lessons. Apply what is relevant; now solve the new task. ---\n")
    return "\n".join(parts)


def extract_skeleton(code: str, max_chars: int = 400) -> str:
    """Extract signatures and docstrings from code, omitting implementation details."""
    if not code:
        return ""
    try:
        tree = ast.parse(code)
        skeleton_parts: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args_list = []
                for a in node.args.args:
                    arg_str = a.arg
                    if a.annotation:
                        arg_str += f": {ast.unparse(a.annotation)}"
                    args_list.append(arg_str)
                prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
                sig = f"{prefix}{node.name}({', '.join(args_list)})"
                if node.returns:
                    sig += f" -> {ast.unparse(node.returns)}"
                sig += ":"

                docstring = ast.get_docstring(node)
                if docstring:
                    body = f'    """{docstring.strip()}"""\n    ...'
                else:
                    body = "    ..."
                skeleton_parts.append(f"{sig}\n{body}")
            elif isinstance(node, ast.ClassDef):
                skeleton_parts.append(f"class {node.name}:\n    ...")
        if skeleton_parts:
            return "\n\n".join(skeleton_parts)[:max_chars]
    except Exception as exc:
        logger.debug("AST skeleton generation error: %s", exc)

    sig_lines = []
    for line in code.splitlines():
        trimmed = line.strip()
        if trimmed.startswith(("def ", "async def ", "class ")):
            sig_lines.append(line)
            sig_lines.append("    ...")
    if sig_lines:
        return "\n".join(sig_lines)[:max_chars]
    return code[:max_chars]


def format_lessons_skeleton(
    lessons: list[tuple[float, Lesson]], max_skeleton_chars: int = 400
) -> str:
    """Render retrieved lessons as compact structural skeletons for smaller models (Directive D4)."""
    if not lessons:
        return ""
    parts = ["LESSONS FROM SIMILAR TASKS (pattern and signature reference only):"]
    for i, (_, lesson) in enumerate(lessons, 1):
        parts.append(f"--- Lesson {i} ---")
        parts.append(f"Task: {lesson.task.strip()}")
        if lesson.failure:
            parts.append(f"Avoid previous mistake: {lesson.failure.strip()[:200]}")
        skeleton = extract_skeleton(lesson.code, max_chars=max_skeleton_chars)
        parts.append(f"Pattern reference:\n```python\n{skeleton}\n```")
    parts.append("--- End of lessons. Write your own complete code for the new task. ---\n")
    return "\n".join(parts)


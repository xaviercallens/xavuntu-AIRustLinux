"""
Versioned component registry: the safe, reversible half of a hot swap.

Layout under *root*::

    <component>/v0001.py ... v000N.py   immutable version files (never overwritten)
    <component>/active.json             pointer {"version", "sha256"}, replaced atomically
    <component>/lineage.jsonl           append-only audit trail of every decision

A swap is a pointer move, never an in-place edit: nothing under ``anse/`` is touched,
no process is signalled, and every promotion can be undone with :meth:`rollback`.
The lineage is the source of truth; a missing or corrupted pointer is rebuilt from it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

try:
    import fcntl
except ImportError:  # non-POSIX: single-writer use only
    fcntl = None  # type: ignore[assignment]

_COMPONENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_POINTER_NAME = "active.json"
_LINEAGE_NAME = "lineage.jsonl"
_POINTER_EVENTS = ("register", "promote", "rollback")


class RegistryError(RuntimeError):
    """The requested registry operation is not possible (unknown component, nothing to roll back)."""


class RegistryCorruptionError(RegistryError):
    """On-disk state is inconsistent and cannot be repaired from the lineage."""


@dataclass(frozen=True)
class ActivePointer:
    version: int
    sha256: str


def code_sha256(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


DEFAULT_PROMPT_STRATEGY_CODE = '''"""Default swappable prompt strategy component for ANSE (Directive D8)."""

def format_pain_prompt(
    task: str,
    code: str,
    energy: float,
    category: str,
    returncode: int,
    stderr: str,
    stdout: str,
    model_tier: str = ">3B",
    test_feedback: str = "",
) -> str:
    feedback = f"{test_feedback}\\n" if test_feedback else ""
    if model_tier == "<=3B":
        code_snip = code[:200] if code else "(no code block found)"
        stderr_snip = stderr[:200] if stderr else "(empty)"
        return (
            f"TASK: {task}\\n\\n"
            f"PAIN SIGNAL: Your previous attempt failed with Energy {energy:.1f} ({category}).\\n"
            f"Failing code summary:\\n```python\\n{code_snip}\\n```\\n"
            f"Execution feedback:\\n---\\n{feedback}Return code: {returncode}\\nStderr:\\n{stderr_snip}\\n---\\n"
            "Analyze the failure and provide the complete fixed Python code in a ```python ... ``` block."
        )
    else:
        code_snip = code[-4000:] if code else "(no code block was found in your reply)"
        stderr_snip = stderr[-1000:] if stderr else "(empty)"
        stdout_snip = stdout[-1000:] if stdout else "(empty)"
        return (
            f"TASK: {task}\\n\\n"
            f"PAIN SIGNAL: Your previous attempt failed with Energy {energy:.1f} ({category}).\\n"
            f"Your previous code:\\n```python\\n{code_snip}\\n```\\n"
            f"Execution feedback:\\n---\\n{feedback}Return code: {returncode}\\nStderr:\\n{stderr_snip}\\nStdout:\\n{stdout_snip}\\n---\\n"
            "Analyze the failure, correct the bug, and provide the complete fixed Python code in a ```python ... ``` block."
        )
'''



class ComponentRegistry:
    """On-disk store of component versions with an atomic active pointer and an audit trail."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ── paths ────────────────────────────────────────────────────────────────
    def _dir(self, component: str) -> Path:
        if not _COMPONENT_RE.match(component):
            raise RegistryError(f"Invalid component name: {component!r}")
        return self.root / component

    def version_path(self, component: str, version: int) -> Path:
        return self._dir(component) / f"v{version:04d}.py"

    def lineage_path(self, component: str) -> Path:
        return self._dir(component) / _LINEAGE_NAME

    def pointer_path(self, component: str) -> Path:
        return self._dir(component) / _POINTER_NAME

    def versions(self, component: str) -> list[int]:
        found = []
        for path in self._dir(component).glob("v[0-9][0-9][0-9][0-9].py"):
            found.append(int(path.stem[1:]))
        return sorted(found)

    def components(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if (p / _LINEAGE_NAME).exists())

    # ── low-level writes ─────────────────────────────────────────────────────
    @contextmanager
    def _locked(self, component: str) -> Iterator[None]:
        directory = self._dir(component)
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / ".lock", "a+", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_version(self, component: str, code: str) -> int:
        existing = self.versions(component)
        version = (existing[-1] + 1) if existing else 1
        # mode "x": creation fails rather than overwriting an existing version file
        with open(self.version_path(component, version), "x", encoding="utf-8") as handle:
            handle.write(code)
            handle.flush()
            os.fsync(handle.fileno())
        return version

    def _write_pointer(self, component: str, pointer: ActivePointer) -> None:
        """Write-to-temp + fsync + os.replace: readers see the old or the new pointer, never a mix."""
        directory = self._dir(component)
        fd, tmp_name = tempfile.mkstemp(prefix=".active-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"version": pointer.version, "sha256": pointer.sha256}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.pointer_path(component))
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _append_lineage(self, component: str, entry: dict[str, Any]) -> dict[str, Any]:
        full = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "component": component, **entry}
        path = self.lineage_path(component)
        # A crash can leave a torn last line; start on a fresh line so this entry stays parseable.
        torn = path.exists() and path.stat().st_size > 0 and not path.read_bytes().endswith(b"\n")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(("\n" if torn else "") + json.dumps(full, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return full

    # ── reads ────────────────────────────────────────────────────────────────
    def lineage(self, component: str) -> list[dict[str, Any]]:
        """All parseable lineage entries, oldest first. A torn trailing line is ignored."""
        path = self.lineage_path(component)
        if not path.exists():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries

    def _read_pointer(self, component: str) -> ActivePointer | None:
        """The pointer if it is present, well-formed and matches its version file; else None."""
        try:
            data = json.loads(self.pointer_path(component).read_text(encoding="utf-8"))
            pointer = ActivePointer(version=int(data["version"]), sha256=str(data["sha256"]))
            code = self.version_path(component, pointer.version).read_text(encoding="utf-8")
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return pointer if code_sha256(code) == pointer.sha256 else None

    def _pointer_from_lineage(self, component: str) -> ActivePointer:
        for entry in reversed(self.lineage(component)):
            if entry.get("event") not in _POINTER_EVENTS:
                continue
            version, sha = entry.get("active_version"), entry.get("active_sha256")
            if not isinstance(version, int) or not isinstance(sha, str):
                continue
            path = self.version_path(component, version)
            if path.exists() and code_sha256(path.read_text(encoding="utf-8")) == sha:
                return ActivePointer(version=version, sha256=sha)
            raise RegistryCorruptionError(
                f"{component}: lineage says v{version:04d} is active but its file is missing or altered"
            )
        raise RegistryCorruptionError(
            f"{component}: no usable pointer and no lineage to rebuild it from"
        )

    def active(self, component: str) -> ActivePointer:
        """
        The active pointer. The lineage is authoritative: a pointer that is missing, malformed,
        altered, or stale (crash between lineage append and pointer replace) is rebuilt from
        it, and the repair is itself logged.
        """
        if not self.lineage_path(component).exists():
            raise RegistryError(f"Unknown component: {component!r}")
        pointer = self._read_pointer(component)
        if pointer is not None and pointer == self._pointer_from_lineage(component):
            return pointer
        with self._locked(
            component
        ):  # re-check under the lock: a writer may have been mid-promotion
            pointer = self._read_pointer(component)
            expected = self._pointer_from_lineage(component)
            if pointer != expected:
                self._write_pointer(component, expected)
                self._append_lineage(
                    component,
                    {
                        "event": "repair",
                        "restored_version": expected.version,
                        "reason": "active pointer missing, corrupted or stale; rebuilt from lineage",
                    },
                )
        return expected

    def active_version(self, component: str) -> int:
        return self.active(component).version

    def code(self, component: str, version: int) -> str:
        path = self.version_path(component, version)
        if not path.exists():
            raise RegistryError(f"{component}: version {version} does not exist")
        return path.read_text(encoding="utf-8")

    def active_code(self, component: str) -> str:
        return self.code(component, self.active(component).version)

    def load_active(self, component: str) -> ModuleType:
        """
        Import the active version as a fresh module object: this is the swap taking effect.
        Only hand-registered parents and children that passed the hypervisor gates ever
        become active, and the pointer's sha256 is verified before the file is executed.
        """
        pointer = self.active(component)
        path = self.version_path(component, pointer.version)
        spec = importlib.util.spec_from_file_location(
            f"anse_registry_{component}_v{pointer.version:04d}", path
        )
        if spec is None or spec.loader is None:
            raise RegistryError(f"{component}: cannot build an import spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    # ── mutations ────────────────────────────────────────────────────────────
    def register(self, component: str, code: str, note: str = "initial parent") -> int:
        """Register the first (parent) version. Idempotent if the component already exists."""
        if not self.lineage_path(component).exists():
            with self._locked(component):
                if not self.lineage_path(component).exists():
                    version = self._write_version(component, code)
                    sha = code_sha256(code)
                    self._append_lineage(
                        component,
                        {
                            "event": "register",
                            "active_version": version,
                            "active_sha256": sha,
                            "note": note,
                        },
                    )
                    self._write_pointer(component, ActivePointer(version, sha))
                    return version
        return self.active_version(component)

    def ensure_default_prompt_strategy(self) -> int:
        """Register the default prompt_strategy component if not already registered (Directive D8)."""
        return self.register(
            "prompt_strategy",
            DEFAULT_PROMPT_STRATEGY_CODE,
            note="initial default prompt strategy component",
        )

    def promote(self, component: str, child_code: str, record: dict[str, Any]) -> int:
        """
        Store *child_code* as a new version and make it active. *record* (energies, test
        counts, reason...) is written to the lineage. Order: version file, lineage, pointer;
        a crash between the last two is healed by :meth:`active` from the lineage.
        """
        self.active(component)  # repairs the pointer first if needed
        with self._locked(component):
            parent = self._pointer_from_lineage(component)
            version = self._write_version(component, child_code)
            sha = code_sha256(child_code)
            self._append_lineage(
                component,
                {
                    **record,
                    "event": "promote",
                    "decision": "promoted",
                    "parent_version": parent.version,
                    "parent_sha256": parent.sha256,
                    "child_version": version,
                    "child_sha256": sha,
                    "active_version": version,
                    "active_sha256": sha,
                },
            )
            self._write_pointer(component, ActivePointer(version, sha))
            return version

    def record_rejection(
        self, component: str, child_code: str, record: dict[str, Any]
    ) -> dict[str, Any]:
        """Audit a rejected child. Its code is not stored as a version; only its hash is kept."""
        self.active(component)  # repairs the pointer first if needed
        with self._locked(component):
            parent = self._pointer_from_lineage(component)
            return self._append_lineage(
                component,
                {
                    **record,
                    "event": "evaluate",
                    "decision": "rejected",
                    "parent_version": parent.version,
                    "parent_sha256": parent.sha256,
                    "child_version": None,
                    "child_sha256": code_sha256(child_code),
                },
            )

    def rollback(self, component: str, reason: str = "manual rollback") -> int:
        """Re-activate the parent of the active version. Version files are kept; the move is logged."""
        self.active(component)  # repairs the pointer first if needed
        with self._locked(component):
            current = self._pointer_from_lineage(component)
            promotion: dict[str, Any] | None = None
            for entry in reversed(self.lineage(component)):
                if (
                    entry.get("event") == "promote"
                    and entry.get("child_version") == current.version
                ):
                    promotion = entry
                    break
            if promotion is None:
                raise RegistryError(
                    f"{component}: v{current.version:04d} has no parent to roll back to"
                )
            parent_version = int(promotion["parent_version"])
            sha = code_sha256(self.code(component, parent_version))
            if sha != promotion.get("parent_sha256"):
                raise RegistryCorruptionError(
                    f"{component}: v{parent_version:04d} no longer matches the hash recorded at promotion"
                )
            self._append_lineage(
                component,
                {
                    "event": "rollback",
                    "from_version": current.version,
                    "to_version": parent_version,
                    "active_version": parent_version,
                    "active_sha256": sha,
                    "reason": reason,
                },
            )
            self._write_pointer(component, ActivePointer(parent_version, sha))
            return parent_version

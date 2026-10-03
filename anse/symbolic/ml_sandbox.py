"""
ML Architecture Sandbox Executor.

Phase 2: Micro-ML Architect.
Provides a specialized sandbox that wraps a candidate `nn.Module` in a standard
PyTorch training loop against procedural synthetic datasets, evaluating
parameter count, accuracy, and validation loss.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

from anse.config import SandboxConfig, get_config
from anse.symbolic.sandbox import ExecutionResult, scan_dangerous_imports


@dataclass
class MLExecutionResult(ExecutionResult):
    parameters: int = 0
    accuracy: float = 0.0
    val_loss: float = float("inf")
    train_loss: float = float("inf")
    is_shape_mismatch: bool = False
    is_oom: bool = False


_ML_RUNNER_SCRIPT = textwrap.dedent("""
import sys
import json
import traceback
import subprocess
import time

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError as e:
    sys.exit(f"ImportError: {e}")

target_file = sys.argv[1]
stats_file = sys.argv[2]
task_type = sys.argv[3] if len(sys.argv) > 3 else "classification"

# 1. Generate Synthetic Dataset
X = torch.randn(2000, 20)
y = (X[:, :5].sum(dim=1) > 0).long()
X_train, X_val = X[:1600], X[1600:]
y_train, y_val = y[:1600], y[1600:]

# 2. Load the candidate model
import importlib.util
spec = importlib.util.spec_from_file_location("candidate_module", target_file)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    # Find the nn.Module subclass (excluding nn.Module itself)
    model_class = None
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and issubclass(obj, nn.Module) and obj is not nn.Module:
            model_class = obj
            break
    if model_class is None:
        raise ValueError("Could not find an nn.Module subclass in the generated code.")
    
    model = model_class()
except (OSError, subprocess.SubprocessError) as exc:
    traceback.print_exc()
    sys.exit(1)

# 3. Count parameters
total_params = sum(p.numel() for p in model.parameters())

# 4. Train the model
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.01)

epochs = 50
start_time = time.perf_counter()
shape_mismatch = False
oom = False

train_loss = float("inf")
try:
    for epoch in range(epochs):
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        loss.backward()
        optimizer.step()
        train_loss = loss.item()
except RuntimeError as e:
    err_str = str(e).lower()
    if "size mismatch" in err_str or "mat1 and mat2 shapes cannot be multiplied" in err_str:
        shape_mismatch = True
    elif "out of memory" in err_str:
        oom = True
    traceback.print_exc()
    sys.exit(1)
except (OSError, subprocess.SubprocessError) as exc:
    traceback.print_exc()
    sys.exit(1)

# 5. Evaluate
model.eval()
val_loss = float("inf")
accuracy = 0.0
try:
    with torch.no_grad():
        outputs = model(X_val)
        val_loss = criterion(outputs, y_val).item()
        preds = torch.argmax(outputs, dim=1)
        correct = (preds == y_val).sum().item()
        accuracy = correct / len(y_val)
except (ValueError, TypeError) as exc:
    traceback.print_exc()
    sys.exit(1)

end_time = time.perf_counter()

# 6. Dump stats
stats = {
    "parameters": total_params,
    "accuracy": accuracy,
    "val_loss": val_loss,
    "train_loss": train_loss,
    "duration_ms": (end_time - start_time) * 1000.0,
    "is_shape_mismatch": shape_mismatch,
    "is_oom": oom
}
with open(stats_file, "w") as f:
    json.dump(stats, f)

sys.exit(0)
""").strip()


def _parse_ml_stats(
    stats_path: Path, returncode: int, stderr: str, elapsed_ms: float
) -> tuple[int, float, float, float, float, bool, bool]:
    params = 0
    acc = 0.0
    val_loss = float("inf")
    train_loss = float("inf")
    shape_mismatch = False
    oom = False

    if returncode != 0:
        stderr_lower = stderr.lower()
        if (
            "size mismatch" in stderr_lower
            or "mat1 and mat2 shapes cannot be multiplied" in stderr_lower
            or "shape" in stderr_lower
        ):
            shape_mismatch = True
        if "out of memory" in stderr_lower:
            oom = True

    if stats_path.exists():
        try:
            with open(stats_path) as f:
                stats = json.load(f)
            params = stats.get("parameters", params)
            acc = stats.get("accuracy", acc)
            val_loss = stats.get("val_loss", val_loss)
            train_loss = stats.get("train_loss", train_loss)
            elapsed_ms = stats.get("duration_ms", elapsed_ms)
            shape_mismatch = stats.get("is_shape_mismatch", shape_mismatch)
            oom = stats.get("is_oom", oom)
        except (ValueError, TypeError, OSError):
            val_loss = float("inf")

    return params, acc, val_loss, train_loss, elapsed_ms, shape_mismatch, oom


def _tier1_ml_execute(
    code: str, timeout: float, task_type: str = "classification"
) -> MLExecutionResult:
    """Run ML architecture code in a subprocess wrapper."""
    with tempfile.TemporaryDirectory(prefix="anse_t1_ml_") as tmpdir:
        script_path = Path(tmpdir) / "solution.py"
        script_path.write_text(code, encoding="utf-8")
        runner_path = Path(tmpdir) / "_runner.py"
        runner_path.write_text(_ML_RUNNER_SCRIPT, encoding="utf-8")
        stats_path = Path(tmpdir) / "_stats.json"

        start = time.perf_counter()
        try:
            sub_env = {"PATH": os.environ.get("PATH", ""), "HOME": tmpdir}
            if sys.platform == "win32":
                for k in (
                    "SYSTEMROOT",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "SYSTEMDRIVE",
                    "COMSPEC",
                    "PATHEXT",
                ):
                    if k in os.environ:
                        sub_env[k] = os.environ[k]

            proc = subprocess.run(
                [sys.executable, str(runner_path), str(script_path), str(stats_path), task_type],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
                env=sub_env,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            (params, acc, val_loss, train_loss, elapsed_ms, shape_mismatch, oom) = _parse_ml_stats(
                stats_path, proc.returncode, proc.stderr, elapsed_ms
            )

            return MLExecutionResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                returncode=proc.returncode,
                timed_out=False,
                duration_ms=elapsed_ms,
                tier_used=1,
                peak_ram_mb=0.0,
                parameters=params,
                accuracy=acc,
                val_loss=val_loss,
                train_loss=train_loss,
                is_shape_mismatch=shape_mismatch,
                is_oom=oom,
            )
        except subprocess.TimeoutExpired:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return MLExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {timeout}s",
                returncode=-1,
                timed_out=True,
                duration_ms=elapsed_ms,
                tier_used=1,
                peak_ram_mb=0.0,
            )


class MLSandboxExecutor:
    """
    Executes PyTorch architecture proposals.
    """

    def __init__(self, cfg: SandboxConfig | None = None) -> None:
        self._cfg = cfg or get_config().sandbox

    def execute(self, code: str, task_type: str = "classification") -> MLExecutionResult:
        # For Phase 2 we strictly rely on Tier 1 (CPU execution)
        # to guarantee deterministic parameter counts and avoid GPU state leak.
        # Dangerous imports could still be scanned if needed.
        dangerous = scan_dangerous_imports(code, self._cfg.dangerous_modules)
        result = _tier1_ml_execute(code, self._cfg.timeout_seconds, task_type=task_type)
        result.dangerous_imports = dangerous
        return result

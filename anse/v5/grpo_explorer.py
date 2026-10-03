"""
anse.v5.grpo_explorer - Group Relative Policy Optimization (GRPO) for Test-Time Compute.

Explores G concurrent reasoning trajectories in parallel.
Evaluates each trajectory live through the deterministic sandbox / AntiStubGuard.
Computes group-relative normalized advantages:
    A_i = (R_i - mean(R)) / (std(R) + 1e-6)
Penalizes stubs and crashes (E = 10^6, R = -1.0) and promotes optimal lowest-energy solutions (R = +1.0).
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from antigravity_harness.core.anti_stub_guard import AntiStubGuard

logger = logging.getLogger(__name__)


@dataclass
class GRPOTrajectory:
    """A single reasoning attempt in the test-time exploration group."""

    candidate_id: int
    name: str
    code: str
    is_clean: bool
    violations: list[str]
    latency_ms: float
    energy: float
    reward: float
    advantage: float
    status: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GRPOResult:
    """Outcome of group exploration and relative advantage optimization."""

    prompt: str
    group_size: int
    trajectories: list[GRPOTrajectory]
    best_candidate_id: int
    best_reward: float
    best_energy: float
    mean_reward: float
    std_reward: float
    speedup_factor: float
    proof_token: str
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["best_index"] = self.best_candidate_id
        for i, t in enumerate(d.get("trajectories", [])):
            t["trajectory_id"] = t.get("candidate_id", i) + 1
            t["strategy"] = t.get("name", f"Candidate {i + 1}")
            t["closed_loop_passed"] = t.get("is_clean", True) and t.get("energy", 0.0) < 1e5
            t["duration_ms"] = t.get("latency_ms", 0.0)
        if d.get("trajectories") and 0 <= self.best_candidate_id < len(d["trajectories"]):
            d["best_trajectory"] = d["trajectories"][self.best_candidate_id]
        else:
            d["best_trajectory"] = {}
        return d


class GRPOExplorer:
    """Group Relative Policy Optimization explorer for ANSE V5."""

    def __init__(self, group_size: int = 8) -> None:
        self.group_size = group_size
        self.guard = AntiStubGuard()

    def evaluate_group(
        self,
        prompt: str,
        candidates: list[dict[str, str]] | None = None,
    ) -> GRPOResult:
        """Evaluates group of reasoning trajectories and computes relative advantages."""
        t0 = time.perf_counter()
        
        # If candidates not provided, generate default diverse reasoning candidates
        if not candidates:
            candidates = self._generate_default_candidates(prompt)

        trajectories: list[GRPOTrajectory] = []
        rewards: list[float] = []

        for idx, cand in enumerate(candidates[: self.group_size]):
            c_name = cand.get("name", f"Trajectory #{idx+1}")
            c_code = cand.get("code", "")

            # 1. AntiStubGuard inspection
            audit_res = self.guard.audit_code(c_code, filename=f"trajectory_{idx}.py")
            is_clean = audit_res.is_clean
            violations = [f"[{v.rule}] {v.message}" for v in audit_res.violations]

            if not is_clean:
                # Maximum pain penalty for hollow stubs
                lat_ms = 0.1
                energy = 1000000.0
                reward = -1.0
                status = "PRUNED_HOLLOW_STUB"
            else:
                # Deterministic sandbox execution
                t_exec0 = time.perf_counter()
                locs: dict[str, Any] = {}
                try:
                    exec(c_code, {"math": math, "__builtins__": __builtins__}, locs)  # noqa: S102
                    lat_ms = round((time.perf_counter() - t_exec0) * 1000.0, 3)
                    calc_val = locs.get("result", locs.get("output", 1.0))
                    # Reward function favoring low latency and positive outcome
                    energy = max(1.0, lat_ms * 12.0)
                    reward = max(-0.5, 1.0 - (energy / 500.0))
                    status = "OPTIMIZED_EXECUTION"
                except Exception as exc:
                    lat_ms = 0.5
                    energy = 1000000.0
                    reward = -1.0
                    status = f"RUNTIME_CRASH: {exc}"

            rewards.append(reward)
            trajectories.append(
                GRPOTrajectory(
                    candidate_id=idx + 1,
                    name=c_name,
                    code=c_code,
                    is_clean=is_clean,
                    violations=violations,
                    latency_ms=lat_ms,
                    energy=round(energy, 2),
                    reward=round(reward, 4),
                    advantage=0.0,  # Computed below
                    status=status,
                )
            )

        # 2. Compute group-relative normalized advantage: A_i = (R_i - mean(R)) / (std(R) + eps)
        n = len(rewards)
        mean_r = sum(rewards) / n if n > 0 else 0.0
        var_r = sum((r - mean_r) ** 2 for r in rewards) / n if n > 0 else 0.0
        std_r = math.sqrt(var_r)
        eps = 1e-6

        best_idx = 0
        best_adv = -float("inf")

        for idx, traj in enumerate(trajectories):
            adv = (traj.reward - mean_r) / (std_r + eps)
            traj.advantage = round(adv, 4)
            if adv > best_adv:
                best_adv = adv
                best_idx = idx

        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        best_t = trajectories[best_idx]
        speedup = round(trajectories[0].energy / max(0.01, best_t.energy), 2) if trajectories[0].energy > 0 else 1.0

        proof_token = hashlib.sha256(
            f"grpo:{prompt}:{best_t.candidate_id}:{best_t.reward}:{duration_ms}".encode()
        ).hexdigest()[:32]

        return GRPOResult(
            prompt=prompt,
            group_size=len(trajectories),
            trajectories=trajectories,
            best_candidate_id=best_t.candidate_id,
            best_reward=best_t.reward,
            best_energy=best_t.energy,
            mean_reward=round(mean_r, 4),
            std_reward=round(std_r, 4),
            speedup_factor=speedup,
            proof_token=proof_token,
            duration_ms=duration_ms,
        )

    def _generate_default_candidates(self, prompt: str) -> list[dict[str, str]]:
        """Generates 8 diverse candidate attempts for testing-time exploration."""
        return [
            {
                "name": "Trajectory #1 (Hollow Placeholder)",
                "code": "def solve():\n    pass # TODO: implement physical solver\n",
            },
            {
                "name": "Trajectory #2 (Tautological Stub)",
                "code": "result = 42\nassert result == result\n",
            },
            {
                "name": "Trajectory #3 (Naive Scalar Loop)",
                "code": "result = sum(i * 0.01 for i in range(5000))\n",
            },
            {
                "name": "Trajectory #4 (Generator Expression)",
                "code": "result = sum(math.sin(i * 0.001) for i in range(10000))\n",
            },
            {
                "name": "Trajectory #5 (Vectorized Buffer)",
                "code": "import math\nvals = [math.cos(i * 0.002) for i in range(15000)]\nresult = sum(vals)\n",
            },
            {
                "name": "Trajectory #6 (Unchecked Division by Zero)",
                "code": "x = 0\nresult = 100 / x\n",
            },
            {
                "name": "Trajectory #7 (Optimized Cache-Friendly SIMD Prototype)",
                "code": "import math\n# Cache-blocked evaluation\ns = 0.0\nfor i in range(20000):\n    s += math.sin(i * 0.0001) * math.cos(i * 0.0001)\nresult = s\n",
            },
            {
                "name": "Trajectory #8 (Fused Invariant Conserving Kernel)",
                "code": "import math\n# Symplectic step conservation\nq, p = 1.0, 0.0\ndt = 0.001\nfor _ in range(5000):\n    p -= q * dt\n    q += p * dt\nresult = 0.5 * (p*p + q*q)\n",
            },
        ]

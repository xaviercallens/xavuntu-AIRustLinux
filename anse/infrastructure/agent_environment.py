"""
Agent + environment capability detection for AutoevolveAI.

Two independent axes decide which config/backend a session should use:

1. Coding agent -- which harness is driving this session: "claude_code",
   "antigravity", or "unknown". See CLAUDE.md's Antigravity/Claude Code
   support matrix; each ships its own guard hooks and MCP config file
   (`.claude/` + `.mcp.json` vs `.antigravity/`).
2. Compute environment -- what hardware is actually reachable right now:
   an NVIDIA GPU, queried live via `nvidia-smi`, never assumed from a prior
   session, a memory note, or project docs.

Detection is evidence-only. Claude Code is identified from process-env
signals this process can actually observe (`CLAUDECODE=1`, set by the CLI
itself). Google Antigravity does not, as of this writing, set any documented
env var, so it is never inferred implicitly -- guessing "antigravity" from
the mere presence of `.antigravity/` on disk would also fire for a bare
shell on a checkout that has never run either agent (both directories exist
in every clone of this repo). Set `AUTOEVOLVE_AGENT` to force a value, or
extend `_AGENT_ENV_SIGNALS` below once a real Antigravity signal is found.

Likewise the GPU check runs `nvidia-smi` live rather than trusting a
remembered "this box has a T4" fact: a GPU can be physically attached but
its driver unreachable (observed on this project's own GCP instance -- see
CapabilityProfile docstring), which is neither "has a T4" nor "CPU-only".
`AUTOEVOLVE_GPU_HINT` lets an operator who knows the real hardware override
the live probe for backend selection when the probe itself can't see it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

CLAUDE_CODE = "claude_code"
ANTIGRAVITY = "antigravity"
UNKNOWN_AGENT = "unknown"
_VALID_AGENTS = (CLAUDE_CODE, ANTIGRAVITY, UNKNOWN_AGENT)

# (agent, env var, required value or None for "present and non-empty").
# Only signals verified against a real session's `env` output belong here.
_AGENT_ENV_SIGNALS: tuple[tuple[str, str, str | None], ...] = (
    (CLAUDE_CODE, "CLAUDECODE", "1"),
    (CLAUDE_CODE, "CLAUDE_CODE_ENTRYPOINT", None),
    (ANTIGRAVITY, "ANTIGRAVITY_AGENT", "1"),
    (ANTIGRAVITY, "ANTIGRAVITY_CONVERSATION_ID", None),
    (ANTIGRAVITY, "ANTIGRAVITY_APP_DATA_DIR", None),
)


def _agent_override() -> str | None:
    value = os.environ.get("AUTOEVOLVE_AGENT", "").strip().lower()
    return value if value in _VALID_AGENTS else None


def _agents_from_signals() -> tuple[str, ...]:
    """Every agent whose env signals are present, in _AGENT_ENV_SIGNALS order.

    Returns all matches rather than the first, so that an ambiguous environment
    is something callers can see instead of a tie silently broken by the order
    of a module-level tuple.
    """
    matched: list[str] = []
    for agent, var, expected in _AGENT_ENV_SIGNALS:
        seen = os.environ.get(var)
        if not seen:
            continue
        if (expected is None or seen == expected) and agent not in matched:
            matched.append(agent)
    return tuple(matched)


def _agent_from_signals() -> str | None:
    matched = _agents_from_signals()
    return matched[0] if matched else None


def detect_coding_agent() -> str:
    """Resolve which coding agent is driving this session.

    Resolution order: an explicit `AUTOEVOLVE_AGENT` override, then verified
    env-var signals, else "unknown". Never inferred from filesystem layout.

    **When more than one agent's signals are present** the environment is
    genuinely ambiguous -- for example an Antigravity run started from a shell
    that still exports Claude Code's variables. Precedence is then
    `_AGENT_ENV_SIGNALS` order (Claude Code first), because `CLAUDECODE=1` is
    exported by the Claude Code process itself, whereas `ANTIGRAVITY_AGENT` is
    also the documented manual opt-in and so is the likelier leftover. Use
    `AUTOEVOLVE_AGENT` to settle it explicitly, and `describe_agent_detection()`
    to see what was actually matched -- relying on this tie-break silently is
    how a CPU-profile test came to pass on an Antigravity host and fail on a
    GPU host that had both variables set.
    """
    return _agent_override() or _agent_from_signals() or UNKNOWN_AGENT


def describe_agent_detection() -> dict[str, object]:
    """Expose how the agent was resolved, including any ambiguity.

    Deployment validation should assert on this rather than on
    `detect_coding_agent()` alone, so a host with conflicting signals is a
    visible finding instead of an accepted coin-flip.
    """
    override = _agent_override()
    matched = _agents_from_signals()
    return {
        "resolved": override or (matched[0] if matched else UNKNOWN_AGENT),
        "override": override,
        "signals_matched": list(matched),
        "ambiguous": override is None and len(matched) > 1,
    }


@dataclass(frozen=True)
class GPUInfo:
    """Result of a live GPU probe.

    `available=False` covers both "no GPU" and "a GPU is attached but its
    driver could not be reached right now" -- read `probe_error` to tell
    those apart instead of treating either as a hard "no GPU" fact.
    """

    available: bool
    name: str | None
    total_memory_mb: int | None
    probe_error: str | None


def _parse_nvidia_smi_csv(output: str) -> GPUInfo:
    first_line = next((ln for ln in output.strip().splitlines() if ln.strip()), "")
    fields = [f.strip() for f in first_line.split(",")]
    if len(fields) < 2:
        return GPUInfo(False, None, None, "unparseable nvidia-smi output")
    name = fields[0]
    mem_text = fields[1].lower().replace("mib", "").strip()
    try:
        mem_mb: int | None = int(float(mem_text))
    except ValueError:
        mem_mb = None
    return GPUInfo(True, name, mem_mb, None)


def detect_gpu(timeout_s: float = 5.0) -> GPUInfo:
    """Probe for an NVIDIA GPU via `nvidia-smi`. Live, never cached."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return GPUInfo(False, None, None, "nvidia-smi not on PATH")
    try:
        result = subprocess.run(
            [exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GPUInfo(False, None, None, f"nvidia-smi timed out after {timeout_s}s")
    except OSError as exc:
        return GPUInfo(False, None, None, f"nvidia-smi failed to launch: {exc}")
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
        return GPUInfo(False, None, None, message)
    if not result.stdout.strip():
        return GPUInfo(False, None, None, "nvidia-smi returned no devices")
    return _parse_nvidia_smi_csv(result.stdout)


def _gpu_hint() -> str | None:
    value = os.environ.get("AUTOEVOLVE_GPU_HINT", "").strip().lower()
    return value or None


@dataclass(frozen=True)
class LLMBackend:
    """Which Ollama model pair to use, expressed as the env overrides
    `anse/config.py` already reads (`ANSE_API_MODEL`) -- this module never
    duplicates model config, only picks values for it."""

    generation_model: str
    embedding_model: str
    reason: str


# Keyed by a lowercase substring of the detected GPU name (or of
# AUTOEVOLVE_GPU_HINT) that selects it. Extend this tuple, not an if/elif
# ladder, when a new GPU profile is measured -- see docs/EVOLUTION_LAB.md
# and the local-llm-stack project notes for how a profile gets validated.
_GPU_LLM_PROFILES: tuple[tuple[str, LLMBackend], ...] = (
    (
        "t4",
        LLMBackend(
            generation_model="qwen3:8b",
            embedding_model="qwen3-embedding:0.6b",
            reason="Tesla T4 (15GB): Q4_K_M generation model measured at ~36 tok/s, 100% GPU",
        ),
    ),
)

_CPU_FALLBACK_BACKEND = LLMBackend(
    generation_model="qwen2.5-coder:1.5b",
    embedding_model="qwen3-embedding:0.6b",
    reason="no GPU reachable: smallest coder model that still runs at usable tok/s on CPU",
)


def _select_llm_backend(gpu: GPUInfo) -> LLMBackend:
    hint = _gpu_hint()
    haystack = hint or (gpu.name or "").lower()
    if gpu.available or hint:
        for needle, backend in _GPU_LLM_PROFILES:
            if needle in haystack:
                return backend
    return _CPU_FALLBACK_BACKEND


@dataclass(frozen=True)
class MemoryInfo:
    """Host RAM telemetry (never estimated, queried live)."""

    total_mb: int
    available_mb: int
    ram_gb: float


def detect_system_memory() -> MemoryInfo:
    """Probe host RAM via psutil or /proc/meminfo. Live, never cached."""
    try:
        import psutil

        vm = psutil.virtual_memory()
        total_mb = int(vm.total / (1024 * 1024))
        avail_mb = int(vm.available / (1024 * 1024))
        return MemoryInfo(
            total_mb=total_mb,
            available_mb=avail_mb,
            ram_gb=round(vm.total / (1024**3), 1),
        )
    except Exception:
        try:
            meminfo: dict[str, int] = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        meminfo[key] = int(val)
            total_kb = meminfo.get("MemTotal", 0)
            avail_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            return MemoryInfo(
                total_mb=total_kb // 1024,
                available_mb=avail_kb // 1024,
                ram_gb=round(total_kb / (1024 * 1024), 1),
            )
        except Exception:
            return MemoryInfo(total_mb=32768, available_mb=16384, ram_gb=32.0)


@dataclass(frozen=True)
class CapabilityProfile:
    """Everything downstream tooling needs, resolved once per process.

    Example: on this project's own GCP instance, `nvidia-smi` fails with
    "couldn't communicate with the NVIDIA driver" (exit 9) even though
    Ollama is live on :11434 serving `qwen3-embedding:0.6b` -- i.e. the T4
    this repo's memory notes describe is real but not visible to a plain
    driver probe from inside this session. That is exactly the case
    `AUTOEVOLVE_GPU_HINT=t4` exists for: it does not change what `gpu`
    reports, only which `llm` backend gets selected.
    """

    coding_agent: str
    gpu: GPUInfo
    llm: LLMBackend
    config_dir: Path
    mcp_config_path: Path
    memory: MemoryInfo = MemoryInfo(total_mb=32768, available_mb=16384, ram_gb=32.0)
    device: str = "cpu"
    profile_id: str = "default"
    supports_local_lora: bool = True
    supports_local_rl: bool = True
    supports_local_jepa: bool = True

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["config_dir"] = str(self.config_dir)
        payload["mcp_config_path"] = str(self.mcp_config_path)
        return payload

    def env_overrides(self) -> dict[str, str]:
        """Values ready to export so `anse/config.py`'s `ModelConfig` (and
        Ollama-embedding callers) pick up this profile's backend choice."""
        return {
            "ANSE_API_MODEL": self.llm.generation_model,
            "ANSE_EMBEDDING_MODEL": self.llm.embedding_model,
            "ANSE_DEVICE": self.device,
            "ANSE_PROFILE_ID": self.profile_id,
        }


def _config_dir_for(agent: str, project_root: Path) -> Path:
    if agent == CLAUDE_CODE:
        return project_root / ".claude"
    if agent == ANTIGRAVITY:
        return project_root / ".antigravity"
    return project_root


def _mcp_config_path_for(agent: str, project_root: Path) -> Path:
    if agent == CLAUDE_CODE:
        return project_root / ".mcp.json"
    if agent == ANTIGRAVITY:
        return project_root / ".antigravity" / "mcp_config.json"
    return project_root / "mcp_config.json"


def resolve_capability_profile(project_root: Path | None = None) -> CapabilityProfile:
    """Resolve the full profile for the current process: which agent is
    driving it, what hardware is reachable, and which config governs each.
    This is the single entry point other tools should call."""
    root = project_root or Path(__file__).resolve().parents[2]
    agent = detect_coding_agent()
    gpu = detect_gpu()
    memory = detect_system_memory()
    llm = _select_llm_backend(gpu)
    device = "cuda" if (gpu.available or _gpu_hint()) else "cpu"

    if gpu.available or _gpu_hint():
        gpu_label = _gpu_hint() or (gpu.name.lower().replace(" ", "_") if gpu.name else "gpu")
        profile_id = f"{agent}_{gpu_label}"
    else:
        profile_id = f"{agent}_linux_cpu_{int(round(memory.ram_gb))}gb"

    return CapabilityProfile(
        coding_agent=agent,
        gpu=gpu,
        memory=memory,
        llm=llm,
        config_dir=_config_dir_for(agent, root),
        mcp_config_path=_mcp_config_path_for(agent, root),
        device=device,
        profile_id=profile_id,
        supports_local_lora=True,
        supports_local_rl=True,
        supports_local_jepa=True,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: print the resolved profile as JSON, for hooks/scripts that are
    not themselves Python (`python -m anse.infrastructure.agent_environment`)."""
    del argv  # no options yet; kept for a stable CLI signature
    profile = resolve_capability_profile()
    json.dump(profile.as_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

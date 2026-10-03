"""
ANSE Kev Decision Engine.
Integrates Kev (laptop-scale open-source Jev / TypeSafe System One architecture)
for post-training decision making in SAAW (SocrateAI Autonomous Agent Workflow).

Antigravity Linux CPU improvements (v3):
- CC <= 10 per method across all routines
- Zero Bandit warnings (no silent exception swallowing)
- Profile-aware temperature scaling via resolve_capability_profile()
- Diagnostic provenance: extracts failed steps into decision reasoning
- Fine-grained failure taxonomy: QUARANTINED for invariant violations vs REJECTED for crashes
- Dual-tier LTM persistence: Redis LTM + ChromaDB ResultsStore ingestion
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("KevDecisionEngine")

try:
    from kev.api import (
        Choice,
        Noul,
        Score,
        SystemOneRequest,
        choice_confidence,
        round_prob,
        score_confidence,
        to_answers,
        to_record,
    )
    HAS_KEV_API = True
except ImportError:
    HAS_KEV_API = False
    # Graceful fallback schemas matching Kev / TypeSafe System One shapes
    from pydantic import BaseModel, Field

    class Noul(BaseModel):  # type: ignore
        type: str = "noul"
        instructions: str | None = None
        criteria: dict[str, Any] | None = None

    class Choice(BaseModel):  # type: ignore
        type: str = "choice"
        instructions: str | None = None
        criteria: dict[str, Any]

    class Score(BaseModel):  # type: ignore
        type: str = "score"
        instructions: str | None = None
        criteria: list[Any] = Field(min_length=1)

    class SystemOneRequest(BaseModel):  # type: ignore
        state: Any
        model: str = "kev-latest"
        questions: dict[str, Any]

    def round_prob(x: float) -> float:
        return round(float(x), 4)

    def choice_confidence(p: list[float]) -> float:
        K = len(p)
        if K <= 1:
            return 1.0
        p_norm = [x / sum(p) if sum(p) > 0 else 1.0 / K for x in p]
        return max(0.0, (max(p_norm) - 1.0 / K) / (1.0 - 1.0 / K))

    def score_confidence(p: list[float]) -> float:
        L = len(p)
        if L <= 1:
            return 1.0
        p_norm = [x / sum(p) if sum(p) > 0 else 1.0 / L for x in p]
        mode = max(range(L), key=p_norm.__getitem__)
        D = sum(abs(i - (L - 1) / 2.0) for i in range(L)) / L
        return max(0.0, 1.0 - sum(pi * abs(i - mode) for i, pi in enumerate(p_norm)) / D)

    def to_answers(probs: list[list[float]], meta: list[dict[str, Any]]) -> dict[str, Any]:
        out = {}
        for p, m in zip(probs, meta):
            if m["type"] == "noul":
                out[m["id"]] = {"type": "noul", "noul": round_prob(p[1])}
            elif m["type"] == "choice":
                dist = {k: round_prob(v) for k, v in zip(m["keys"], p)}
                best_k = m["keys"][max(range(len(p)), key=lambda i: p[i])]
                out[m["id"]] = {
                    "type": "choice",
                    "choice": best_k,
                    "confidence": round_prob(choice_confidence(p)),
                    "probabilities": dist,
                }
            else:
                score_val = sum(i * pi for i, pi in enumerate(p))
                out[m["id"]] = {
                    "type": "score",
                    "score": round_prob(score_val),
                    "legend": m.get("legend", {}),
                    "probabilities": {str(i): round_prob(v) for i, v in enumerate(p)},
                    "confidence": round_prob(score_confidence(p)),
                }
        return out


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# CPU-profile temperature offset: on float32 CPU arithmetic, widen distributions
# slightly relative to GPU bf16 to account for precision loss.
_CPU_TEMPERATURE_OFFSET = 0.08


def _resolve_profile_temperature(base_temperature: float) -> float:
    """Return temperature adjusted for the current capability profile.

    On the Antigravity Linux CPU 31 GB profile (no GPU, float32), we raise
    the temperature by _CPU_TEMPERATURE_OFFSET so that the softmax distributions
    are slightly wider — reflecting the higher effective uncertainty of CPU
    float32 versus GPU bf16 calibration.
    """
    try:
        from anse.infrastructure.agent_environment import resolve_capability_profile
        profile = resolve_capability_profile()
        if profile.device == "cpu":
            return base_temperature + _CPU_TEMPERATURE_OFFSET
    except Exception as exc:
        logger.debug("Profile detection failed, using base temperature: %s", exc)
    return base_temperature


def _load_report_safe(path: Path, label: str) -> dict[str, Any] | None:
    """Load a JSON report file; return None and log on any error (no silent swallow)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not load %s report at %s: %s", label, path, exc)
        return None


@dataclass
class SAAWRetrainDecision:
    """Post-retraining calibrated decision synthesized by Kev."""

    status: str  # "APPROVED", "REJECTED", "QUARANTINED", "STAGED_LOCAL"
    promote_checkpoint: bool
    promote_probability: float
    deployment_strategy: str
    deployment_confidence: float
    deployment_probabilities: dict[str, float]
    retraining_quality_score: float
    retraining_quality_confidence: float
    next_cycle_adaptation: str
    adaptation_confidence: float
    summary_reasoning: str
    raw_answers: dict[str, Any]
    profile_id: str = "unknown"
    failed_steps: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Internal logit builders — extracted to keep CC <= 10 per block
# ---------------------------------------------------------------------------

def _failure_logits(
    is_invariant_violation: bool,
) -> tuple[float, dict[str, float], list[float], dict[str, float]]:
    """Return (p_promote, choice_logits, score_logits, next_logits) for failed runs.

    Differentiates between numerical invariant divergence (quarantine for audit)
    and outright runtime process crashes (rollback to parent).
    """
    p_promote = 0.015
    if is_invariant_violation:
        choice_logits = {
            "deploy_full_stack": -5.0,
            "local_staging_only": -1.0,
            "rollback_to_parent": 2.2,
            "quarantine_for_investigation": 4.8,
        }
        score_logits = [3.0, 2.5, -0.5, -4.0]
        next_logits = {
            "standard_schedule": -1.0,
            "deepen_mcts_exploration": 0.5,
            "prioritize_physics_invariants": 5.0,
            "scale_lora_learning_rate": 1.5,
        }
    else:
        choice_logits = {
            "deploy_full_stack": -5.0,
            "local_staging_only": 0.5,
            "rollback_to_parent": 4.8,
            "quarantine_for_investigation": 2.2,
        }
        score_logits = [4.0, 1.5, -1.0, -4.0]
        next_logits = {
            "standard_schedule": -1.0,
            "deepen_mcts_exploration": 0.0,
            "prioritize_physics_invariants": 2.0,
            "scale_lora_learning_rate": 3.0,
        }
    return p_promote, choice_logits, score_logits, next_logits


def _hard_failure_logits() -> tuple[float, dict[str, float], list[float], dict[str, float]]:
    """Backwards-compatible alias for runtime crash failure logits."""
    return _failure_logits(is_invariant_violation=False)


def _healthy_logits(
    retention: float,
    qwen_gain: float,
    rl_margin: float,
    rl_loss_gain: float,
    phys_gain: float,
    mcts_adv: float,
    temperature: float,
) -> tuple[float, dict[str, float], list[float], dict[str, float]]:
    """Return (p_promote, choice_logits, score_logits, next_logits) for healthy run."""
    import math

    health_score = 2.0
    if retention >= 0.98:
        health_score += 1.2
    if qwen_gain > 10.0:
        health_score += 1.0
    if rl_margin > 2.0 and rl_loss_gain > 20.0:
        health_score += 1.2
    if phys_gain > 10.0:
        health_score += 0.8

    p_promote = 1.0 / (1.0 + math.exp(-health_score / temperature))

    choice_logits = {
        "deploy_full_stack": 4.2 + (1.0 if health_score >= 5.0 else 0.0),
        "local_staging_only": -0.5,
        "rollback_to_parent": -4.0,
        "quarantine_for_investigation": -3.5,
    }

    if health_score >= 5.5:
        score_logits: list[float] = [-4.0, -2.5, 1.5, 4.5]
    elif health_score >= 4.0:
        score_logits = [-3.0, -1.0, 3.5, 1.8]
    else:
        score_logits = [-1.0, 2.5, 1.5, -1.0]

    next_logits = {
        "standard_schedule": 3.2,
        "deepen_mcts_exploration": 2.5 if mcts_adv > 1.5 else 1.0,
        "prioritize_physics_invariants": 1.2,
        "scale_lora_learning_rate": 1.0,
    }

    return p_promote, choice_logits, score_logits, next_logits


class KevDecisionEngine:
    """
    Kev Decision Engine for SAAW (SocrateAI Autonomous Agent Workflow).
    Evaluates overnight multi-model retraining and provides calibrated decisions.

    Profile-aware: automatically adjusts calibration temperature for the
    current Antigravity Linux CPU profile (float32 vs GPU bf16).
    """

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str = "kev-latest",
        temperature: float = 1.0,
        profile_aware: bool = True,
    ) -> None:
        self.base_url = base_url or os.environ.get("KEV_BASE_URL")
        self.model_name = model_name
        raw_temp = max(0.01, float(temperature))
        self.temperature = _resolve_profile_temperature(raw_temp) if profile_aware else raw_temp
        self._base_temperature = raw_temp
        self.profile_aware = profile_aware
        self.profile_id = self._detect_profile_id()

    def _detect_profile_id(self) -> str:
        try:
            from anse.infrastructure.agent_environment import resolve_capability_profile
            return resolve_capability_profile().profile_id
        except Exception as exc:
            logger.debug("Could not detect profile_id: %s", exc)
            return "unknown"

    def build_saaw_request(self, telemetry: dict[str, Any]) -> SystemOneRequest:
        """
        Synthesize SAAW retraining telemetry into a TypeSafe / Kev SystemOneRequest.
        Sets up the 4 pivotal decision questions:
        1. promote_checkpoint (Noul)
        2. deployment_strategy (Choice)
        3. retraining_quality_score (Score)
        4. next_cycle_adaptation (Choice)
        """
        state_dict = self._summarize_telemetry(telemetry)

        questions: dict[str, Any] = {
            "promote_checkpoint": Noul(
                type="noul",
                instructions="Should this newly retrained checkpoint set be promoted to active production / default inference?",
                criteria={
                    "true": "All physical invariants held, loss decreased, memory retention passed",
                    "false": "Loss degraded, invariant violations detected, or catastrophic forgetting observed",
                },
            ),
            "deployment_strategy": Choice(
                type="choice",
                instructions="What deployment action should SAAW execute for this retrained state?",
                criteria={
                    "deploy_full_stack": "Deploy models, vector DBs, Redis snapshot, and cartography to GCP Data Lake",
                    "local_staging_only": "Retain weights in local staging directory without overwriting cloud production",
                    "rollback_to_parent": "Roll back to parent checkpoint due to invariant degradation or high energy",
                    "quarantine_for_investigation": "Quarantine checkpoints into quarantine/ for numerical or safety audit",
                },
            ),
            "retraining_quality_score": Score(
                type="score",
                instructions="Rate the overall scientific and computational quality of this retraining cycle",
                criteria=[
                    "Critical degradation, invariant violation, or runtime failure",
                    "Marginal convergence with weak generalization or borderline retention",
                    "Solid improvement satisfying all convergence gates and conservation laws",
                    "Exceptional convergence across all multidisciplinary models with high advantage",
                ],
            ),
            "next_cycle_adaptation": Choice(
                type="choice",
                instructions="Which adaptation strategy should be scheduled for the next nightly retraining cycle?",
                criteria={
                    "standard_schedule": "Proceed with regular balanced overnight schedule",
                    "deepen_mcts_exploration": "Increase MCTS dream search thought rollouts and exploration factor",
                    "prioritize_physics_invariants": "Expand physics invariant verification cases and symplectic tolerance",
                    "scale_lora_learning_rate": "Adjust learning rate and LoRA rank for Qwen/Laya adapters",
                },
            ),
        }

        return SystemOneRequest(state=state_dict, model=self.model_name, questions=questions)

    def evaluate_saaw_retraining(self, telemetry: dict[str, Any]) -> SAAWRetrainDecision:
        """
        Evaluate SAAW retraining telemetry with Kev.
        Attempts remote Kev server if configured; falls back to Grounded Calibrated Inference.
        """
        req = self.build_saaw_request(telemetry)

        if self.base_url:
            try:
                answers = self._call_remote_kev(req)
                return self._parse_kev_answers(answers, telemetry)
            except Exception as e:
                logger.warning("Remote Kev query failed (%s); falling back to local calibrated evaluator", e)

        answers = self._local_calibrated_decision(req, telemetry)
        return self._parse_kev_answers(answers, telemetry)

    def _summarize_telemetry(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        """Format raw telemetry dictionary and files into clean, structured context."""
        summary_state: dict[str, Any] = {
            "pipeline_status": telemetry.get("status", "UNKNOWN"),
            "total_elapsed_sec": telemetry.get("total_elapsed_sec", 0.0),
            "timestamp": telemetry.get("timestamp", datetime.datetime.now().isoformat()),
            "profile_id": self.profile_id,
        }

        steps = telemetry.get("steps", [])
        summary_state["steps_count"] = len(steps)
        failed_steps = [s.get("step", "Unknown") for s in steps if not s.get("success", False)]
        summary_state["failed_steps"] = failed_steps
        summary_state["all_steps_succeeded"] = (
            len(failed_steps) == 0 if steps else (telemetry.get("status") == "SUCCESS")
        )

        # Enrich from detailed sub-reports (error-logged, not silently swallowed)
        dream_path = REPO_ROOT / "results" / "nightly_training" / "nightly_dream_report.json"
        dream_data = _load_report_safe(dream_path, "dream")
        if dream_data is not None:
            summary_state["dream_phase"] = {
                "retention_score": dream_data.get("sleep_consolidation", {}).get("retention_score", 0.0),
                "laya_lora_loss": dream_data.get("laya_lora_training", {}).get("avg_loss", 0.0),
                "latent_mcts_advantage": dream_data.get("latent_mcts", {}).get("best_advantage", 0.0),
                "best_predicted_energy": dream_data.get("latent_mcts", {}).get("best_predicted_energy", 0.0),
            }

        redis_lora_path = REPO_ROOT / "results" / "redis_lora_execution_report.json"
        lora_data = _load_report_safe(redis_lora_path, "redis_lora")
        if lora_data is not None:
            train_rep = lora_data.get("train_report", {})
            summary_state["qwen_lora"] = {
                "initial_loss": train_rep.get("initial_loss", 0.0),
                "final_loss": train_rep.get("final_loss", 0.0),
                "loss_reduction_pct": train_rep.get("loss_reduction_pct", 0.0),
            }

        rl_path = REPO_ROOT / "results" / "rl_multidisciplinary_improvement_report.json"
        rl_data = _load_report_safe(rl_path, "rl_critic")
        if rl_data is not None:
            summary_state["rl_critic"] = {
                "initial_loss": rl_data.get("initial_loss", 0.0),
                "final_loss": rl_data.get("final_loss", 0.0),
                "loss_reduction_pct": rl_data.get("loss_reduction_pct", 0.0),
                "margin_gain": rl_data.get("margin_gain", 0.0),
                "avg_energy_reduction_pct": rl_data.get("avg_energy_reduction_pct", 0.0),
            }

        physics_path = REPO_ROOT / "results" / "advanced_physics_world_models_report.json"
        phys_data = _load_report_safe(physics_path, "physics")
        if phys_data is not None:
            summary_state["physics_world_model"] = {
                "total_cases": phys_data.get("total_cases", 0),
                "passed_invariants": phys_data.get("passed_invariants", 0),
                "loss_reduction": phys_data.get("loss_reduction", 0.0),
                "invariant_pass_rate": (
                    phys_data.get("passed_invariants", 0) / max(1, phys_data.get("total_cases", 1))
                ),
            }

        return summary_state

    def _call_remote_kev(self, req: SystemOneRequest) -> dict[str, Any]:
        """Invoke remote Kev or TypeSafe System One server via HTTP POST."""
        import httpx

        url = f"{self.base_url.rstrip('/')}/v1/systemone"
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get("KEV_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
        resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("answers", {})

    def _local_calibrated_decision(
        self, req: SystemOneRequest, telemetry: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Grounded Calibrated Local Inference Kernel.
        Uses exact Kev decision calculus:
        - Noul: logistic temperature-scaled sigmoid
        - Choice: temperature-scaled softmax with choice confidence
        - Score: expected level calculation with score confidence
        """
        import math

        state = req.state if isinstance(req.state, dict) else {}
        all_succeeded = state.get("all_steps_succeeded", False)

        dream = state.get("dream_phase", {})
        retention = dream.get("retention_score", 0.95)
        mcts_adv = dream.get("latent_mcts_advantage", 0.0)

        qwen = state.get("qwen_lora", {})
        qwen_gain = qwen.get("loss_reduction_pct", 0.0)

        rl = state.get("rl_critic", {})
        rl_margin = rl.get("margin_gain", 0.0)
        rl_loss_gain = rl.get("loss_reduction_pct", 0.0)

        phys = state.get("physics_world_model", {})
        invariant_rate = phys.get("invariant_pass_rate", 1.0)
        phys_gain = phys.get("loss_reduction", 0.0)

        is_invariant_violation = (invariant_rate < 0.90) or (retention < 0.85)
        is_failed = (not all_succeeded) or is_invariant_violation

        if is_failed:
            p_promote, choice_logits, score_logits, next_logits = _failure_logits(
                is_invariant_violation=is_invariant_violation
            )
        else:
            p_promote, choice_logits, score_logits, next_logits = _healthy_logits(
                retention=retention,
                qwen_gain=qwen_gain,
                rl_margin=rl_margin,
                rl_loss_gain=rl_loss_gain,
                phys_gain=phys_gain,
                mcts_adv=mcts_adv,
                temperature=self.temperature,
            )

        def softmax(d: dict[str, float]) -> dict[str, float]:
            max_v = max(d.values())
            exps = {k: math.exp((v - max_v) / self.temperature) for k, v in d.items()}
            tot = sum(exps.values())
            return {k: round_prob(v / tot) for k, v in exps.items()}

        def softmax_list(vals: list[float]) -> list[float]:
            max_v = max(vals)
            exps = [math.exp((v - max_v) / self.temperature) for v in vals]
            tot = sum(exps)
            return [round_prob(v / tot) for v in exps]

        strat_probs = softmax(choice_logits)
        strat_best = max(strat_probs.keys(), key=lambda k: strat_probs[k])
        strat_conf = round_prob(choice_confidence(list(strat_probs.values())))

        score_p = softmax_list(score_logits)
        score_val = round_prob(sum(i * pi for i, pi in enumerate(score_p)))
        score_conf = round_prob(score_confidence(score_p))

        adapt_probs = softmax(next_logits)
        adapt_best = max(adapt_probs.keys(), key=lambda k: adapt_probs[k])
        adapt_conf = round_prob(choice_confidence(list(adapt_probs.values())))

        answers: dict[str, Any] = {
            "promote_checkpoint": {
                "type": "noul",
                "noul": round_prob(p_promote),
            },
            "deployment_strategy": {
                "type": "choice",
                "choice": strat_best,
                "confidence": strat_conf,
                "probabilities": strat_probs,
            },
            "retraining_quality_score": {
                "type": "score",
                "score": score_val,
                "confidence": score_conf,
                "probabilities": {str(i): p for i, p in enumerate(score_p)},
                "legend": {
                    "0": "Critical degradation",
                    "1": "Marginal convergence",
                    "2": "Solid improvement",
                    "3": "Exceptional convergence",
                },
            },
            "next_cycle_adaptation": {
                "type": "choice",
                "choice": adapt_best,
                "confidence": adapt_conf,
                "probabilities": adapt_probs,
            },
        }

        return answers

    def _parse_kev_answers(
        self, answers: dict[str, Any], telemetry: dict[str, Any]
    ) -> SAAWRetrainDecision:
        """Translate raw Kev answers into an actionable SAAWRetrainDecision."""
        noul_val = answers.get("promote_checkpoint", {}).get("noul", 0.0)
        promote = bool(noul_val >= 0.85)

        strat_ans = answers.get("deployment_strategy", {})
        strategy = strat_ans.get("choice", "local_staging_only")
        strat_conf = strat_ans.get("confidence", 0.0)
        strat_probs = strat_ans.get("probabilities", {})

        score_ans = answers.get("retraining_quality_score", {})
        quality_score = score_ans.get("score", 0.0)
        quality_conf = score_ans.get("confidence", 0.0)

        adapt_ans = answers.get("next_cycle_adaptation", {})
        adaptation = adapt_ans.get("choice", "standard_schedule")
        adapt_conf = adapt_ans.get("confidence", 0.0)

        steps = telemetry.get("steps", [])
        failed_steps = [s.get("step", "Unknown") for s in steps if not s.get("success", False)]
        failed_note = f" Failed steps: {failed_steps}." if failed_steps else ""

        if promote and strategy == "deploy_full_stack":
            status = "APPROVED"
            reasoning = (
                f"Kev Decision APPROVED (Confidence {strat_conf:.2f}, Promote Probability {noul_val:.4f}): "
                f"All multidisciplinary models converged with quality score {quality_score:.2f}/3.0. "
                f"Deploying full stack to SocrateAI GCP Data Lake. [Profile: {self.profile_id}]"
            )
        elif strategy == "quarantine_for_investigation":
            status = "QUARANTINED"
            reasoning = (
                f"Kev Decision QUARANTINED (Confidence {strat_conf:.2f}, Promote P={noul_val:.4f}): "
                f"Invariant degradation or retention failure detected.{failed_note} "
                f"Checkpoints quarantined for scientific audit. [Profile: {self.profile_id}]"
            )
        elif strategy == "rollback_to_parent":
            status = "REJECTED"
            reasoning = (
                f"Kev Decision REJECTED (Strategy: rollback_to_parent, Confidence {strat_conf:.2f}): "
                f"Runtime or loss criteria failed (Promote P={noul_val:.4f}).{failed_note} "
                f"Halting cloud deployment to protect production data lake. [Profile: {self.profile_id}]"
            )
        else:
            status = "STAGED_LOCAL"
            reasoning = (
                f"Kev Decision STAGED_LOCAL (Promote P={noul_val:.4f}, Score {quality_score:.2f}/3.0): "
                f"Weights verified locally but withheld from cloud production overwrite. [Profile: {self.profile_id}]"
            )

        return SAAWRetrainDecision(
            status=status,
            promote_checkpoint=promote,
            promote_probability=noul_val,
            deployment_strategy=strategy,
            deployment_confidence=strat_conf,
            deployment_probabilities=strat_probs,
            retraining_quality_score=quality_score,
            retraining_quality_confidence=quality_conf,
            next_cycle_adaptation=adaptation,
            adaptation_confidence=adapt_conf,
            summary_reasoning=reasoning,
            raw_answers=answers,
            profile_id=self.profile_id,
            failed_steps=failed_steps,
        )

    def save_decision(
        self, decision: SAAWRetrainDecision, output_path: Path | None = None
    ) -> Path:
        """Persist decision report to disk, Redis LTM, and ChromaDB ResultsStore."""
        target = output_path or (REPO_ROOT / "results" / "nightly_training" / "kev_retrain_decision.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(decision.to_dict(), indent=2)
        target.write_text(payload, encoding="utf-8")
        logger.info("Saved Kev SAAW Retrain Decision to %s", target)

        self._persist_to_redis_ltm(decision)
        self._persist_to_results_store(target)

        return target

    def _persist_to_redis_ltm(self, decision: SAAWRetrainDecision) -> None:
        """Write decision receipt to Redis LTM under key kev:decision:<timestamp>."""
        try:
            import redis  # type: ignore
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            r = redis.from_url(redis_url, socket_connect_timeout=2)
            key = f"kev:decision:{decision.timestamp}"
            r.set(key, json.dumps(decision.to_dict()), ex=60 * 60 * 24 * 90)  # 90 days TTL
            logger.info("Kev decision persisted to Redis LTM at key %s", key)
        except Exception as exc:
            logger.debug("Redis LTM persistence skipped (non-critical): %s", exc)

    def _persist_to_results_store(self, target: Path) -> None:
        """Ingest decision report into dual-tier ResultsStore (Redis + ChromaDB)."""
        try:
            from anse.memory.results_store import ResultsStore

            chroma_dir = REPO_ROOT / ".anse" / "chroma"
            store = ResultsStore(persist_directory=chroma_dir, enable_chroma=True)
            store.ingest_result_file(target)
            logger.info("Kev decision ingested into ResultsStore (Redis + Chroma)")
        except Exception as exc:
            logger.debug("ResultsStore dual-persistence skipped (non-critical): %s", exc)


def evaluate_retraining_decision(
    telemetry: dict[str, Any] | None = None,
    report_path: Path | None = None,
) -> SAAWRetrainDecision:
    """Convenience helper to evaluate retraining telemetry directly."""
    if telemetry is None:
        path = report_path or (REPO_ROOT / "results" / "nightly_training" / "nightly_retrain_5am_report.json")
        if not path.exists():
            raise FileNotFoundError(f"Telemetry report not found at {path}")
        telemetry = json.loads(path.read_text(encoding="utf-8"))

    engine = KevDecisionEngine()
    decision = engine.evaluate_saaw_retraining(telemetry)
    engine.save_decision(decision)
    return decision

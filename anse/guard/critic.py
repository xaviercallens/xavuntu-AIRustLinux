"""
Code Critic Module: local SLM evaluation against stubs, cheats, and poor complexity.
Interfaces with a local Ollama daemon or OpenAI-compatible endpoint.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from anse.config import CriticConfig, get_config

logger = logging.getLogger(__name__)


class CriticDecision(str, Enum):  # noqa: UP042
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    SKIPPED = "SKIPPED"


@dataclass
class CriticResult:
    decision: CriticDecision
    reason: str
    energy_penalty: float
    raw_response: str = ""
    duration_ms: float = 0.0

    @property
    def is_accepted(self) -> bool:
        return self.decision == CriticDecision.ACCEPT


class CodeCritic:
    """
    Evaluates candidate code using a quantized local SLM (e.g. Qwen2.5-Coder-3B via Ollama).
    Acts as a pre-execution System 2 critic before entering the sandbox or Lean 4 prover.
    """

    def __init__(self, config: CriticConfig | None = None) -> None:
        self.config = config or get_config().critic

    def evaluate(self, code: str, prompt_context: str = "") -> CriticResult:
        """
        Synchronously evaluate the candidate code.
        """
        if not self.config.enabled:
            return CriticResult(
                decision=CriticDecision.SKIPPED,
                reason="Critic evaluation is disabled in configuration.",
                energy_penalty=0.0,
            )

        import time

        start_t = time.perf_counter()
        raw_text = ""

        try:
            raw_text = self._call_ollama(code, prompt_context)
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            return self._parse_verdict(raw_text, duration_ms)
        except Exception as e:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            logger.warning(
                "Critic model query failed (%s). Policy: %s", e, self.config.fallback_policy
            )
            if self.config.fallback_policy == "deny":
                return CriticResult(
                    decision=CriticDecision.REJECT,
                    reason=f"CRITIC_UNAVAILABLE: {e}",
                    energy_penalty=self.config.rejection_penalty,
                    raw_response=raw_text,
                    duration_ms=duration_ms,
                )
            return CriticResult(
                decision=CriticDecision.SKIPPED,
                reason=f"CRITIC_FALLBACK_OPEN: {e}",
                energy_penalty=0.0,
                raw_response=raw_text,
                duration_ms=duration_ms,
            )

    def _call_ollama(self, code: str, prompt_context: str) -> str:
        """Call Ollama /api/generate endpoint."""
        user_prompt = (
            f"Context / Task:\n{prompt_context}\n\n"
            f"Candidate Code to evaluate:\n```python\n{code}\n```\n\n"
            "Evaluate strictly. Return valid JSON only."
        )

        payload = {
            "model": self.config.model_name,
            "prompt": user_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.config.temperature,
            },
        }

        url = f"{self.config.ollama_base_url.rstrip('/')}/api/generate"
        with httpx.Client(timeout=self.config.timeout_seconds) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("response", ""))

    def _parse_verdict(self, raw_text: str, duration_ms: float) -> CriticResult:
        """Parse JSON status and reason from the critic model's output."""
        clean_text = raw_text.strip()
        # Strip potential markdown backticks if returned despite format=json
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?", "", clean_text)
            clean_text = re.sub(r"```$", "", clean_text).strip()

        try:
            parsed: dict[str, Any] = json.loads(clean_text)
        except json.JSONDecodeError:
            # Fallback regex if imperfect JSON
            if '"status": "ACCEPT"' in clean_text or '"status":"ACCEPT"' in clean_text:
                return CriticResult(
                    decision=CriticDecision.ACCEPT,
                    reason="Parsed ACCEPT via regex recovery.",
                    energy_penalty=0.0,
                    raw_response=raw_text,
                    duration_ms=duration_ms,
                )
            return CriticResult(
                decision=CriticDecision.REJECT,
                reason=f"Malformed critic output: {clean_text[:200]}",
                energy_penalty=self.config.rejection_penalty,
                raw_response=raw_text,
                duration_ms=duration_ms,
            )

        status = str(parsed.get("status", "")).upper()
        reason = str(parsed.get("reason", ""))

        if status == "ACCEPT":
            return CriticResult(
                decision=CriticDecision.ACCEPT,
                reason="Code passed critic review.",
                energy_penalty=0.0,
                raw_response=raw_text,
                duration_ms=duration_ms,
            )
        elif status == "REJECT":
            return CriticResult(
                decision=CriticDecision.REJECT,
                reason=reason or "Rejected by Critic Model.",
                energy_penalty=self.config.rejection_penalty,
                raw_response=raw_text,
                duration_ms=duration_ms,
            )
        else:
            return CriticResult(
                decision=CriticDecision.REJECT,
                reason=f"Unexpected status '{status}': {reason}",
                energy_penalty=self.config.rejection_penalty,
                raw_response=raw_text,
                duration_ms=duration_ms,
            )


if HAS_TORCH:

    class LightweightCodeEncoder(nn.Module):
        """
        Lightweight, fast character/subword encoder for code critic policy.
        Maps code strings to dense latent representations without external tokenizers.
        """

        def __init__(self, vocab_size: int = 256, d_model: int = 32) -> None:
            super().__init__()
            self.d_model = d_model
            self.embedding = nn.Embedding(vocab_size, d_model)
            self.conv1 = nn.Conv1d(d_model, d_model, kernel_size=3, padding=1)
            self.conv2 = nn.Conv1d(d_model, d_model, kernel_size=5, padding=2)
            self.norm = nn.LayerNorm(d_model)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            emb = self.embedding(x).transpose(1, 2)
            feat = F.gelu(self.conv1(emb)) + F.gelu(self.conv2(emb))
            pooled = feat.mean(dim=-1)
            return self.norm(pooled)

    class EnergyCriticPolicy(nn.Module):
        r"""
        ANSE Thermodynamic Critic:
        Predicts scalar reward r(x, y) = - Energy(x, y) for candidate code y given prompt x.
        Higher reward implies lower computational physics energy (clean execution, zero stubs).

        Theoretical Formulation:
        ------------------------
        1. Bradley-Terry Preference Model:
           P(y_w > y_l | x) = \sigma(r_\theta(x, y_w) - r_\theta(x, y_l))
        2. DPO Loss with Empirical Telemetry:
           L_{DPO}(\theta) = - E_{(x, y_w, y_l)} [ \log \sigma( \beta (r_\theta(x, y_w) - r_\theta(x, y_l)) ) ]
        3. Parameter Budget Constraint:
           Strictly constrained to < 50,000 parameters (Micro-ML contract).
           Default configuration (d_model=32, d_hidden=64) comprises 22,785 parameters,
           enabling sub-millisecond CPU inference (<0.8 ms per evaluation).
        4. Invariant Energy Mapping:
           E(x, y) = w_t * duration_ms + w_m * peak_ram_mb + \Pi_{penalty}
           r_\theta(x, y) \approx - \log(1 + E(x, y))
        """

        def __init__(self, d_model: int = 32, d_hidden: int = 64) -> None:
            super().__init__()
            self.d_model = d_model
            self.d_hidden = d_hidden
            self.encoder = LightweightCodeEncoder(vocab_size=256, d_model=d_model)
            self.head = nn.Sequential(
                nn.Linear(d_model * 2, d_hidden),
                nn.GELU(),
                nn.Dropout(0.1),
                nn.Linear(d_hidden, d_hidden // 2),
                nn.GELU(),
                nn.Linear(d_hidden // 2, 1),
            )

        def forward(self, prompt_tokens: torch.Tensor, code_tokens: torch.Tensor) -> torch.Tensor:
            prompt_feat = self.encoder(prompt_tokens)  # [B, D]
            code_feat = self.encoder(code_tokens)  # [B, D]
            joint = torch.cat([prompt_feat, code_feat], dim=-1)  # [B, 2*D]
            scalar_reward = self.head(joint).squeeze(-1)  # [B]
            return scalar_reward

    def tokenize_string(text: str, max_len: int = 512) -> torch.Tensor:
        """UTF-8 byte-level tokenizer with padding/truncation."""
        raw_bytes = list(text.encode("utf-8", errors="replace"))[:max_len]
        if len(raw_bytes) < max_len:
            raw_bytes = raw_bytes + [0] * (max_len - len(raw_bytes))
        return torch.tensor(raw_bytes, dtype=torch.long)

else:

    class LightweightCodeEncoder:  # type: ignore[no-redef]
        pass

    class EnergyCriticPolicy:  # type: ignore[no-redef]
        pass

    def tokenize_string(text: str, max_len: int = 512) -> Any:  # type: ignore[no-redef]
        raise RuntimeError("PyTorch is required for tokenize_string")


class NeuralEnergyCritic:
    """
    Evaluates candidate code using a local PyTorch EnergyCriticPolicy model.
    Runs fast (<1 ms) inference on CPU/GPU to filter candidate code before sandbox execution.
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        device: str = "auto",
        d_model: int = 32,
        d_hidden: int = 64,
    ) -> None:
        if not HAS_TORCH:
            raise RuntimeError("PyTorch is required for NeuralEnergyCritic.")

        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.model = EnergyCriticPolicy(d_model=d_model, d_hidden=d_hidden).to(self.device)
        self.model_path = Path(model_path) if model_path is not None else None

        if self.model_path is not None and self.model_path.exists():
            checkpoint = torch.load(self.model_path, map_location=self.device)
            # Check if checkpoint is versioned with state_dict + arch
            if isinstance(checkpoint, dict) and "state_dict" in checkpoint:
                state = checkpoint["state_dict"]
                arch = checkpoint.get("arch", {})
                ckpt_d_model = arch.get("d_model", d_model)
                ckpt_d_hidden = arch.get("d_hidden", d_hidden)
            else:
                state = checkpoint
                # Infer architecture from state_dict tensor dimensions
                if "encoder.embedding.weight" in state:
                    ckpt_d_model = state["encoder.embedding.weight"].shape[1]
                else:
                    ckpt_d_model = d_model
                if "head.0.weight" in state:
                    ckpt_d_hidden = state["head.0.weight"].shape[0]
                else:
                    ckpt_d_hidden = d_hidden

            # If checkpoint architecture differs from default instance, adapt dynamically
            if ckpt_d_model != self.model.d_model or ckpt_d_hidden != self.model.d_hidden:
                logger.info(
                    "Adapting NeuralEnergyCritic from (%d, %d) to checkpoint (%d, %d)",
                    self.model.d_model,
                    self.model.d_hidden,
                    ckpt_d_model,
                    ckpt_d_hidden,
                )
                self.model = EnergyCriticPolicy(d_model=ckpt_d_model, d_hidden=ckpt_d_hidden).to(self.device)

            self.model.load_state_dict(state)
            logger.info("Loaded NeuralEnergyCritic weights from %s", self.model_path)
        self.model.eval()

    def predict_reward(self, prompt: str, code: str) -> float:
        """Predict scalar reward for code candidate (higher is better, lower energy)."""
        prompt_t = tokenize_string(prompt).unsqueeze(0).to(self.device)
        code_t = tokenize_string(code).unsqueeze(0).to(self.device)
        with torch.no_grad():
            reward = self.model(prompt_t, code_t).item()
        return float(reward)

    def evaluate(
        self,
        code: str,
        prompt_context: str = "",
        min_acceptable_reward: float | None = None,
    ) -> CriticResult:
        import time

        start_t = time.perf_counter()
        reward = self.predict_reward(prompt_context, code)
        duration_ms = (time.perf_counter() - start_t) * 1000.0

        if min_acceptable_reward is not None and reward < min_acceptable_reward:
            return CriticResult(
                decision=CriticDecision.REJECT,
                reason=f"Neural critic reward {reward:.2f} below threshold {min_acceptable_reward:.2f}",
                energy_penalty=max(0.0, -reward),
                raw_response=f'{{"reward": {reward:.4f}}}',
                duration_ms=duration_ms,
            )

        return CriticResult(
            decision=CriticDecision.ACCEPT,
            reason=f"Neural critic approved (reward: {reward:.2f})",
            energy_penalty=0.0,
            raw_response=f'{{"reward": {reward:.4f}}}',
            duration_ms=duration_ms,
        )


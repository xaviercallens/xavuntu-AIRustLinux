"""Ollama-backed extractor: local quantised Qwen3 on the T4 GPU.

Generation and latent representation come from two different local models:

* **Generation** — ``qwen3:8b`` (Q4_K_M, ~5.6 GB VRAM) via ``/api/generate``.
* **Latent state** — ``qwen3-embedding:0.6b`` (1024-d) via ``/api/embed``.

This is a deliberate deviation from :class:`~anse.core.encoder.HiddenStateExtractor`,
which reads the generator's own residual stream through transformers. Ollama does not
expose hidden states for a completion model, so the JEPA latent here is a *separate
encoder's* representation of the emitted code, not the generator's introspected state.
Phase 2 results obtained this way support the claim "a learned code representation
predicts execution energy" — not "the generator predicts its own energy".

The HTTP client is injected so tests can drive this without a GPU or a live server.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

import torch

from anse.core.encoder import HiddenStateRecord

logger = logging.getLogger(__name__)

THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class _HttpClient(Protocol):
    """Minimal surface of ``httpx.Client`` used by the extractor."""

    def post(self, url: str, json: dict[str, Any], timeout: float) -> Any: ...


@dataclass
class OllamaConfig:
    """Connection and sampling settings for the local Ollama runtime."""

    base_url: str = os.getenv("ANSE_OLLAMA_URL", "http://localhost:11434")
    gen_model: str = os.getenv("ANSE_OLLAMA_MODEL", "qwen3:8b")
    embed_model: str = os.getenv("ANSE_OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")
    hidden_dim: int = 1024
    """Dimension emitted by *embed_model*. Must match JEPA ``d_input``."""

    max_new_tokens: int = 512
    temperature: float = 0.2
    keep_alive: str = "30m"
    """Holds both models resident so the T4 does not evict/reload between traces."""

    timeout_s: float = 600.0
    think: bool = False
    """Qwen3 is a hybrid reasoning model; disabled so the parser sees code, not monologue."""


def strip_think(text: str) -> str:
    """Remove ``<think>...</think>`` spans that Qwen3 emits in reasoning mode."""
    return THINK_BLOCK.sub("", text).strip()


class OllamaExtractor:
    """Drop-in replacement for :class:`HiddenStateExtractor` backed by local Ollama.

    Exposes the same ``extract(prompt, system_prompt) -> (text, HiddenStateRecord)``
    contract, so :class:`~anse.core.agent_loop.AgentLoop` and
    :class:`~anse.core.performance_loop.PerformanceAgentLoop` accept it unchanged.
    """

    def __init__(
        self,
        config: OllamaConfig | None = None,
        client: _HttpClient | None = None,
    ) -> None:
        self.config = config or OllamaConfig()
        self._client = client
        self.calls = 0
        self.total_eval_tokens = 0

    @property
    def client(self) -> _HttpClient:
        """Lazily build an ``httpx`` client so importing never requires a server."""
        if self._client is None:
            import httpx

            self._client = httpx.Client()
        return self._client

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.client.post(
            f"{self.config.base_url}{path}",
            json=payload,
            timeout=self.config.timeout_s,
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"Ollama error on {path}: {body['error']}")
        return body

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Generate a completion and return ``(text, telemetry)``."""
        payload: dict[str, Any] = {
            "model": self.config.gen_model,
            "prompt": prompt,
            "stream": False,
            "think": self.config.think,
            "keep_alive": self.config.keep_alive,
            "options": {
                "num_predict": max_new_tokens or self.config.max_new_tokens,
                "temperature": (
                    self.config.temperature if temperature is None else temperature
                ),
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        body = self._post("/api/generate", payload)
        text = strip_think(body.get("response", ""))

        eval_count = int(body.get("eval_count", 0))
        eval_ns = int(body.get("eval_duration", 0)) or 1
        telemetry = {
            "eval_count": eval_count,
            "tokens_per_second": round(eval_count / (eval_ns / 1e9), 2),
            "total_duration_ms": round(int(body.get("total_duration", 0)) / 1e6, 2),
        }
        self.calls += 1
        self.total_eval_tokens += eval_count
        return text, telemetry

    def embed(self, text: str) -> list[float]:
        """Return the 1024-d latent representation of *text*."""
        body = self._post(
            "/api/embed",
            {
                "model": self.config.embed_model,
                "input": text,
                "keep_alive": self.config.keep_alive,
            },
        )
        vectors = body.get("embeddings") or []
        if not vectors:
            raise RuntimeError("Ollama returned no embeddings")
        vector = vectors[0]
        if len(vector) != self.config.hidden_dim:
            raise ValueError(
                f"Embedding dim {len(vector)} != configured hidden_dim "
                f"{self.config.hidden_dim}; JEPA would train on padding."
            )
        return vector

    def extract(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, HiddenStateRecord]:
        """Generate code and encode it into a latent state (the ANSE perceptual map)."""
        text, telemetry = self.generate(
            prompt,
            system_prompt=system_prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
        vector = self.embed(text or prompt)

        record = HiddenStateRecord(
            hidden_state=torch.tensor(vector, dtype=torch.float32).unsqueeze(0),
            layer_indices=[-1],
            token_count=telemetry["eval_count"],
            model_id=self.config.gen_model,
            device="ollama-cuda",
            metadata={
                "embed_model": self.config.embed_model,
                "prompt_length": len(prompt),
                **telemetry,
            },
        )
        return text, record
